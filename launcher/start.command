#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
finish() { result=$?; if [ "$result" -ne 0 ]; then echo "起動に失敗しました。Docker Desktopと上のエラーを確認してください。"; docker compose ps 2>/dev/null || true; docker compose logs --tail 30 2>/dev/null || true; fi; read -r -p "Enterキーで終了します..." _ || true; exit "$result"; }
trap finish EXIT
docker info >/dev/null 2>&1 || { echo "Docker Desktopを起動してください。"; exit 1; }
echo "ソースからビルドして起動します。初回は時間がかかります..."
docker compose up --build --wait --wait-timeout 300
open "http://127.0.0.1:8080/" || true
echo "準備ができました。http://127.0.0.1:8080/"
