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
        - ロール: トレーダー
        - カテゴリ: 🏢 ロビー, 📈 マーケット
        - チャンネル: ルール, 参加受付, 雑談, 買取所, カジノ, ランキング, ギャラリー, 管理者ログ
        """
        guild = ctx.guild
        
        try:
            # 1. Create Role
            role_name = "トレーダー"
            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                # Check for old name to rename
                old_role = discord.utils.get(guild.roles, name="密輸業者")
                if old_role:
                    await old_role.edit(name=role_name, color=discord.Color.blue())
                    role = old_role
                    await ctx.send(f"✅ ロール名を変更しました: {role.mention}")
                else:
                    try:
                        role = await guild.create_role(name=role_name, color=discord.Color.blue(), hoist=True)
                        await ctx.send(f"✅ ロール作成完了: {role.mention}")
                    except discord.Forbidden:
                        await ctx.send("エラー: 権限がありません。")
                        return
            else:
                await ctx.send(f"ロール確認: {role.mention}")

            # ---------------------------------------------------------
            # Category 1: Lobby (Public)
            # ---------------------------------------------------------
            lobby_cat_name = "ロビー"
            lobby_cat = discord.utils.get(guild.categories, name=lobby_cat_name)
            # Check old
            if not lobby_cat: lobby_cat = discord.utils.get(guild.categories, name="ロビー (Lobby)")
            if lobby_cat and lobby_cat.name != lobby_cat_name: await lobby_cat.edit(name=lobby_cat_name)

            lobby_overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            if not lobby_cat:
                lobby_cat = await guild.create_category(lobby_cat_name, overwrites=lobby_overwrites)
                await ctx.send(f"✅ カテゴリ作成: {lobby_cat_name}")
            
            # Channel: rules
            rules_ch_name = "ルール"
            rules_ch = discord.utils.get(guild.text_channels, name=rules_ch_name, category=lobby_cat)
            if not rules_ch:
                rules_ch = await guild.create_text_channel(rules_ch_name, category=lobby_cat)
                await ctx.send(f"✅ チャンネル作成: {rules_ch.mention}")
                
                # Post Rules
                embed = discord.Embed(title="システムガイド", color=discord.Color.blue())
                embed.description = (
                    "**目的**\n"
                    "画像を売却してクレジットを稼ぎ、ランキング上位を目指します。\n\n"
                    "**流れ**\n"
                    "1. **参加**: `!join` で専用チャンネルを作成。\n"
                    "2. **売却**: 専用チャンネルで `!sell` (または `!smuggle`) で画像をアップロード。\n"
                    "3. **査定**: AIが評価し、即座にクレジットが支払われます。\n"
                    "4. **ギャラリー**: 売却されたアイテムは「ギャラリー」に展示されます。\n\n"
                    "**💰 ボーナス**\n"
                    "タグが多いほど査定額がアップします (+100 Credits/個)\n\n"
                    "**コマンド一覧**\n"
                    "- `!join`: 参加 / 専用チャンネル作成\n"
                    "- `!sell`: アイテム売却 (画像添付)\n"
                    "- `!market`: 販売リスト表示\n"
                    "- `!buy [ID]`: アイテム購入\n"
                    "- `!lock [ID]`: 販売ロック/解除\n"
                    "- `!balance`: 残高確認\n"
                    "- `!pay @user [金額]`: 送金\n"
                )
                await rules_ch.send(embed=embed)
            
            # Channel: entry
            entry_ch_name = "参加受付"
            entry_overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            }
            entry_ch = discord.utils.get(guild.text_channels, name=entry_ch_name, category=lobby_cat)
            if not entry_ch:
                entry_ch = await guild.create_text_channel(entry_ch_name, category=lobby_cat, overwrites=entry_overwrites)
                await ctx.send(f"✅ チャンネル作成: {entry_ch.mention}")
                
                embed = discord.Embed(title="参加受付", color=discord.Color.green())
                embed.description = "参加するには `!join` と入力してください。"
                await entry_ch.send(embed=embed)


            # ---------------------------------------------------------
            # Category 2: Market (Restricted)
            # ---------------------------------------------------------
            market_cat_name = "マーケット"
            market_cat = discord.utils.get(guild.categories, name=market_cat_name)
            if not market_cat: market_cat = discord.utils.get(guild.categories, name="闇市 (Shadow Market)")
            if market_cat and market_cat.name != market_cat_name: await market_cat.edit(name=market_cat_name)
            
            market_overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            }

            if not market_cat:
                market_cat = await guild.create_category(market_cat_name, overwrites=market_overwrites)
                await ctx.send(f"✅ カテゴリ作成: {market_cat_name}")
            else:
                await market_cat.edit(overwrites=market_overwrites)
                await ctx.send(f"カテゴリ設定更新: {market_cat_name}")

            # Create Channels
            channels_to_create = [
                ("雑談", "general", "交流スペース"),
                ("買取所", "buy-center", "コマンド用チャンネル"),
                ("カジノ", "casino", "ミニゲーム"),
                ("ランキング", "ranking", "資産ランキング"),
                ("ログ", "market-logs", "取引履歴")
            ]

            for ch_display, ch_name, topic in channels_to_create:
                ch = discord.utils.get(guild.text_channels, name=ch_display, category=market_cat)
                if not ch:
                    # Check for old names to rename? (e.g. smuggling-spot -> buy-center)
                    # For now just create new ones.
                    ch = await guild.create_text_channel(ch_display, category=market_cat, topic=topic)
                    await ctx.send(f"✅ チャンネル作成: {ch.mention}")

            # Admin Log Channel (New)
            admin_log_name = "backend-logs"
            admin_log = discord.utils.get(guild.text_channels, name=admin_log_name, category=market_cat)
            if not admin_log:
                admin_overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    role: discord.PermissionOverwrite(read_messages=False), 
                    guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                }
                admin_log = await guild.create_text_channel(admin_log_name, category=market_cat, topic="管理者ログ", overwrites=admin_overwrites)
                await ctx.send(f"✅ 管理者ログ作成: {admin_log.mention}")

            
            # Forum: Gallery
            forum_name = "ギャラリー"
            forum = discord.utils.get(guild.forums, name=forum_name, category=market_cat)
            if not forum: forum = discord.utils.get(guild.forums, name="闇市ギャラリー", category=market_cat)
            if forum and forum.name != forum_name: await forum.edit(name=forum_name)

            if not forum:
                tags = [
                    discord.ForumTag(name="販売中", emoji="🟢"),
                    discord.ForumTag(name="完売", emoji="🔴"),
                    discord.ForumTag(name="S級", emoji="💎"),
                    discord.ForumTag(name="注目", emoji="🔥")
                ]
                forum = await guild.create_forum(name=forum_name, category=market_cat, topic="アイテム展示場", available_tags=tags)
                await ctx.send(f"✅ フォーラム作成: {forum.mention}")
            
            # Bot Gallery Setup
            if forum:
                async with aiosqlite.connect(self.bot.bank.db_path, timeout=60.0) as db:
                     cursor = await db.execute("SELECT thread_id FROM user_galleries WHERE user_id = ?", (self.bot.user.id,))
                     row = await cursor.fetchone()
                     if not row:
                         thread = await forum.create_thread(name="[Official] System Shop", content="公式ショップ")
                         t = thread.thread if hasattr(thread, 'thread') else thread
                         # Create record for bot
                         await db.execute("INSERT OR REPLACE INTO user_galleries (user_id, thread_id) VALUES (?, ?)", (self.bot.user.id, t.id))
                         await db.commit()
                         await ctx.send("✅ 公式ショップ設立完了")

            await ctx.send("セットアップ完了。")

        except Exception as e:
            await ctx.send(f"エラー: {e}")
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
