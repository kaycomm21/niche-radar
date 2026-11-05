"""DB → 화면용 집계 JSON (web/public/data). 웹앱은 이 JSON만 읽는다."""
from __future__ import annotations

import json
import shutil
from collections import Counter, defaultdict
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
    mp = config.ROOT / "config" / "rpm_measured.yaml"
    rpm_measured = config.load_rpm(mp) if mp.exists() else {}

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

    ai_map = {r[0]: json.loads(r[1]) for r in con.execute("SELECT video_id, json FROM ai_teardown")}
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
        if not v["is_short"] and v["group"] in rpm_measured:          # M4 실측 RPM 이 있으면 가정치 대신 사용
            lo, hi = rpm_measured[v["group"]]
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
        ai = ai_map.get(v["video_id"])
        if ai and ai.get("group") and ch.get("source") != "seed":
            v["group"] = ai["group"]                    # Gemini 그룹 판정 우선 (시드 채널은 시드 그룹 유지)
        v["labels"] = M.labels(v)
        if ai and (ai.get("buzz_24h") or 0) >= 10 and "issue" not in v["labels"]:
            v["labels"].append("issue")                 # 📣 Brave: 유튜브 밖 24시간 내 언급 10건 이상
        v["score"] = M.rework_score(v, ai_fit=(ai or {}).get("fit"))
        v["ai"] = {k: ai[k] for k in ("angle", "reason", "buzz_24h") if ai and k in ai} or None
        v["recipe"] = M.suggest_recipe(v)
        vmap[v["video_id"]] = v

    def vcard(v: dict) -> dict:
        return {"id": v["video_id"], "t": v["title"], "c": v["channel_id"], "ct": v["channel_title"],
                "pub": (v["published_at"] or "")[:10], "dur": v["duration_s"], "sh": v["is_short"], "cat": v["category_id"],
                "v": v["views"], "lk": v["likes"], "cm": v["comments"], "th": v["thumb"],
                "mx": round(v["multiple"], 2) if v["multiple"] else None, "med": v["channel_median"],
                "v24": v["views_24h"], "rk": v["chart_rank"], "lb": v["labels"], "g": v["group"],
                "sc": v["score"], "rc": list(v["recipe"]), "rpm": [round(v["rpm_lo"]), round(v["rpm_hi"])],
                "src": v["source"], "ai": v.get("ai"), "lang": v["lang"],
                "cc": (chans.get(v["channel_id"]) or {}).get("country")}

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
    kr_charts = {k: v for k, v in charts.items() if ":" not in k}
    _write(out_dir / "charts.json", {"date": today, "categories": config.CHART_CATEGORIES, "charts": kr_charts})
    # 🌍 해외 레퍼런스 (한국화 재생산용)
    fr = {}
    for region, cat, name in config.FOREIGN_CHARTS:
        key = f"{region}:{cat}"
        if key in charts:
            fr[key] = {"name": name, "long": charts[key]["long"][:50], "short": charts[key]["short"][:30]}
    loc = _load_json(Path(config.DB_PATH).parent / "localize.json", {})
    _write(out_dir / "overseas.json", {"date": today, "charts": fr, "plans": loc})
    # 📦 생산 패키지 보드 (exports 폴더 스캔)
    pk = []
    for meta_p in sorted(Path(exports_dir).glob("*/ⓒ_패키지_*/meta.json")) + sorted(Path(exports_dir).glob("packages/*/meta.json")):
        m = _load_json(meta_p, {})
        d = meta_p.parent
        sb = _load_json(d / "storyboard.json", {})
        pk.append({"dir": str(d.relative_to(config.ROOT)) if d.is_relative_to(config.ROOT) else str(d), "title": m.get("title"),
                   "channel": sb.get("channel"), "secs": sb.get("est_total_s"), "shots": len(sb.get("shots", [])),
                   "has_shorts": (d / "shorts.md").exists(), "auto": "packages" in d.parts, "date": d.parts[-2] if "packages" not in d.parts else d.name[:10]})
    props = []
    for sp in sorted(Path(exports_dir).glob("proposals/*/source.json")):
        it = _load_json(sp, {})
        props.append({"dir": str(sp.parent.relative_to(config.ROOT)) if sp.parent.is_relative_to(config.ROOT) else str(sp.parent),
                      "name": it.get("name"), "org": it.get("org"), "close": it.get("close"), "budget": it.get("budget")})
    kids = [{"dir": str(mp.parent.relative_to(config.ROOT)) if mp.parent.is_relative_to(config.ROOT) else str(mp.parent), **_load_json(mp, {})}
            for mp in sorted(Path(exports_dir).glob("kids/*/meta.json"))]
    _write(out_dir / "packages.json", {"date": today, "items": pk, "proposals": props, "kids": kids, "queue": _load_json(Path(exports_dir) / "production_queue.json", [])})

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
        vs30 = [v for v in by_channel.get(cid, []) if v["age_days"] is not None and v["age_days"] <= 30]
        pop = sum((v["views"] or 0) + 10 * (v["likes"] or 0) for v in vs30)   # Playboard식 인기도: 조회 + 좋아요×10 (최근 30일 영상)
        cats = Counter(v["category_id"] for v in by_channel.get(cid, [])[:30] if v["category_id"])
        f["cat"] = cats.most_common(1)[0][0] if cats else None
        f["pop"] = pop
        rows.append({"id": cid, "t": ch["title"], "h": ch["handle"], "cat": f["cat"], "pop": pop, "g": ch["group"], "src": ch["source"], "th": ch["thumb"],
                     "subs": f["subs"], "sg": f["sub_gain"], "sgr": f["growth"], "vg": f["view_gain"],
                     "v30": f["views30_uploads"], "avg": f["avg_views"], "up30": f["uploads30"],
                     "gr": f["grade"]["letter"], "gs": f["grade"]["score"], "fl": f["flags"], "rev": f["rev"],
                     "top": vcard(top) if top and (top["multiple"] or 0) >= 3 else None, "dh": f["days_hist"]})
    _write(out_dir / "rankings.json", {"date": today, "items": rows})
    _write(out_dir / "search.json", [[r["id"], r["t"], r["h"], r["subs"], r["g"]] for r in rows])   # 🔍 클라이언트 검색 색인

    # ---------------- 순위(SB Rank식) · 카테고리 평균 · 유사 채널 준비
    def rank_of(key):
        order = sorted([c for c in feats if feats[c].get(key) is not None], key=lambda c: -feats[c][key])
        return {c: i + 1 for i, c in enumerate(order)}
    rk_subs, rk_pop, rk_v30 = rank_of("subs"), rank_of("pop"), rank_of("views30_uploads")
    cat_members = defaultdict(list)
    for c, f in feats.items():
        cat_members[f.get("cat")].append(c)
    rk_cat = {}
    for cat, mem in cat_members.items():
        for i, c in enumerate(sorted(mem, key=lambda c: -(feats[c]["subs"] or 0))):
            rk_cat[c] = i + 1

    def vid_stats(vs):
        n = len(vs)
        if not n:
            return None
        views = [v["views"] or 0 for v in vs]
        return {"n": n, "avg_views": sum(views) / n,
                "like_rate": M.median([(v["likes"] or 0) / v["views"] for v in vs if v["views"]]),
                "comment_rate": M.median([(v["comments"] or 0) / v["views"] for v in vs if v["views"]])}
    cat_stats = {}
    for cat, mem in cat_members.items():
        allv = [v for c in mem for v in by_channel.get(c, [])[:30]]
        cat_stats[cat] = vid_stats(allv)

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
        h_list = hist.get(cid, [])
        daily = []
        for prev_row, row in zip(h_list[-366:], h_list[-365:]):
            daily.append({"d": row[0], "subs": row[1], "ds": None if row[1] is None or prev_row[1] is None else row[1] - prev_row[1],
                          "views": row[2], "dv": None if row[2] is None or prev_row[2] is None else row[2] - prev_row[2]})
        allvs = by_channel.get(cid, [])
        v90 = [v for v in allvs if v["age_days"] is not None and v["age_days"] <= 90]
        mine = vid_stats(v90) or vid_stats(allvs[:30])
        subs_me = f["subs"] or 0
        similar = sorted([c for c in cat_members.get(f.get("cat"), []) if c != cid and feats[c]["subs"]],
                         key=lambda c: abs((feats[c]["subs"] or 0) - subs_me))[:6]
        group_peers = [c for c in feats if c != cid and chans[c]["group"] and chans[c]["group"] == ch["group"]]
        peer_avg = M.median([feats[c]["avg_views"] for c in group_peers if feats[c]["avg_views"]]) if group_peers else None
        cat_avg = M.median([feats[c]["avg_views"] for c in cat_members.get(f.get("cat"), []) if c != cid and feats[c]["avg_views"]])
        extra = {
            "ranks": {"subs": rk_subs.get(cid), "pop": rk_pop.get(cid), "views30": rk_v30.get(cid), "cat": rk_cat.get(cid),
                      "cat_n": len(cat_members.get(f.get("cat"), [])), "n": len(feats), "cat_id": f.get("cat")},
            "daily": daily[::-1],
            "video_stats": {"mine": mine, "category": cat_stats.get(f.get("cat"))},
            "perf": {"avg_views": f["avg_views"], "group_median": peer_avg, "category_median": cat_avg,
                     "group": ch["group"], "category": config.CATEGORY_NAMES.get(f.get("cat"), f.get("cat"))},
            "similar": [{"id": c, "t": chans[c]["title"], "th": chans[c]["thumb"], "subs": feats[c]["subs"], "avg": feats[c]["avg_views"],
                         "gr": feats[c]["grade"]["letter"]} for c in similar],
            "rev_year": [r * 12 for r in f["rev"]],
            "top_videos": [vcard(v) for v in sorted(allvs, key=lambda v: -(v["views"] or 0))[:10]],
        }
        _write(out_dir / "channels" / f"{cid}.json", {**extra,
            "id": cid, "t": ch["title"], "handle": ch["handle"], "g": ch["group"], "src": ch["source"], "th": ch["thumb"],
            "country": ch["country"], "hist": h[-365:], "f": {k: f[k] for k in f if k != "grade"}, "grade": f["grade"],
            "fc_subs": fc_subs, "fc_views": fc_views, "milestones": ms, "fmt": fmt,
            "videos": [vcard(v) for v in vs]})

    # ---------------- 홈(플레이보드식) 위젯 데이터
    def d1(cid, idx):
        h = hist.get(cid, [])
        return (h[-1][idx] - h[-2][idx]) if len(h) >= 2 and h[-1][idx] is not None and h[-2][idx] is not None else None
    rise = []
    for cid, f in feats.items():
        g7 = f["sub_gain"] if f["sub_gain"] is not None else d1(cid, 1)
        if g7:
            rise.append({"id": cid, "t": chans[cid]["title"], "th": chans[cid]["thumb"], "subs": f["subs"], "gain": g7,
                         "rate": (g7 / f["subs"]) if f["subs"] else None, "win": "30일" if f["sub_gain"] is not None else "1일"})
    rise.sort(key=lambda r: -r["gain"])
    vrise = sorted([c for c in feats], key=lambda c: -(d1(c, 2) or 0))[:20]
    top24 = sorted([v for v in vids if v["views_24h"]], key=lambda v: -v["views_24h"])[:20]
    _write(out_dir / "home.json", {
        "date": today,
        "chart_long": [vcard(vmap[r[0]]) for r in con.execute("SELECT video_id FROM chart_daily WHERE date=? AND category_id='0' AND format='long' ORDER BY rank LIMIT 10", (today,)) if r[0] in vmap],
        "chart_short": [vcard(vmap[r[0]]) for r in con.execute("SELECT video_id FROM chart_daily WHERE date=? AND format='short' ORDER BY rank LIMIT 10", (today,)) if r[0] in vmap],
        "subs_rise": rise[:20],
        "views_rise": [{"id": c, "t": chans[c]["title"], "th": chans[c]["thumb"], "subs": feats[c]["subs"], "gain": d1(c, 2)} for c in vrise if d1(c, 2)],
        "top24": [vcard(v) for v in top24],
        "explode": [vcard(v) for v in sorted([v for v in vids if (v["multiple"] or 0) >= 10 and (v["views"] or 0) >= 10000 and (v["age_days"] or 99) <= 7], key=lambda v: -(v["views_24h"] or 0))[:10]],
    })

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
