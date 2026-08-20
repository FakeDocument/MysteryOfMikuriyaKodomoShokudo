#!/bin/sh
set -eu

# 疎通確認機能のコマンドインジェクションで取得させる実行ユーザーを www-data に固定するため、
# アプリ本体は www-data で動かし、80番ポートの待受のみ root の nginx が引き受ける。
setpriv --reuid=www-data --regid=www-data --init-groups \
    /srv/portal/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 &

exec nginx -g "daemon off;"
