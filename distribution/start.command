#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
finish() { result=$?; if [ "$result" -ne 0 ]; then echo "準備に失敗しました。上のエラーを確認して再実行してください。"; docker compose ps 2>/dev/null || true; docker compose logs --tail 30 2>/dev/null || true; fi; read -r -p "Enterキーで閉じます..." _ || true; exit "$result"; }
trap finish EXIT
command -v docker >/dev/null || { echo "Docker Desktopをインストールしてください。"; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker Desktopを起動してから再実行してください。"; exit 1; }
docker compose version >/dev/null
expected=$(sed -n '3p' release.txt)
actual=$(docker info --format '{{.Architecture}}')
case "$expected:$actual" in arm64:aarch64|arm64:arm64|amd64:x86_64|amd64:amd64) ;; *) echo "CPUの種類が配布ファイルと異なります。対応するZIPを選んでください。"; exit 1;; esac
missing=0
while IFS= read -r img; do
  docker image inspect "$img" >/dev/null 2>&1 || missing=1
done < images.txt
if [ "$missing" = 1 ]; then
  echo "環境イメージをダウンロードしています。数分以上かかる場合があります..."
  curl --fail --location --retry 3 --output images.tar.gz.part "$(sed -n '2p' release.txt)"
  printf '%s  images.tar.gz.part\n' "$(sed -n '1p' release.txt)" | shasum -a 256 -c -
  docker load --input images.tar.gz.part
  rm images.tar.gz.part
fi
echo "環境を起動しています..."
docker compose up --no-build --pull never --wait --wait-timeout 300
open "http://127.0.0.1:8080/" || true
echo "準備ができました。調査ノート: http://127.0.0.1:8080/"
