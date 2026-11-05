import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture
def con():
    from radar.db import connect
    return connect(":memory:")


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    from radar import config
    monkeypatch.setattr(config, "WEB_DATA_DIR", tmp_path / "web")
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path / "exports")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "radar.db")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_MIN_INTERVAL", "0")
    return tmp_path
