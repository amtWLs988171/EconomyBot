import discord
from discord.ext import commands, tasks
from gradio_client import Client, handle_file
import asyncio
import aiosqlite
import os
import aiohttp
import uuid
import traceback
import imagehash
from PIL import Image
import random
import csv
import json
import math
from datetime import datetime, time, timedelta
# from utils.bloom_filter import BloomFilter # Removed

class InventoryView(discord.ui.View):
    def __init__(self, ctx, items, per_page=5):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.items = items
        self.per_page = per_page
        self.current_page = 0
        self.max_page = max(0, (len(items) - 1) // per_page)
        self.update_buttons()

    def update_buttons(self):
        self.prev_btn.disabled = self.current_page == 0
        self.next_btn.disabled = self.current_page == self.max_page

    def get_embed(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        batch = self.items[start:end]
        
        embed = discord.Embed(title=f"{self.ctx.author.display_name}の所持品 ({self.current_page + 1}/{self.max_page + 1})", color=discord.Color.gold())
        if not batch:
             embed.description = "表示するアイテムがありません。"
             return embed
             
        description = ""
        for item_id, tags, thread_id, score in batch:
            tag_summary = tags.split(",")[0] if tags else "不明"
            thread_link = f"<#{thread_id}>" if thread_id else "不明"
            description += f"**ID: {item_id}** | {tag_summary} (Score: {score:.1f}) | {thread_link}\n"
        
        embed.description = description
        embed.set_footer(text=f"Total: {len(self.items)} items")
        return embed

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.blurple)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("他人のインベントリは操作できません。", ephemeral=True)
            return

        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.blurple)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("他人のインベントリは操作できません。", ephemeral=True)
            return

        if self.current_page < self.max_page:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
             await interaction.response.defer()

class ResellPriceModal(discord.ui.Modal, title="再販価格の設定"):
    def __init__(self, bot, item_id):
        super().__init__()
        self.bot = bot
        self.item_id = item_id
        self.price_input = discord.ui.TextInput(
            label="価格 (Credits)",
            placeholder="100以上の整数",
            min_length=3,
            max_length=10
        )
        self.add_item(self.price_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(self.price_input.value)
            if price < 100: raise ValueError
        except:
             await interaction.response.send_message("❌ 価格は100以上の整数で入力してください。", ephemeral=True)
             return

        async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db:
            # Re-verify ownership
            cursor = await db.execute("""
                SELECT thread_id, message_id, tags, aesthetic_score FROM market_items 
                WHERE item_id = ? AND buyer_id = ? AND status IN ('sold', 'owned')
            """, (self.item_id, interaction.user.id))
            row = await cursor.fetchone()
            
            if not row:
                await interaction.response.send_message("❌ エラー: アイテムを所有していないか、既に販売中です。", ephemeral=True)
                return
            
            thread_id, message_id, tags, score = row
            
            # Update DB
            await db.execute("""
                UPDATE market_items 
                SET status = 'on_sale', price = ?, seller_id = ?, buyer_id = NULL 
                WHERE item_id = ?
            """, (price, interaction.user.id, self.item_id))
            await db.commit()
            
            # Update Gallery Message
            try:
                guild = interaction.guild
                thread = guild.get_thread(thread_id)
                if not thread:
                     try: thread = await guild.fetch_channel(thread_id)
                     except: pass
                
                if thread:
                     try:
                         msg = await thread.fetch_message(message_id)
                         
                         # Edit Embed
                         embed = msg.embeds[0]
                         embed.clear_fields()
                         embed.title = "🔄 再販中 (Resale)"
                         embed.color = discord.Color.orange()
                         
                         tags_str = tags if tags else "None"
                         grade = "B"
                         if score >= 9.0: grade = "S"
                         elif score >= 7.0: grade = "A"
                         
                         embed.add_field(name="ID", value=f"**#{self.item_id}**", inline=True)
                         embed.add_field(name="販売者", value=interaction.user.mention, inline=True)
                         embed.add_field(name="価格", value=f"💰 {price:,}", inline=True)
                         embed.add_field(name="グレード", value=f"**{grade}** ({score:.2f})", inline=True)
                         embed.add_field(name="特徴 (Tags)", value=tags_str, inline=False)
                         
                         from cogs.market import BuyView
                         await msg.edit(content=f"📢 **再販中!** (ID: {self.item_id})", embed=embed, view=BuyView(self.bot))
                         
                         await interaction.response.send_message(f"✅ **再販設定完了！** (ID: {self.item_id}, Price: {price:,})\n🔗 {msg.jump_url}")
                         return
                     except Exception as e:
                         print(f"Failed to edit msg: {e}")
            except Exception as e:
                print(f"Resell Error: {e}")
            
            await interaction.response.send_message(f"✅ **再販設定完了(DBのみ)**: 元のメッセージが見つかりませんでしたが、販売リストには追加されました。")

class ResellSelect(discord.ui.Select):
    def __init__(self, bot, items):
        options = []
        for item_id, tags, score in items[:25]: # Max 25 options
            tag_summary = tags.split(",")[0] if tags else "Unknown"
            options.append(discord.SelectOption(
                label=f"ID: {item_id}",
                description=f"Score: {score:.1f} | {tag_summary}",
                value=str(item_id)
            ))
        super().__init__(placeholder="再販するアイテムを選択してください...", min_values=1, max_values=1, options=options)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        item_id = int(self.values[0])
        await interaction.response.send_modal(ResellPriceModal(self.bot, item_id))

class ResellSelectView(discord.ui.View):
    def __init__(self, bot, items):
        super().__init__(timeout=60)
        self.add_item(ResellSelect(bot, items))


class BrokerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ai_client_score = None
        self.ai_client_tag = None
        self.setup_clients()
        
        # AI Queue System
        self.ai_queue = asyncio.Queue()
        self.ai_worker_task = self.bot.loop.create_task(self.ai_worker())
        
        # self.daily_task_loop.start() # Removed

    def cog_unload(self):
        # self.daily_task_loop.cancel() # Removed
        self.ai_worker_task.cancel()

    def setup_clients(self):
        try:
            token = getattr(self.bot, 'hf_token', None)
            self.ai_client_score = Client("Eugeoter/waifu-scorer-v3", token=token)
            self.ai_client_tag = Client("SmilingWolf/wd-tagger", token=token)
            print("Broker AI Clients Loaded.")
        except Exception as e:
            print(f"Broker AI Clients Error: {e}")
            self.ai_client_score = None
            self.ai_client_tag = None



    async def ai_worker(self):
        """Worker to process AI requests sequentially."""
        print("AI Worker Started.")
        while True:
            try:
                # task_type: 'tag' or 'score'
                # future: asyncio.Future to set result
                task_type, file_path, future = await self.ai_queue.get()
                
                try:
                    res = None
                    if task_type == 'tag':
                        res = await asyncio.to_thread(self._run_predict_sync, self.ai_client_tag, file_path)
                    elif task_type == 'score':
                        res = await asyncio.to_thread(self._run_predict_sync, self.ai_client_score, file_path)
                    
                    if not future.done():
                        future.set_result(res)
                except Exception as e:
                    if not future.done():
                        future.set_exception(e)
                finally:
                    self.ai_queue.task_done()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"AI Worker Error: {e}")



    def _run_predict_sync(self, client, file_path):
        """Run prediction in a separate thread"""
        try:
             return client.predict(handle_file(file_path), api_name="/predict")
        except Exception as e:
             print(f"Prediction Error: {e}")
             raise e

    def calculate_phash(self, image_path):
        with Image.open(image_path) as img:
            return str(imagehash.phash(img))

    async def get_risk_factor(self, current_hash):
        if not current_hash:
            return 10, "Unknown Error", 0
        
        async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db:
            cursor = await db.execute("SELECT image_hash FROM market_items WHERE image_hash IS NOT NULL")
            rows = await cursor.fetchall()

        current_hash_obj = imagehash.hex_to_hash(current_hash)
        min_dist = 100
        
        for (db_hash_str,) in rows:
            try:
                db_hash_obj = imagehash.hex_to_hash(db_hash_str)
                dist = current_hash_obj - db_hash_obj
                if dist < min_dist:
                    min_dist = dist
            except:
                continue

        if min_dist <= 5:
            return 100, f"類似画像あり (類似度: {min_dist})", min_dist
        else:
            return 0, "OK", min_dist

    async def _calculate_price(self, score, tag_list, character_list):
        """Calculates final price."""
        base_price = 1000
        
        trend_bonus = 0
        matched_trends = []
        
        char_bonus = 0
        if character_list:
            char_bonus = 2000 * len(character_list)
        
        # Tag Bonus (Simple Count)
        # 100 Credits per tag
        tag_bonus = len(tag_list) * 100

        rarity_multiplier = 1.0
        checked_tags = []

        score = max(0.0, min(10.0, score))
        base_value_exp = int(1000 * (score ** 2))
        final_price = base_value_exp + char_bonus + tag_bonus
        
        return final_price, trend_bonus, matched_trends, char_bonus, rarity_multiplier, checked_tags

    @commands.command(name="join")
    async def join(self, ctx):
        """プライベートルームを作成し、トレーダーとして登録します。"""
        # 1. Permission/Role Check
        role = discord.utils.get(ctx.guild.roles, name="トレーダー")
        if role and role not in ctx.author.roles:
            try:
                await ctx.author.add_roles(role)
            except:
                pass # Fail silently if permission issue, admin can fix

        # 2. Gallery Setup (From old Register)
        market_category = discord.utils.get(ctx.guild.categories, name="マーケット")
        # Legacy check
        if not market_category: market_category = discord.utils.get(ctx.guild.categories, name="闇市 (Shadow Market)")
        
        forum = discord.utils.get(ctx.guild.forums, name="ギャラリー")
        if not forum: forum = discord.utils.get(ctx.guild.forums, name="闇市ギャラリー")

        async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db:
            # Check existing gallery registration
            cursor = await db.execute("SELECT thread_id FROM user_galleries WHERE user_id = ?", (ctx.author.id,))
            row = await cursor.fetchone()
            
            if not row and forum:
                try:
                    thread_with_message = await forum.create_thread(
                        name=f"Gallery: {ctx.author.display_name}",
                        content=f"{ctx.author.mention} のギャラリー"
                    )
                    t = thread_with_message.thread if hasattr(thread_with_message, 'thread') else thread_with_message
                    
                    await db.execute("INSERT INTO user_galleries (user_id, thread_id) VALUES (?, ?)", (ctx.author.id, t.id))
                    # Bonus for new joining
                    await self.bot.bank.deposit_credits(ctx.author, 3000, db_conn=db)
                    await db.commit()
                except Exception as e:
                    print(f"Gallery creation failed: {e}")

        # 3. Private Room Setup
        try:
            guild = ctx.guild
            cat_name = "Private Rooms"
            category = discord.utils.get(guild.categories, name=cat_name)
            
            if not category:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True)
                }
                category = await guild.create_category(cat_name, overwrites=overwrites)
            
            safe_name = "".join(c for c in ctx.author.name.lower() if c.isalnum() or c in "-_")
            ch_name = f"room-{safe_name}-{ctx.author.id}"
            
            existing = discord.utils.get(category.text_channels, name=ch_name)
            
            if existing:
                await ctx.send(f"既にチャンネルが存在します: {existing.mention}")
                return
                
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            }
            
            channel = await guild.create_text_channel(ch_name, category=category, overwrites=overwrites)
            await ctx.send(f"チャンネルを作成しました: {channel.mention}")
            
            await channel.send(f"ようこそ、{ctx.author.mention}。\nここでアイテムを売却 (`!sell`) できます。")

        except Exception as e:
            await ctx.send(f"エラー: {e}")
            traceback.print_exc()

    @commands.command(name="smuggle", aliases=["sell"])
    async def smuggle(self, ctx):
        """画像アイテムを売却します。"""
        # 1. Restriction Check
        if not ctx.channel.name.startswith("room-") and not ctx.channel.name.startswith("hideout-"):
            await ctx.send("個室 (`room-xxx`) で行ってください。")
            return

        if not ctx.message.attachments:
            await ctx.send("画像ファイルを添付してください。")
            return
            
        attachment = ctx.message.attachments[0]
        if not attachment.content_type.startswith('image/'):
            await ctx.send("画像ファイルのみ有効です。")
            return

        image_url = attachment.url
        await ctx.send("処理中...")

        # 1. Download & Hash
        temp_path, img_hash = await self._download_and_hash(image_url)
        if not temp_path:
            await ctx.send("ダウンロード失敗。")
            return

        try:
            is_dup, dup_msg, _ = await self.get_risk_factor(img_hash)
            
            if is_dup >= 50:
                 await ctx.send(f"エラー: {dup_msg}")
                 return

            await ctx.send(f"アップロード完了。鑑定中...")
            
            tag_list, tags_str, character_list = await self._run_tagger(temp_path)
            score = await self._run_scorer(temp_path)
            
            # 5. Pricing
            final_price, trend_bonus, matched_trends, char_bonus, rarity_mult, rare_tags = await self._calculate_price(score, tag_list, character_list)
            
            # 6. Grading
            grade = "B"
            if score >= 9.0: grade = "S"
            elif score >= 7.0: grade = "A"
            
            # 7. Post to Gallery & DB Insert
            item_id = None
            async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO market_items (seller_id, image_url, aesthetic_score, price, status, image_hash, tags, grade, thread_id, message_id)
                    VALUES (?, ?, ?, ?, 'on_sale', ?, ?, ?, 0, 0)
                    """,
                    (self.bot.user.id, image_url, score, int(final_price * 1.5), img_hash, str(tag_list), grade)
                )
                item_id = cursor.lastrowid
                
                embed = discord.Embed(title=f"📦 新規入荷 (ID: #{item_id})", color=discord.Color.blue())
                embed.set_image(url=image_url)
                embed.add_field(name="販売者", value=self.bot.user.mention, inline=True)
                embed.add_field(name="価格", value=f"{int(final_price * 1.5):,} Credits", inline=True)
                embed.add_field(name="グレード", value=f"**{grade}** ({score:.2f})", inline=True)
                
                if character_list:
                    chars_str = ", ".join(character_list)
                    embed.add_field(name="キャラクター", value=f"{chars_str}", inline=True)
                embed.add_field(name="タグ", value=tags_str[:1000], inline=False)
                
                try:
                    await self._post_to_gallery(ctx, embed, temp_path, tags_str, item_id, grade, final_price, tag_list, image_url, img_hash, db_conn=db)
                    await db.commit()
                except Exception as e:
                    await ctx.send(f"エラー: {e}")
                    traceback.print_exc()
                    return

        except Exception as e:
            await ctx.send(f"エラーが発生しました: {e}")
            traceback.print_exc()
        finally:
             if os.path.exists(temp_path): os.remove(temp_path)

    async def _post_to_gallery(self, ctx, embed, temp_path, tags_str, item_id, grade, final_price, tag_list, image_url, img_hash, db_conn):
        """Handles posting to the appropriate thread or forum."""
        bot_thread = None
        
        # 1. Fetch User Gallery (Using shared conn)
        cursor = await db_conn.execute("SELECT thread_id FROM user_galleries WHERE user_id = ?", (self.bot.user.id,))
        row = await cursor.fetchone()
        if row:
            bot_thread = ctx.guild.get_thread(row[0])
            if not bot_thread:
                    try: bot_thread = await ctx.guild.fetch_channel(row[0])
                    except: pass

        from cogs.market import BuyView
        view = BuyView(self.bot)
        
        message = None
        thread_ref = None

        if bot_thread:
            thread_ref = bot_thread
            message = await bot_thread.send(
                content=f"**販売:** (ID: #{item_id})",
                embed=embed,
                file=discord.File(temp_path, filename="artifact.png"),
                view=view
            )
            await ctx.send(f"✅ 出品完了 (ID: {item_id})\n{message.jump_url}")
        else:
                forum = discord.utils.get(ctx.guild.forums, name="ギャラリー")
                if not forum: forum = discord.utils.get(ctx.guild.forums, name="闇市ギャラリー")

                if forum:
                    title = f"[{grade}] {tags_str[:30]}..." if len(tags_str) > 30 else f"[{grade}] {tags_str}"
                    if not title: title = f"[{grade}] Item"

                    thread_with_message = await forum.create_thread(
                        name=title,
                        content=f"**販売:** (ID: #{item_id})",
                        embed=embed,
                        file=discord.File(temp_path, filename="artifact.png"),
                        view=view
                    )
                    thread_ref = thread_with_message.thread if hasattr(thread_with_message, 'thread') else thread_with_message
                    message = thread_with_message.message 
                    if not message and hasattr(thread_ref, 'starter_message'): message = thread_ref.starter_message
                    
                    await ctx.send(f"✅ 出品完了 (ID: {item_id})\n{thread_ref.mention}")
                else:
                    await ctx.send("フォーラムが見つかりません。")
                    raise Exception("Gallery Forum Not Found")

        # DB Updates & Payment
        await self.bot.bank.deposit_credits(ctx.author, final_price, db_conn=db_conn)

        
        # Link Update
        await db_conn.execute(
            "UPDATE market_items SET thread_id = ?, message_id = ? WHERE item_id = ?",
            (thread_ref.id, message.id if message else 0, item_id)
        )
        
        await ctx.send(f"💰 報酬: `{final_price:,} Credits`")





    @commands.command(name="inventory", aliases=["bag", "inv"])
    async def inventory(self, ctx):
        """自分が所有している(購入済み)アイテムを表示します。"""
        async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db:
            cursor = await db.execute("""
                SELECT item_id, tags, thread_id, aesthetic_score 
                FROM market_items 
                WHERE buyer_id = ? AND status IN ('sold', 'owned')
            """, (ctx.author.id,))
            rows = await cursor.fetchall()
            
        if not rows:
            await ctx.send("🎒 **持ち物:** 何も持っていません。ギャラリーで購入するか、密輸してください。")
            return

        view = InventoryView(ctx, rows, per_page=5)
        await ctx.send(embed=view.get_embed(), view=view)



    @commands.command(name="resell")
    async def resell(self, ctx):
        """所有しているアイテムを選択して再販します。"""
        async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db:
            cursor = await db.execute("""
                SELECT item_id, tags, aesthetic_score 
                FROM market_items 
                WHERE buyer_id = ? AND status IN ('sold', 'owned')
                ORDER BY item_id DESC
            """, (ctx.author.id,))
            rows = await cursor.fetchall()
            
        if not rows:
            await ctx.send("🎒 **持ち物:** 再販できるアイテムを持っていません。")
            return

        view = ResellSelectView(self.bot, rows)
        await ctx.send("🔄 **再販するアイテムを選択してください:**", view=view)

    @commands.command(name="reset_risk")
    async def reset_risk(self, ctx):
        """(Debug) Clears all image hashes from the database to reset pHash risk."""
        async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db:
            await db.execute("UPDATE market_items SET image_hash = NULL")
            await db.commit()
        await ctx.send("🔄 **記憶消去完了。** 当局は押収品に関するデータを失いました。\nこれで再び低リスクで密輸できます！")

async def setup(bot):
    await bot.add_cog(BrokerCog(bot))
