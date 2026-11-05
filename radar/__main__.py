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


def cmd_package(a) -> int:
    from .package import build_briefs
    today = a.date or date.today().isoformat()
    paths = build_briefs(connect(config.DB_PATH), config.EXPORTS_DIR / today, today)
    print(f"brief {len(paths)}건 → exports/{today}/")
    return 0


def cmd_add_channel(a) -> int:
    from .addchannel import add_and_collect
    today = date.today()
    seed, _ = load_seed()
    con = connect(config.DB_PATH)
    yt, quota, mode = _client(con, today, a.fixture, seed, job="add-channel")
    try:
        r = add_and_collect(con, yt, quota, a.q, today.isoformat(), a.group)
    except Exception as e:  # noqa: BLE001
        r = {"ok": False, "reason": str(e)}
    con.commit()
    r["mode"] = mode
    print(json.dumps(r, ensure_ascii=False))
    if a.out:
        Path(a.out).write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    if r.get("ok"):
        export.build(con, today.isoformat(), last_run={"mode": f"add-channel ({mode})"})
    return 0 if r.get("ok") else 4


def cmd_gtrends(a) -> int:
    from .gtrends import run
    run(config.WEB_DATA_DIR / "gtrends.json", a.date or date.today().isoformat())
    return 0


def cmd_blog(a) -> int:
    from .blog import run
    from .llm import NoKey
    try:
        d = run(os.environ.get("ISSUE_BODY", ""), a.number)
    except NoKey:
        print("NOKEY")
        return 5
    print(f"OUT={d.relative_to(config.ROOT)}")
    return 0


def cmd_calibrate(a) -> int:
    from .calibrate import report
    today = a.date or date.today().isoformat()
    md = report(connect(config.DB_PATH), today)
    out = Path(a.out) if a.out else config.EXPORTS_DIR / f"ⓒ_판정보정리포트_{today.replace('-', '')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(md)
    return 0


def cmd_enrich(a) -> int:
    """Phase 2: 판정 후보에 Gemini 적합도·Brave 이슈화를 붙이고 화면을 다시 만든다 (키 없으면 건너뜀)."""
    from . import ai
    today = a.date or date.today().isoformat()
    con = connect(config.DB_PATH)
    q = json.loads((config.WEB_DATA_DIR / "queue.json").read_text(encoding="utf-8"))
    s = json.loads((config.WEB_DATA_DIR / "surging.json").read_text(encoding="utf-8"))
    ids = [c["id"] for c in q["top3"] + q["pending"]] + [c["id"] for c in s["items"][:30]]
    ids = list(dict.fromkeys(ids))
    rows = [dict(r) | {"channel_title": r["ct"]} for r in con.execute(
        f"SELECT v.*, c.title ct FROM videos v LEFT JOIN channels c USING(channel_id) WHERE video_id IN ({','.join('?' * len(ids))})", ids)]
    rows.sort(key=lambda r: ids.index(r["video_id"]))
    n_g = ai.gemini_fit(con, today, rows)
    top = [(c["id"], ai.search_query(c["t"])) for c in (q["top3"] + q["pending"])[:10]]
    n_b = len(ai.brave_buzz(con, today, top))
    print(f"gemini {n_g}건 · brave {n_b}건" + ("" if os.environ.get("GEMINI_API_KEY") or os.environ.get("BRAVE_API_KEY") else " (키 없음 — 건너뜀)"))
    if n_g or n_b:
        export.build(con, today, last_run=json.loads((config.WEB_DATA_DIR / "summary.json").read_text(encoding="utf-8")).get("last_run"))
    return 0


def cmd_weekly(a) -> int:
    """M3-18 주간 시장 브리핑 (규칙 기반, AI 없음): 그룹별 터진 것 5 / 뜨는 키워드 5 / 따라 할 것 3 / 피할 것 1."""
    W = config.WEB_DATA_DIR
    surging = json.loads((W / "surging.json").read_text(encoding="utf-8"))["items"]
    queue = json.loads((W / "queue.json").read_text(encoding="utf-8"))
    trends = json.loads((W / "trends.json").read_text(encoding="utf-8"))
    d = surging and json.loads((W / "summary.json").read_text(encoding="utf-8"))["date"]
    kws = trends["rising"][:5] or trends["frequent"][:5]
    cands = queue["top3"] + queue["pending"]
    follow = [c for c in cands if c.get("g")][:3]
    avoid = [c for c in sorted(surging, key=lambda v: -(v.get("mx") or 0))
             if (c.get("sc") or {}).get("excluded") or any("정치" in r or "단정" in r for r in (c.get("sc") or {}).get("reasons", []))][:1]
    L = [f"## 📊 주간 시장 브리핑 ({d}, 규칙 기반)", "", "### 🔥 이번 주 터진 것 5", "| 영상 | 채널 | 배수 | 조회 |", "|---|---|---:|---:|"]
    for v in surging[:5]:
        L.append(f"| [{v['t'][:50].replace('|','/')}](https://www.youtube.com/watch?v={v['id']}) | {v.get('ct') or ''} | {v.get('mx') or 0:.0f}× | {v.get('v') or 0:,} |")
    L += ["", "### 📈 뜨는 키워드 5" + ("" if trends["has_prev"] else " (지난주 데이터가 쌓이기 전이라 빈도 기준)"), ""]
    L += [f"- **{k['kw']}** — {k['n']}편" + (f" (지난주 {k['prev']}편, {k['growth']}배)" if k.get("growth") else "") for k in kws]
    L += ["", "### ✅ 따라 할 것 3 (내 채널 매핑된 판정 대기 카드)", ""]
    L += [f"- [{c['g']}] {c['t'][:60]} — {c['rc'][0]} {c['rc'][1]} ({c['sc']['total']}/{c['sc']['max']}점)" for c in follow] or ["- 없음"]
    L += ["", "### ⛔ 피할 것 1", ""]
    L += [f"- {c['t'][:60]} — {', '.join(c['sc']['reasons'])}" for c in avoid] or ["- 이번 주 해당 없음"]
    L += ["", "판정은 레이더 🎯 오늘 탭에서 하세요: https://kaycomm21.github.io/niche-radar/"]
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"주간 브리핑 → {a.out}")
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
    s = sub.add_parser("package"); s.add_argument("--date"); s.set_defaults(f=cmd_package)
    s = sub.add_parser("oauth-init"); s.add_argument("--name", required=True); s.set_defaults(f=lambda a: (__import__("radar.mychannel", fromlist=["x"]).oauth_init(a.name), 0)[1])
    s = sub.add_parser("mychannel"); s.add_argument("--days", type=int, default=28); s.set_defaults(f=lambda a: (print(json.dumps([{k: o[k] for k in ("channel", "views", "revenue", "rpm", "median_video_views")} for o in __import__("radar.mychannel", fromlist=["x"]).run(a.days)], ensure_ascii=False)), 0)[1])
    s = sub.add_parser("add-channel"); s.add_argument("--q", required=True); s.add_argument("--group"); s.add_argument("--out"); s.add_argument("--fixture", action="store_true"); s.set_defaults(f=cmd_add_channel)
    s = sub.add_parser("gtrends"); s.add_argument("--date"); s.set_defaults(f=cmd_gtrends)
    s = sub.add_parser("blog"); s.add_argument("--number", default=""); s.set_defaults(f=cmd_blog)
    s = sub.add_parser("calibrate"); s.add_argument("--date"); s.add_argument("--out", default=None); s.set_defaults(f=cmd_calibrate)
    s = sub.add_parser("enrich"); s.add_argument("--date"); s.set_defaults(f=cmd_enrich)
    s = sub.add_parser("weekly"); s.add_argument("--out", default="weekly.md"); s.set_defaults(f=cmd_weekly)
    s = sub.add_parser("alert"); s.add_argument("--out", default="alert.md"); s.set_defaults(f=cmd_alert)
    s = sub.add_parser("verdict-from-issue"); s.add_argument("--number", required=True); s.set_defaults(f=cmd_verdict_from_issue)
    a = ap.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    raise SystemExit(main())
