# 第 6 章: 仕上げと拡張 (Advanced & Deploy)

おめでとうございます！ここまでで、Discord Bot としての核となる機能はほぼ完成しました。
最終章では、この Bot をさらに「ゲーム」として面白くするためのスパイスと、Bot を世界に公開するためのヒントを紹介します。

---

## 1. トレンド機能の実装 (Trend System)

株価のように毎日価格が変動したら、ゲームはもっと面白くなります。
`cogs/broker.py` に「本日のトレンド」機能を追加してみましょう。

```python
import random

# トレンドの候補リスト
TREND_THEMES = ["cat_ears", "blue_hair", "megane", "school_uniform", "maid"]

class Broker(commands.Cog):
    def __init__(self, bot):
        self.trend = None # 今日のトレンド

    # 毎日(または起動時)にトレンドを更新
    async def update_trend(self):
        self.trend = random.choice(TREND_THEMES)
        print(f"今日のトレンド: {self.trend}")

    # smuggleコマンド内でボーナス計算
    # ...
    # if self.trend in tags_str:
    #     price *= 2 # トレンドが含まれていたら価格2倍！
    #     await ctx.send(f"🔥 トレンドボーナス({self.trend})！価格が2倍になりました！")
```

`discord.ext.tasks` を使えば、「毎日朝 6 時に実行」といった定期実行も簡単に作れます。

---

## 2. 重複画像の防止 (Bloom Filter & ImageHash)

同じ画像を何度も投稿してお金を稼ぐ「グリッチ(不正技)」を防ぐ必要があります。
これには **Perceptual Hash (知覚ハッシュ)** という技術を使います。

```bash
pip install ImageHash
```

```python
import imagehash
from PIL import Image
import io

# ハッシュ値を計算する関数
def get_image_hash(image_bytes):
    img = Image.open(io.BytesIO(image_bytes))
    return imagehash.average_hash(img)

# データベースにハッシュを保存しておき、
# 新しい画像のハッシュと比較して、差が小さければ「重複」とみなす
```

---

## 3. Bot を 24 時間動かし続けるには？ (Deployment)

自分の PC で `python main.py` を動かし続けるのは大変です。PC を閉じると Bot も止まってしまいます。
Bot をずっと動かし続けるには、**クラウドサーバー (VPS)** を使うのが一般的です。

### おすすめのサービス

1.  **Railway / Render / Heroku**: 初心者向けのクラウドサービス。設定が簡単。
2.  **AWS / Google Cloud / Azure**: プロ向け。1 年間無料枠などがある。
3.  **Oracle Cloud**: ずっと無料で使える枠がある（人気すぎて契約が難しい場合も）。
4.  **VPS (ConoHa, Sakura など)**: 月額数百円で自分専用の Linux サーバーが借りられる。

### デプロイの手順 (VPS の場合)

1.  サーバーを借りる (OS は Ubuntu がおすすめ)
2.  SSH で接続する
3.  `git clone` でコードを持ってくる
4.  `pip install` でライブラリを入れる
5.  **Docker** または **Systemd** を使って、Bot をバックグラウンドで起動する

---

## 4. 最後に

これで「Discord Bot 開発の教科書」は終了です。
あなたは以下の技術を習得しました：

- ✅ **Python & Discord.py**: Bot 開発の基礎
- ✅ **SQLite & aiosqlite**: データベースによるデータの永続化
- ✅ **Cogs**: 大規模開発に耐えうるコード設計
- ✅ **Hugging Face API**: 最新 AI 技術との連携
- ✅ **Discord UI**: ボタンやインタラクションの活用

この Bot はまだ「ベータ版」です。
新しいアイテムを追加したり、RPG のような戦闘機能を追加したり、ガチャ機能を作ったり...
ここから先は、あなたのアイデア次第でどこまでも拡張できます。

Happy Coding! 🚀
