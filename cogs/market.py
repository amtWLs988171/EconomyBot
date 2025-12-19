import discord
from discord.ext import commands
from gradio_client import Client, handle_file
import asyncio
import aiosqlite
import os
import aiohttp
import uuid
import traceback
import imagehash
from PIL import Image

class BuyView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="💸 今すぐ購入", style=discord.ButtonStyle.green, custom_id="shadow_broker:buy_btn")
    async def buy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. Identify Item by Thread ID
        thread_id = interaction.channel_id
        buyer = interaction.user
        
        async with aiosqlite.connect(self.bot.bank.db_path) as db:
            cursor = await db.execute("SELECT item_id, price, seller_id, status FROM market_items WHERE thread_id = ?", (thread_id,))
            row = await cursor.fetchone()
            
            if not row:
                await interaction.response.send_message("❌ データが見つかりません。", ephemeral=True)
                return
            
            item_id, price, seller_id, status = row
            
            if status != 'on_sale':
                await interaction.response.send_message("❌ 売り切れです。", ephemeral=True)
                return
            
            if buyer.id == seller_id:
                await interaction.response.send_message("❌ 自分の商品は購入できません。", ephemeral=True)
                return

            # 2. Check Balance
            try:
                await self.bot.bank.withdraw_credits(buyer, price)
            except ValueError:
                await interaction.response.send_message(f"❌ 残高不足です！ ({price:,} クレジット必要)", ephemeral=True)
                return

            # 3. Process Transaction
            # Update DB to SOLD first (to prevent double buy)
            await db.execute("UPDATE market_items SET status = 'owned', buyer_id = ?, seller_id = ?, price = 0 WHERE item_id = ?", (buyer.id, buyer.id, item_id))
            # Wait, if we set status='owned', price=0? No, maybe keep price for record?
            # Actually, `price` in DB is "Current Sale Price". If not on sale, maybe null or 0.
            # But let's set seller_id = buyer_id (Ownership transfer)
            await db.commit()
            
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
                await self.bot.bank.deposit_credits(seller, payout)
                payout_msg = f" (販売者へ `{payout:,}` 円送金)"
            
            await interaction.response.send_message(f"✅ **取引成立！**\n`{price:,}` 円支払いました。{payout_msg}", ephemeral=True)
            
            # --- Visual Transfer & Logging ---
            try:
                # 1. Log to shadow-logs
                log_channel = discord.utils.get(interaction.guild.text_channels, name="shadow-logs")
                if log_channel:
                    img_url = ""
                    # We need image url from somewhere, fetch from DB or message
                    # Let's fetch from DB for logging
                    async with aiosqlite.connect(self.bot.bank.db_path) as db:
                        c2 = await db.execute("SELECT image_url, tags, aesthetic_score FROM market_items WHERE item_id = ?", (item_id,))
                        r2 = await c2.fetchone()
                        img_url = r2[0] if r2 else ""
                        tags_str = r2[1] if r2 else ""

                    log_embed = discord.Embed(title="💸 Transaction Log", color=discord.Color.green())
                    log_embed.add_field(name="Item ID", value=f"#{item_id}", inline=True)
                    log_embed.add_field(name="Buyer", value=buyer.mention, inline=True)
                    log_embed.add_field(name="Seller", value=f"<@{seller_id}>" if seller_id else "Unknown", inline=True)
                    log_embed.add_field(name="Price", value=f"{price:,}", inline=True)
                    if img_url: log_embed.set_thumbnail(url=img_url)
                    await log_channel.send(embed=log_embed)

                # 2. Cleanup Seller Message
                # We know thread_id is interaction.channel_id
                # But message_id? Interaction.message.id!
                try:
                    await interaction.message.delete()
                except:
                    # Could not delete, maybe edit
                    await interaction.message.edit(content=f"❌ **完売 (Sold)**", view=None, embed=None)

                # 3. Post to Buyer's Gallery
                async with aiosqlite.connect(self.bot.bank.db_path) as db:
                    cursor = await db.execute("SELECT thread_id FROM user_galleries WHERE user_id = ?", (buyer.id,))
                    row = await cursor.fetchone()
                
                new_thread_id = 0
                new_msg_id = 0
                
                if row:
                    buyer_thread = interaction.guild.get_thread(row[0])
                    if not buyer_thread:
                         try: buyer_thread = await interaction.guild.fetch_channel(row[0])
                         except: pass
                    
                    if buyer_thread:
                         # Reconstruct Embed for Gallery
                         # Need to fetch details again or use what we have? 
                         # We have img_url from logging step
                         gallery_embed = discord.Embed(title=f"🖼️ 所持品 (ID: #{item_id})", color=discord.Color.gold())
                         if img_url: gallery_embed.set_image(url=img_url)
                         gallery_embed.add_field(name="Tags", value=tags_str, inline=False)
                         
                         new_msg = await buyer_thread.send(content=f"**獲得:** {buyer.mention}", embed=gallery_embed)
                         new_thread_id = buyer_thread.id
                         new_msg_id = new_msg.id
                    else:
                         await interaction.followup.send("⚠️ あなたのギャラリーが見つかりませんでした。`!join` で作成してください。", ephemeral=True)
                else:
                     await interaction.followup.send("⚠️ ギャラリー未登録のため、アイテムは倉庫(DB)に保管されました。`!join` してください。", ephemeral=True)
                
                # Update DB with new location
                if new_thread_id:
                     async with aiosqlite.connect(self.bot.bank.db_path) as db:
                        await db.execute("UPDATE market_items SET thread_id = ?, message_id = ? WHERE item_id = ?", (new_thread_id, new_msg_id, item_id))
                        await db.commit()

            except Exception as e:
                print(f"Failed transfer logic: {e}")
                import traceback
                traceback.print_exc()

class MarketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ai_client = None

    async def cog_load(self):
        # Register Persistent View
        self.bot.add_view(BuyView(self.bot))

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
            await ctx.send("🏪 現在販売中の作品がありません。先に絵を鑑定してもらって売ってみましょう！")
            return

        embed = discord.Embed(title="🏰 AIアートギャラリー (Market)", color=discord.Color.purple())
        for item_id, price, score, url in items:
            embed.add_field(
                name=f"🖼️ No.{item_id} (スコア: {score:.2f})",
                value=f"価格: `{price:,} 円`\n[画像を見る]({url})",
                inline=False
            )
        embed.set_footer(text="購入するには '!購入 [番号]' を入力してください。")
        await ctx.send(embed=embed)

    @commands.command(name="buy")
    async def buy(self, ctx, item_id: int):
        """ギャラリーにある絵を購入します。"""
        async with aiosqlite.connect(self.bot.bank.db_path) as db:
            cursor = await db.execute(
                "SELECT price, image_url, status FROM market_items WHERE item_id = ?",
                (item_id,)
            )
            row = await cursor.fetchone()
            
            if not row:
                await ctx.send("❌ その番号の作品は見つかりませんでした。")
                return
            
            price, image_url, status = row
            
            if status != 'on_sale':
                await ctx.send("❌ すでに販売された作品です。")
                return
            
            # Check balance
            buyer_balance = await self.bot.bank.get_balance(ctx.author)
            if buyer_balance < price:
                await ctx.send(f"❌ 残高が不足しています。(必要: {price:,} 円, 保有: {buyer_balance:,} 円)")
                return
            
            # Process Transaction
            try:
                await self.bot.bank.withdraw_credits(ctx.author, price)
                
                await db.execute(
                    "UPDATE market_items SET status = 'sold' WHERE item_id = ?",
                    (item_id,)
                )
                await db.commit()
                
                embed = discord.Embed(title="🎉 購入成功！", description=f"素晴らしい作品を所持することになりました。\n`{price:,} 円`を支払いました。", color=discord.Color.green())
                embed.set_image(url=image_url)
                await ctx.send(embed=embed)
                
            except ValueError as e:
                 await ctx.send(f"❌ 取引失敗: {e}")

async def setup(bot):
    await bot.add_cog(MarketCog(bot))
