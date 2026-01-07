# 📘 Discord Bot 開発の教科書: Python で作る闇経済シミュレーション

この教科書では、あなた自身の手で「Shadow Art Broker (EconomyBot)」と同じ機能を持つ Discord Bot を一から作り上げる方法を解説します。
プログラミング初心者でも理解できるように、基礎から応用まで段階的にステップアップしていきます。

## 📚 目次 (Curriculum)

### 第 1 章: 準備と基礎 (Getting Started)

- **[01. 開発環境の構築と最初の Bot](01_setup_and_basics.md)**
  - Python のインストール
  - Discord Developer Portal での Bot 作成
  - 最小構成の Bot を動かす (`on_ready`, `on_message`)

### 第 2 章: データベースの魔術 (Database Magic)

- **[02. データを保存しよう: SQLite 入門](02_database_basics.md)**
  - データベースとは？なぜ必要なのか？
  - `aiosqlite` を使った非同期データベース操作
  - ユーザーのお金を保存する `BankSystem` を作る

### 第 3 章: 経済システムの構築 (Economy System)

- **[03. 銀行機能の実装](03_economy_system.md)**
  - `cogs` 機能によるコード分割
  - 所持金の表示 (`!balance`)
  - 送金機能 (`!pay`) とエラー処理

### 第 4 章: AI 画像の「密輸」 (AI & Smuggling)

- **[04. AI との連携: 画像認識と価値判定](04_ai_integration.md)**
  - Hugging Face API (Gradio) の使い方
  - 画像の美学スコア (`Waifu Scorer`) の取得
  - 画像タグ解析 (`WD Tagger`)
  - `!smuggle` コマンドのプロトタイプ作成

### 第 5 章: 闇市場を作る (Market & Auction)

- **[05. マーケットとトランザクション](05_market_system.md)**
  - 商品を出品するロジック
  - Discord Forum Channel との連携
  - 購入処理とアイテム所有権の移転

### 第 6 章: 高度な機能とデプロイ (Advanced & Deploy)

- **[06. 仕上げと拡張](06_advanced_features.md)**
  - トレンド機能の実装
  - 重複画像チェック (Bloom Filter / ImageHash)
  - Bot を 24 時間動かし続けるには？

---

まずは **[第 1 章: 準備と基礎](01_setup_and_basics.md)** から始めましょう！
