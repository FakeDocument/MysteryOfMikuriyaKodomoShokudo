"""共通項目と実行環境別の上書きを検証する。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docker/notebook"))

from app.block_variants import resolve_environment


class EnvironmentSelectionTests(unittest.TestCase):
    def test_共通項目を残して対象環境の項目を追加する(self) -> None:
        value = {
            "common": "共通する値",
            "$colab": {"bar": "colab"},
            "$local": {"bar": "local"},
        }
        self.assertEqual(
            resolve_environment(value, "$colab"),
            {"common": "共通する値", "bar": "colab"},
        )
        self.assertEqual(
            resolve_environment(value, "$local"),
            {"common": "共通する値", "bar": "local"},
        )

    def test_共通項目と同じ対象項目が存在する時上書きする(self) -> None:
        value = {
            "env": "common",
            "$colab": {"env": "colab"},
        }
        self.assertEqual(
            resolve_environment(value, "$colab"),
            {
                "env": "colab",
            },
        )

    def test_配列内や入れ子のオブジェクトも解決する(self) -> None:
        value = {
            "messages": [
                {"text": "共通"},
                {"$colab": {"text": "セル"}, "$local": {"text": "端末"}},
            ]
        }
        self.assertEqual(
            resolve_environment(value, "$colab"),
            {
                "messages": [
                    {"text": "共通"},
                    {"text": "セル"},
                ]
            },
        )

    def test_対象環境の指定がなければ共通値を使う(self) -> None:
        value = {"bar": "common", "$colab": {"bar": "colab"}}
        self.assertEqual(resolve_environment(value, "$local"), {"bar": "common"})

    def test_通常のlocalとcolabキーは共通項目として保持する(self) -> None:
        value = {"local": "通常の値", "colab": "通常の値"}
        self.assertEqual(resolve_environment(value, "$colab"), value)


if __name__ == "__main__":
    unittest.main()
