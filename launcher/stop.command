#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "コンテナを停止しています..."
docker compose stop

echo "停止しました。"
read -r -p "Enterキーで終了します..." _
