@echo off
cd /d "%~dp0.."

set /p ans=進捗データを含むすべてのコンテナ・ボリュームを削除します。よろしいですか？ (y/N):
if /i "%ans%"=="y" (
  docker compose down -v
  echo 初期化しました。
) else (
  echo 中止しました。
)
pause
