"""DB → 화면용 집계 JSON (web/public/data). 웹앱은 이 JSON만 읽는다."""
from __future__ import annotations

import json
import shutil
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import config, metrics as M
from .collect import assign_group

KST = timezone(timedelta(hours=9))


def _d(s: str | None) -> date | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).date()


def _load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def build(con, today: str, out_dir: Path | None = None, exports_dir: Path | None = None,
          last_run: dict | None = None) -> dict:
    out_dir = Path(out_dir or config.WEB_DATA_DIR)
    exports_dir = Path(exports_dir or config.EXPORTS_DIR)
    t = date.fromisoformat(today)
    yday = (t - timedelta(days=1)).isoformat()
    rpm = config.load_rpm()
    ppl_cfg = config.load_rpm(config.ROOT / "config" / "ppl_kr.yaml")

    chans = {r["channel_id"]: dict(r) for r in con.execute("SELECT * FROM channels")}
    vids = [dict(r) for r in con.execute("SELECT * FROM videos")]
    vd_today = {r[0]: r for r in con.execute("SELECT video_id, views, comments FROM video_daily WHERE date=?", (today,))}
    vd_yday = {r[0]: r for r in con.execute("SELECT video_id, views, comments FROM video_daily WHERE date=?", (yday,))}
    chart_rows = [dict(r) for r in con.execute("SELECT * FROM chart_daily WHERE date >= ?", ((t - timedelta(days=7)).isoformat(),))]

    # ---------------- 영상 단위 지표
    by_channel: dict[str, list[dict]] = defaultdict(list)
    for v in vids:
        by_channel[v["channel_id"]].append(v)
    for cid, vs in by_channel.items():
        vs.sort(key=lambda v: v["published_at"] or "", reverse=True)
        recent = vs[:config.RECENT_PER_CHANNEL]
        # 업로드 3일 미만 영상은 아직 조회가 덜 쌓여 중앙값을 끌어내리므로 기준에서 뺀다 (5편 미만이면 전체 사용)
        mature = [v for v in recent if (_d(v["published_at"]) or t) <= t - timedelta(days=3)]
        base = mature if len(mature) >= 5 else recent
        med_all = M.median([v["views"] for v in base])
        med_fmt = {}
        for fmt in (0, 1):
            same = [v["views"] for v in base if v["is_short"] == fmt]
            med_fmt[fmt] = M.median(same) if len(same) >= 5 else med_all
        for v in vs:
            v["channel_median"] = med_fmt[v["is_short"]]
            # 채널 최근 영상을 수집하지 않은(차트로만 본) 채널은 배수 계산 불가
            v["multiple"] = M.outlier_multiple(v["views"], v["channel_median"]) if len(recent) >= 5 else None

    best_rank: dict[str, int] = {}
    chart_7d: set[str] = set()
    for r in chart_rows:
        if r["date"] == today:
            best_rank[r["video_id"]] = min(best_rank.get(r["video_id"], 999), r["rank"])
        chart_7d.add(r["video_id"])

    inc24 = {}
    for vid, row in vd_today.items():
        y = vd_yday.get(vid)
        if y and row[1] is not None and y[1] is not None:
            inc24[vid] = (row[1] - y[1], ((row[2] or 0) - (y[2] or 0)) / max(1, y[2] or 0))
    inc_values = sorted(x[0] for x in inc24.values())

    vmap = {}
    for v in vids:
        ch = chans.get(v["channel_id"], {})
        pub = _d(v["published_at"])
        v["age_days"] = (t - pub).days if pub else None
        # 레퍼런스(시드) 채널은 시드 그룹, 차트 채널은 영상 제목으로 내 채널 그룹을 매핑
        v["group"] = ch.get("group") if ch.get("source") == "seed" else assign_group(v["title"] or "")
        v["source"] = ch.get("source")
        v["channel_title"] = ch.get("title")
        lo, hi = M.rpm_for(rpm, v["category_id"], v["title"], bool(v["is_short"]), config.FINANCE_KW, config.HEALTH_KW)
        v["rpm_lo"], v["rpm_hi"] = lo, hi
        v["money_kw"] = any(k.lower() in (v["title"] or "").lower() for k in config.FINANCE_KW + config.HEALTH_KW)
        v["chart_rank"] = best_rank.get(v["video_id"])
        v["chart_within_7d"] = v["video_id"] in chart_7d and (v["age_days"] is not None and v["age_days"] <= 7)
        if v["video_id"] in inc24:
            v["views_24h"], v["comments_24h_growth"] = inc24[v["video_id"]]
            v["views_24h_pct"] = M.percentile_rank(inc_values, v["views_24h"])
        else:
            v["views_24h"] = v["comments_24h_growth"] = v["views_24h_pct"] = None
        v["subs"] = None
        v["labels"] = M.labels(v)
        v["score"] = M.rework_score(v)
        v["recipe"] = M.suggest_recipe(v)
        vmap[v["video_id"]] = v

    def vcard(v: dict) -> dict:
        return {"id": v["video_id"], "t": v["title"], "c": v["channel_id"], "ct": v["channel_title"],
                "pub": (v["published_at"] or "")[:10], "dur": v["duration_s"], "sh": v["is_short"], "cat": v["category_id"],
                "v": v["views"], "lk": v["likes"], "cm": v["comments"], "th": v["thumb"],
                "mx": round(v["multiple"], 2) if v["multiple"] else None, "med": v["channel_median"],
                "v24": v["views_24h"], "rk": v["chart_rank"], "lb": v["labels"], "g": v["group"],
                "sc": v["score"], "rc": list(v["recipe"]), "rpm": [round(v["rpm_lo"]), round(v["rpm_hi"])],
                "src": v["source"]}

    # ---------------- 채널 단위
    hist: dict[str, list] = defaultdict(list)
    for r in con.execute("SELECT channel_id, date, subs, views, videos FROM channel_daily ORDER BY date"):
        hist[r[0]].append((r[1], r[2], r[3], r[4]))

    feats: dict[str, dict] = {}
    for cid, ch in chans.items():
        if not ch["active"]:
            continue
        h = hist.get(cid, [])
        last = h[-1] if h else None
        subs = last[1] if last else None
        vs = by_channel.get(cid, [])[:config.RECENT_PER_CHANNEL]
        window = [x for x in h if x[0] >= (t - timedelta(days=30)).isoformat()]
        days_hist = len(h)
        growth = sub_gain = view_gain = None
        if len(window) >= 7 and window[0][1] and subs is not None:
            sub_gain = subs - window[0][1]
            growth = sub_gain / window[0][1]
            view_gain = (window[-1][2] or 0) - (window[0][2] or 0)
        v30 = [v for v in vs if v["age_days"] is not None and v["age_days"] <= 30]
        views30_uploads = sum(v["views"] or 0 for v in v30)
        longs = [v for v in vs if not v["is_short"]]
        avg_views = (sum(v["views"] or 0 for v in vs) / len(vs)) if vs else None
        eff = (sum(v["views"] or 0 for v in (longs or vs)) / len(longs or vs) / subs) if vs and subs else None
        eng = M.median([((v["likes"] or 0) + (v["comments"] or 0)) / v["views"] for v in vs if v["views"]])
        cons = M.upload_consistency([(t - _d(v["published_at"])).days for v in vs if v["published_at"]])
        if cons is not None:
            cons *= min(1.0, len(v30) / 4)
        ofreq = (sum(1 for v in vs if (v["multiple"] or 0) >= 3) / len(vs)) if len(vs) >= 5 else None
        rev_lo = sum((v["views"] or 0) * v["rpm_lo"] / 1000 for v in v30)
        rev_hi = sum((v["views"] or 0) * v["rpm_hi"] / 1000 for v in v30)
        flags = []
        if subs and subs >= 10000 and avg_views is not None and avg_views / subs < 0.05:
            flags.append("조회÷구독 5% 미만")
        if growth and growth > 0.1 and view_gain is not None and window and (window[0][2] or 0) and view_gain / window[0][2] < 0.01:
            flags.append("구독 급증 대비 조회 정체")
        ppl = None
        if longs:
            avg_long = sum(v["views"] or 0 for v in longs) / len(longs)
            lo_c, hi_c = ppl_cfg.get("cpv_long", (15, 50))
            mn = ppl_cfg.get("min_fee", (300000, 1000000))
            ppl = [round(max(mn[0], avg_long * lo_c), -4), round(max(mn[1], avg_long * hi_c), -4)]
        feats[cid] = {"ppl": ppl, "subs": subs, "growth": growth, "sub_gain": sub_gain, "view_gain": view_gain,
                      "efficiency": eff, "engagement": eng, "consistency": cons, "outlier_freq": ofreq,
                      "avg_views": avg_views, "views30_uploads": views30_uploads, "uploads30": len(v30),
                      "rev": [round(rev_lo), round(rev_hi)], "flags": flags, "days_hist": days_hist}
        for v in by_channel.get(cid, []):
            v["subs"] = subs

    uni = {k: [f[k] for f in feats.values() if f[k] is not None] for k in M.GRADE_WEIGHTS}
    for cid, f in feats.items():
        f["grade"] = M.grade(f, uni)

    # 💰 '작은 채널 대박' 가중은 subs 가 채워진 뒤 재계산
    for v in vids:
        if "money" in v["labels"] and v["subs"] is not None and v["subs"] < 100_000:
            v["score"]["total"] = round(min(v["score"]["max"], v["score"]["total"] + 5), 1)
            v["score"]["reasons"].append("구독 10만 미만 채널의 대박 = 재현 가능성 ↑ (+5)")

    # ---------------- 판정 카드 / 생산 큐 (§A)
    verdicts = _load_json(exports_dir / "verdicts.json", {})
    cards_state_path = Path(config.DB_PATH).parent / "cards_state.json"   # 판정 카드 최초 노출일 (data 브랜치에 보관)
    cards_state = _load_json(cards_state_path, {})
    cand = [v for v in vids if v["labels"] and not v["score"]["excluded"] and v["video_id"] not in verdicts
            and v["age_days"] is not None and v["age_days"] <= 30]
    cand.sort(key=lambda v: (v["score"]["total"], v["multiple"] or 0), reverse=True)
    pending, archived = [], []
    per_channel: dict[str, int] = defaultdict(int)
    for v in cand:
        first = cards_state.get(v["video_id"])
        if first and (t - date.fromisoformat(first)).days >= 7:
            archived.append(v["video_id"])     # A4: 7일 무응답 → 자동 보관
            continue
        if per_channel[v["channel_id"]] >= 2:  # 한 채널이 카드를 독점하지 않게 채널당 2장
            continue
        per_channel[v["channel_id"]] += 1
        pending.append(v)
    top3, used_groups = [], set()
    for v in pending:                           # 서로 다른 내 채널 그룹 우선
        if v["group"] not in used_groups:
            top3.append(v)
            used_groups.add(v["group"])
        if len(top3) == 3:
            break
    for v in pending:
        if len(top3) == 3:
            break
        if v not in top3:
            top3.append(v)
    rest = [v for v in pending if v not in top3][:27]
    for v in top3 + rest:
        cards_state.setdefault(v["video_id"], today)
    archived_cards = [vcard(vmap[i]) for i in archived if i in vmap][:50]
    _write(cards_state_path, {k: d for k, d in cards_state.items() if (t - date.fromisoformat(d)).days <= 60})

    if (out_dir / "channels").exists():
        shutil.rmtree(out_dir / "channels")
    _write(out_dir / "queue.json", {"date": today, "top3": [vcard(v) for v in top3], "pending": [vcard(v) for v in rest],
                                    "archived": archived_cards, "decided": len(verdicts),
                                    "card_age": {v["video_id"]: cards_state.get(v["video_id"]) for v in top3 + rest}})

    # ---------------- M1-1 인기 차트 (순위 변동)
    prev = {(r["category_id"], r["format"], r["video_id"]): r["rank"]
            for r in con.execute("SELECT * FROM chart_daily WHERE date=?", (yday,))}
    charts: dict[str, dict[str, list]] = defaultdict(lambda: {"long": [], "short": []})
    for r in con.execute("SELECT * FROM chart_daily WHERE date=? ORDER BY category_id, format, rank", (today,)):
        v = vmap.get(r["video_id"])
        if not v:
            continue
        p = prev.get((r["category_id"], r["format"], r["video_id"]))
        charts[r["category_id"]][r["format"]].append({**vcard(v), "rank": r["rank"], "delta": None if p is None else p - r["rank"]})
    _write(out_dir / "charts.json", {"date": today, "categories": config.CHART_CATEGORIES, "charts": charts})

    # ---------------- M1-4 급상승 (최근 14일, 배수 3배↑)
    surging = [v for v in vids if v["age_days"] is not None and v["age_days"] <= 14 and (v["multiple"] or 0) >= 3
               and (v["views"] or 0) >= M.MIN_VIEWS]
    surging.sort(key=lambda v: (v["multiple"], v["views_24h"] or 0), reverse=True)
    _write(out_dir / "surging.json", {"date": today, "items": [vcard(v) for v in surging[:300]]})

    # ---------------- M1-2 채널 순위
    rows = []
    for cid, f in feats.items():
        ch = chans[cid]
        top = max(by_channel.get(cid, [])[:30], key=lambda v: v["multiple"] or 0, default=None)
        rows.append({"id": cid, "t": ch["title"], "g": ch["group"], "src": ch["source"], "th": ch["thumb"],
                     "subs": f["subs"], "sg": f["sub_gain"], "sgr": f["growth"], "vg": f["view_gain"],
                     "v30": f["views30_uploads"], "avg": f["avg_views"], "up30": f["uploads30"],
                     "gr": f["grade"]["letter"], "gs": f["grade"]["score"], "fl": f["flags"], "rev": f["rev"],
                     "top": vcard(top) if top and (top["multiple"] or 0) >= 3 else None, "dh": f["days_hist"]})
    _write(out_dir / "rankings.json", {"date": today, "items": rows})

    # ---------------- M2 채널 상세 (6~9, 11~13)
    for cid, f in feats.items():
        ch = chans[cid]
        h = hist.get(cid, [])
        fc_subs = M.holt_forecast([x[1] for x in h])
        fc_views = M.holt_forecast([x[2] for x in h])
        ms = {}
        if fc_subs and f["subs"] is not None:
            for target in (100_000, 1_000_000):
                d = M.milestone_days(f["subs"], fc_subs["trend_per_day"], target)
                ms[str(target)] = None if d is None else (t + timedelta(days=d)).isoformat()
        vs = by_channel.get(cid, [])[:config.RECENT_PER_CHANNEL]
        heat = [[0] * 24 for _ in range(7)]
        for v in vs:
            if v["published_at"]:
                k = datetime.fromisoformat(v["published_at"].replace("Z", "+00:00")).astimezone(KST)
                heat[k.weekday()][k.hour] += 1
        titles = [v["title"] or "" for v in vs]
        fmt = {"n": len(vs), "short_ratio": (sum(v["is_short"] for v in vs) / len(vs)) if vs else None,
               "avg_dur": (sum(v["duration_s"] or 0 for v in vs if not v["is_short"]) / max(1, sum(1 for v in vs if not v["is_short"]))),
               "title_len": (sum(len(x) for x in titles) / len(titles)) if titles else None,
               "title_num": (sum(any(c.isdigit() for c in x) for x in titles) / len(titles)) if titles else None,
               "title_q": (sum("?" in x for x in titles) / len(titles)) if titles else None, "heat": heat}
        _write(out_dir / "channels" / f"{cid}.json", {
            "id": cid, "t": ch["title"], "handle": ch["handle"], "g": ch["group"], "src": ch["source"], "th": ch["thumb"],
            "country": ch["country"], "hist": h[-365:], "f": {k: f[k] for k in f if k != "grade"}, "grade": f["grade"],
            "fc_subs": fc_subs, "fc_views": fc_views, "milestones": ms, "fmt": fmt,
            "videos": [vcard(v) for v in vs]})

    # ---------------- M1-5 주제 트렌드
    from .trends import compute as compute_trends
    _write(out_dir / "trends.json", compute_trends(con, today))

    # ---------------- 요약 · 쿼터
    q = [dict(r) for r in con.execute("SELECT date, SUM(units) u FROM quota_log GROUP BY date ORDER BY date DESC LIMIT 30")]
    qt = [dict(r) for r in con.execute("SELECT endpoint, job, units, calls FROM quota_log WHERE date=?", (today,))]
    from .seed import load_seed
    _, excluded = load_seed()
    summary = {"date": today, "generated_at": datetime.now(KST).isoformat(timespec="minutes"),
               "mode": (last_run or {}).get("mode", "unknown"),
               "counts": {"channels_active": len(feats), "channels_seed": sum(1 for c in chans.values() if c["source"] == "seed" and c["active"]),
                          "videos": len(vids), "chart_rows_today": sum(len(x["long"]) + len(x["short"]) for x in charts.values()),
                          "surging": len(surging), "cards_pending": len(top3) + len(rest), "decided": len(verdicts)},
               "quota": {"budget": config.QUOTA_BUDGET, "today": sum(x["units"] for x in qt), "by_endpoint": qt, "history": q},
               "formulas": M.FORMULAS, "rpm": rpm, "categories": config.CATEGORY_NAMES,
               "groups": sorted({c["group"] for c in chans.values() if c["group"]}), "seed_excluded": excluded,
               "last_run": last_run, "repo": "kaycomm21/niche-radar"}
    _write(out_dir / "summary.json", summary)
    return summary["counts"]
