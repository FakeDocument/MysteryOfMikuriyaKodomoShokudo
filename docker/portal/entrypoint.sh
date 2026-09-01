#!/bin/sh
set -eu

# アプリ本体は非rootの www-data で動かし、80番ポートの待受だけを root の nginx が引き受ける。
setpriv --reuid=www-data --regid=www-data --init-groups \
    /srv/portal/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 &

exec nginx -g "daemon off;"
