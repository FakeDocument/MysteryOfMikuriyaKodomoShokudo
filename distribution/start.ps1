$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
function Docker-Checked {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw "Docker の処理に失敗しました: $args" }
}
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktopをインストールしてください。' }
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktopを起動してから再実行してください。' }
    Docker-Checked compose version
    $release = Get-Content release.txt
    $actual = & docker info --format '{{.Architecture}}'
    if ($LASTEXITCODE -ne 0) { throw 'DockerのCPU情報を取得できません。' }
    if ($actual -notin @('x86_64', 'amd64') -or $release[2] -ne 'amd64') { throw 'Windows x64用のDocker環境が必要です。' }
    $missing = $false
    foreach ($image in Get-Content images.txt) {
        & docker image inspect $image *> $null
        if ($LASTEXITCODE -ne 0) { $missing = $true }
    }
    if ($missing) {
        Write-Host '環境イメージをダウンロードしています。数分以上かかる場合があります...'
        & curl.exe --fail --location --retry 3 --output images.tar.gz.part $release[1]
        if ($LASTEXITCODE -ne 0) { throw 'ダウンロードに失敗しました。接続と空き容量を確認してください。' }
        $hash = (Get-FileHash images.tar.gz.part -Algorithm SHA256).Hash
        if ($hash -ne $release[0]) { throw 'チェックサムが一致しません。もう一度実行してください。' }
        Docker-Checked load --input images.tar.gz.part
        Remove-Item images.tar.gz.part
    }
    Write-Host '環境を起動しています...'
    Docker-Checked compose up --no-build --pull never --wait --wait-timeout 300
    Start-Process 'http://127.0.0.1:8080/'
    Write-Host '準備ができました。調査ノート: http://127.0.0.1:8080/'
} catch {
    Write-Host $_ -ForegroundColor Red
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        & docker compose ps
        & docker compose logs --tail 30
    }
    Read-Host 'Enterキーで閉じます'
    exit 1
}
Read-Host 'Enterキーで閉じます'
