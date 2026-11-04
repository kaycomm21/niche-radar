import io
import json
import urllib.error

import pytest

from conftest import FIX, load
from radar import collect, config
from radar.quota import BudgetExceeded, Quota
from radar.seed import load_seed
from radar.youtube import ApiError, ChartNotFound, RealYouTube


def test_parse_duration():
    assert collect.parse_duration("PT18M42S") == 1122
    assert collect.parse_duration("PT1H2M3S") == 3723
    assert collect.parse_duration("P1DT1S") == 86401
    assert collect.parse_duration("PT45S") == 45
    assert collect.parse_duration(None) == 0


def test_detect_short():
    assert collect.detect_short(45, "아무거나", [])
    assert collect.detect_short(150, "이거 실화 #Shorts", [])
    assert not collect.detect_short(150, "3분 요약", [])
    assert not collect.detect_short(1200, "#shorts", [])


def test_seed_excludes_none_urls():
    ok, excluded = load_seed()
    assert len(ok) == 64
    reasons = " ".join(e["reason"] for e in excluded)
    assert any(e["channel"] == "Minority Mindset and Graham Stephan" for e in excluded)
    assert "검색 상위 12개" in reasons
    assert all(cid.startswith("UC") and len(cid) == 24 for cid in ok)


def test_upsert_video_from_fixture(con):
    items = load("videos_most_popular.json")["items"]
    collect.upsert_video(con, items[0], "2026-11-04")
    collect.upsert_video(con, items[1], "2026-11-04")
    rows = {r["video_id"]: dict(r) for r in con.execute("SELECT * FROM videos")}
    assert rows["AAAAAAAAAA1"]["duration_s"] == 1122 and rows["AAAAAAAAAA1"]["is_short"] == 0
    assert rows["AAAAAAAAAA2"]["is_short"] == 1 and rows["AAAAAAAAAA2"]["comments"] is None
    assert con.execute("SELECT COUNT(*) FROM video_daily").fetchone()[0] == 2


def test_quota_logs_and_stops(con):
    q = Quota(con, "2026-11-04", budget=101)
    q.spend("videos.list")
    q.spend("search.list")
    assert q.used_today() == 101
    with pytest.raises(BudgetExceeded):
        q.spend("channels.list")
    assert q.used_today() == 101
    assert q.calls_today("search.list") == 1


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_real_client_with_mocked_http(con, monkeypatch):
    seen = []

    def fake_urlopen(url, timeout=30):
        seen.append(url)
        if "chart=mostPopular" in url:
            return FakeResp((FIX / "videos_most_popular.json").read_bytes())
        if "/channels?" in url:
            return FakeResp((FIX / "channels_list.json").read_bytes())
        return FakeResp((FIX / "playlist_items.json").read_bytes())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    yt = RealYouTube("SECRET-KEY-123", Quota(con, "2026-11-04", 8000))
    items, token = yt.most_popular("25")
    assert len(items) == 2 and token == "CDIQAA"
    assert "videoCategoryId=25" in seen[0] and "regionCode=KR" in seen[0]
    assert yt.channels(["UCsJ6RuBiTVWRX156FVbeaGg"])[0]["statistics"]["subscriberCount"] == "3730000"
    assert yt.quota.used_today() == 2


def test_real_client_error_never_leaks_key(con, monkeypatch):
    def boom(url, timeout=30):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, io.BytesIO((FIX / "error_403_quota.json").read_bytes()))

    monkeypatch.setattr("urllib.request.urlopen", boom)
    yt = RealYouTube("SECRET-KEY-123", Quota(con, "2026-11-04", 8000))
    with pytest.raises(ApiError) as e:
        yt.channels(["x"])
    assert "SECRET-KEY-123" not in str(e.value) and "quotaExceeded" in str(e.value)


def test_real_client_404_is_chart_not_found(con, monkeypatch):
    def nf(url, timeout=30):
        raise urllib.error.HTTPError(url, 404, "NF", {}, io.BytesIO(b'{"error":{"errors":[{"reason":"notFound"}]}}'))

    monkeypatch.setattr("urllib.request.urlopen", nf)
    yt = RealYouTube("k", Quota(con, "2026-11-04", 8000))
    with pytest.raises(ChartNotFound):
        yt.most_popular("29")
