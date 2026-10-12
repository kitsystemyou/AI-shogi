# AI & JEV 将棋アリーナ (Shogi Arena)

各社先端LLM（**GPT-6-Luna**, **Gemini3.8flash**, **ClaudeSonnet5**）および TypeSafe AI 社の判定特化型AI **JEV** に将棋を対戦させ、勝敗やリアルタイム進行、棋譜履歴を閲覧・再生できるWebアプリケーションです。

---

## 🌟 主な機能

1. **先手・後手の自由なマッチング**:
   - `GPT-6-Luna` (OpenAI)
   - `Gemini3.8flash` (Google Gemini)
   - `ClaudeSonnet5` (Anthropic Claude)
   - `JEV` (TypeSafe AI)
   上記の4つのAIモデルから先手・後手を自由に選択して対局を開始可能。

2. **公平な局面情報の提供**:
   - 各LLMおよびJEVに対し、**同等の局面情報**（手番、手数、SFEN、9×9視覚テキスト盤面、両者の持ち駒、これまでの指し手履歴、合法手一覧）を提供。
   - **JEV** に対しては、TypeSafe AI の仕様に完全準拠し、`state` に局面情報、`questions` の `choice` 型 `criteria` に合法手を渡して判定を取得。

3. **リアルタイム対局 & 美麗な将棋盤UI**:
   - Server-Sent Events (SSE) によるリアルタイム指し手ストリーミング。
   - LLM API が HTTP 402 または 429 を返した場合は対局を中断し、履歴に記録。
   - 中断した対局は対戦履歴から棋譜を復元して再開可能。
   - 和風木目調の9×9将棋盤、駒の正立/反転、成駒の赤字表示、直前の指し手ハイライト。
   - 先手・後手の駒台（持ち駒表示）。
   - 各AIの思考時間、選択理由、API生レスポンスの閲覧。

4. **棋譜履歴・リプレイ機能**:
   - 対戦終了後、または対戦履歴一覧から過去の対局を選択し、初手から終局まで「1手進む」「1手戻る」「自動再生」などでじっくり再生・検証可能。
   - 棋譜のクリップボードコピー機能。
   - SQLite による全対局データの自動保存。

5. **柔軟なAPIキー設定**:
   - `.env` ファイルによる設定、またはWeb画面上の「API設定」モーダルから動的にAPIキーやモデル名、エンドポイントを設定可能。

---

## 🚀 セットアップと起動方法

### 1. 依存ライブラリのインストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定

`.env.example` を `.env` にコピーし、ご利用になるサービスのAPIキーを設定してください：

```bash
cp .env.example .env
```

`.env` の記述例:
```env
# OpenAI (GPT-6-Luna)
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-6-luna

# Google Gemini (Gemini3.8flash)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.8-flash

# Anthropic Claude (ClaudeSonnet5)
ANTHROPIC_API_KEY=your_anthropic_api_key_here
ANTHROPIC_MODEL=claude-sonnet-5

# TypeSafe AI JEV
JEV_API_KEY=your_typesafe_api_key_here
JEV_MODEL=jev-latest
JEV_ENDPOINT=https://api.typesafe.ai/v1/systemone
```
※APIキーはWeb画面上の「API設定」ボタンからも直接入力・保存が可能です。
※`GPT-6-Luna` はアプリ内のプレイヤー名です。OpenAI に送信する実モデル名は `OPENAI_MODEL` で設定します（既定値: `gpt-6-luna`）。

### 3. アプリケーションの起動

起動スクリプトを実行します：

```bash
./run.sh
```

または直接 uvicorn で起動：

```bash
python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

起動後、ブラウザで以下のURLにアクセスしてください：
👉 **http://localhost:8000**

---

## 📁 ディレクトリ構成

```
AI-shogi/
├── backend/
│   ├── app.py                # FastAPI APIサーバー & フロントエンド配信
│   ├── ai_service.py         # 各LLMおよびJEV API呼び出しロジック
│   ├── match_runner.py       # バックグラウンド対局ループ & SSE配信
│   ├── shogi_engine.py       # 将棋ルール、局面生成、合法手、終局判定
│   ├── database.py           # SQLite DB (matches, moves) CRUD
│   └── config.py             # 環境変数・設定管理
├── frontend/
│   ├── index.html            # Web UI HTML (Tailwind CSS, Lucide)
│   ├── style.css             # 将棋盤木目デザイン・駒スタイル
│   └── app.js                # リアルタイム盤面描画・リプレイ制御
├── requirements.txt          # Python依存ライブラリ
├── run.sh                    # 起動スクリプト
└── README.md                 # 本説明書
```
