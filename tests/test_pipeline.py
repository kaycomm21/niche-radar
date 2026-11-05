import json
from datetime import date, timedelta

from radar import __main__ as cli, collect, config, export
from radar.db import connect
from radar.quota import Quota
from radar.seed import load_seed
from radar.youtube import FakeYouTube


def test_fixture_pipeline_end_to_end(tmp_env):
    assert cli.main(["demo", "--days", "10", "--date", "2026-11-04"]) == 0
    web = config.WEB_DATA_DIR
    for f in ("summary.json", "queue.json", "charts.json", "rankings.json", "surging.json"):
        assert (web / f).exists(), f
    s = json.loads((web / "summary.json").read_text(encoding="utf-8"))
    assert s["counts"]["channels_seed"] == 64
    assert s["quota"]["today"] <= config.QUOTA_BUDGET
    q = json.loads((web / "queue.json").read_text(encoding="utf-8"))
    assert 1 <= len(q["top3"]) <= 3
    assert all(c["lb"] and not c["sc"]["excluded"] for c in q["top3"])
    charts = json.loads((web / "charts.json").read_text(encoding="utf-8"))
    assert charts["charts"]["0"]["long"] or charts["charts"]["0"]["short"]
    some = next((web / "channels").glob("*.json"))
    ch = json.loads(some.read_text(encoding="utf-8"))
    assert ch["fc_subs"] is not None and len(ch["hist"]) == 10   # 10일 히스토리 → Holt 예측 가능
    # 모든 API 호출이 quota_log 에 기록됨
    con = connect(config.DB_PATH)
    assert con.execute("SELECT COUNT(DISTINCT date) FROM quota_log").fetchone()[0] == 10


def test_budget_stop_is_graceful(tmp_env):
    seed, _ = load_seed()
    con = connect(config.DB_PATH)
    d = date(2026, 11, 4)
    q = Quota(con, d.isoformat(), budget=30)
    stats = collect.run_daily(con, FakeYouTube(q, d, seed), q, seed, d.isoformat())
    assert stats["stopped_by_budget"] and stats["units_used"] <= 30


def test_verdict_removes_card(tmp_env):
    cli.main(["demo", "--days", "3", "--date", "2026-11-04"])
    q = json.loads((config.WEB_DATA_DIR / "queue.json").read_text(encoding="utf-8"))
    vid = q["top3"][0]["id"]
    assert cli.main(["verdict", "--id", vid, "--action", "queue", "--title", "t", "--issue", "1"]) == 0
    con = connect(config.DB_PATH)
    export.build(con, "2026-11-04")
    q2 = json.loads((config.WEB_DATA_DIR / "queue.json").read_text(encoding="utf-8"))
    assert vid not in [c["id"] for c in q2["top3"] + q2["pending"]]
    pq = json.loads((config.EXPORTS_DIR / "production_queue.json").read_text(encoding="utf-8"))
    assert pq[0]["id"] == vid


def test_cards_auto_archive_after_7_days(tmp_env):
    cli.main(["demo", "--days", "2", "--date", "2026-11-04"])
    q = json.loads((config.WEB_DATA_DIR / "queue.json").read_text(encoding="utf-8"))
    vid = q["top3"][0]["id"]
    state = json.loads((config.DB_PATH.parent / "cards_state.json").read_text(encoding="utf-8"))
    state[vid] = (date(2026, 11, 4) - timedelta(days=8)).isoformat()
    (config.DB_PATH.parent / "cards_state.json").write_text(json.dumps(state), encoding="utf-8")
    export.build(connect(config.DB_PATH), "2026-11-04")
    q2 = json.loads((config.WEB_DATA_DIR / "queue.json").read_text(encoding="utf-8"))
    assert vid in [c["id"] for c in q2["archived"]]
    assert vid not in [c["id"] for c in q2["top3"] + q2["pending"]]


def test_quota_plan_2000_channels_under_budget():
    assert cli.quota_plan(2000)["total"] <= config.QUOTA_BUDGET


def test_verdict_from_issue_body(tmp_env, monkeypatch):
    body = '<!-- radar-verdict: x -->\n```json\n{"action":"hold","id":"vid123","title":"T","channel":"C","group":"G","recipe":"R1"}\n```\n\n메모: 나중에'
    monkeypatch.setenv("ISSUE_BODY", body)
    assert cli.main(["verdict-from-issue", "--number", "7"]) == 0
    v = json.loads((config.EXPORTS_DIR / "verdicts.json").read_text(encoding="utf-8"))
    assert v["vid123"]["action"] == "hold" and v["vid123"]["issue"] == "7" and v["vid123"]["note"] == "나중에"
    monkeypatch.setenv("ISSUE_BODY", "그냥 이슈")
    assert cli.main(["verdict-from-issue", "--number", "8"]) == 3


def test_exclude_channel_deactivates(tmp_env):
    from radar.seed import load_seed
    seed, _ = load_seed()
    cid = next(iter(seed))
    cli.main(["verdict", "--id", cid, "--action", "exclude_channel", "--title", "x"])
    cli.main(["demo", "--days", "1", "--date", "2026-11-04"])
    con = connect(config.DB_PATH)
    # 시드 채널도 제외 판정이 우선 (sync_seed 이후 apply_exclusions)
    assert con.execute("SELECT active FROM channels WHERE channel_id=?", (cid,)).fetchone()[0] == 0


def test_alert_dedup(tmp_env):
    cli.main(["demo", "--days", "5", "--date", "2026-11-04"])
    out = config.DB_PATH.parent / "a.md"
    cli.main(["alert", "--out", str(out)])
    first = out.read_text(encoding="utf-8") if out.exists() else ""
    if out.exists():
        out.unlink()
    cli.main(["alert", "--out", str(out)])
    assert not out.exists()          # 같은 영상은 두 번 알리지 않음
    assert first == "" or "레퍼런스 채널" in first


def test_trends_and_weekly(tmp_env):
    cli.main(["demo", "--days", "10", "--date", "2026-11-04"])
    tr = json.loads((config.WEB_DATA_DIR / "trends.json").read_text(encoding="utf-8"))
    assert tr["frequent"] and tr["has_prev"]
    out = config.DB_PATH.parent / "w.md"
    assert cli.main(["weekly", "--out", str(out)]) == 0
    md = out.read_text(encoding="utf-8")
    assert "터진 것 5" in md and "뜨는 키워드 5" in md and "피할 것 1" in md


def test_ppl_estimate_present(tmp_env):
    cli.main(["demo", "--days", "2", "--date", "2026-11-04"])
    ch = json.loads(next((config.WEB_DATA_DIR / "channels").glob("*.json")).read_text(encoding="utf-8"))
    assert "ppl" in ch["f"]


def test_calibrate_report(tmp_env):
    cli.main(["demo", "--days", "5", "--date", "2026-11-04"])
    out = config.DB_PATH.parent / "c.md"
    assert cli.main(["calibrate", "--date", "2026-11-04", "--out", str(out)]) == 0
    md = out.read_text(encoding="utf-8")
    assert "급상승 배수 기준" in md and "수집 중단 후보" in md


def test_channel_detail_extras_and_search_index(tmp_env):
    cli.main(["demo", "--days", "4", "--date", "2026-11-04"])
    ch = json.loads(next((config.WEB_DATA_DIR / "channels").glob("*.json")).read_text(encoding="utf-8"))
    for k in ("ranks", "daily", "video_stats", "perf", "similar", "rev_year", "top_videos"):
        assert k in ch, k
    assert ch["daily"] and "ds" in ch["daily"][0]
    idx = json.loads((config.WEB_DATA_DIR / "search.json").read_text(encoding="utf-8"))
    assert len(idx) >= 64 and len(idx[0]) == 5


def test_add_channel_by_handle_and_id(tmp_env):
    from radar.addchannel import parse_query
    assert parse_query("https://www.youtube.com/@syukaworld") == ("handle", "@syukaworld")
    assert parse_query("https://www.youtube.com/channel/UCsJ6RuBiTVWRX156FVbeaGg")[0] == "id"
    assert parse_query("슈카월드") == ("name", "슈카월드")
    cli.main(["demo", "--days", "1", "--date", "2026-11-04"])
    con = connect(config.DB_PATH)
    cid = con.execute("SELECT channel_id FROM channels WHERE source='chart' LIMIT 1").fetchone()[0]
    assert cli.main(["add-channel", "--q", "@h" + cid[2:13].lower(), "--fixture"]) == 0
    con = connect(config.DB_PATH)
    assert con.execute("SELECT source FROM channels WHERE channel_id=?", (cid,)).fetchone()[0] == "manual"
    assert cli.main(["add-channel", "--q", "@nonexistent", "--fixture"]) == 4
