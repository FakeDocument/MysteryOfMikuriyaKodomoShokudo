@echo off
setlocal
cd /d "%~dp0.."

echo Dockerの起動状態を確認しています...
docker info >nul 2>&1
if errorlevel 1 (
  echo Docker Desktopが起動していません。Docker Desktopを起動してから、もう一度実行してください。
  pause
  exit /b 1
)

echo イメージを取得しています(初回のみ時間がかかります)...
docker compose pull

echo コンテナを起動しています...
docker compose up -d

echo サービスの起動を待っています...
set /a count=0
:wait_loop
set /a count+=1
if %count% gtr 60 (
  echo タイムアウトしました。手動で状態を確認してください。
  goto open_browser
)
timeout /t 3 >nul
docker inspect --format="{{.State.Health.Status}}" sushictf-kali 2>nul | findstr "healthy" >nul
if errorlevel 1 goto wait_loop

:open_browser
start "" "http://127.0.0.1:8080/"
start "" "http://127.0.0.1:6901/vnc.html?autoconnect=true&reconnect=true&reconnect_delay=5000"

echo 起動が完了しました。
pause
