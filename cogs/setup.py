import discord
from discord.ext import commands
import asyncio
import aiosqlite

class SetupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="init_server")
    @commands.has_permissions(administrator=True)
    async def init_server(self, ctx):
        """
        자동으로 서버를 설정합니다. (관리자 전용)
        - 카테고리: 闇市 (Shadow Market)
        - 채널: 密輸現場 (Smuggling Spot)
        - 포럼: 闇市ギャラリー (Shadow Gallery)
        - 역할: 密輸業者 (Smuggler)
        """
        guild = ctx.guild
        
    @commands.command(name="init_server")
    @commands.has_permissions(administrator=True)
    async def init_server(self, ctx):
        """
        サーバーの構成を自動セットアップします。
        - ロール: 密輸業者
        - カテゴリ: 🏢 ロビー (Lobby), 🌑 闇市 (Shadow Market)
        - チャンネル: ルール, 参加受付, 雑談, 密輸現場, 賭博場, 番付, ギャラリー
        """
        guild = ctx.guild
        
        try:
            # 1. Create Role
            role_name = "密輸業者"
            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                try:
                    role = await guild.create_role(name=role_name, color=discord.Color.dark_grey(), hoist=True)
                    await ctx.send(f"✅ ロール作成完了: {role.mention}")
                except discord.Forbidden:
                    await ctx.send("❌ **エラー:** ロール作成権限がありません。")
                    return
            else:
                await ctx.send(f"ℹ️ ロールは既に存在します: {role.mention}")

            # ---------------------------------------------------------
            # Category 1: Lobby (Public)
            # ---------------------------------------------------------
            lobby_cat_name = "ロビー (Lobby)"
            lobby_cat = discord.utils.get(guild.categories, name=lobby_cat_name)
            
            # Permissions: Everyone can see
            lobby_overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            if not lobby_cat:
                lobby_cat = await guild.create_category(lobby_cat_name, overwrites=lobby_overwrites)
                await ctx.send(f"✅ カテゴリ作成: **{lobby_cat_name}**")
            
            # Channel: rules (Read Only)
            rules_ch_name = "ルール"
            rules_ch = discord.utils.get(guild.text_channels, name=rules_ch_name, category=lobby_cat)
            if not rules_ch:
                rules_ch = await guild.create_text_channel(rules_ch_name, category=lobby_cat)
                await ctx.send(f"✅ チャンネル作成: {rules_ch.mention}")
                
                # Post Rules
                embed = discord.Embed(title="🎮 ゲームの仕組み (How to Play)", color=discord.Color.red())
                embed.description = (
                    "**💰 目的**\n"
                    "画像を密輸（アップロード）してクレジットを稼ぎ、闇市のランキング上位を目指しましょう。\n\n"
                    "**🔄 ゲームの流れ**\n"
                    "1. **隠れ家確保**: `!join` で自分専用の「隠れ家チャンネル」を作成します。\n"
                    "2. **密輸**: 隠れ家で `!smuggle` コマンドと共に画像をアップロード。\n"
                    "3. **査定**: AIが美学スコア(1-10)を判定し、即座に買取金を支払います。\n"
                    "4. **展示**: 売却された物品は自動的に「闇市ギャラリー」に展示されます。\n\n"
                    "**⚔️ マケット戦略 (PVP)**\n"
                    "- **購入**: ギャラリーの品は `!buy [ID]` で誰でも購入可能。\n"
                    "- **インフレ**: 取引されるたび、価格が **10%** ずつ上昇します。\n"
                    "- **ロック**: 所有者は `!lock [ID]` で販売拒否が可能。ただし...\n"
                    "- **強奪**: ロックされた品でも **2倍の価格** を払えば強制買収できます。\n\n"
                    "**💎 ロイヤルティ**\n"
                    "- ギャラリーの展示品に `🔥` リアクションがつくと、密輸者(あなた)に **+100 Credits** のボーナスが入ります。\n\n"
                    "**💻 主なコマンド**\n"
                    "- `!join`: 隠れ家を作成。\n"
                    "- `!smuggle`: (隠れ家専用) 画像を売却。\n"
                    "- `!market`: ギャラリーを見る。\n"
                    "- `!buy [ID]`: アイテムを購入。\n"
                    "- `!lock [ID]`: アイテムをロック/解除。\n"
                    "- `!balance`: 所持金確認。\n"
                    "- `!pay @user [金額]`: 送金。\n"
                )
                embed.set_footer(text="Economy Bot System")
                await rules_ch.send(embed=embed)
            
            # Channel: entry (Join Command)
            entry_ch_name = "参加受付"
            entry_overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=True), # Allow typing !join
            }
            entry_ch = discord.utils.get(guild.text_channels, name=entry_ch_name, category=lobby_cat)
            if not entry_ch:
                entry_ch = await guild.create_text_channel(entry_ch_name, category=lobby_cat, overwrites=entry_overwrites)
                await ctx.send(f"✅ チャンネル作成: {entry_ch.mention}")
                
                # Post Welcome
                embed = discord.Embed(title="🚪 闇市への入り口", color=discord.Color.dark_blue())
                embed.description = (
                    "ようこそ、闇の世界へ。\n"
                    "取引に参加するには、以下のコマンドを入力して登録を済ませてください。\n\n"
                    "**コマンド:**\n"
                    "`!join`\n\n"
                    "※登録すると、あなただけの「隠れ家」が作成されます。"
                )
                await entry_ch.send(embed=embed)


            # ---------------------------------------------------------
            # Category 2: Shadow Market (Restricted)
            # ---------------------------------------------------------
            shadow_cat_name = "闇市 (Shadow Market)"
            shadow_cat = discord.utils.get(guild.categories, name=shadow_cat_name)
            
            # Permissions: Everyone FALSE, Role TRUE
            shadow_overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            }

            if not shadow_cat:
                shadow_cat = await guild.create_category(shadow_cat_name, overwrites=shadow_overwrites)
                await ctx.send(f"✅ カテゴリ作成: **{shadow_cat_name}**")
            else:
                # Update permissions if exists
                await shadow_cat.edit(overwrites=shadow_overwrites)
                await ctx.send(f"♻️ カテゴリ権限更新: **{shadow_cat_name}**")

            # Create Channels
            # (Display Name, Code Name (unused here but good for logic), Topic)
            channels_to_create = [
                ("雑談", "general", "裏社会の社交場。"),
                # ("トレンド", "trends", "本日の流行情報 (AM 6:00更新)。"), # Removed
                ("密輸現場", "smuggling-spot", "ここで `!smuggle` コマンドを使用します。"),
                ("賭博場", "casino", "金と運の使い道。"),
                ("番付", "leaderboard", "実力者たちのランキング。"),
                ("ログ", "shadow-logs", "取引履歴。")
            ]

            for ch_display, ch_name, topic in channels_to_create:
                ch = discord.utils.get(guild.text_channels, name=ch_display, category=shadow_cat)
                if not ch:
                    ch = await guild.create_text_channel(ch_display, category=shadow_cat, topic=topic)
                    await ctx.send(f"✅ チャンネル作成: {ch.mention}")
            
            # Forum: Gallery
            forum_name = "闇市ギャラリー"
            forum = discord.utils.get(guild.forums, name=forum_name, category=shadow_cat)
            if not forum:
                tags = [
                    discord.ForumTag(name="販売中", emoji="🟢"),
                    discord.ForumTag(name="完売", emoji="🔴"),
                    discord.ForumTag(name="S級", emoji="💎"),
                    discord.ForumTag(name="偽物", emoji="💩"),
                    discord.ForumTag(name="注目", emoji="🔥")
                ]
                forum = await guild.create_forum(name=forum_name, category=shadow_cat, topic="密輸品展示場", available_tags=tags)
                await ctx.send(f"✅ フォーラム作成: {forum.mention}")
            
            # Bot Gallery Setup (Same as before)
            if forum:
                async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db:
                     cursor = await db.execute("SELECT thread_id FROM user_galleries WHERE user_id = ?", (self.bot.user.id,))
                     row = await cursor.fetchone()
                     if not row:
                         thread = await forum.create_thread(name="[Official] 闇のブローカー", content="公式取引所")
                         t = thread.thread if hasattr(thread, 'thread') else thread
                         await db.execute("INSERT OR REPLACE INTO user_galleries (user_id, thread_id) VALUES (?, ?)", (self.bot.user.id, t.id))
                         await db.commit()
                         await ctx.send("✅ 公式ギャラリー設立完了")

            await ctx.send("🎉 **サーバー構成の再構築が完了しました！**")

        except Exception as e:
            await ctx.send(f"❌ エラーが発生しました: {e}")
            import traceback
            traceback.print_exc()



    @commands.command(name="reset_game")
    @commands.has_permissions(administrator=True)
    async def reset_game(self, ctx):
        """ゲームデータを完全に消去し、初期化します。(危険!)"""
        embed = discord.Embed(title="💣 ゲームリセット", description="**警告: 以下のデータを全て削除します。**\n- カテゴリ: 闇市, ロビー, Hideouts\n- ロール: 密輸業者\n- データベース: 全ユーザーの所持金, アイテム, ギャラリー設定\n\n本当に実行しますか？ `yes` と入力してください。", color=discord.Color.red())
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == "yes"

        try:
            await self.bot.wait_for('message', check=check, timeout=15.0)
        except asyncio.TimeoutError:
            await ctx.send("❌ 時間切れによりキャンセルされました。")
            return

        msg = await ctx.send("💥 **初期化プロセスを開始...**")
        guild = ctx.guild

        # 1. Delete Channels & Categories
        categories = ["闇市 (Shadow Market)", "ロビー (Lobby)", "🕵️ Hideouts"]
        deleted_cats = 0
        
        for cat_name in categories:
            cat = discord.utils.get(guild.categories, name=cat_name)
            if cat:
                for channel in cat.channels:
                    try: await channel.delete()
                    except: pass
                try: 
                    await cat.delete()
                    deleted_cats += 1
                except: pass
        
        await msg.edit(content=f"🗑️ チャンネル/カテゴリ削除完了 ({deleted_cats}件)")

        # 2. Delete Role
        role_name = "密輸業者"
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            try: await role.delete()
            except: pass
            
        # 3. Wipe DB Tables
        async with aiosqlite.connect(self.bot.bank.db_path) as db:
            await db.execute("DELETE FROM bank")
            await db.execute("DELETE FROM market_items")
            # await db.execute("DELETE FROM market_trends") # Table might not exist if removed, but good to ensure
            await db.execute("DELETE FROM user_galleries")
            # Reset SQLite Autoincrement
            await db.execute("DELETE FROM sqlite_sequence WHERE name='market_items'")
            await db.commit()
            
        await ctx.send("✨ **全データの消去が完了しました。**\n`!init_server` を実行して再構築してください。")

async def setup(bot):
    await bot.add_cog(SetupCog(bot))
