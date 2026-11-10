#!/bin/sh
# Colab版の標的サービスを、Colabに近いLinuxコンテナで実際に起動して統合テストする。
# user/network namespaceを作るため、--privileged で実行する。
# google.colab はColab外に無いため、中継URLを返すスタブを使う。
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
IMAGE=${COLAB_INTEGRATION_IMAGE:-python:3.12-bookworm}

if [ "${1:-}" != "--inside" ]; then
    exec docker run --rm --privileged \
        -v "$ROOT":/src:ro \
        -e PYTHONPATH=/src/tests/stubs \
        -e PYTHONDONTWRITEBYTECODE=1 \
        "$IMAGE" sh /src/scripts/colab_integration.sh --inside
fi

python3 - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, "/src/scripts")
import colab_assets

colab_assets.prepare_from_source(Path("/src"), Path("/lab"))
sys.path.insert(0, "/lab")
from colab_lab import Lab

Lab(Path("/lab")).install_tools()
PY
cd /src
MIKURIYA_COLAB_INTEGRATION_ROOT=/lab python3 -m unittest tests.test_colab_integration -v
