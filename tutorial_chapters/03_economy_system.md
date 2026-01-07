# 第 3 章: 経済システムの構築 (Economy System)

これまでは `main.py` にすべてのコードを書いてきましたが、機能が増えるにつれてファイルが長くなり、管理が大変になります。
この章では、Discord Bot の機能分割システム **"Cogs (コグ)"** を使ってコードを整理し、本格的な銀行機能（残高確認、送金）を実装します。

---

## 1. Cogs (コグ) とは？

Robot（Bot）の「取り外し可能なパーツ」のようなものです。
「銀行機能パーツ」「密輸機能パーツ」のようにファイルを分けることで、メンテナンスがしやすくなります。

### フォルダ構成の変更

プロジェクトフォルダの中に、`cogs` という新しいフォルダを作ってください。

```
MyBot/
├── .env
├── main.py
├── bank_system.py
├── economy.db
└── cogs/          <-- New!
    └── bank.py    <-- この中に作ります
```

---

## 2. 銀行機能 (`cogs/bank.py`) の作成

`cogs` フォルダの中に `bank.py` を作成し、以下のコードを記述します。
これが「銀行機能パーツ」の設計図です。

```python
import discord
from discord.ext import commands
# 親フォルダにある bank_system をインポートするための魔法
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bank_system import BankSystem

class Bank(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # データベース操作クラスを準備
        self.bank = BankSystem("economy.db")

    # 起動時にデータベースを準備
    async def cog_load(self):
        await self.bank.initialize()

    # コマンド: 残高確認 (!balance / !bal)
    @commands.command(aliases=['bal', 'money'])
    async def balance(self, ctx):
        # 誰の残高？ -> コマンドを打った人(ctx.author)
        bal = await self.bank.get_balance(ctx.author.id)
        await ctx.send(f"💰 {ctx.author.mention} さんの所持金: **{bal:,}円**")

    # コマンド: 送金 (!pay @user 金額)
    @commands.command()
    async def pay(self, ctx, member: discord.Member, amount: int):
        # 1. バリデーション (不正チェック)
        if amount <= 0:
            await ctx.send("❌ 送金額は1円以上である必要があります。")
            return
        if member.id == ctx.author.id:
            await ctx.send("❌ 自分自身には送金できません。")
            return

        sender_bal = await self.bank.get_balance(ctx.author.id)

        # 2. 残高不足チェック
        if sender_bal < amount:
            await ctx.send("❌ 残高が足りません。")
            return

        # 3. 送金処理 (引き落とし & 入金)
        # Note: 本来は「トランザクション」を使って同時に行うべきですが、簡易的に実装します
        await self.bank.deposit(ctx.author.id, -amount) # 引き落とし
        await self.bank.deposit(member.id, amount)      # 入金

        await ctx.send(f"💸 {ctx.author.mention} が {member.mention} に **{amount:,}円** 送金しました！")

# メインファイルからロードされるための設定
async def setup(bot):
    await bot.add_cog(Bank(bot))
```

---

## 3. Bot 本体 (`main.py`) の修正

パーツを作ったので、本体(`main.py`)の方でそのパーツを読み込むように変更します。
`discord.Client` ではなく、より強力な `commands.Bot` を使うように書き換えます。

```python
import discord
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Botの設定
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # メンバー情報(誰がいるか)を知るために必要！

# commands.Bot を使用 (Clientより高機能)
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'{bot.user} としてログインしました！')

# Cogsの読み込みとBot起動を行う関数
async def main():
    # cogsフォルダにある bank.py を読み込む
    # ファイル名が変わったらここも変える: 'cogs.ファイル名'
    await bot.load_extension('cogs.bank')
    await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
```

**⚠️ 注意**: Developer Portal で `Server Members Intent` を ON にしないと、`!pay` コマンドでメンバーを認識できずにエラーになることがあります。必ず ON にしてください。

---

## 🧐 パイソン文法 & Discord.py 深掘り解説 (Code Deep Dive)

今回は少し高度な機能が出てきました。詳しく見ていきましょう。

### 1. `commands.Cog` (コグ)

```python
class Bank(commands.Cog):
    ...
async def setup(bot):
    await bot.add_cog(Bank(bot))
```

- **Cog**: Bot の機能をグループ分けするためのクラスです。`commands.Cog` を継承(コピーして改造)して作ります。
- **継承 (Inheritance)**: `class Bank(commands.Cog)` の `( ... )` は、「`commands.Cog` の機能を全部引き継いだうえで、新しい機能を追加します」という意味です。
- **setup 関数**: Bot 本体が「このファイルを読み込んで！」と言ったときに実行される関数です。ここでクラスを Bot に登録(`add_cog`)します。

### 2. コマンド引数の型変換 (Type Hinting & Converters)

```python
async def pay(self, ctx, member: discord.Member, amount: int):
```

これが `discord.py` の魔法の一つ、**Converter** です。

- **`member: discord.Member`**: ここに型を書くだけで、ユーザーが `!pay @Vincent ...` と入力したとき、自動的に `@Vincent` という文字を「Vincent さんのユーザーデータ(Member オブジェクト)」に変換してくれます。
- **`amount: int`**: ユーザーが入力した数字(文字列)を、自動的に計算可能な数字(整数)に変換してくれます。数字以外が入力されるとエラーを出してくれます。

### 3. コンテキスト (`ctx`)

```python
async def balance(self, ctx):
    await ctx.send(...)
```

- **`ctx` (Context)**: コマンドが実行されたときの「状況」が詰まった箱です。
  - `ctx.author`: コマンドを打った人
  - `ctx.channel`: コマンドが打たれた場所
  - `ctx.send()`: その場所に返事をするメソッド
- 以前の `on_message` では `message.channel.send` と書いていましたが、`ctx.send` はそれのショートカット版です。

### 4. バリデーション (入力チェック)

```python
if amount <= 0:
    ...
    return
```

- プログラムは、ユーザーがまともな入力をするとは限りません。マイナスの金額を送金できたら、簡単にお金が増やせてしまいます。
- そういう「やってはいけない入力」を弾く処理を**バリデーション**と呼びます。
- **`return`**: 関数を途中で終了させます。エラーメッセージを送った後、それ以上処理が進まないように重要です。

---

## 4. 実行テスト

1. `python main.py` を実行します。
2. `!bal` または `!money` と打って残高が表示されるか確認します。
3. 誰かに送金してみましょう: `!pay @友達の名前 100`
   - もし友達がいなければ、自分宛に送ってみてエラー(`自分自身には送金できません`)が出るか確認しましょう。
   - マイナスの金額を入れてエラーが出るかも確認しましょう。

---

### 次のステップ

銀行が完成しました！いよいよこの Bot のメインコンテンツ、**「AI 画像の密輸」** に挑戦します。
AI を動かすのは難しそうですが、API を使えば驚くほど簡単です。
👉 **[第 4 章: AI との連携 (AI & Smuggling)](04_ai_integration.md)**
