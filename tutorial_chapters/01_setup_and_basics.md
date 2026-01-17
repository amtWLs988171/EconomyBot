# 第 1 章: 準備と基礎 (Getting Started)

この章では、Discord Bot を作るための準備を行い、実際に Bot を動かすところまで進めます。
「Bot が自分に返事をしてくれた！」という感動を味わいましょう。

---

## 1. 必要なツールの準備

Bot 開発には「武器」が必要です。以下のツールをインストールしてください。

### 🐍 Python (プログラミング言語)

Bot の頭脳となるプログラムを書くための言語です。

- **ダウンロード**: [python.org](https://www.python.org/downloads/)
- **注意**: インストール時に "Add Python to PATH" というチェックボックスに必ずチェックを入れてください！

### 💻 VS Code (コードエディタ)

プログラムを書くための高機能なメモ帳です。

- **ダウンロード**: [code.visualstudio.com](https://code.visualstudio.com/)

### 🐙 Git (バージョン管理)

プログラムのセーブデータを管理するツールです。

- **ダウンロード**: [git-scm.com](https://git-scm.com/)

---

## 2. Discord Developer Portal での作業

Bot のアカウント（魂）を作成し、Discord サーバーに招待します。

1.  [Discord Developer Portal](https://discord.com/developers/applications) にアクセスし、ログインします。
2.  右上の **"New Application"** ボタンをクリックし、名前（例: `MyFirstBot`）を入力して作成します。
3.  左メニューの **"Bot"** をクリックします。
4.  **"Reset Token"** をクリックして、**Token（トークン）** を発行し、コピーします。
    - **⚠️ 重要**: このトークンは Bot の「パスワード」です。**絶対に他人に教えないでください！**
5.  同ページの **"Message Content Intent"** などの **Privileged Gateway Intents** をすべて ON（有効）にして、"Save Changes" を押します。
    - これを ON にしないと、Bot がメッセージを読めません。
6.  左メニューの **"OAuth2" -> "URL Generator"** をクリックします。
    - **SCOPES**: `bot` にチェック。
    - **BOT PERMISSIONS**: `Administrator` (管理者) にチェック。
7.  生成された URL をコピーしてブラウザで開き、自分のサーバーに Bot を招待します。

---

## 3. プロジェクトの作成

自分の PC 上に Bot の家（フォルダ）を作ります。

1.  適当な場所にフォルダを新規作成します（例: `MyBot`）。
2.  VS Code を開き、"File" -> "Open Folder" で `MyBot` フォルダを開きます。

### 仮想環境の作成 (Virtual Environment)

**なぜこれが必要なの？**
Python では、プロジェクトごとに使う「道具（ライブラリ）」のバージョンが違うことがよくあります。
もし全員が同じ場所（PC 全体）に道具を置いてしまうと、「Bot A は古い道具を使いたいのに、Bot B が新しい道具に書き換えてしまって動かない！」というトラブル（競合）が起きます。
仮想環境を作ることで、**このプロジェクト専用の独立した部屋**を用意し、他のプロジェクトに影響を与えずに開発できるようにします。

プロジェクトごとに部屋を分けるようなものです。ターミナル（VS Code の上部メニュー "Terminal" -> "New Terminal"）で以下を入力します：

```bash
# Mac/Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\activate
```

### ライブラリのインストール

Discord 用の魔法の道具箱 `discord.py` と、環境変数を扱う `python-dotenv` をインストールします。

```bash
pip install discord.py python-dotenv
```

---

## 4. 最初のコードを書く

いよいよ Bot に命を吹き込みます。

### Step 1: 環境変数の設定

トークンをコードに直接書くのは危険なので、`.env` という秘密のファイルを作ってそこに隠します。
フォルダ内に `.env` という名前の新しいファイルを作成し、以下を記述します：

```env
DISCORD_TOKEN=あなたのトークンをここに貼り付け
```

### Step 2: `main.py` の作成と徹底解説

Bot の本体となるファイル `main.py` を作成します。
まずは以下のコードをコピペして、その後に続く「文法解説」をじっくり読んでください。

```python
import discord
import os
from dotenv import load_dotenv

# 1. 設定の読み込み
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# 2. Botの設定 (Intents)
intents = discord.Intents.default()
intents.message_content = True

# 3. クライアントの作成
client = discord.Client(intents=intents)

# 4. イベント処理: 起動したとき
@client.event
async def on_ready():
    print(f'{client.user} としてログインしました！')

# 5. イベント処理: メッセージを受け取ったとき
@client.event
async def on_message(message):
    # 自分自身のメッセージには反応しない
    if message.author == client.user:
        return

    # "ping" と言われたら "Pong!" と返す
    if message.content == 'ping':
        await message.channel.send('Pong!')

# 6. Botの起動
client.run(TOKEN)
```

---

## 🧐 パイソン文法 深掘り解説 (Code Deep Dive)

魔法の呪文のように見えるコードも、一つ一つ分解すれば意味があります。
プログラミング初心者のために、このコードで使われている重要な文法を解説します。

### 1. 道具箱を開ける (`import`)

```python
import discord
from dotenv import load_dotenv
```

- **`import` (インポート)**: パイソンには最初からすべての機能が入っているわけではありません。`import discord` は「Discord を操作する道具箱(ライブラリ)を持ってきて！」という命令です。
- **`from ... import ...`**: これは「`dotenv` という大きな道具箱の中から、`load_dotenv` という特定の道具だけを取り出して！」という意味です。全部読み込むより効率的です。

### 2. 変数と代入 (`=`)

```python
TOKEN = os.getenv("DISCORD_TOKEN")
```

- **変数 (Variable)**: `TOKEN` は箱のようなものです。右側の `os.getenv(...)` で取得した「秘密のパスワード」を、`TOKEN` という名前の箱に入れて(代入して)います。
- 以降、コードの中で `TOKEN` と書けば、中に入っているパスワードを取り出せます。

### 3. オブジェクトとインスタンス

```python
intents = discord.Intents.default()
client = discord.Client(intents=intents)
```

- **クラス (Class)**: `discord.Client` は「ロボットの設計図」です。設計図そのものは動きません。
- **インスタンス (Instance)**: `client = ...` の部分は、設計図から「実体のロボット」を 1 体製造して、`client` という名前を付けています。この `client` が実際に動く Bot です。

### 4. デコレータ (`@`)

```python
@client.event
```

- **デコレータ**: 関数の上に付いている `@` マークは「飾り付け」です。
- ここでは「下の関数(`on_ready` など)は、ただの関数じゃなくて**Bot のイベント対応用**だよ！」と Bot 本体に教えて登録しています。これがないと、Bot はいつその関数を実行していいか分かりません。

### 5. 非同期処理 (`async` / `await`) **【最重要】**

```python
async def on_message(message):
    ...
    await message.channel.send('Pong!')
```

Discord Bot において最も重要で、少し難しい概念です。

- **`async def` (非同期関数)**: 「完了まで時間がかかるかもしれない関数」の宣言です。通信待ちなどの間、PC をフリーズさせずに他の作業(他の人のチャットを読むなど)を並行して行えるようになります。
- **`await` (待機)**: 「ここで処理が終わるのを待ってね」という合図です。
  - `message.channel.send('Pong!')` (メッセージ送信) は、インターネットを通じて Discord のサーバーにデータを送るため、一瞬ですが時間がかかります。
  - `await` を書くことで、**送信完了を確実に待ってから**次の行に進みます。これを忘れるとエラーになったり、メッセージが届かなかったりします。

### 6. 条件分岐 (`if`)

```python
if message.content == 'ping':
    await message.channel.send('Pong!')
```

- **`if`**: 「もし〜なら」という条件判断です。
- **`==`**: 「左と右が同じなら」という意味です。 (`=` 1 つだと代入になってしまうので注意！)
- **インデント (字下げ)**: Python では、`if` の中身であることを示すために、行頭をスペース 4 つ分空けます。これがズレると動かなくなります。
  - ここでは、「メッセージの中身が 'ping' だった場合**のみ**、その下の `send` を実行する」という構造を作っています。

### 7. f-文字列 (f-string)

```python
print(f'{client.user} としてログインしました！')
```

- 文字列の前に `f` を付けると、文字列の中に変数を埋め込めるようになります。
- `{client.user}` の部分が、実際の Bot の名前に置き換わって表示されます。

---

## 5. 実行してみよう！

ターミナルで以下のコマンドを入力して実行します：

```bash
python main.py
```

エラーが出ずに `MyFirstBot#1234 としてログインしました！` と表示されれば成功です！
Discord で Bot がいるチャンネルで `ping` と発言してみてください。
Bot が `Pong!` と返してくれたら、あなたの最初の Bot の完成です！🎉

---

### 次のステップ

次は、Bot に「記憶」を持たせるために、データベースについて学びます。
👉 **[第 2 章: データを保存しよう (Database Magic)](02_database_basics.md)**
