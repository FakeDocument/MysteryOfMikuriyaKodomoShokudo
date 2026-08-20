#!/bin/sh
set -eu

smbd --foreground --no-process-group &
nmbd --foreground --no-process-group &

exec nginx -g "daemon off;"
