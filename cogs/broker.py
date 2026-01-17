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
        
        embed = discord.Embed(title=f"🎒 {self.ctx.author.display_name}の持ち物 ({self.current_page + 1}/{self.max_page + 1})", color=discord.Color.gold())
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
            await interaction.response.send_message("自分以外のインベントリは操作できません。", ephemeral=True)
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
            await interaction.response.send_message("自分以外のインベントリは操作できません。", ephemeral=True)
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
        self.setup_clients()
        # self.tag_data = {} # Removed
        # self.load_tag_data() # Removed
        
        # AI Queue System
        self.ai_queue = asyncio.Queue()
        self.ai_worker_task = self.bot.loop.create_task(self.ai_worker())
        
        # BloomFilter removed
        # self.bloom = BloomFilter(capacity=10000, error_rate=0.001)
        # self.bot.loop.create_task(self.initialize_bloom_filter())
        
        self.daily_task_loop.start()

    def cog_unload(self):
        self.daily_task_loop.cancel()
        self.ai_worker_task.cancel()
        # Save Bloom Filter on unload
        # self.bloom.save_to_file("bloom_filter.bin") # Removed

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

    # load_tag_data Removed

    @tasks.loop(hours=24)
    async def daily_task_loop(self):
        """Runs daily to decay saturation (economy maintenance)"""
        # await self.update_daily_trends() # Removed
        await self.decay_saturation()

    # initialize_bloom_filter Removed

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

    @daily_task_loop.before_loop
    async def before_daily_task(self):
        await self.bot.wait_until_ready()
        # Sleep until 6 AM
        now = datetime.now()
        target = now.replace(hour=6, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        # For testing, we might want to run immediately if DB is empty, but let's just log.
        print(f"Next Daily Trend Update: {target}")
        await asyncio.sleep((target - now).total_seconds())

    # update_daily_trends Removed

    # get_current_trends Removed

    def _run_predict_sync(self, client, file_path):
        """Run prediction in a separate thread"""
        print(f"DEBUG: Thread Running for {file_path}")
        try:
             # Try passing path directly first?
             # Some Gradio apps accept path strings.
             # If this fails, we catch it.
             return client.predict(handle_file(file_path), api_name="/predict")
        except Exception as e:
             print(f"DEBUG: Prediction Thread Error: {e}")
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
            return 100, f"⛔ **重複警告** (類似度: {min_dist})", min_dist
        else:
            return 0, f"✅ **確認完了** (新規アイテム)", min_dist

    async def update_market_trends(self, tags, db_conn=None):
        """Update saturation for tags on new upload."""
        if db_conn:
            for tag in tags:
                await db_conn.execute("INSERT OR IGNORE INTO market_trends (tag_name) VALUES (?)", (tag,))
                await db_conn.execute("""
                    UPDATE market_trends 
                    SET saturation = saturation + 1
                    WHERE tag_name = ?
                """, (tag,))
        else:
            async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db:
                await self.update_market_trends(tags, db)
                await db.commit()

    async def decay_saturation(self):
        """Called daily to reduce saturation."""
        async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db:
            # Decay by 10% or at least 1
            await db.execute("""
                UPDATE market_trends 
                SET saturation = CAST(saturation * 0.9 AS INTEGER) 
                WHERE saturation > 0
            """)
            await db.commit()
        print("Daily Saturation Decay Applied.")



    async def get_tag_value_modifier(self, tags):
        # Logarithmic Saturation Decay
        # Multiplier = 1 / log10(saturation + 2)
        # Base saturation starts at 0.
        # If saturation is 100 -> log10(102) ~ 2.0 -> Mult ~ 0.5
        # If saturation is 500 -> log10(502) ~ 2.7 -> Mult ~ 0.37
        
        multiplier = 1.0
        async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db:
            for tag in tags:
                cursor = await db.execute("SELECT current_price, saturation FROM market_trends WHERE tag_name = ?", (tag,))
                row = await cursor.fetchone()
                
                if row:
                    price, sat = row
                    # Apply saturation penalty
                    # Use a weighted average or minimum multiplier?
                    # Let's use the WORST modifier (the most saturated tag pulls down the whole value)
                    # Or average? Average feels fairer.
                    
                    sat_mult = 1.0 / math.log10(max(sat, 0) + 2)
                    
                    # Accumulate? Let's average the multipliers of known tags
                    # But we need to handle "no record" tags as 1.0
                    # This logic is complex. Simplified:
                    # Modify the aggregate multiplier by the impact of this tag.
                    # Let's take the Minimum modifier found.
                    if sat_mult < multiplier:
                         multiplier = sat_mult
        
        return max(multiplier, 0.1)



    # trends command Removed

    async def _download_and_hash(self, url):
        """Downloads image from URL and calculates pHash."""
        temp_path = f"temp_{uuid.uuid4()}.png"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200: return None, None
                    data = await resp.read()
            with open(temp_path, "wb") as f: f.write(data)
            
            img_hash = await asyncio.to_thread(self.calculate_phash, temp_path)
            return temp_path, img_hash
        except Exception as e:
            print(f"Download Error: {e}")
            if os.path.exists(temp_path): os.remove(temp_path)
            return None, None

    async def _run_tagger(self, file_path):
        """Runs the tagger AI via Queue. Returns (tag_list, tags_str, character_list)."""
        if not self.ai_client_tag: return [], "", []
        
        future = self.bot.loop.create_future()
        await self.ai_queue.put(('tag', file_path, future))
        
        try:
            # Enforce 20s timeout
            res = await asyncio.wait_for(future, timeout=30.0) # Slightly longer to account for queue wait

            # Debug output for verification
            # print(f"DEBUG: Tagger Raw Output Type: {type(res)}")
            
            # Helper to parse Gradio Label output
            def parse_gradio_label(data):
                if isinstance(data, dict) and 'confidences' in data:
                    return {item['label']: item['confidence'] for item in data['confidences']}
                return data if isinstance(data, dict) else {}

            # Initialize containers
            confidences = {}
            character_confidences = {}
            
            # Handle Tuple Output (New Tagger Model: [comb_tags_str, rating_dict, char_dict, gen_dict])
            if isinstance(res, (list, tuple)) and len(res) >= 3:
                # index 2 is character tags
                # index 3 is general tags
                
                if len(res) > 3:
                    confidences = parse_gradio_label(res[3])
                elif len(res) > 0 and isinstance(res[0], dict):
                     # Fallback if structure is different
                    confidences = parse_gradio_label(res[0])

                if isinstance(res[2], dict) or (isinstance(res[2], dict) and 'confidences' in res[2]):
                    character_confidences = parse_gradio_label(res[2])

            elif isinstance(res, dict):
                confidences = parse_gradio_label(res)

            # Fallback for file path output
            if isinstance(res, str) and os.path.exists(res):
                 # This path is legacy/fallback, unlikely to happen with this model
                 pass

            tag_list = []
            character_list = []

            # Process General Tags
            if confidences:
                # Ensure values are floats
                clean_confidences = {}
                for k, v in confidences.items():
                    try:
                        clean_confidences[k] = float(v)
                    except:
                        continue
                        
                sorted_tags = sorted(clean_confidences.items(), key=lambda x: x[1], reverse=True)
                tag_list = [t[0] for t in sorted_tags if t[1] > 0.35][:20]

            # Process Character Tags
            if character_confidences:
                clean_chars = {}
                for k, v in character_confidences.items():
                     try:
                        clean_chars[k] = float(v)
                     except:
                        continue

                sorted_chars = sorted(clean_chars.items(), key=lambda x: x[1], reverse=True)
                character_list = [c[0] for c in sorted_chars if c[1] > 0.5] # Higher threshold for chars

            return tag_list, ", ".join(tag_list), character_list
                
        except asyncio.TimeoutError:
            print("Tagging Timeout (Queue/Process limit reached)")
        except Exception as e:
            print(f"Tagging Error: {e}")
            traceback.print_exc()
            
        return [], "timeout_fallback", []

    # _fetch_tag_count (Danbooru) Removed

    async def _run_scorer(self, file_path):
        """Runs the aesthetic scorer AI via Queue."""
        if not self.ai_client_score: return random.uniform(2.0, 5.0)
        
        future = self.bot.loop.create_future()
        await self.ai_queue.put(('score', file_path, future))
        
        try:
            # Enforce 20s timeout
            res = await asyncio.wait_for(future, timeout=30.0)
            return float(res)
        except:
            return random.uniform(2.0, 5.0)

    async def _calculate_price(self, score, tag_list, character_list):
        """Calculates final price, trend bonus, and rarity multiplier."""
        tag_multiplier = await self.get_tag_value_modifier(tag_list)
        base_price = 1000
        
        # trends = await self.get_current_trends() # Removed
        trend_bonus = 0
        matched_trends = []
        
        # Trend logic removed
        
        # Character Bonus
        char_bonus = 0
        if character_list:
            char_bonus = 2000 * len(character_list)

        # --- Rarity Bonus (Danbooru) Removed ---
        rarity_multiplier = 1.0
        checked_tags = [] # No longer used

        # Ensure score is within bounds
        score = max(0.0, min(10.0, score))
        
        # New Formula: 1000 * (score^2)
        base_value_exp = int(1000 * (score ** 2))
        
        # Simple Price Calculation
        final_price = base_value_exp + char_bonus
        
        # Stocks Logic Removed

        return final_price, trend_bonus, matched_trends, char_bonus, rarity_multiplier, checked_tags



    @commands.command(name="join")
    async def join(self, ctx):
        """闇市の隠れ家を作成します。"""
        try:
            guild = ctx.guild
            cat_name = "🕵️ Hideouts"
            category = discord.utils.get(guild.categories, name=cat_name)
            
            if not category:
                # Create Private Category
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True)
                }
                category = await guild.create_category(cat_name, overwrites=overwrites)
            
            # Check existing channel (Use ID for safety)
            # Sanitized Name: hideout-username-1234
            safe_name = "".join(c for c in ctx.author.name.lower() if c.isalnum() or c in "-_")
            ch_name = f"hideout-{safe_name}-{ctx.author.id}"
            
            # Also check simpler name for backward compatibility if we want, but let's stick to new standard
            existing = discord.utils.get(category.text_channels, name=ch_name)
            
            if existing:
                await ctx.send(f"⚠️ あなたの隠れ家は既に存在します: {existing.mention}")
                return
                
            # Create Channel
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            }
            
            channel = await guild.create_text_channel(ch_name, category=category, overwrites=overwrites)
            await ctx.send(f"✅ 隠れ家を用意しました... こちらへどうぞ: {channel.mention}")
            
            await channel.send(f"🕵️ **ようこそ、{ctx.author.mention}。**\nここはあなただけの隠れ家です。\n`!smuggle` で密輸品を鑑定・売却しましょう。\n(誰にも見られることはありません...)")

        except Exception as e:
            await ctx.send(f"❌ 隠れ家の作成に失敗しました: {e}")
            traceback.print_exc()

    @commands.command(name="smuggle")
    async def smuggle(self, ctx):
        """The main loop: Upload -> Risk -> Gamble -> Appraise -> Sell"""
        # 1. Restriction Check
        if not ctx.channel.name.startswith("hideout-"):
            await ctx.send("🚫 **密輸は「隠れ家」で行ってください。**\n`!join` で隠れ家を作成できます。")
            return

        if not ctx.message.attachments:
            await ctx.send("📦 **密輸品(画像)を添付してください！**")
            return
            
        attachment = ctx.message.attachments[0]
        if not attachment.content_type.startswith('image/'):
            await ctx.send("❌ 画像ファイルのみ有効です。")
            return

        image_url = attachment.url
        await ctx.send("🕵️ **密輸作戦を開始します...**")

        # 1. Download & Hash
        temp_path, img_hash = await self._download_and_hash(image_url)
        if not temp_path:
            await ctx.send("❌ ダウンロードに失敗しました。")
            return

        try:
            # 2. Bloom Filter Check Removed
            # if self.bloom.check(img_hash): ...

            # 3. DB Duplicate Check (Strict & Reliable)
            # Even if Bloom said "No", we still check DB for *similar* images (hamming distance),
            # which Bloom Filter cannot do.
            is_dup, dup_msg, _ = await self.get_risk_factor(img_hash)
            
            if is_dup >= 50:
                 await ctx.send(f"❌ **密輸失敗:** {dup_msg}\n(同じ画像が既に存在します)")
                 return

            await ctx.send(f"✅ **密輸成功!**\n闇市の鑑定人に連絡しています...")
            
            # 4. AI Valuation
            tag_list, tags_str, character_list = await self._run_tagger(temp_path)
            score = await self._run_scorer(temp_path)
            
            # Removed score rejection check (< 4.0) to accept all items.

            # 5. Pricing
            final_price, trend_bonus, matched_trends, char_bonus, rarity_mult, rare_tags = await self._calculate_price(score, tag_list, character_list)
            
            # 6. Grading
            grade = "B"
            if score >= 9.0: grade = "S"
            elif score >= 7.0: grade = "A"
            
            # 7. Post to Gallery & DB Insert
            # 7. Post to Gallery & DB Insert (Atomic)
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
                # Do NOT commit yet
                
                # Create Embed
                embed = discord.Embed(title=f"📦 新規入荷 (ID: #{item_id})", color=discord.Color.purple())
                embed.set_image(url=image_url)
                embed.add_field(name="販売者", value=self.bot.user.mention, inline=True)
                embed.add_field(name="価格", value=f"💰 {int(final_price * 1.5):,}", inline=True)
                embed.add_field(name="グレード", value=f"**{grade}** ({score:.2f})", inline=True)
                
                if rarity_mult > 1.0:
                     embed.add_field(name="✨ レアリティボーナス", value=f"x{rarity_mult:.1f} ({', '.join(rare_tags[:3])})", inline=True)
                     
                if character_list:
                    chars_str = ", ".join(character_list)
                    embed.add_field(name="👤 キャラクター", value=f"{chars_str} (+{char_bonus:,})", inline=True)
                if matched_trends:
                    embed.add_field(name="🔥 トレンドボーナス!", value=f"+{trend_bonus:,} ({', '.join(matched_trends)})", inline=False)
                embed.add_field(name="特徴 (Tags)", value=tags_str[:1000], inline=False)
                
                # Post Logic & Completion
                try:
                    # Pass 'db' to share transaction
                    await self._post_to_gallery(ctx, embed, temp_path, tags_str, item_id, grade, final_price, tag_list, image_url, img_hash, db_conn=db)
                    
                    await db.commit() # Commit all changes (Item, Money, Trends)
                    
                except Exception as e:
                    await ctx.send(f"❌ 投稿処理中にエラーが発生: {e}")
                    traceback.print_exc()
                    # Implicit Rollback on exit context manager without commit?
                    # Actually aiosqlite context manager does commit on exit? 
                    # No, it *closes*. If we didn't commit, changes are lost? 
                    # SQLite default is to rollback uncommitted transactions on close. Yes.
                    # But verifying: aiosqlite context manager for CONNECTION just closes it.
                    # So uncommitted changes are rolled back. Correct.
                    return

        except Exception as e:
            await ctx.send(f"❌ エラーが発生しました: {e}")
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
                content=f"**販売中:** {tags_str[:50]}... (ID: #{item_id})",
                embed=embed,
                file=discord.File(temp_path, filename="artifact.png"),
                view=view
            )
            await ctx.send(f"✅ **密輸成功！(ID: {item_id})**\n公式ギャラリーに入荷しました: {message.jump_url}")
        else:
                forum = discord.utils.get(ctx.guild.forums, name="闇市ギャラリー")
                if forum:
                # ... (Same forum logic)
                    title = f"[{grade}] {tags_str[:30]}..." if len(tags_str) > 30 else f"[{grade}] {tags_str}"
                    if not title: title = f"[{grade}] 謎の品"

                    thread_with_message = await forum.create_thread(
                        name=title,
                        content=f"**販売中:** {tags_str[:50]}... (ID: #{item_id})",
                        embed=embed,
                        file=discord.File(temp_path, filename="artifact.png"),
                        view=view
                    )
                    thread_ref = thread_with_message.thread if hasattr(thread_with_message, 'thread') else thread_with_message
                    message = thread_with_message.message 
                    if not message and hasattr(thread_ref, 'starter_message'): message = thread_ref.starter_message
                    
                    await ctx.send(f"✅ **密輸成功！(ID: {item_id})**\n臨時スレッドが作成されました: {thread_ref.mention}")
                else:
                    await ctx.send("❌ フォーラム「闇市ギャラリー」が見つかりません。`!init_server` を確認してください。")
                    # If we return here, we must raise exception to trigger rollback in caller!
                    raise Exception("Gallery Forum Not Found")

        # DB Updates & Payment (Atomic)
        await self.bot.bank.deposit_credits(ctx.author, final_price, db_conn=db_conn)
        await self.update_market_trends(tag_list, db_conn=db_conn)
        
        # Update Bloom Filter
        self.bloom.add(image_url)
        self.bloom.add(img_hash)
        
        # Final Link Update
        await db_conn.execute(
            "UPDATE market_items SET thread_id = ?, message_id = ? WHERE item_id = ?",
            (thread_ref.id, message.id if message else 0, item_id)
        )
        
        await ctx.send(f"💰 **報酬受取:** `{final_price:,} Credits` を受け取りました。")

    @commands.command(name="register")
    async def register(self, ctx):
        """闇のブローカーとして登録し、個人用ギャラリーを開設します。"""
        
        async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db:
            # 1. Check if already joined
            cursor = await db.execute("SELECT thread_id FROM user_galleries WHERE user_id = ?", (ctx.author.id,))
            row = await cursor.fetchone()
            
            if row:
                await ctx.send(f"⚠️ 既に登録済みです。ギャラリー: <#{row[0]}>")
                return

            # 2. Assign Role & Find Forum
            role = discord.utils.get(ctx.guild.roles, name="密輸業者")
            forum = discord.utils.get(ctx.guild.forums, name="闇市ギャラリー")
            
            if not forum:
                await ctx.send("❌ フォーラム `闇市ギャラリー` が見つかりません。管理者に連絡してください。")
                return

            if role:
                try:
                    await ctx.author.add_roles(role)
                except discord.Forbidden:
                    await ctx.send("⚠️ ロールの付与に失敗しました(権限不足)。")

            # 3. Create Gallery Thread
            try:
                thread_with_message = await forum.create_thread(
                    name=f"[Gallery] {ctx.author.display_name}",
                    content=f"{ctx.author.mention} の個人ギャラリーへようこそ。\nここで獲得した戦利品が展示されます。"
                )
                thread = thread_with_message.thread if hasattr(thread_with_message, 'thread') else thread_with_message
                
                # 4. Save to DB & Give Starting Funds (Atomic)
                await db.execute("INSERT INTO user_galleries (user_id, thread_id) VALUES (?, ?)", (ctx.author.id, thread.id))
                await self.bot.bank.deposit_credits(ctx.author, 3000, db_conn=db)
                
                await db.commit()
                
                await ctx.send(f"🎉 **登録完了！** あなたのギャラリーが開設されました: {thread.mention}\n💰 **開業資金 3,000クレジット** が支給されました！")

            except Exception as e:
                await ctx.send(f"❌ ギャラリー作成に失敗しました: {e}")
                traceback.print_exc()
                # Rollback handled by context manager (no commit)


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
