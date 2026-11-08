"""JSONの共通項目へ、対象環境の項目を上書きする。"""

from typing import Any


def resolve_environment(value: Any, environment: str) -> Any:
    """配列・オブジェクトをたどり、共通項目へ環境別の項目を重ねる。"""
    if isinstance(value, list):
        return [resolve_environment(item, environment) for item in value]
    if isinstance(value, dict):
        return {
            key: resolve_environment(item, environment)
            for key, item in {**value, **value.get(environment, {})}.items()
            if key not in {"$local", "$colab"}
        }
    return value
