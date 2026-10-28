# Colab実行の試作

「御厨こども食堂の謎」の第1章から、標的の起動、Nmapによる調査、ポート調査2問の回答判定、正解後の会話を試すノートブック。

2026-10-28にColabのCPUランタイムで起動から回答・会話表示・進捗ファイルの復元まで確認済み。[検証結果](verification.md)を参照。

## 試し方

1. [Colabで試作を開く](https://colab.research.google.com/github/FakeDocument/MysteryOfMikuriyaKodomoShokudo/blob/main/experiments/colab/MysteryOfMikuriyaKodomoShokudo-Colab.ipynb)。
2. Googleアカウントでログインする。
3. CPUランタイムで「調査環境を準備する」を実行する。
4. コマンドセルでNmapを実行し、結果を回答フォームに記録する。
5. 中断時は必要に応じて進捗JSONをダウンロードし、「調査環境を停止する」を実行する。

同じランタイム内では、準備セルを再実行しても進捗を保持する。ランタイム削除後は、準備セルを実行してから保存済みの進捗JSONを読み込む。

配布用の[ノートブック本体](MysteryOfMikuriyaKodomoShokudo-Colab.ipynb)は、このリポジトリで管理する。ColabのGitHub連携で開くURLは[Google Colab公式の説明](https://github.com/googlecolab/open_in_colab)に基づく。ダウンロードしたファイルは、Colabの「ノートブックをアップロード」からも開ける。

## 構成

- ノートブック内にPythonの起動処理、既存の寿司屋サイト・Samba共有、最初の設問と回答設定をZIPで同梱する。
- 初回にAPTでNginx、Samba、Nmapなどを導入する。導入時のサービス自動起動は抑止する。
- 標的サービスは専用のuser/network namespaceで動作する。外向きの経路は作成せず、既存と同じ `172.30.0.10` の80・445番を使用する。
- コマンドセルの `nmap`・`curl`・`smbclient` は、ラッパーから同じネットワークへ入り、実際のバイナリを実行する。Nmapの出力を合成しない。
- Sambaが標準入力のEOFで終了しないよう、監督プロセスが入力パイプを保持する。起動処理の再実行時と停止時には、その環境が作成したプロセスを回収する。
- 掛け合い・設問・正解の正本は既存の章JSONと回答JSONとし、生成時に取り込む。

ファイルシステムはColabカーネルと共有する。ネットワークの分離を検証する試作であり、コンテナと同等の隔離は提供しない。ランタイムにはプレイヤー自身がコードを実行でき、正解データも読み取れる。

今回の移植範囲は第1章のポート調査部分。政府側サービス、Webメール、DIRBを含む後続の攻略導線と、Webページをノートブック内で閲覧する方法は今後の検証対象とする。

Colabのランタイムや導入パッケージは提供側の更新で変わる。この試作では、APTパッケージのバージョンは固定していない。利用制限は[Colab公式FAQ](https://research.google.com/colaboratory/faq.html)を参照する。

## 開発時の生成・検証

起動処理・教材データを更新したら、次のコマンドでノートブックを再生成し、生成済みの `.ipynb` も一緒にコミットする。配布用ファイルは回答欄と実行出力を空にした状態にする。

```sh
uv run --no-project python scripts/build_colab.py
uv run --no-project python -m unittest discover -s tests -v
```

実サービスの統合テストは、ノートブックの準備が完了した専用Linux環境で実行する。`MIKURIYA_COLAB_INTEGRATION_ROOT` には展開済みの教材ディレクトリを指定する。通常のテスト実行ではこの統合テストをスキップする。

```sh
MIKURIYA_COLAB_INTEGRATION_ROOT=/content/mikuriya-colab python -m unittest discover -s tests -p test_colab_integration.py -v
```
