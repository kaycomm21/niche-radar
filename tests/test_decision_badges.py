from radar.metrics import decision_badges

BASE = {"views": 200_000, "likes": 4_000, "comments": 1_000, "rpm_lo": 2000, "rpm_hi": 5000,
        "labels": [], "category_id": "22", "age_days": 3, "channel_median": 30_000}


def test_small_hit_and_revenue():
    d = decision_badges({**BASE, "subs": 40_000, "multiple": 6.0}, 50_000, None, "2026-11-06")
    assert d["tier"] == "small_hit"
    assert d["ratio"] == 5.0
    assert d["rev"] == [100_000, 250_000]
    assert d["eng"] == 0.025


def test_tiers():
    assert decision_badges({**BASE, "subs": 50_000, "multiple": 1.0}, None, None, "2026-11-06")["tier"] == "small"
    assert decision_badges({**BASE, "subs": 200_000}, None, None, "2026-11-06")["tier"] == "mid"
    assert decision_badges({**BASE, "subs": 500_000}, None, None, "2026-11-06")["tier"] == "big"


def test_golden_and_archive():
    d = decision_badges({**BASE, "subs": 1, "labels": ["issue"], "age_days": 1}, None, "2026-11-02", "2026-11-06")
    assert d["golden_h"] == 24
    assert d["archive_d"] == 3
    assert decision_badges({**BASE, "subs": 1, "labels": ["issue"], "age_days": 5}, None, None, "2026-11-06")["golden_h"] == 0
    assert decision_badges({**BASE, "subs": 1}, None, None, "2026-11-06")["golden_h"] is None   # 에버그린


def test_missing_values_safe():
    d = decision_badges({**BASE, "subs": None, "views": None, "likes": None, "comments": None}, None, "bad-date", "2026-11-06")
    assert d["tier"] is None and d["ratio"] is None and d["eng"] is None and d["archive_d"] is None
    assert d["rev"] == [60_000, 150_000]   # 기준 조회 = 원 채널 중앙값 3만
