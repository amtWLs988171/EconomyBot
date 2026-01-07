# 第 5 章: 闇市場を作る (Market System)

鑑定したアイテムを買い取るだけでは、Bot が在庫を抱えて赤字になってしまいます。
買い取ったアイテムを他のユーザーに販売し、経済を循環させる「マーケット機能」を作りましょう。

この章では、Discord の **「フォーラムチャンネル (Forum Channel)」** を活用して、見やすくて使いやすいショップを構築します。

---

## 1. データベースの拡張 (`bank_system.py`)

まずは「商品データ」を保存できるようにデータベースを進化させます。
`bank_system.py` の `initialize` メソッドに、新しいテーブル `market_items` を追加します。

```python
    async def initialize(self):
        async with aiosqlite.connect(self.db_path) as db:
            # ... (既存の bank テーブル作成) ...

            # 新しいテーブル: 商品リスト
            await db.execute("""
                CREATE TABLE IF NOT EXISTS market_items (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT, -- 商品ID (自動連番)
                    seller_id INTEGER,                         -- 出品者 (密輸した人)
                    image_url TEXT,                            -- 画像のURL
                    price INTEGER,                             -- 販売価格
                    status TEXT DEFAULT 'on_sale'              -- 状態 (販売中/売切れ)
                )
            """)
            await db.commit()
```

そして、商品を登録・検索・更新するメソッドも追加します。

```python
    # 商品を登録する
    async def add_item(self, seller_id, image_url, price):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO market_items (seller_id, image_url, price)
                VALUES (?, ?, ?)
            """, (seller_id, image_url, price))
            await db.commit()
            return cursor.lastrowid # 登録された商品のIDを返す

    # 商品を購入済みにする
    async def buy_item(self, item_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE market_items
                SET status = 'sold_out'
                WHERE item_id = ?
            """, (item_id,))
            await db.commit()
```

---

## 2. マーケット機能 (`cogs/market.py`) の作成

新しいファイル `cogs/market.py` を作成します。
ここでは、Discord のフォーラムチャンネルに「商品スレッド」を立てる機能を実装します。

```python
import discord
from discord.ext import commands
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bank_system import BankSystem

# 商品を並べるフォーラムチャンネルのID (Botの設定で書き換えてください！)
SHOP_CHANNEL_ID = 123456789012345678

class Market(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bank = BankSystem("economy.db")

    # 購入ボタンを作る (View)
    class BuyButton(discord.ui.View):
        def __init__(self, item_id, price, bank_system):
            super().__init__(timeout=None) # 期限切れなし
            self.item_id = item_id
            self.price = price
            self.bank = bank_system

        @discord.ui.button(label="購入する", style=discord.ButtonStyle.green, emoji="💸")
        async def buy_callback(self, interaction, button):
            # 1. お金があるか確認
            buyer_balance = await self.bank.get_balance(interaction.user.id)
            if buyer_balance < self.price:
                await interaction.response.send_message("❌ お金が足りません！", ephemeral=True)
                return

            # 2. 購入処理 (引き落とし & ステータス更新)
            await self.bank.deposit(interaction.user.id, -self.price)
            await self.bank.buy_item(self.item_id)

            # 3. ボタンを無効化して更新
            button.label = "売切れ"
            button.style = discord.ButtonStyle.grey
            button.disabled = True
            await interaction.response.edit_message(view=self)

            await interaction.followup.send(f"🎉 {interaction.user.mention} が商品を購入しました！")

    # 密輸(smuggle)したときに呼び出される関数
    async def list_item(self, guild, seller_id, image_url, price, tags):
        channel = guild.get_channel(SHOP_CHANNEL_ID)

        # データベースに登録
        item_id = await self.bank.add_item(seller_id, image_url, price)

        # 売買ボタンを作成
        view = self.BuyButton(item_id, price, self.bank)

        # フォーラムにスレッドを作成 (ここがショーウインドウになります)
        thread = await channel.create_thread(
            name=f"商品 #{item_id}: {tags[:20]}...", # スレッドタイトル
            content=f"💰 価格: **{price:,}円**\n出品者: <@{seller_id}>",
            file=await self.url_to_file(image_url), # 画像をアップロード
            view=view
        )
        return thread.jump_url

    # ユーティリティ: URLからファイルを読み込む (省略)
    async def url_to_file(self, url):
        # 実際には aiohttp などで画像をダウンロードして discord.File に変換します
        pass

async def setup(bot):
    await bot.add_cog(Market(bot))
```

---

## 3. Smuggle コマンドとの連携

前の章で作った `cogs/broker.py` から、この `list_item` を呼び出すように改造します。

```python
    # (cogs.broker.py 内)
    market_cog = self.bot.get_cog('Market')
    if market_cog:
        post_url = await market_cog.list_item(ctx.guild, ctx.author.id, attachment.url, price, tags_str)
        await ctx.send(f"✅ 出品しました！\n{post_url}")
```

---

## 🧐 パイソン文法 & Discord UI 深掘り解説 (Code Deep Dive)

### 1. `discord.ui.View` と `Button`

```python
class BuyButton(discord.ui.View):
    @discord.ui.button(...)
    async def buy_callback(...):
```

- **インタラクション (Interaction)**: 「コマンドを打つ」だけでなく、「ボタンを押す」「メニューを選ぶ」といったアクションを処理する仕組みです。
- **コールバック (Callback)**: 「ボタンが押されたときに呼び出される関数」のことです。ここで購入処理を行います。
- `interaction.response.send_message(..., ephemeral=True)`: **Ephemeral (エフェメラル)** は「自分にしか見えないメッセージ」です。「お金が足りません」のようなエラーを全員に見せるのは恥ずかしいので、これを使います。

### 2. クラスのネスト (Inner Class)

- 今回、`BuyButton` クラスを `Market` クラスの**中**には書かずに独立させても良いですが、コードが短い場合は中に入れてしまうこともあります。
- ただし、ボタンの状態(`item_id`など)を保持する必要があるため、クラスとして定義するのが一般的です。

### 3. 非同期処理の連携

- `broker` コグから `market` コグの関数を呼び出しています。コグ同士は `bot.get_cog('コグの名前')` で繋がることができます。
- これにより、「密輸係」と「販売係」がスムーズに連携できます。

---

### 次のステップ

これで、基本的な経済サイクル（密輸 → 鑑定 → 出品 → 購入）が完成しました！おめでとうございます！🎉
最後に、この Bot をさらに面白くするための「応用機能」について紹介します。
👉 **[第 6 章: 仕上げと拡張 (Advanced & Deploy)](06_advanced_features.md)**
