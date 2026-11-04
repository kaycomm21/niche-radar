"""실행 진입점.  python -m radar <명령>

  daily        일간 수집 + 집계 (YOUTUBE_API_KEY 없으면 자동 fixture 모드)
  demo         fixture 모드로 N일치 가상 히스토리를 쌓고 집계 (키 없이 화면 확인용)
  export       DB → 화면용 JSON 만 다시 생성
  search       search.list 수동 실행 (100유닛/회, 하루 20회 상한)
  verdict      판정 기록 (생산큐/보류/폐기) → exports/verdicts.json
  quota-plan   유니버스 크기별 하루 쿼터 예상표
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from . import collect, config, export
from .db import connect
from .quota import Quota
from .seed import load_seed
from .youtube import FakeYouTube, RealYouTube


def _client(con, today: date, fixture: bool, seed, job="daily"):
    quota = Quota(con, today.isoformat(), config.QUOTA_BUDGET, job)
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if fixture or not key:
        return FakeYouTube(quota, today, seed), quota, "fixture"
    return RealYouTube(key, quota), quota, "live"


def cmd_daily(a) -> int:
    today = date.fromisoformat(a.date) if a.date else date.today()
    seed, excluded = load_seed()
    con = connect(config.DB_PATH)
    yt, quota, mode = _client(con, today, a.fixture, seed)
    stats = collect.run_daily(con, yt, quota, seed, today.isoformat(),
                              time_budget_s=float(os.environ.get("RADAR_TIME_BUDGET_S", "1200")))
    stats["mode"] = mode
    stats["seed_excluded"] = len(excluded)
    counts = export.build(con, today.isoformat(), last_run=stats)
    print(json.dumps({"mode": mode, "units_used": stats["units_used"], "budget": config.QUOTA_BUDGET,
                      "stopped_by_budget": stats["stopped_by_budget"], "stopped_by_time": stats["stopped_by_time"],
                      "errors": stats.get("errors", []), **counts}, ensure_ascii=False))
    return 0


def cmd_demo(a) -> int:
    end = date.fromisoformat(a.date) if a.date else date.today()
    seed, _ = load_seed()
    con = connect(config.DB_PATH)
    stats = {}
    for i in range(a.days - 1, -1, -1):
        d = end - timedelta(days=i)
        yt, quota, _ = _client(con, d, True, seed)
        stats = collect.run_daily(con, yt, quota, seed, d.isoformat())
    stats["mode"] = "fixture"
    counts = export.build(con, end.isoformat(), last_run=stats)
    print(json.dumps({"mode": "fixture", "days": a.days, **counts}, ensure_ascii=False))
    return 0


def cmd_export(a) -> int:
    today = a.date or date.today().isoformat()
    con = connect(config.DB_PATH)
    print(json.dumps(export.build(con, today, last_run={"mode": "export-only"}), ensure_ascii=False))
    return 0


def cmd_search(a) -> int:
    today = date.today()
    seed, _ = load_seed()
    con = connect(config.DB_PATH)
    yt, quota, mode = _client(con, today, a.fixture, seed, job="search")
    if quota.calls_today("search.list") >= config.SEARCH_DAILY_CAP:
        print(f"오늘 search.list {config.SEARCH_DAILY_CAP}회 상한 도달 — 실행 안 함")
        return 1
    items = yt.search(a.q)
    con.commit()
    out = [{"video_id": i["id"].get("videoId"), "channel_id": i["snippet"]["channelId"], "title": i["snippet"]["title"]} for i in items]
    config.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (config.EXPORTS_DIR / f"search_{today.isoformat()}.json").write_text(
        json.dumps({"q": a.q, "mode": mode, "items": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out)}건 → exports/search_{today.isoformat()}.json")
    return 0


def cmd_verdict_from_issue(a) -> int:
    """verdict 워크플로용: env ISSUE_BODY 의 ```json 블록을 읽어 판정 기록. (셸에 본문을 넣지 않아 주입 위험 없음)"""
    import re
    body = os.environ.get("ISSUE_BODY", "")
    m = re.search(r"```json\s*(\{.*?\})\s*```", body, re.S)
    if "radar-verdict" not in body or not m:
        print("판정 양식이 아님 — 건너뜀")
        return 3
    d = json.loads(m.group(1))
    note = body[m.end():].replace("메모:", "").strip()[:500] or None
    args = argparse.Namespace(id=str(d["id"]), action=d["action"], issue=a.number, title=d.get("title"),
                              channel=d.get("channel"), group=d.get("group"), recipe=d.get("recipe"), note=note)
    return cmd_verdict(args)


VALID = {"queue": "생산큐", "hold": "보류", "drop": "폐기", "exclude_channel": "채널제외"}


def cmd_verdict(a) -> int:
    if a.action not in VALID:
        print("action 은 queue/hold/drop/exclude_channel 중 하나", file=sys.stderr)
        return 2
    p = config.EXPORTS_DIR / "verdicts.json"
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    data[a.id] = {"action": a.action, "label": VALID[a.action], "date": date.today().isoformat(),
                  "issue": a.issue, "title": a.title, "channel": a.channel, "note": a.note}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.action == "queue":    # 생산 큐 = Phase 2 생산 패키지 입력
        q = config.EXPORTS_DIR / "production_queue.json"
        items = json.loads(q.read_text(encoding="utf-8")) if q.exists() else []
        if not any(x["id"] == a.id for x in items):
            items.append({"id": a.id, "title": a.title, "channel": a.channel, "group": a.group,
                          "recipe": a.recipe, "date": date.today().isoformat(), "issue": a.issue, "status": "대기"})
        q.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{VALID[a.action]} 기록: {a.id}")
    return 0


def cmd_alert(a) -> int:
    """M5-22: 레퍼런스(시드) 채널의 새 💥(10배↑, 3일 이내) 영상을 Issue 본문(md)으로. 이미 알린 영상은 제외."""
    q = json.loads((config.WEB_DATA_DIR / "surging.json").read_text(encoding="utf-8"))
    state_p = config.DB_PATH.parent / "alerts_state.json"
    seen = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else []
    new = [v for v in q["items"] if v.get("src") == "seed" and (v.get("mx") or 0) >= 10 and v["id"] not in seen
           and (date.fromisoformat(q["date"]) - date.fromisoformat(v["pub"])).days <= 3]
    if not new:
        print("새 💥 없음")
        return 0
    lines = [f"레퍼런스 채널에서 새로 터진 영상 {len(new)}건 ({q['date']}). 판정은 레이더 홈 카드에서 하세요.", "",
             "| 영상 | 채널 | 배수 | 조회 | → 내 채널 |", "|---|---|---:|---:|---|"]
    for v in new[:20]:
        t = v["t"].replace("|", "/")
        lines.append(f"| [{t}](https://www.youtube.com/watch?v={v['id']}) | {v.get('ct') or ''} | {v['mx']:.1f}× | {v.get('v') or 0:,} | {v.get('g') or '-'} |")
    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    state_p.write_text(json.dumps((seen + [v["id"] for v in new])[-2000:]), encoding="utf-8")
    print(f"새 💥 {len(new)}건 → {a.out}")
    return 0


def quota_plan(n_channels: int, chart_cats: int = len(config.CHART_CATEGORIES)) -> dict:
    charts = chart_cats * config.CHART_PAGES
    ch_stats = -(-n_channels // 50)
    playlists = n_channels
    videos = -(-n_channels * config.RECENT_PER_CHANNEL // 50)
    return {"channels": n_channels, "charts": charts, "channels.list": ch_stats, "playlistItems.list": playlists,
            "videos.list(최근영상)": videos, "total": charts + ch_stats + playlists + videos}


def cmd_quota_plan(a) -> int:
    print("| 유니버스 | 인기차트 | channels.list | playlistItems | videos.list | 합계(유닛/일) | 예산 8,000 대비 |")
    print("|---:|---:|---:|---:|---:|---:|---:|")
    for n in (100, 500, 1000, 2000, 3000):
        p = quota_plan(n)
        print(f"| {n:,} | {p['charts']} | {p['channels.list']} | {p['playlistItems.list']:,} | {p['videos.list(최근영상)']:,} | "
              f"{p['total']:,} | {p['total'] / config.QUOTA_BUDGET:.0%} |")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="radar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("daily"); s.add_argument("--fixture", action="store_true"); s.add_argument("--date"); s.set_defaults(f=cmd_daily)
    s = sub.add_parser("demo"); s.add_argument("--days", type=int, default=45); s.add_argument("--date"); s.set_defaults(f=cmd_demo)
    s = sub.add_parser("export"); s.add_argument("--date"); s.set_defaults(f=cmd_export)
    s = sub.add_parser("search"); s.add_argument("--q", required=True); s.add_argument("--fixture", action="store_true"); s.set_defaults(f=cmd_search)
    s = sub.add_parser("verdict")
    for k in ("id", "action"):
        s.add_argument("--" + k, required=True)
    for k in ("issue", "title", "channel", "group", "recipe", "note"):
        s.add_argument("--" + k, default=None)
    s.set_defaults(f=cmd_verdict)
    s = sub.add_parser("quota-plan"); s.set_defaults(f=cmd_quota_plan)
    s = sub.add_parser("alert"); s.add_argument("--out", default="alert.md"); s.set_defaults(f=cmd_alert)
    s = sub.add_parser("verdict-from-issue"); s.add_argument("--number", required=True); s.set_defaults(f=cmd_verdict_from_issue)
    a = ap.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    raise SystemExit(main())
