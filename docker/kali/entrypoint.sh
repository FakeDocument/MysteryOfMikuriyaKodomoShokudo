#!/bin/bash
set -eu

export USER=player
export HOME=/home/player
export DISPLAY=:1

mkdir -p "$HOME/.config/tigervnc"
echo "${VNC_PASSWORD:-99}" | vncpasswd -f > "$HOME/.config/tigervnc/passwd"
chmod 600 "$HOME/.config/tigervnc/passwd"
chown -R player:player "$HOME"

su player -c "vncserver :1 -geometry 1280x800 -depth 24 -localhost yes -SecurityTypes VncAuth"

exec websockify --heartbeat=30 --web=/usr/share/novnc/ 6901 localhost:5901
