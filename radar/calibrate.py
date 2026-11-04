"""판정 기준 보정 리포트 (30일 운영 후 사용, 지금도 실행 가능).
- 배수 기준별 급상승 건수 → 화면이 감당할 수준(≈300건)이 되는 기준 추천
- §A3 수집 중단 규칙: 30일간 카드 → 생산 큐 전환율 < 10% 인 그룹·카테고리 = 수집 중단 후보
- 판정 분포(생산큐/보류/폐기) · 레시피 분포
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, timedelta

from . import config


def report(con, today: str, target_surging: int = 300) -> str:
    t = date.fromisoformat(today)
    since = (t - timedelta(days=14)).isoformat()
    rows = con.execute("""SELECT v.video_id, v.channel_id, v.views, v.is_short, v.published_at, v.category_id
                          FROM videos v WHERE v.published_at >= ? AND v.views >= 10000""", (since,)).fetchall()
    meds = {}
    for cid, in con.execute("SELECT DISTINCT channel_id FROM videos"):
        vs = sorted(r[0] or 0 for r in con.execute("SELECT views FROM videos WHERE channel_id=? ORDER BY published_at DESC LIMIT 30", (cid,)))
        meds[cid] = vs[len(vs) // 2] if len(vs) >= 5 else None
    mults = [r[2] / meds[r[1]] for r in rows if meds.get(r[1])]
    th_rows = []
    rec = None
    for th in (3, 5, 7, 10, 15, 20):
        n = sum(1 for m in mults if m >= th)
        th_rows.append(f"| {th}× | {n:,} |")
        if rec is None and n <= target_surging:
            rec = th

    verdicts = {}
    p = config.EXPORTS_DIR / "verdicts.json"
    if p.exists():
        verdicts = json.loads(p.read_text(encoding="utf-8"))
    acts = Counter(v["action"] for v in verdicts.values())
    state_p = config.DB_PATH.parent / "cards_state.json"
    cards = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else {}
    cut = (t - timedelta(days=30)).isoformat()
    shown = [vid for vid, d in cards.items() if d >= cut]
    by_cat = defaultdict(lambda: [0, 0])
    for vid in shown:
        r = con.execute("SELECT category_id FROM videos WHERE video_id=?", (vid,)).fetchone()
        cat = config.CATEGORY_NAMES.get(r[0], r[0]) if r else "알수없음"
        by_cat[cat][0] += 1
        if verdicts.get(vid, {}).get("action") == "queue":
            by_cat[cat][1] += 1
    days = con.execute("SELECT COUNT(DISTINCT date) FROM channel_daily").fetchone()[0]
    L = [f"# ⓒ 판정 기준 보정 리포트 ({today})", "",
         f"> 데이터 {days}일치. **30일 미만이면 참고용** (기획서: 30일 운영 후 보정).", "",
         "## 1. 급상승 배수 기준 (최근 14일, 조회 1만↑)", "| 기준 | 건수 |", "|---:|---:|", *th_rows, "",
         f"→ 화면 목표 {target_surging}건 이하가 되는 최소 기준: **{rec or '20× 초과'}배**" + (" (현재 기획서 기준 3배 유지 여부 판단)" if rec and rec != 3 else ""), "",
         "## 2. 판정 분포", "| 판정 | 건수 |", "|---|---:|",
         *([f"| {k} | {v} |" for k, v in acts.most_common()] or ["| 없음 | 0 |"]), "",
         "## 3. §A3 수집 중단 후보 (카테고리별 30일 카드→생산큐 전환율)", "| 카테고리 | 노출 카드 | 생산큐 | 전환율 | 판정 |", "|---|---:|---:|---:|---|"]
    for cat, (n, q) in sorted(by_cat.items(), key=lambda x: -x[1][0]):
        rate = q / n if n else 0
        verdict = "⛔ 중단 후보" if n >= 10 and rate < 0.10 else ("관찰" if n < 10 else "유지")
        L.append(f"| {cat} | {n} | {q} | {rate:.0%} | {verdict} |")
    L += ["", "※ '중단 후보'는 자동 삭제하지 않는다. 영근님이 순위 화면의 [수집 제외] 또는 config 수정으로 확정."]
    return "\n".join(L) + "\n"
