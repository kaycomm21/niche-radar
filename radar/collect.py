"""일간 수집: 인기 차트 → 채널 통계 → 채널 최근 영상. 쿼터 예산 안에서 우선순위대로."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

from . import config
from .quota import BudgetExceeded, Quota

DUR = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
HANGUL = re.compile(r"[가-힣]")


def parse_duration(s: str | None) -> int:
    if not s:
        return 0
    m = DUR.fullmatch(s)
    if not m:
        return 0
    d, h, mi, se = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def detect_short(duration_s: int, title: str, tags: list[str]) -> bool:
    """쇼츠 판정 규칙: 60초 이하, 또는 180초 이하 + '#shorts' 표기 (API에 쇼츠 여부 필드가 없어서 추정)."""
    if 0 < duration_s <= 60:
        return True
    text = (title + " " + " ".join(tags)).lower()
    return 0 < duration_s <= 180 and "#short" in text


def detect_lang(title: str) -> str:
    return "ko" if HANGUL.search(title or "") else "other"


def assign_group(title: str, extra: str = "") -> str | None:
    text = (title + " " + extra).lower()
    best, hits = None, 0
    for g, kws in config.GROUP_RULES.items():
        n = sum(1 for k in kws if k.lower() in text)
        if n > hits:
            best, hits = g, n
    return best


def upsert_video(con, item: dict, today: str) -> str:
    sn, st, cd = item.get("snippet", {}), item.get("statistics", {}), item.get("contentDetails", {})
    vid = item["id"]
    tags = sn.get("tags") or []
    dur = parse_duration(cd.get("duration"))
    title = sn.get("title", "")
    thumbs = sn.get("thumbnails", {})
    thumb = (thumbs.get("medium") or thumbs.get("default") or {}).get("url")
    views, likes, comments = (int(st[k]) if st.get(k) is not None else None for k in ("viewCount", "likeCount", "commentCount"))
    con.execute(
        """INSERT INTO videos(video_id, channel_id, title, published_at, duration_s, is_short, category_id, tags, thumb, lang,
                              views, likes, comments, stats_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(video_id) DO UPDATE SET title=excluded.title, duration_s=excluded.duration_s, is_short=excluded.is_short,
             category_id=excluded.category_id, tags=excluded.tags, thumb=excluded.thumb, lang=excluded.lang,
             views=excluded.views, likes=excluded.likes, comments=excluded.comments, stats_at=excluded.stats_at""",
        (vid, sn.get("channelId"), title, sn.get("publishedAt"), dur, int(detect_short(dur, title, tags)),
         sn.get("categoryId"), json.dumps(tags[:15], ensure_ascii=False), thumb, detect_lang(title),
         views, likes, comments, today))
    # 일별 스냅샷은 업로드 30일 이내 영상만 (24시간 증가·이슈화 판정용). DB 크기를 git에 올릴 수 있는 수준으로 유지
    pub = (sn.get("publishedAt") or "")[:10]
    if pub and (date.fromisoformat(today) - date.fromisoformat(pub)).days <= 30:
        con.execute("INSERT OR REPLACE INTO video_daily(video_id, date, views, likes, comments) VALUES (?,?,?,?,?)",
                    (vid, today, views, likes, comments))
    return vid


def sync_seed(con, seed: dict[str, dict], today: str) -> int:
    n = 0
    for cid, info in seed.items():
        cur = con.execute("SELECT source FROM channels WHERE channel_id=?", (cid,)).fetchone()
        if cur is None:
            con.execute("""INSERT INTO channels(channel_id, title, "group", source, added_at, active)
                           VALUES (?,?,?,?,?,1)""", (cid, info["channel"], info["group"], "seed", today))
            n += 1
        else:  # 차트로 먼저 들어온 채널이 시드에 추가되면 시드로 승격
            con.execute("""UPDATE channels SET "group"=?, source='seed', active=1 WHERE channel_id=?""", (info["group"], cid))
    return n


def collect_charts(con, yt, today: str, stats: dict) -> None:
    from .youtube import ChartNotFound
    universe = con.execute("SELECT COUNT(*) FROM channels WHERE active=1").fetchone()[0]
    for cat in config.CHART_CATEGORIES:
        token, rank = None, {"long": 0, "short": 0}
        for _ in range(config.CHART_PAGES):
            try:
                items, token = yt.most_popular(cat, token)
            except ChartNotFound:
                stats["chart_missing"].append(cat)
                break
            for it in items:
                vid = upsert_video(con, it, today)
                is_short = con.execute("SELECT is_short FROM videos WHERE video_id=?", (vid,)).fetchone()[0]
                fmt = "short" if is_short else "long"
                rank[fmt] += 1
                con.execute("INSERT OR REPLACE INTO chart_daily(date, category_id, format, rank, video_id) VALUES (?,?,?,?,?)",
                            (today, cat, fmt, rank[fmt], vid))
                stats["chart_rows"] += 1
                cid = it["snippet"]["channelId"]
                exists = con.execute("SELECT 1 FROM channels WHERE channel_id=?", (cid,)).fetchone()
                if not exists and universe < config.UNIVERSE_CAP:
                    con.execute("""INSERT INTO channels(channel_id, title, "group", source, added_at, active)
                                   VALUES (?,?,?,?,?,1)""",
                                (cid, it["snippet"].get("channelTitle"), assign_group(it["snippet"].get("title", "")), "chart", today))
                    universe += 1
                    stats["new_chart_channels"] += 1
            if not token:
                break


def collect_channel_stats(con, yt, today: str, stats: dict) -> None:
    ids = [r[0] for r in con.execute("SELECT channel_id FROM channels WHERE active=1 ORDER BY source='seed' DESC, channel_id")]
    seen = set()
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        for it in yt.channels(batch):
            sn, st, cd = it.get("snippet", {}), it.get("statistics", {}), it.get("contentDetails", {})
            seen.add(it["id"])
            subs = None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0))
            th = sn.get("thumbnails", {})
            con.execute("""UPDATE channels SET title=?, handle=?, country=?, uploads_playlist=?, thumb=?, published_at=?, last_stats_at=?
                           WHERE channel_id=?""",
                        (sn.get("title"), sn.get("customUrl"), sn.get("country"),
                         cd.get("relatedPlaylists", {}).get("uploads"),
                         (th.get("default") or {}).get("url"), sn.get("publishedAt"), today, it["id"]))
            con.execute("INSERT OR REPLACE INTO channel_daily(channel_id, date, subs, views, videos) VALUES (?,?,?,?,?)",
                        (it["id"], today, subs, int(st.get("viewCount", 0)), int(st.get("videoCount", 0))))
            stats["channels_updated"] += 1
    missing = set(ids) - seen
    for cid in missing:   # API가 돌려주지 않은 채널(삭제·비공개) → 비활성
        con.execute("UPDATE channels SET active=0 WHERE channel_id=?", (cid,))
    stats["channels_missing"] = len(missing)


def collect_recent_videos(con, yt, today: str, stats: dict) -> None:
    rows = con.execute("""SELECT channel_id, uploads_playlist FROM channels
                          WHERE active=1 AND uploads_playlist IS NOT NULL
                          ORDER BY (source='seed') DESC, COALESCE(last_videos_at,'') ASC""").fetchall()
    pending: list[str] = []

    def flush():
        while pending:
            batch, pending[:] = pending[:50], pending[50:]
            for it in yt.videos(batch):
                upsert_video(con, it, today)
                stats["videos_updated"] += 1

    for r in rows:
        items = yt.playlist_items(r["uploads_playlist"], config.RECENT_PER_CHANNEL)
        for it in items:
            vid = it["contentDetails"]["videoId"]
            done = con.execute("SELECT 1 FROM videos WHERE video_id=? AND stats_at=?", (vid, today)).fetchone()
            if not done:
                pending.append(vid)
        con.execute("UPDATE channels SET last_videos_at=? WHERE channel_id=?", (today, r["channel_id"]))
        stats["channels_videos_fetched"] += 1
        if len(pending) >= 50:
            flush()
    flush()


def prune(con, today: str) -> dict:
    t = date.fromisoformat(today)
    snap_cut = (t - timedelta(days=config.SNAPSHOT_RETENTION_DAYS)).isoformat()
    vsnap_cut = (t - timedelta(days=config.VIDEO_SNAPSHOT_DAYS)).isoformat()
    stale_cut = (t - timedelta(days=config.STALE_DAYS)).isoformat()
    chart_cut = (t - timedelta(days=config.CHART_RETENTION_DAYS)).isoformat()
    out = {
        "channel_daily": con.execute("DELETE FROM channel_daily WHERE date < ?", (snap_cut,)).rowcount,
        "video_daily": con.execute("DELETE FROM video_daily WHERE date < ?", (vsnap_cut,)).rowcount,
        "chart_daily": con.execute("DELETE FROM chart_daily WHERE date < ?", (chart_cut,)).rowcount,
        "stale_videos": con.execute("DELETE FROM videos WHERE COALESCE(stats_at,'') < ?", (stale_cut,)).rowcount,
    }
    # 30일 갱신 못 한 비시드 채널 → 비활성 (A3 정신: 쓸모없는 수집 중단)
    # 오래된 영상 중 최근 30편 밖 + 차트 기록 없음 → 삭제 (중앙값 계산에 안 쓰임)
    out["old_videos"] = con.execute(
        """DELETE FROM videos WHERE video_id IN (
             SELECT video_id FROM (SELECT video_id, ROW_NUMBER() OVER (PARTITION BY channel_id ORDER BY published_at DESC) rn FROM videos)
             WHERE rn > ?) AND video_id NOT IN (SELECT video_id FROM chart_daily)""", (config.RECENT_PER_CHANNEL + 10,)).rowcount
    out["stale_channels"] = con.execute(
        "UPDATE channels SET active=0 WHERE source!='seed' AND active=1 AND COALESCE(last_stats_at, added_at) < ?", (stale_cut,)).rowcount
    # 차트 채널 중 최근 30일 업로드 없음 → 비활성 (기획서 M1-3: 30일 무활동 자동 제외)
    out["inactive_channels"] = con.execute(
        """UPDATE channels SET active=0 WHERE source='chart' AND active=1 AND added_at < ?
           AND channel_id NOT IN (SELECT channel_id FROM videos WHERE published_at >= ?)""", (stale_cut, stale_cut)).rowcount
    return out


def run_daily(con, yt, quota: Quota, seed: dict[str, dict], today: str) -> dict:
    stats = {"date": today, "chart_rows": 0, "chart_missing": [], "new_chart_channels": 0, "channels_updated": 0,
             "videos_updated": 0, "channels_videos_fetched": 0, "stopped_by_budget": False}
    stats["new_seed_channels"] = sync_seed(con, seed, today)
    try:
        collect_charts(con, yt, today, stats)
        collect_channel_stats(con, yt, today, stats)
        collect_recent_videos(con, yt, today, stats)
    except BudgetExceeded as e:
        stats["stopped_by_budget"] = True
        stats["budget_message"] = str(e)
    stats["pruned"] = prune(con, today)
    stats["units_used"] = quota.used_today()
    con.commit()
    return stats
