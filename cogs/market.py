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
from datetime import datetime, timedelta

class BuyView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="購入", style=discord.ButtonStyle.green, custom_id="shadow_broker:buy_btn")
    async def buy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. Identify Item by Message ID (Unique to the specific button press)
        # using message_id instead of channel_id allows multiple items in one thread.
        message_id = interaction.message.id
        buyer = interaction.user
        
        async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db:
            cursor = await db.execute("SELECT item_id, price, seller_id, status, image_url, tags FROM market_items WHERE message_id = ?", (message_id,))
            row = await cursor.fetchone()
            
            if not row:
                await interaction.response.send_message("❌ データが見つかりません。", ephemeral=True)
                return
            
            item_id, price, seller_id, status, img_url, tags_str = row
            img_url = img_url or ""
            tags_str = tags_str or ""
            
            if status != 'on_sale':
                await interaction.response.send_message("❌ 売り切れです。", ephemeral=True)
                return
            
            if buyer.id == seller_id:
                await interaction.response.send_message("❌ 自分の商品は購入できません。", ephemeral=True)
                return

            # 2. Check Balance & Process Transaction (ATOMIC)
            try:
                # Pass 'db' to withdraw_credits so it uses the SAME transaction
                await self.bot.bank.withdraw_credits(buyer, price, db_conn=db)
                
                # Inflation Logic (10% increase)
                new_price = int(price * 1.1)

                # Update DB (Ownership transfer, New Price, Reset Lock)
                await db.execute("UPDATE market_items SET status = 'owned', buyer_id = ?, seller_id = ?, price = ?, is_locked = 0 WHERE item_id = ?", (buyer.id, buyer.id, new_price, item_id))
                
                # Pay Seller (With Tax Logic)
                seller = interaction.guild.get_member(seller_id)
                payout_msg = ""
                
                if seller_id == self.bot.user.id:
                    # Bot Sale
                    pass
                elif seller:
                    # User Resale: 20% Tax
                    tax_rate = 0.2
                    tax_amount = int(price * tax_rate)
                    payout = int(price - tax_amount)
                    # Pass 'db' to deposit
                    await self.bot.bank.deposit_credits(seller, payout, db_conn=db)
                    payout_msg = f" (販売者へ `{payout:,}` 円送金)"
                
                await db.commit() # Commit EVERYTHING together
                
                await interaction.response.send_message(f"✅ 購入しました。\n`{price:,}` 円支払いました。{payout_msg}", ephemeral=True)

            except ValueError:
                await interaction.response.send_message(f"❌ 残高不足 ({price:,} 円必要)", ephemeral=True)
                return
            except Exception as e:
                await interaction.response.send_message(f"❌ エラー: {e}", ephemeral=True)
                return
            
            # --- Visual Transfer & Logging ---
            try:
                # 1. Log to market-logs
                log_channel = discord.utils.get(interaction.guild.text_channels, name="market-logs")
                # Fallback
                if not log_channel: log_channel = discord.utils.get(interaction.guild.text_channels, name="shadow-logs")
                
                if log_channel:

                    log_embed = discord.Embed(title="Transaction Log", color=discord.Color.green())
                    log_embed.add_field(name="Item ID", value=f"#{item_id}", inline=True)
                    log_embed.add_field(name="Buyer", value=buyer.mention, inline=True)
                    log_embed.add_field(name="Seller", value=f"<@{seller_id}>" if seller_id else "Unknown", inline=True)
                    log_embed.add_field(name="Price", value=f"{price:,}", inline=True)
                    if img_url: log_embed.set_thumbnail(url=img_url)
                    await log_channel.send(embed=log_embed)

                # 2. Cleanup Seller Message
                try:
                    await interaction.message.delete()
                except:
                    # Could not delete, maybe edit
                    await interaction.message.edit(content=f"❌ **完売**", view=None, embed=None)

                # 3. Post to Buyer's Gallery
                async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db_gal:
                    cursor = await db_gal.execute("SELECT thread_id FROM user_galleries WHERE user_id = ?", (buyer.id,))
                    row = await cursor.fetchone()
                
                new_thread_id = 0
                new_msg_id = 0
                
                if row:
                    buyer_thread = interaction.guild.get_thread(row[0])
                    if not buyer_thread:
                         try: buyer_thread = await interaction.guild.fetch_channel(row[0])
                         except: pass
                    
                    if buyer_thread:
                         gallery_embed = discord.Embed(title=f"所持品 (ID: #{item_id})", color=discord.Color.gold())
                         if img_url: gallery_embed.set_image(url=img_url)
                         gallery_embed.add_field(name="Tags", value=tags_str, inline=False)
                         
                         new_msg = await buyer_thread.send(content=f"**獲得:** {buyer.mention}", embed=gallery_embed)
                         new_thread_id = buyer_thread.id
                         new_msg_id = new_msg.id
                    else:
                         await interaction.followup.send("ギャラリーが見つかりません。`!join` してください。", ephemeral=True)
                else:
                     await interaction.followup.send("ギャラリー未登録のため、アイテムは倉庫に保管されました。", ephemeral=True)
                
                # Update DB with new location
                if new_thread_id:
                     async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db_upd:
                        await db_upd.execute("UPDATE market_items SET thread_id = ?, message_id = ? WHERE item_id = ?", (new_thread_id, new_msg_id, item_id))
                        await db_upd.commit()

            except Exception as e:
                print(f"Failed transfer logic: {e}")
                import traceback
                traceback.print_exc()

class ConfirmView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=30)
        self.user = user
        self.value = None

    @discord.ui.button(label="💸 支払う (Pay)", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id: return
        self.value = True
        self.stop()

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id: return
        self.value = False
        self.stop()

class MarketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ai_client = None

    async def cog_load(self):
        # Register Persistent View
        self.bot.add_view(BuyView(self.bot))
        # No persistent view for AuctionView needed? 
        # Actually yes, if we want buttons to work after restart.
        # But AuctionView takes item_id. 
        # Standard pattern: Use dynamic custom_id e.g. "auction:bid:item_id" OR generic callback that checks DB.
        # The Implementation above used a generic "auction_bid_btn" which looks up by Thread ID.
        # So we can register a generic instance.
        # Auction View Removed
        # self.bot.add_view(AuctionView(self.bot, 0))
        # self.auction_check_loop.start()

    def setup_client(self):
        try:
            token = getattr(self.bot, 'hf_token', None)
            if token and token != "YOUR_HUGGINGFACE_TOKEN_HERE":
                print(f"HF Token 検知: {token[:4]}****")
                self.ai_client = Client("Eugeoter/waifu-scorer-v3", token=token)
            else:
                print("HF Tokenが設定されていません。(匿名モードを試行)")
                self.ai_client = Client("Eugeoter/waifu-scorer-v3")
        except Exception as e:
            print(f"AI Client 初期化失敗: {e}")
            traceback.print_exc()
            self.ai_client = None

    def calculate_phash(self, image_path):
        """画像のPerceptual Hashを計算します。"""
        with Image.open(image_path) as img:
            return str(imagehash.phash(img))

    async def check_duplicate(self, current_hash):
        """DBから全ハッシュを取得し、ハミング距離を比較します。"""
        if not current_hash:
            return False

        async with aiosqlite.connect(self.bot.bank.db_path) as db:
            cursor = await db.execute("SELECT image_hash FROM market_items WHERE image_hash IS NOT NULL")
            rows = await cursor.fetchall()
        
        current_hash_obj = imagehash.hex_to_hash(current_hash)
        
        for (db_hash_str,) in rows:
            try:
                db_hash_obj = imagehash.hex_to_hash(db_hash_str)
                distance = current_hash_obj - db_hash_obj
                if distance <= 5: # 閾値 5
                    return True
            except:
                continue
        return False


    @commands.command(name="market", aliases=["gallery", "shop"])
    async def market(self, ctx):
        """現在販売中の美術品リストを見ます。"""
        async with aiosqlite.connect(self.bot.bank.db_path) as db:
            cursor = await db.execute(
                "SELECT item_id, price, aesthetic_score, image_url FROM market_items WHERE status = 'on_sale' ORDER BY item_id DESC LIMIT 10"
            )
            items = await cursor.fetchall()
            
        if not items:
            await ctx.send("販売中の作品がありません。")
            return

        embed = discord.Embed(title="販売リスト", color=discord.Color.purple())
        for item_id, price, score, url in items:
            embed.add_field(
                name=f"ID: {item_id} (スコア: {score:.2f})",
                value=f"価格: `{price:,} 円`\n[画像を見る]({url})",
                inline=False
            )
        embed.set_footer(text="購入するには '!購入 [番号]' を入力してください。")
        await ctx.send(embed=embed)

    @commands.command(name="lock")
    async def lock(self, ctx, item_id: int):
        """所持品をロック/解除します。ロック中は価格が2倍になります。"""
        async with aiosqlite.connect(self.bot.bank.db_path) as db:
            cursor = await db.execute("SELECT is_locked, buyer_id FROM market_items WHERE item_id = ?", (item_id,))
            row = await cursor.fetchone()
            
            if not row:
                await ctx.send("❌ アイテムが見つかりません。")
                return
            
            is_locked, owner_id = row
            if owner_id != ctx.author.id:
                await ctx.send("❌ あなたの所有物ではありません。")
                return
            
            new_lock = not is_locked
            await db.execute("UPDATE market_items SET is_locked = ? WHERE item_id = ?", (new_lock, item_id))
            await db.commit()
            
            status = "ロックしました (買収価格: 2倍)" if new_lock else "ロック解除しました"
            await ctx.send(f"✅ {status}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.member.bot: return
        
        if str(payload.emoji) != "🔥": return

        async with aiosqlite.connect(self.bot.bank.db_path) as db:
            cursor = await db.execute("SELECT seller_id, item_id, price FROM market_items WHERE message_id = ?", (payload.message_id,))
            row = await cursor.fetchone()
            
            if row:
                seller_id, item_id, price = row
                if seller_id and seller_id != payload.user_id:
                     seller = self.bot.get_user(seller_id)
                     if seller:
                         await self.bot.bank.deposit_credits(seller, 100, db_conn=db)
                         await db.commit()

    @commands.command(name="buy")
    async def buy(self, ctx, item_id: int):
        """ギャラリーにある絵を購入します。"""
        async with aiosqlite.connect(self.bot.bank.db_path) as db:
            cursor = await db.execute(
                "SELECT price, image_url, status, is_locked, buyer_id FROM market_items WHERE item_id = ?",
                (item_id,)
            )
            row = await cursor.fetchone()
            
            if not row:
                await ctx.send("❌ アイテムが見つかりません。")
                return
            
            price, image_url, status, is_locked, current_owner_id = row
            
            if current_owner_id == ctx.author.id:
                 await ctx.send("❌ 自分の商品は購入できません。")
                 return

            final_price = price
            
            # Lock Logic
            if is_locked:
                final_price = price * 2
                embed = discord.Embed(title="ロックされています", description=f"所有者が販売を拒否しています。\n**{final_price:,} Credits** (2倍) で強制買収しますか？", color=discord.Color.red())
                view = ConfirmView(ctx.author)
                msg = await ctx.send(embed=embed, view=view)
                await view.wait()
                
                if not view.value:
                    await msg.edit(content="キャンセルしました。", view=None, embed=None)
                    return
            
            # Check balance
            buyer_balance = await self.bot.bank.get_balance(ctx.author)
            if buyer_balance < final_price:
                await ctx.send(f"❌ 残高不足 (必要: {final_price:,} 円)")
                return
            
            # Process Transaction
            try:
                # Withdraw from Buyer
                await self.bot.bank.withdraw_credits(ctx.author, final_price, db_conn=db)
                
                # Pay Seller (Current Owner)
                if current_owner_id:
                    owner = self.bot.get_user(current_owner_id)
                    payout = final_price # Owner gets full amount (User: "Owner gets double")
                    if owner:
                        await self.bot.bank.deposit_credits(owner, payout, db_conn=db)
                    else:
                        # Offline deposit
                        await db.execute("INSERT INTO bank (user_id, guild_id, balance) VALUES (?, ?, ?) ON CONFLICT(user_id, guild_id) DO UPDATE SET balance = balance + ?", (current_owner_id, ctx.guild.id, payout, payout))
                
                # Inflation: +10%
                new_base_price = int(price * 1.1)
                
                await db.execute(
                    "UPDATE market_items SET status = 'owned', buyer_id = ?, is_locked = 0, price = ? WHERE item_id = ?",
                    (ctx.author.id, new_base_price, item_id,)
                )
                await db.commit()
                
                msg_text = f"購入完了。\n`{final_price:,} 円`を支払いました。"
                if is_locked:
                     msg_text = f"買収成功。\n(2倍価格 `{final_price:,} 円`)"
                
                embed = discord.Embed(title="取引完了", description=msg_text, color=discord.Color.green())
                embed.set_image(url=image_url)
                embed.set_footer(text=f"新価格: {new_base_price:,} Credits")
                await ctx.send(embed=embed)
                
            except ValueError as e:
                 await ctx.send(f"❌ 取引失敗: {e}")

async def setup(bot):
    await bot.add_cog(MarketCog(bot))
