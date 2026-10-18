# SushiCTF — 御厨こども食堂の謎

ブラウザの調査ノートと専用の調査端末を使って進める、日本語の事件調査CTFです。コマンドの操作はゲーム内で学べます。自分でKali Linuxや攻撃ツールをインストールする必要はありません。

[セットアップ案内サイト](https://fakedocument.github.io/MysteryOfMikuriyaKodomoShokudo/) · [最新版をダウンロード](https://github.com/FakeDocument/MysteryOfMikuriyaKodomoShokudo/releases/latest)

## 1. パソコンを準備する

公式対応は **Windows 11（Intel / AMDの64bit版）** と **Apple Silicon搭載Mac（M1以降）** です。Windows ARM、Intel Mac、Linuxは公式動作保証の対象外です。

メモリ8GB以上、空き容量4GB以上を目安にしてください。CTF本体の容量は約3GBです。Docker Desktop本体とセットアップ時の一時領域には別途容量が必要です。初回のダウンロードにはインターネット接続が必要です。

1. [Windows用Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) または [Mac用Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/) をインストールします。Macでは「Apple silicon」を選びます。
2. WindowsでWSL 2の導入や再起動を求められたら、インストーラーの案内に従います。
3. Docker Desktopを起動し、エンジンの起動が完了するまで待ちます。WindowsはLinuxコンテナモードで使用してください。

Dockerは、ゲーム用の小さな実行環境をパソコンの中で動かすソフトです。Docker Desktopの利用条件と対応OSは、リンク先の公式案内を確認してください。

## 2. ZIPをダウンロードして展開する

[最新版の配布ページ](https://github.com/FakeDocument/MysteryOfMikuriyaKodomoShokudo/releases/latest) の「Assets」から、自分のパソコン用のファイルを選びます。まだリリースが作成されていない場合、ダウンロードは利用できません。

- Windows：`SushiCTF-Windows-x64.zip`
- Apple Silicon Mac：`SushiCTF-macOS-arm64.zip`

WindowsはZIPを右クリックして「すべて展開」、MacはZIPをダブルクリックします。展開したフォルダーを、デスクトップなどの書き込み可能な場所に置いてください。ZIPの中から直接起動しないでください。「Source code」は開発者用です。

## 3. 起動ファイルをダブルクリックする

- Windows：展開先の `はじめる.bat`
- Mac：展開先の `はじめる.command`

初回は同じリリースの環境イメージを自動でダウンロードし、改ざんや破損がないことを確認してからDockerへ読み込みます。ダウンロードは約800MBで、準備には数分以上かかることがあります。画面に「準備ができました」と出るまでウィンドウを閉じないでください。失敗した場合は原因を解消し、同じファイルを再実行できます。

準備が終わると [調査ノート](http://127.0.0.1:8080/) がブラウザに開きます。序章から読み進めてください。[調査端末](http://127.0.0.1:6901/vnc.html?autoconnect=true&reconnect=true&reconnect_delay=5000) はゲーム内のリンクからも開けます。起動用ウィンドウは完了後に閉じて構いません。

Macで実行権限がないと表示された場合は、ターミナルで `chmod +x ` と入力し、展開した `はじめる.command` をドラッグしてEnterを押します。その後、もう一度ダブルクリックします。OSの保護機能に止められた場合は、配布元を確認したうえでOSの案内に従って許可してください。

## 中断・再開・最初からやり直す

- **中断**：`とめる.bat` / `とめる.command` をダブルクリック。回答と調査メモは残ります。
- **再開**：Docker Desktopを起動して `はじめる` を再実行。読み込み済みの環境はオフラインで起動できます。
- **最初から**：`初期化.bat` / `初期化.command` を実行し、確認で `y` を入力。回答・調査メモを含む進捗が削除されます。その後 `はじめる` を実行します。

ブラウザを閉じるだけでは環境は停止しません。進捗はDockerの専用ボリュームに保存されます。Docker Desktopでボリュームを削除すると進捗も消えます。旧版と新版を同時に起動せず、更新前に旧版を停止してください。版を戻す場合の進捗互換性は保証しません。

## 困ったとき

- **Dockerが見つからない・接続できない**：Docker Desktopを起動して待ち、再実行してください。インストール直後はOSの再起動が必要なことがあります。
- **ダウンロードが失敗した**：インターネット接続と空き容量を確認し、再実行してください。途中のファイルは再取得されます。
- **チェックサムが一致しない**：再実行して再取得してください。繰り返す場合は配布ページと通信環境を確認してください。
- **起動に時間がかかる・タイムアウトする**：Docker Desktopへ割り当てるメモリと空き容量を確認してください。起動失敗時には状態とログが表示されます。
- **ポート使用中**：8080番・6901番を使う別のアプリや以前のSushiCTFを停止して再実行してください。
- **ネットワーク作成エラー**：VPNや既存のDocker環境が `172.30.0.0/24` を使っていないか確認してください。
- **ブラウザが開かない**：起動完了後に、上の「調査ノート」リンクを開いてください。調査端末で接続が切れた場合はページを再読み込みしてください。

## 遊ぶ範囲

調査対象は、この環境内のゲーム用サーバーです。外部のWebサイトや他人の機器へ攻撃する必要はありません。攻略対象は隔離ネットワーク内に置き、ブラウザ用の入口はこのパソコンの `127.0.0.1` だけへ公開します。調査端末からはインターネットへ接続できるため、ゲームで案内された対象を調査してください。ゲームの起動後は外部サービスなしで攻略できます。

## 開発・配布する人へ

リポジトリから動かす場合は、Docker起動後にルートで `docker compose up --build --wait --wait-timeout 300` を実行します。停止は `docker compose stop` です。

CIは `v` で始まるタグ（例：`v1.0.0`）のpushで、amd64・arm64の環境イメージをそれぞれビルドし、チェックサムとOS別ランチャーZIPをGitHub Releasesへ公開します。環境イメージはZIPに入れず、ランチャーが同じリリースから自動取得します。両アーキテクチャのヘルスチェックが通ってから公開します。

一般公開用のReleasesは公開リポジトリに作成してください。非公開リポジトリの配布URLは、この認証なしランチャーから取得できません。非公開リポジトリでのPages利用には対応するGitHubプランが必要です。

GitHub Pagesの初回設定は、リポジトリの **Settings → Pages → Build and deployment → Source → GitHub Actions** を選びます。既定ブランチへのpushでREADMEから案内サイトを生成・デプロイします。READMEが手順の正本です。サイト用の依存は `site/requirements.txt`、生成は `python scripts/build_site.py` です。

CIの配布スクリプトは `scripts/package_release.py`、ランチャー本体は `distribution/` にあります。Docker Desktop本体のインストールは初回だけ手動です。その後のCTF環境構築・起動は起動ファイルから行えます。
