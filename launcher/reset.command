#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "進捗データを含むすべてのコンテナ・ボリュームを削除します。よろしいですか？ (y/N)"
read -r ans
if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
  docker compose down -v
  echo "初期化しました。"
else
  echo "中止しました。"
fi
read -r -p "Enterキーで終了します..." _
