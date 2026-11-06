import pytest

from radar import metrics as M


def test_median_and_outlier():
    assert M.median([1, 3, None, 2]) == 2
    assert M.median([]) is None
    assert M.outlier_multiple(3000, 1000) == 3
    assert M.outlier_multiple(3_816_649, 68.5) is None      # 평소 조회 1,000 미만 채널 → 배수 잡음 제외
    assert M.surge_rank(20, 1_000_000) > M.surge_rank(20, 20_000)
    assert M.outlier_multiple(300, 0) is None


def test_labels():
    base = {"multiple": 3.2, "views": 50000, "duration_s": 900, "is_short": 0, "rpm_hi": 6000, "age_days": 5}
    assert set(M.labels(base)) == {"fire", "money"}
    assert M.labels({**base, "multiple": 1.5}) == []
    assert M.labels({**base, "multiple": 1.0, "chart_within_7d": True}) == ["fire"]
    assert "money" not in M.labels({**base, "is_short": 1})
    assert "money" not in M.labels({**base, "duration_s": 300})
    assert "issue" in M.labels({"views_24h_pct": 0.97, "comments_24h_growth": 0.2})


def test_rework_score_reuse_excluded():
    s = M.rework_score({"title": "드라마 명장면 하이라이트 모음", "multiple": 20})
    assert s["excluded"] and s["total"] == 0 and s["parts"]["policy"] == 0


def test_rework_score_parts():
    s = M.rework_score({"title": "로마 제국이 망한 진짜 이유", "multiple": 10, "rpm_hi": 6000, "duration_s": 900,
                        "category_id": "27", "group": "히스토리X"})
    assert s["parts"]["burst"] == 20 and s["parts"]["money"] == 20 and s["parts"]["fit"] is None
    assert s["parts"]["life"] == 10 and s["parts"]["policy"] == 10 and s["max"] == 80
    assert s["total"] == 20 + 20 + 13 + 10 + 10


def test_grade_letters_and_coverage():
    uni = {"growth": [0.0, 0.1, 0.2], "efficiency": [0.1, 0.2, 0.3]}
    g = M.grade({"growth": 0.2, "efficiency": 0.3, "engagement": None, "consistency": None, "outlier_freq": None}, uni)
    assert g["coverage"] == 55 and g["parts"]["engagement"] is None
    assert g["score"] == pytest.approx((30 * 5 / 6 + 25 * 5 / 6) * 100 / 55, rel=1e-3)
    assert M.grade_letter(85) == "S" and M.grade_letter(39.9) == "D"


def test_holt_linear_series():
    ys = [1000 + 10 * i for i in range(30)]
    fc = M.holt_forecast(ys)
    assert fc["trend_per_day"] == pytest.approx(10, rel=0.05)
    assert fc["forecast"]["30"] == pytest.approx(ys[-1] + 300, rel=0.01)
    assert M.holt_forecast([1, 2, 3]) is None


def test_milestone():
    assert M.milestone_days(90_000, 100, 100_000) == 100
    assert M.milestone_days(90_000, -5, 100_000) is None
    assert M.milestone_days(1, 0.001, 1_000_000) is None   # 10년 초과
    assert M.milestone_days(200_000, 1, 100_000) == 0


def test_consistency():
    assert M.upload_consistency([0, 7, 14, 21]) == 1.0
    assert M.upload_consistency([0, 1]) is None
    assert 0 < M.upload_consistency([0, 1, 20, 21]) < 1


def test_rpm_keyword_boost():
    rpm = {"25": (1500, 5000), "default": (800, 2500), "shorts": (30, 120), "kw_finance": (1.6, 1.6)}
    assert M.rpm_for(rpm, "25", "금리 전망", False, ["금리"], []) == (2400, 8000)
    assert M.rpm_for(rpm, "25", "금리 전망", True, ["금리"], []) == (30, 120)


def test_min_views_noise_floor():
    assert M.labels({"multiple": 50, "views": 900}) == []
    assert M.labels({"multiple": 3, "views": 10_000}) == ["fire"]


def test_group_ascii_word_boundary():
    from radar.collect import assign_group
    assert assign_group("software update review") is None          # 'war' 오매칭 금지
    assert assign_group("The war that ended an empire") == "히스토리X"
    assert assign_group("금리 인하 전망") == "경제적자유구역"
