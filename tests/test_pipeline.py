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
