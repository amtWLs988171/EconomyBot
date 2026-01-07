# 第 4 章: AI との連携: 画像認識と価値判定 (AI Integration)

銀行システムができたら、次はお金を稼ぐ手段が必要です。
この Bot の最大の特徴である **「画像を AI に鑑定させて価値を決める」** 機能を作ります。

「AI を動かす」と聞くと難しそうですが、Hugging Face というサイトが提供している API を使えば、数行のコードで実装できます。

---

## 1. 必要なライブラリのインストール

Hugging Face の AI モデルを Python から操作するための `gradio_client` をインストールします。

```bash
pip install gradio_client
```

---

## 2. Broker (ブローカー) 機能の作成 (`cogs/broker.py`)

「密輸」「鑑定」を担当する `cogs/broker.py` を作成します。
まずは AI 鑑定を行うための最小限のコードを書いてみましょう。

```python
import discord
from discord.ext import commands
from gradio_client import Client, handle_file
import os

# 鑑定に使用するAIモデルのアドレス
TAGGER_MODEL = "SmilingWolf/wd-tagger"
SCORER_MODEL = "Eugeoter/waifu-scorer-v3"

class Broker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # .envからトークンを取得
        self.hf_token = os.getenv("HF_TOKEN")

    @commands.command()
    async def smuggle(self, ctx):
        # 1. 画像が添付されているかチェック
        if not ctx.message.attachments:
            await ctx.send("❌ 画像を添付してください！")
            return

        attachment = ctx.message.attachments[0]
        # 画像ファイル以外は弾く
        if not attachment.content_type.startswith('image/'):
            await ctx.send("❌ 画像ファイルのみ受け付けています。")
            return

        await ctx.send("🕵️ 鑑定中...少々お待ちください...")

        try:
            # 2. AI鑑定 (API呼び出し)
            # URLを直接渡すのではなく、一度ダウンロードしてからAPIに渡すのが確実です
            # Note: 実際にはダウンロード処理が必要ですが、ここでは簡略化のためURLを使用する場合の例です
            # (本格的な実装では一時保存処理推奨)

            # --- ここで実際のAIコード ---
            # WD Tagger (タグ解析)
            tagger_client = Client(TAGGER_MODEL, hf_token=self.hf_token)
            # 画像URLを渡して解析
            tag_result = tagger_client.predict(
                image=handle_file(attachment.url),
                api_name="/predict"
            )
            # 結果は複雑なデータなので、必要な部分を取り出します
            # (モデルによって戻り値の形式が違うので注意！)
            tags_str = str(tag_result)

            # Waifu Scorer (美学スコア)
            scorer_client = Client(SCORER_MODEL, hf_token=self.hf_token)
            score_result = scorer_client.predict(
                input_image=handle_file(attachment.url),
                api_name="/predict"
            )
            # 例: 結果が "Score: 8.5" のような文字列だと仮定して数値を取り出す
            # 実際にはJSONなどで返ってくることが多いです
            score = float(score_result)

            # 3. 結果発表
            await ctx.send(f"📊 鑑定結果:\nスコア: **{score}**\nタグ情報: {tags_str[:50]}...")

        except Exception as e:
            await ctx.send(f"❌ エラーが発生しました: {e}")
            print(e)

async def setup(bot):
    await bot.add_cog(Broker(bot))
```

> **注意**: 上記のコードは概念コードです。実際の Hugging Face API は戻り値の形式がモデルごとに異なります。
> 正確に動作させるためには、以下の「深掘り解説」でデータ構造を理解する必要があります。

---

## 3. Bot 本体 (`main.py`) の修正

新しく作った `cogs/broker` を読み込むように、`main.py` の `main()` 関数を修正します。

```python
async def main():
    await bot.load_extension('cogs.bank')
    await bot.load_extension('cogs.broker') # 追加！
    await bot.start(TOKEN)
```

---

## 🧐 パイソン文法 & API 深掘り解説 (Code Deep Dive)

### 1. 例外処理 (`try` / `except`)

```python
try:
    # 危険な処理 (API呼び出しなど)
    ...
except Exception as e:
    # エラーが起きたときの処理
    await ctx.send(f"エラー: {e}")
```

- **`try`**: 「失敗するかもしれないけど、やってみて！」というブロックです。ネットワーク通信は相手のサーバーがダウンしていたりして失敗することがあるので、必ずこれで囲みます。
- **`except`**: 「もし失敗したら、パニックにならずにここを実行して」というブロックです。これがないと、エラーが起きた瞬間に Bot 全体が停止してしまいます。

### 2. リストとインデックス (`attachments[0]`)

```python
attachment = ctx.message.attachments[0]
if not attachment.content_type.startswith('image/'): ...
```

- **`attachments`**: 添付ファイルのリスト（配列）です。
- **`[0]`**: 「一番最初のもの」という意味です。Python など多くの言語では、数字は 0 から数え始めます（0 番目、1 番目...）。
- **`content_type`**: ファイルの種類を表す ID カードです。画像なら `image/png` や `image/jpeg` となっているので、`image/` で始まっているか(`startswith`)を確認しています。

### 3. API クライアント (`Client`, `predict`)

```python
client = Client("モデル名", hf_token=...)
result = client.predict(...)
```

- **API (Application Programming Interface)**: 「外部のソフトウェアの機能を借りるための窓口」です。
- ここでは自分の PC で AI を動かすのではなく、「Hugging Face というデパートにいる AI さん」に画像を送って(`predict`)、結果を返してもらっています。
- これにより、低スペックな PC でも高度な AI 機能を使うことができます。

---

## 4. 価格計算ロジックの実装（仕上げ）

AI からスコア(例: 7.5)を受け取ったら、それをお金に換算しましょう。
単純な掛け算ではなく、**「良いものほど急激に高くなる」** 計算式にするのがゲームバランスのコツです。

```python
def calculate_price(score: float):
    # 基本価格: スコアの2乗 × 1000
    # 例:
    # スコア 5.0 -> 25 * 1000 = 25,000円
    # スコア 9.0 -> 81 * 1000 = 81,000円
    price = int((score ** 2) * 1000)
    return price
```

これを `smuggle` コマンドの中に組み込み、`self.bank.deposit` でお金を振り込めば、「密輸機能」の完成です！

---

### 次のステップ

鑑定して買い取ったアイテム、ただ Bot が持っているだけでは意味がありません。
これを他のユーザーが買えるように「市場（マーケット）」に並べましょう。
👉 **[第 5 章: 闇市場を作る (Market & Auction)](05_market_system.md)**
