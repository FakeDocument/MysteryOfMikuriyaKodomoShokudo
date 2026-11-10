---
name: colab-maintenance
description: Colab版（`colab/` のノートブック教材と標的サービス）を変更・検証・配布するときの保守手順。章JSON・Docker版の標的サービス・Colab用の起動処理を変更したとき、Colab版の不具合を調べるとき、Colab実機で確認するときに使う。
---

# Colab版の保守手順

Colab版の経緯と決定事項は `knowledge` スキルの「オンライン版の検討」節を正本とする。ここには、変更時に何を直し、どう確かめるかだけを書く。

## 前提

- Colab版は、Docker版と同じ設定ファイル・アプリ・共有ファイルを、Colabランタイム内のuser/network namespaceで起動する。Dockerは使わない。ColabのrootはホストのネットワークをDockerデーモンが操作する権限（`CAP_NET_ADMIN`）を持たず、`dockerd` はiptablesのNATチェーンを作れずに起動に失敗する（2026-11-10にColab実機で確認）。
- 標的サービスの正本はDocker版（`docker/sushi`・`docker/portal`）。Colab用に書き換えるのは、待受アドレス、実行時の置き場、Webアプリの中継先ポートだけとし、Colab専用の設定やアプリを別に作らない。
- 配布用ノートブック `colab/MysteryOfMikuriyaKodomoShokudo-Colab.ipynb` は手で編集しない。mainへのpushを契機に `.github/workflows/colab-notebook.yml` が生成し、botがコミットする。

## ファイルの役割

| ファイル | 役割 |
| --- | --- |
| `scripts/build_colab.py` | 章JSONなどからノートブックを生成する。`--embed` で作業ツリーを埋め込んだ検証版を作る |
| `scripts/colab_assets.py` | 準備セルが教材を取得し、ランタイムへ配置する。取得対象（`SOURCE_FILES`・`SOURCE_DIRS`）と配置先（`STAGED_FILES`・`STAGED_DIRS`）を持つ |
| `colab/colab_targets.py` | 標的の配置（ホスト名とアドレス、ポート、Samba、起動するプロセス）と、Docker版の設定をColab用に書き換える処理 |
| `colab/colab_lab.py` | 調査環境の起動・停止、コマンドのラッパー、回答判定、合言葉 |
| `colab/colab_web.py` | ブラウザの別タブで標的サイトを開くための中継。`SITES` に中継するサイトを持つ |
| `colab/colab_render.py` | セル出力のHTML化と、本文・設問文中のサイトURLのリンク化 |
| `colab/checkpoints.json` | 合言葉の区切り |
| `scripts/colab_integration.sh` | Colabに近いLinuxコンテナで標的を実際に起動する統合テスト |

## 変更の種類ごとの作業

### 章JSON・回答・画像だけを変えた

- Colabで操作が変わる箇所は `$colab` で分岐する（`knowledge` の環境別JSONの項を参照）。設問IDと正解設定は環境間で共通に保つ。
- Colabのコードセルには端末がない。対話型のコマンドは、`smbclient -U 'ID%パスワード' -c '操作'` のような非対話型にする。取得先は `/content`、閲覧は `cat`。
- プレイヤーが開くサイトのURLは会話・文書などの本文に書く。表示セルが実行時にColabのセッション別URLへのリンクにする。設問文はフォームの固定文字列になり置き換えられないため、URLを書かない。リンクになるのは `colab_web.SITES` に定義したサイトだけで、コマンド例のコードブロック内のURLはリンクにしない。
- 文面だけの変更なら、テストは実行しない（プロジェクトの指示）。

### Docker版の標的サービスを変えた

設定・アプリ・共有ファイルの中身だけの変更は、Colab版にもそのまま反映される。次に当たる場合は、Colab側も合わせて直す。

| 変更 | Colab側で直す場所 |
| --- | --- |
| ホスト名・アドレス・待受ポートの追加や変更 | `colab_targets.HOSTS`・`OPEN_PORTS`、`colab_web.SITES` |
| Samba共有の追加や改名 | `colab_targets.SAMBA_SERVERS` の `shares` と、`colab_assets` の取得対象・配置先 |
| 保護共有のアカウントの変更 | `colab_targets.PORTAL_ACCOUNT`（正本は `docker/portal/Dockerfile`） |
| Webアプリが使うPythonパッケージの追加 | `colab_lab.PYTHON_PACKAGES` |
| 攻略に使うコマンドやAPTパッケージの追加 | `colab_lab.TOOLS` とAPTの導入一覧。コードセルから使うコマンドは `_register_commands` のラッパー対象にも加える |
| 新しいファイルやディレクトリを取得対象にする | `colab_assets` の `SOURCE_*`・`STAGED_*` と、ワークフローの `paths` |

- nginxの `listen` は数字のポートで書く。書き換えられない形式は変換時にエラーになる。Webアプリの中継先は、Docker版の `127.0.0.1:8000` をColab側のポートへ置き換える前提。
- Docker版の文書目録は非rootで動くが、Colab版はrootで動かす。Colabではプレイヤー自身がrootでコードを実行できるため。

### Colab用の起動処理を変えた

`colab_targets.py`・`colab_lab.py`・`colab_web.py`・`colab_assets.py` を変えたら、次の「検証」をすべて行う。

## 検証

1. 単体テスト（macOSでも動く。Linux専用の統合テストはスキップされる）

   ```sh
   uv run --no-project python -m unittest discover -s tests -v
   ```

2. 統合テスト（Docker Desktopが必要。初回はAPT導入で数分かかる）

   ```sh
   scripts/colab_integration.sh
   ```

   `python:3.12-bookworm` を `--privileged` で起動し、標的を実際に立ち上げて、Nmap、Web閲覧、Samba、Webメールと文書目録のSQLインジェクション、外向き経路がないことを確かめる。`google.colab` は `tests/stubs` のスタブで代用する。ColabのOSとパッケージの版は一致しないため、ここで通ってもColab実機での確認は省略しない。

3. Colab実機での確認（起動処理や標的を変えたとき）

   ```sh
   uv run --no-project python scripts/build_colab.py --embed --output <scratchpadのパス>/mikuriya-colab-embed.ipynb
   ```

   生成したファイルをColabの「ノートブックをアップロード」で開き、CPUランタイムで確認する。埋め込み版は未コミットの変更も含み、GitHubへ通信しない。配布用ノートブックへは出力できない。確認する項目は変更に応じて選ぶ。

   - 準備セルが完了し、合言葉で目的の章から再開できる
   - 本文や設問セルのリンクから標的サイトが別タブで開く
   - ログインが必要なサイト（社内Webメール、8080番の文書目録）で、ログイン後に別のページへ移ってもログイン状態が保たれる
   - コードセルの `nmap`・`smbclient`・`curl` が標的へ届く
   - 準備セルを再実行しても進捗が残り、古いリンクを開き直せば新しい環境へつながる

4. 結果を記録する。確認した日付と範囲を `knowledge` の該当項目と `colab/README.md` に書く。Colab実機で確認していないことは、未確認と明記する。

## 配布

- 変更をmainへpushまたはマージすると、ワークフローがテストと生成を行い、botが `.ipynb` をコミットする。生成元のコミットSHAが教材の取得先として固定される。
- 手元で配布用と同じ形式を生成する場合は `scripts/build_colab.py --output <パス>` を使う。取得対象のファイルに未コミットの変更があると停止する。
- 新しいファイルを取得対象に加えたときは、ワークフローの `paths` にも加える。加えないと、そのファイルだけを変えたときにノートブックが再生成されず、古いコミットを取得し続ける。

## 不具合を調べるとき

- 準備セルで止まる：ランタイムの `/content/mikuriya-colab/` の `install.log`（APT・pip）、`startup.log`（標的プロセス）、`nginx.log`、`samba-*/samba.log` を見る。
- サイトが502になる：中継は動いているが、標的に届いていない。準備セルを再実行する。
- サイトの表示やリダイレクトがおかしい：Docker版でも再現するかを先に確かめる。Colabだけで起きるなら `colab_web.py` の中継（ヘッダーの引き継ぎ、`Location` の書き換え）を疑う。
