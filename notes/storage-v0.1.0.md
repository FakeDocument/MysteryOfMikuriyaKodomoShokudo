# v0.1.0 配布容量の調査

2026-10-18にGitHub Releasesの配布ファイルを実際に取得し、gzipを読み切ってtar内のレイヤーを集計した。GBは10進（1 GB = 1,000,000,000 bytes）。

| 対象 | Windows x64（amd64） | Apple Silicon Mac（arm64） |
| --- | ---: | ---: |
| ダウンロードする環境アーカイブ | 827,846,314 bytes（約828 MB） | 800,905,497 bytes（約801 MB） |
| 重複を除いたレイヤーtar合計 | 2,241,411,584 bytes（約2.24 GB） | 2,306,803,712 bytes（約2.31 GB） |
| 4イメージのレイヤーtarを個別に合計 | 2,404,042,752 bytes | 2,489,301,504 bytes |
| 起動用ZIP | 16,198 bytes | 15,660 bytes |

レイヤーtar合計は、配布アーカイブの `manifest.json` が参照する `Layers` の集合を作り、同じレイヤーを一度だけ数えたもの。tarのヘッダー等を含む非圧縮データ量であり、OS上の実占有容量・Docker仮想ディスクの増分そのものではない。Dockerの管理データ、ファイルシステムの割り当て、保存方式によって差が出る。

アーカイブのSHA-256：

- amd64: `be79885ef759b53e2c268198ba7b390725c844b28211b95a66278fa99ba1c689`
- arm64: `03a7b2264b784121c26d3700aa73fd1ae15c437afa5a0858f044fa0c7d7ef2b2`

別途必要になるもの：

- Docker Desktop本体とDockerの実行・管理領域。
- 初回ダウンロード中の約0.8 GBの圧縮ファイル。ランチャーは `docker load` 成功後にこれを削除する。
- `docker load` 中の一時領域。配布物を手動でtarへ展開する処理はランチャーにはないが、Docker内部で使う一時領域のピークは今回未測定。
- 起動後のコンテナ書き込み、ログ、調査ノートの進捗。

参考として、既存の開発環境（macOS上のDocker Engine 29.1.3、classic overlay2、4サービス稼働中）では、CTFコンテナの書き込み層合計は197,418,093 bytes、調査ノートの `/data` は56 KiBだった。これは過去の開発用イメージ・利用状態に対する観測であり、初回セットアップの実測としては扱わない。

20 GBは実測から導いた最低必要容量ではないため、READMEの記載を実測可能な配布サイズと非圧縮データ量に改める。Windows/macOSのクリーン環境におけるDocker Desktop導入から初回起動までのディスク増分・ピーク使用量は未測定で、最低空き容量は確定しない。

参照： [配布リリース](https://github.com/FakeDocument/MysteryOfMikuriyaKodomoShokudo/releases/tag/v0.1.0)、[Dockerの保存方式](https://docs.docker.com/desktop/features/containerd/)、[Macの仮想ディスク容量表示](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/macfaqs/)。
