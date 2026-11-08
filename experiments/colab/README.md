# Colab実行の試作

「御厨こども食堂の謎」の既存JSONから、序章〜終章の教材を生成するノートブック。会話、文書、調査メモ、設問、ヒント、報告書を扱う。

2026-10-28にColabのCPUランタイムで起動から回答・会話表示・進捗ファイルの復元まで確認済み。[検証結果](verification.md)を参照。

## 試し方

1. [Colabで試作を開く](https://colab.research.google.com/github/FakeDocument/MysteryOfMikuriyaKodomoShokudo/blob/main/experiments/colab/MysteryOfMikuriyaKodomoShokudo-Colab.ipynb)。
2. Googleアカウントでログインする。
3. CPUランタイムで「調査環境を準備する」を実行する。
4. 上から表示セルを実行して教材を読む。調査は「＋コード」で追加したセルへコマンドを入力し、結果を回答フォームへ記録する。条件付きの表示セルを先に実行した場合は、必要な設問の正解後に再実行する。
5. 中断時は必要に応じて進捗JSONをダウンロードし、「調査環境を停止する」を実行する。

同じランタイム内では、準備セルを再実行しても進捗と全章共通の調査メモを保持する。ランタイム削除後は、準備セルを実行してから保存済みの進捗JSONを読み込む。

配布用の[ノートブック本体](MysteryOfMikuriyaKodomoShokudo-Colab.ipynb)は、このリポジトリで管理する。ColabのGitHub連携で開くURLは[Google Colab公式の説明](https://github.com/googlecolab/open_in_colab)に基づく。ダウンロードしたファイルは、Colabの「ノートブックをアップロード」からも開ける。

## 構成

- 準備セルで、GitHubの固定コミットのZIPを取得し、Pythonの表示処理、寿司屋サイト・Samba共有、全章の教材・回答設定・画像をランタイムへ配置する。取得処理はPython標準ライブラリで動作する。
- 初回にAPTでNginx、Samba、Nmapなどを導入する。導入時のサービス自動起動は抑止する。
- 標的サービスは専用のuser/network namespaceで動作する。外向きの経路は作成せず、既存と同じ `172.30.0.10` の80・445番を使用する。
- コマンドセルの `nmap`・`curl`・`smbclient` は、ラッパーから同じネットワークへ入り、実際のバイナリを実行する。Nmapの出力を合成しない。
- Sambaが標準入力のEOFで終了しないよう、監督プロセスが入力パイプを保持する。起動処理の再実行時と停止時には、その環境が作成したプロセスを回収する。
- 章の読込順は既存の `manifest.json`、掛け合い・設問・正解の正本は既存の章JSONと回答JSONとし、生成時に取り込む。調査コマンドはプレイヤーが入力する。教材内のシェルコード例には `!` を付け、出力例やPythonコードはそのまま表示する。
- 正解後の掛け合いは、セルの出力に顔画像・話者名・吹き出しをHTMLで表示する。プレイヤーは右側、ほかの話者は左側に配置する。話者定義の既定表情と台詞ごとの表情指定を使い、取得した顔画像をHTML内へ埋め込む。

ファイルシステムはColabカーネルと共有する。ネットワークの分離を検証する試作であり、コンテナと同等の隔離は提供しない。ランタイムにはプレイヤー自身がコードを実行でき、正解データも読み取れる。

教材の変換対象は全章。標的環境は寿司屋のWeb・Sambaを起動する試作で、政府側サービス、Webメール、DIRBを含む後続の攻略導線は今後の検証対象とする。

標的サイトは、準備セルが起動するサイトごとの中継を通してブラウザの別タブで開く。本文中のサイトURLは、Colabがセッションごとに発行するURLへのリンクとして表示する。ランタイムが切れたら準備セルと表示セルを実行し直す。

Colabのランタイムや導入パッケージは提供側の更新で変わる。この試作では、APTパッケージのバージョンは固定していない。利用制限は[Colab公式FAQ](https://research.google.com/colaboratory/faq.html)を参照する。

## 教材の更新・検証

教材・画像・標的データ・表示用Pythonと生成処理は、通常どおり変更をmainへpushまたはマージする。`.github/workflows/colab-notebook.yml` が関連ファイルの変更を検知してテストと生成を実行し、更新した `.ipynb` だけをbotがmainへコミットする。回答欄と実行出力は空の状態で生成する。Actions画面からmainを対象に手動実行することもできる。

生成時にチェックアウトしたmainのコミットSHAを取得先として固定する。これにより、配布済みノートブックのセルと実行時に取得する教材の版を揃える。生成物の更新はトリガーの対象パスに含めず、botのpushには標準の `GITHUB_TOKEN` を使用する。mainへの書き込みが許可されている必要がある。

生成中にmainが更新されてpushに失敗した場合は、最新のmainからテスト・生成をやり直し、最大3回試行する。

開発中のテストは、未コミット変更がある状態でも実行できる。

```sh
uv run --no-project python -m unittest discover -s tests -v
```

手元で生成を確認する場合は `uv run --no-project python scripts/build_colab.py --output /tmp/mikuriya-colab.ipynb` を使う。取得先を現在のHEADに固定するため、このコマンドは教材・実行用ソースの未コミット変更を検出すると停止する。

実サービスの統合テストは、ノートブックの準備が完了した専用Linux環境で実行する。`MIKURIYA_COLAB_INTEGRATION_ROOT` には展開済みの教材ディレクトリを指定する。通常のテスト実行ではこの統合テストをスキップする。

```sh
MIKURIYA_COLAB_INTEGRATION_ROOT=/content/mikuriya-colab python -m unittest discover -s tests -p test_colab_integration.py -v
```
