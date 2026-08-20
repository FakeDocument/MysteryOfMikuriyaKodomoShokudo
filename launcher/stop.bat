@echo off
cd /d "%~dp0.."

echo コンテナを停止しています...
docker compose stop

echo 停止しました。
pause
