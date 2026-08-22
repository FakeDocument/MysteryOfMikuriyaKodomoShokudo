#!/bin/sh
set -eu

smbd --foreground --no-process-group &
python3 /opt/mikuriya-webmail/app.py &

exec nginx -g "daemon off;"
