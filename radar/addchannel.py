"""🔍 채널 검색 → 즉시 분석: URL·@핸들·채널ID·이름을 받아 유니버스에 'manual'로 추가하고 바로 수집한다.

쿼터: ID·@핸들 = channels.list 1유닛 / 이름 검색 = search.list 100유닛(하루 20회 상한 공유)
"""
from __future__ import annotations

import re
import urllib.parse

from . import collect, config
from .quota import Quota

CID = re.compile(r"(UC[\w-]{22})")


def parse_query(q: str) -> tuple[str, str]:
    """→ ('id', UC…) | ('handle', '@…') | ('name', 검색어)"""
    q = q.strip()
    m = CID.search(q)
    if m:
        return "id", m.group(1)
    if "youtube.com" in q or "youtu.be" in q:
        path = urllib.parse.urlparse(q if "://" in q else "https://" + q).path
        h = re.search(r"/(@[^/?#]+)", path)
        if h:
            return "handle", urllib.parse.unquote(h.group(1))
    if q.startswith("@"):
        return "handle", q.split()[0]
    return "name", q


def resolve(yt, q: str, quota: Quota) -> str | None:
    kind, val = parse_query(q)
    if kind == "id":
        return val
    if kind == "handle":
        items = yt.channel_by_handle(val)
        return items[0]["id"] if items else None
    if quota.calls_today("search.list") >= config.SEARCH_DAILY_CAP:
        raise RuntimeError("오늘 이름 검색(search.list) 상한 도달 — URL·@핸들로 요청하세요")
    items = yt.search_channel(val)
    return items[0].get("snippet", {}).get("channelId") if items else None


def add_and_collect(con, yt, quota: Quota, q: str, today: str, group: str | None = None) -> dict:
    cid = resolve(yt, q, quota)
    if not cid:
        return {"ok": False, "reason": f"채널을 찾지 못함: {q}"}
    row = con.execute("SELECT source FROM channels WHERE channel_id=?", (cid,)).fetchone()
    if row is None:
        con.execute("""INSERT INTO channels(channel_id, "group", source, added_at, active) VALUES (?,?, 'manual', ?, 1)""", (cid, group, today))
    elif row[0] not in ("seed",):
        con.execute("""UPDATE channels SET source='manual', active=1, "group"=COALESCE(?, "group") WHERE channel_id=?""", (group, cid))
    stats = {"chart_rows": 0, "chart_missing": [], "new_chart_channels": 0, "channels_updated": 0,
             "videos_updated": 0, "channels_videos_fetched": 0}
    items = yt.channels([cid])
    if not items:
        return {"ok": False, "reason": "channels.list 결과 없음(비공개·삭제 채널?)", "channel_id": cid}
    collect.save_channel_items(con, items, today, stats)
    up = con.execute("SELECT uploads_playlist FROM channels WHERE channel_id=?", (cid,)).fetchone()[0]
    if up:
        vids = [it["contentDetails"]["videoId"] for it in yt.playlist_items(up, config.RECENT_PER_CHANNEL)]
        for i in range(0, len(vids), 50):
            for it in yt.videos(vids[i:i + 50]):
                collect.upsert_video(con, it, today)
                stats["videos_updated"] += 1
        con.execute("UPDATE channels SET last_videos_at=? WHERE channel_id=?", (today, cid))
    con.commit()
    title = con.execute("SELECT title FROM channels WHERE channel_id=?", (cid,)).fetchone()[0]
    return {"ok": True, "channel_id": cid, "title": title, "videos": stats["videos_updated"], "units": quota.used_today()}
