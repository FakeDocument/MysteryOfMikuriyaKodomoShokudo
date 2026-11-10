"""Colab外の統合テスト用に、google.colab.output.eval_js の代わりを務める。

Colabではカーネルのポートへのセッション別URLを返す。ここでは同じポートの
ローカルURLを返し、中継をそのまま試せるようにする。
"""

import re


def eval_js(script: str) -> str:
    port = re.search(r"proxyPort\((\d+)", script)
    if port is None:
        raise ValueError("proxyPort以外の呼び出しには対応していません。")
    return f"http://127.0.0.1:{port[1]}/"
