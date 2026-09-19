# 調査ノートの文章・正解データ

調査ノートの文面は、HTMLやPythonを編集せず、このフォルダのJSONだけで変更できます。

## 章ファイル

プレイヤーへ表示する内容は`chapters/`へ章ごとに分けています。表示順は`chapters/manifest.json`の`chapter_files`で管理します。

```text
chapters/
├── manifest.json
├── prologue.json
├── chapter-1.json
├── chapter-2.json
├── chapter-3.json
├── chapter-4.json
└── finale.json
```

各章の`blocks`配列が、ノート上の表示順をそのまま表します。利用できるブロックは次のとおりです。

- `dialogue`: 所長と主人公の会話。`messages`の順に吹き出しを表示
- `document`: 依頼書などの文書
- `evidence_note`: 全章で内容を共有する、自由記述の調査メモ
- `questions`: 設問カードのまとまり
- `report`: 正答後に表示する、項目と結論を持つ調査報告書

## Markdown

章本文では、次のMarkdownを使用できます。HTMLは文字として表示され、タグとしては実行されません。プレイヤーが入力する証拠メモはプレーンテキストとして保存します。

- `**重要な証拠**`: 太字
- `` `nmap -sV` ``: 文中のコード
- 行頭と行末を `` ``` `` で囲む: コードブロック。開始側には `` ```sh `` のように言語名も付けられます
- 空行: 段落の区切り

コードブロックは`messages[].text`、`document.content.body[]`、`hints.items[]`で使用できます。章の`objective`・`lead`、設問の`prompt`、報告書の`conclusion`では太字と文中コードを使用できます。

````json
{
  "speaker": "director",
  "text": "まず **開いているポート** を確認しよう。\n\n```sh\nnmap -sV 172.30.0.10\n```"
}
````

`questions.items`の各`question`も`blocks`を持ち、次の子ブロックを順番に表示できます。

- `hints`: 所長の付箋
- `dialogue`: その設問の調査結果を受けての会話

章を開いた時から見せる会話は、表示したい位置へ条件なしの`dialogue`を置きます。依頼書より前へ置けば依頼書前に、後ろへ置けば読後に表示されます。調査メモの保存は会話や章の進行条件にしません。特定の設問進捗後だけ会話を見せる場合は、ブロックへ`visible_when`を付けます。

設問内の正解後会話には`{"event": "question_solved"}`を使います。

1件以上の設問がすべて正解した後に章直下の会話や次の設問節を表示する場合は、`questions_solved`と同じ章にある設問IDを指定します。条件が付いたブロックは、指定した設問がすべて解けるまでAPIの応答にも含まれません。

```json
{
  "type": "dialogue",
  "id": "after-scan",
  "visible_when": {
    "event": "questions_solved",
    "question_ids": ["web_service", "file_service"]
  },
  "heading": {
    "kicker": "NEXT STEP",
    "title": "次の調査へ"
  },
  "messages": [
    { "speaker": "director", "text": "次の調査へ進みましょう。" }
  ]
}
```

次の設問をまだ見せたくない場合は、後続の`questions`ブロックにも同じ条件を付けます。

```json
{
  "type": "questions",
  "id": "next-investigation",
  "visible_when": {
    "event": "questions_solved",
    "question_ids": ["web_service", "file_service"]
  },
  "heading": {
    "number": "04",
    "kicker": "NEXT STEP",
    "title": "次の調査結果を記録する"
  },
  "items": [
    {
      "type": "question",
      "id": "next_question",
      "label": "調査 03",
      "prompt": "次に見つけたものは？",
      "placeholder": "調査結果",
      "input_mode": "text",
      "blocks": []
    }
  ]
}
```

通常の設問は`placeholder`と`input_mode`で1つの回答欄を定義します。複数の値を分けて入力させる設問では、代わりに2件以上の`answer_fields`を指定できます。各欄の値は表示順に区切って結合され、`answers.json`の正解と照合されます。

```json
{
  "type": "question",
  "id": "example_port_service",
  "label": "調査 01",
  "prompt": "open の行を記録してください。",
  "answer_fields": [
    {
      "id": "port",
      "label": "ポート番号",
      "placeholder": "例: 80",
      "input_mode": "numeric"
    },
    {
      "id": "service",
      "label": "サービス名",
      "placeholder": "例: http",
      "input_mode": "latin"
    }
  ],
  "blocks": []
}
```

セリフの`speaker`は次のどちらかです。

- `director`: 所長。画面左側に表示
- `player`: 主人公（あなた）。画面右側に表示

セリフの吹き出しから別画面を開かせる場合は、メッセージへ任意の`link`を追加できます。リンクは新しいタブで開き、`href`には`http`または`https`の完全なURLを指定します。

```json
{
  "speaker": "director",
  "text": "調査用の端末です。",
  "link": {
    "label": "調査端末を開く",
    "href": "http://127.0.0.1:6901/vnc.html?autoconnect=true&reconnect=true&reconnect_delay=5000"
  }
}
```

操作説明の画像を吹き出しへ添える場合は、メッセージへ任意の`image`を追加できます。`src`は`/static/images/`配下のPNG・JPEG・WebP、`alt`は画像の内容を説明する代替テキスト、`caption`は任意の画像説明です。画像はクリックすると原寸で開きます。

```json
{
  "speaker": "director",
  "text": "赤丸のアイコンをクリックしてください。",
  "image": {
    "src": "/static/images/tutorial-terminal.png",
    "alt": "調査端末のターミナルアイコンが赤丸で囲まれている。",
    "caption": "赤丸で囲んだアイコンがターミナルです。"
  }
}
```

## `answers.json`

ブラウザへ送らない正解と判定方法を管理します。キーは各章ファイルの設問IDと一致させます。

判定方法は次の3種類です。

- 省略または`one_of`: `accepted`のどれかと一致。大文字・小文字、全角・半角、空白を正規化
- `exact`: `accepted`のどれかと完全一致。パスワードなど、大文字・小文字を区別する回答向け
- `contains_all`: `required_terms`の語をすべて含めば正解。文章で答える推理問題向け

不正解時の専用メッセージが必要な場合は`incorrect_message`を追加します。

## 編集時の注意

- JSONでは末尾のカンマとコメントを使用できません。
- 章の追加・削除・並べ替え時は`manifest.json`も更新します。
- 設問IDと章IDは重複できません。
- 設問を追加した場合、`answers.json`にも同じIDの正解設定が必要です。
- 正解や判定項目を章ファイルへ書くと、起動時にエラーになります。
- Markdown内へHTMLを書いてもHTML要素としては表示されません。
- 編集内容の反映にはnotebookイメージの再ビルドと再起動が必要です。

データだけを検証する場合は、`docker/notebook`で次を実行します。

```sh
./.venv/bin/python -m app.content
```

正常な場合は、章数・設問数とともに`OK`が表示されます。JSONの構文や対応関係に問題がある場合は、対象ファイルと理由が表示されます。
