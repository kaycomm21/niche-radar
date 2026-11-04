import io
import json

from radar import __main__ as cli, ai, config
from radar.db import connect


class R(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_no_keys_is_noop(tmp_env, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    con = connect(":memory:")
    assert ai.gemini_fit(con, "2026-11-04", [{"video_id": "x", "title": "t"}]) == 0
    assert ai.brave_buzz(con, "2026-11-04", [("x", "q")]) == {}


def test_enrich_end_to_end_with_mocks(tmp_env, monkeypatch):
    cli.main(["demo", "--days", "3", "--date", "2026-11-04"])
    monkeypatch.setenv("GEMINI_API_KEY", "GKEY-SECRET")
    monkeypatch.setenv("BRAVE_API_KEY", "BKEY-SECRET")
    monkeypatch.setattr(ai, "GEMINI_DAILY_CAP", 5)
    seen = []

    def fake(req, timeout=30):
        url = req.full_url if hasattr(req, "full_url") else req
        seen.append(url)
        if "generativelanguage" in url:
            body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"group": "경제적자유구역", "fit": 17, "angle": "a", "reason": "r"})}]}}]}
        else:
            body = {"web": {"results": [{}] * 12}}
        return R(json.dumps(body).encode())
    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert cli.main(["enrich", "--date", "2026-11-04"]) == 0
    con = connect(config.DB_PATH)
    assert con.execute("SELECT COUNT(*) FROM ai_teardown").fetchone()[0] >= 5
    assert con.execute("SELECT SUM(calls) FROM quota_log WHERE endpoint='gemini'").fetchone()[0] == 5   # 하루 상한
    q = json.loads((config.WEB_DATA_DIR / "queue.json").read_text(encoding="utf-8"))
    scored = [c for c in q["top3"] + q["pending"] if c["sc"]["parts"]["fit"] is not None]
    assert scored and scored[0]["sc"]["max"] == 100
    assert any("issue" in c["lb"] for c in q["top3"] + q["pending"])


def test_gemini_error_does_not_leak_key(tmp_env, monkeypatch, capsys):
    import urllib.error
    monkeypatch.setenv("GEMINI_API_KEY", "GKEY-SECRET")
    def boom(req, timeout=30):
        raise urllib.error.HTTPError(req.full_url, 403, "x", {}, io.BytesIO(b"{}"))
    monkeypatch.setattr("urllib.request.urlopen", boom)
    con = connect(":memory:")
    ai.gemini_fit(con, "2026-11-04", [{"video_id": "v1", "title": "t"}])
    assert "GKEY-SECRET" not in capsys.readouterr().out


def test_search_query_cleanup():
    assert ai.search_query('머스크가 [단독] 장악했다! #삼성 "GPU" 120만 개') == "머스크가 장악했다 GPU 120만 개"
