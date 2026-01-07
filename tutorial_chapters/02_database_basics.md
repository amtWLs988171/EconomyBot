# 第 2 章: データを保存しよう (Database Magic)

Bot を再起動すると、前の章で作った変数はすべて消えてしまいます。
ユーザーの所持金やアイテムのような大切なデータを、再起動しても消えないように「永続化」するのがデータベースの役割です。

この章では、Python 標準のデータベースエンジン **SQLite** を使って、銀行システム(`BankSystem`)の基礎を作ります。

---

## 1. 必要なライブラリのインストール

Discord Bot は「非同期(Async)」で動いているため、データベース操作も非同期で行う必要があります。
そのためのライブラリ `aiosqlite` をインストールします。

```bash
pip install aiosqlite
```

---

## 2. データベース操作クラスを作る

Bot のコード(`main.py`)が長くなりすぎないように、データベース操作を担当する専用の「クラス」を作ります。
新しいファイル `bank_system.py` を作成し、以下のコードを記述してください。

### `bank_system.py`

```python
import aiosqlite

class BankSystem:
    def __init__(self, db_path):
        self.db_path = db_path

    # 1. データベースの初期化 (テーブル作成)
    async def initialize(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS bank (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER DEFAULT 0
                )
            """)
            await db.commit()
            print("データベースの準備が完了しました。")

    # 2. 残高の確認
    async def get_balance(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT balance FROM bank WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            # データがあればその値を、なければ0を返す
            if row:
                return row[0]
            else:
                return 0

    # 3. お金の預け入れ (残高を増やす)
    async def deposit(self, user_id, amount):
        async with aiosqlite.connect(self.db_path) as db:
            # まだデータがない人のために、なければ作成(INSERT)、あれば更新(UPDATE)
            await db.execute("""
                INSERT INTO bank (user_id, balance)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?
            """, (user_id, amount, amount))
            await db.commit()
```

---

## 🧐 パイソン文法 & SQL 深掘り解説 (Code Deep Dive)

データベース操作は「Python のコード」の中に「SQL という別の言語」が混ざるため、少し複雑に見えます。詳しく見ていきましょう。

### 1. クラスと `__init__`

```python
class BankSystem:
    def __init__(self, db_path):
        self.db_path = db_path
```

- **`class BankSystem`**: 「銀行システム」という機能のまとまり（設計図）を定義します。
- **`__init__` (コンストラクタ)**: このクラスを使うとき、最初に**必ず自動で実行される**特別な関数です。
  - `self.db_path = db_path`: 「データベースファイルの場所」という設定を、このクラス自身(`self`)に記憶させています。

### 2. 非同期コンテキストマネージャ (`async with`)

```python
async with aiosqlite.connect(self.db_path) as db:
    ...
```

- **`connect`**: データベースファイルを開く（電話をかける）操作です。
- **`async with ... as db`**: 「データベースを開いて、使い終わったら**必ず閉じる**」という一連の流れを自動でやってくれる構文です。
  - これを使わないと、ファイルを閉じ忘れてデータが壊れたり、エラーになったりします。
  - `as db`: 開いたデータベース接続に `db` というあだ名を付けて、ブロックの中で使えるようにしています。

### 3. SQL (Structured Query Language)

ダブルクォーテーション 3 つ(`"""`)で囲まれた部分は、Python ではなく**SQL 言語**です。データベースへの命令書です。

#### テーブル作成 (`CREATE TABLE`)

```sql
CREATE TABLE IF NOT EXISTS bank (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0
)
```

- 「もし `bank` という表(テーブル)がなかったら、作ってね」という命令です。
- 表には 2 つの列(カラム)を作ります：
  - `user_id`: ユーザー ID（整数）。**PRIMARY KEY** は「これが背番号（重複しない主キー）」という意味です。
  - `balance`: 残高（整数）。**DEFAULT 0** は「最初の一行を作るときは 0 円からスタート」という意味です。

#### データの取得 (`SELECT`)

```sql
SELECT balance FROM bank WHERE user_id = ?
```

- 「`bank` テーブルから、`user_id` が `?` である人の `balance` を見せて！」という命令です。
- `?` (プレースホルダー): ここには後から具体的な Python の変数(`user_id`)が入ります。直接埋め込まず `?` を使うのは、セキュリティ（SQL インジェクション対策）のためです。

#### データの保存/更新 (`INSERT ... ON CONFLICT`)

```sql
INSERT INTO bank ... VALUES ... ON CONFLICT(user_id) DO UPDATE ...
```

- 非常に便利な「Upsert (Update + Insert)」という合体技です。
- 「新しいデータを**追加(INSERT)**して！ ...でも、もし同じ `user_id` の人が既にいたら(ON CONFLICT)、エラーにせずに**更新(UPDATE)** してね」という意味です。
- これひとつで「新規ユーザー登録」と「既存ユーザーへの入金」の両方を処理できます。

---

## 3. Bot 本体 (`main.py`) と合体させる

作った `BankSystem` を、前章の `main.py` に組み込んで使いましょう。

**`main.py` を以下のように修正します：**

```python
import discord
import os
from dotenv import load_dotenv
from bank_system import BankSystem  # 1. 作ったクラスをインポート

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# 2. 銀行システムのインスタンスを作成
# "economy.db" というファイルにデータを保存します
bank = BankSystem("economy.db")

@client.event
async def on_ready():
    # 3. 起動時にテーブルを作成
    await bank.initialize()
    print(f'{client.user} としてログインしました！')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # !bal: 残高確認
    if message.content == '!bal':
        balance = await bank.get_balance(message.author.id)
        await message.channel.send(f'{message.author.name}さんの残高: {balance}円')

    # !work: 仕事をして100円稼ぐ
    if message.content == '!work':
        await bank.deposit(message.author.id, 100)
        new_balance = await bank.get_balance(message.author.id)
        await message.channel.send(f'働いて100円稼ぎました！ (現在: {new_balance}円)')

client.run(TOKEN)
```

## 4. 実行テスト

1. `python main.py` を実行します。
2. ディレクトリに `economy.db` というファイルが生成されたことを確認してください。
3. Discord で `!bal` と打つと「0 円」と返ってきます。
4. `!work` と打つと「100 円稼ぎました」と返ってきます。
5. **一度 Bot を停止(Ctrl+C)し、再起動してください。**
6. もう一度 `!bal` と打ってみましょう。前の金額が残っていれば、データベース機能の完成です！🎉

---

### 次のステップ

お金の管理ができるようになりました！
次はいよいよこのお金を使って、商品の売買などができるようにシステムを整理していきます。
👉 **[第 3 章: 経済システムの構築 (Economy System)](03_economy_system.md)**
