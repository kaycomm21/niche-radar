"""M1-5 주제 트렌드: 인기 차트 제목·태그의 키워드 빈도와 주간 변화."""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, timedelta

TOKEN = re.compile(r"[가-힣A-Za-z][가-힣A-Za-z0-9+]{1,}")
STOP = set("""shorts short 쇼츠 영상 오늘 진짜 이유 그냥 정말 너무 모든 이번 우리 지금 그리고 하는 있는 없는 했다 합니다 입니다 무슨 어떻게
이거 이게 그게 저게 여기 거기 결국 드디어 역대급 최초 공개 대박 충격 반응 the and for with you this that from full ver official mv ep
feat vs of in on to is are 추천 리뷰 브이로그 vlog 모음 하이라이트 풀버전 라이브 live 방송 다시보기 특집 레전드 ㅋㅋ ㅋㅋㅋ""".split())


def tokens(title: str, tags: list[str]) -> set[str]:
    out = set()
    for t in TOKEN.findall(title or "") + [x for tag in tags for x in TOKEN.findall(tag)]:
        k = t.lower()
        if len(k) >= 2 and k not in STOP and not k.isdigit():
            out.add(k)
    return out


def compute(con, today: str, top: int = 20) -> dict:
    t = date.fromisoformat(today)
    cur_from = (t - timedelta(days=6)).isoformat()
    prev_from, prev_to = (t - timedelta(days=13)).isoformat(), (t - timedelta(days=7)).isoformat()

    def window(a: str, b: str) -> tuple[Counter, dict]:
        rows = con.execute("""SELECT DISTINCT c.video_id, v.title, v.tags FROM chart_daily c JOIN videos v USING(video_id)
                              WHERE c.date BETWEEN ? AND ?""", (a, b)).fetchall()
        cnt, ex = Counter(), {}
        for vid, title, tags in rows:
            for k in tokens(title, json.loads(tags or "[]")):
                cnt[k] += 1
                ex.setdefault(k, []).append({"id": vid, "t": title})
        return cnt, ex

    cur, ex = window(cur_from, today)
    prev, _ = window(prev_from, prev_to)
    has_prev = sum(prev.values()) > 0
    items = []
    for k, n in cur.items():
        if n < 3:
            continue
        p = prev.get(k, 0)
        items.append({"kw": k, "n": n, "prev": p if has_prev else None,
                      "growth": round((n + 1) / (p + 1), 2) if has_prev else None, "examples": ex[k][:3]})
    rising = sorted([i for i in items if i["growth"]], key=lambda i: (i["growth"], i["n"]), reverse=True)[:top] if has_prev else []
    frequent = sorted(items, key=lambda i: i["n"], reverse=True)[:top]
    return {"date": today, "window": [cur_from, today], "has_prev": has_prev, "rising": rising, "frequent": frequent,
            "formula": "최근 7일 인기 차트 영상 제목·태그에 등장한 영상 수(키워드별, 3편 이상). 급부상 = (이번 주+1)÷(지난주+1). 지난주 데이터가 쌓이기 전에는 빈도만 표시"}
