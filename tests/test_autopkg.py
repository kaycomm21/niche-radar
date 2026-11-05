import json

from radar import __main__ as cli, autopkg, config

PKG = {"titles": ["T1", "T2", "T3", "T4", "T5"], "thumbnail_texts": ["a"], "hooks": ["h"],
       "sections": [{"name": "후킹", "broll": ["도시"], "narration": "가" * 400}, {"name": "본론", "broll": [], "narration": "나" * 2500}],
       "tags": ["t"] * 15, "fact_checks": ["숫자 [확인 필요]"], "shorts": [{"title": "s", "text": "x" * 150}], "disclaimer": "투자 권유 아님"}


def test_autopackage_writes_full_package(tmp_env, monkeypatch):
    cli.main(["demo", "--days", "1", "--date", "2026-11-04"])
    q = [{"id": "vid1", "title": "원본", "channel": "C", "group": "경제적자유구역", "recipe": "R2"}]
    (config.EXPORTS_DIR).mkdir(parents=True, exist_ok=True)
    (config.EXPORTS_DIR / "production_queue.json").write_text(json.dumps(q), encoding="utf-8")
    monkeypatch.setattr(autopkg, "gemini_json", lambda *a, **k: PKG)
    assert cli.main(["autopackage"]) == 0
    d = next((config.EXPORTS_DIR / "packages").iterdir())
    for f in ("script.md", "storyboard.json", "meta.json", "shorts.md", "factcheck.md", "titles.md", "source.json"):
        assert (d / f).exists(), f
    m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    assert m["title"] == "T1" and "투자 권유" in m["description"]
    assert cli.main(["autopackage"]) == 0            # 이미 만든 항목은 건너뜀
    assert len(list((config.EXPORTS_DIR / "packages").iterdir())) == 1


def test_autopackage_without_key(tmp_env, monkeypatch):
    (config.EXPORTS_DIR).mkdir(parents=True, exist_ok=True)
    (config.EXPORTS_DIR / "production_queue.json").write_text(json.dumps([{"id": "v", "title": "t"}]), encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert cli.main(["autopackage"]) == 5
