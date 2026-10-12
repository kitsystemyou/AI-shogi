#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# .envが存在しない場合は.env.exampleからコピー
if [ ! -f .env ]; then
    echo "⚠️ .env が見つからないため、.env.example からコピーして作成します。"
    cp .env.example .env
fi

echo "🏯 AI & JEV 将棋アリーナ を起動いたします..."
echo "🌐 ブラウザで http://localhost:8000 にアクセスしてください。"

exec python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
