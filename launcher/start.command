#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "Dockerの起動状態を確認しています..."
if ! docker info > /dev/null 2>&1; then
  echo "Docker Desktopが起動していません。Docker Desktopを起動してから、もう一度実行してください。"
  read -r -p "Enterキーで終了します..." _
  exit 1
fi

echo "イメージを取得しています(初回のみ時間がかかります)..."
docker compose pull

echo "コンテナを起動しています..."
docker compose up -d

echo "サービスの起動を待っています..."
for svc in notebook sushi portal kali; do
  printf "  %s: " "$svc"
  ok=""
  for _ in $(seq 1 60); do
    status=$(docker inspect --format='{{.State.Health.Status}}' "sushictf-${svc}" 2>/dev/null || echo "starting")
    if [ "$status" = "healthy" ]; then
      ok="1"
      break
    fi
    sleep 2
  done
  if [ -n "$ok" ]; then echo "OK"; else echo "タイムアウト(手動で確認してください)"; fi
done

open "http://127.0.0.1:8080/" || true
open "http://127.0.0.1:6901/vnc.html?autoconnect=true" || true

echo "起動が完了しました。このウィンドウは閉じても構いません。"
read -r -p "Enterキーで終了します..." _
