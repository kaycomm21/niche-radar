import json
from datetime import date

from radar import __main__ as cli, bids, config


def test_score_and_build():
    t = date(2026, 11, 5)
    items = bids.build(bids.fixture(t), t)
    top = items[0]
    assert "불빛축제" in top["name"] or "체육대회" in top["name"]
    assert top["parts"]["region"] == 25 and top["parts"]["method"] == 20 and top["matches"]
    assert items[-1]["name"].startswith("청사")          # 무관 공고는 최하위
    assert all(x["dleft"] >= 0 for x in items)


def test_bids_run_and_proposal_from_queue(tmp_env, monkeypatch):
    monkeypatch.delenv("DATA_GO_KR_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GCP_SA_KEY", raising=False)
    assert cli.main(["bids", "--date", "2026-11-05"]) == 0
    d = json.loads((config.WEB_DATA_DIR / "bids.json").read_text(encoding="utf-8"))
    assert d["mode"] == "fixture" and d["count"] == 4
    no = d["items"][0]["no"]
    cli.main(["verdict", "--id", f"bid:{no}", "--action", "queue", "--title", d["items"][0]["name"], "--issue", "1"])
    assert cli.main(["proposals"]) == 0
    p = next((config.EXPORTS_DIR / "proposals").glob("*/proposal.md")).read_text(encoding="utf-8")
    assert "제안서 목차" in p and "유사 실적" in p
    cli.main(["proposals"])                                 # 중복 생성 안 함
    assert len(list((config.EXPORTS_DIR / "proposals").iterdir())) == 1


def test_region_not_fooled_by_haeundae():
    t = date(2026, 11, 5)
    it = {"bidNtceNo": "1", "bidNtceNm": "공연", "ntceInsttNm": "부산광역시 해운대구", "asignBdgtAmt": "100000000", "cntrctCnclsMthdNm": "협상에 의한 계약"}
    assert bids.score(it, t, {})["parts"]["region"] == 10
    it["ntceInsttNm"] = "대구광역시 달성군"
    assert bids.score(it, t, {})["parts"]["region"] == 25
