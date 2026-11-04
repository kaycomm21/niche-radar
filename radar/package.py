"""생산 큐 → 생산 패키지 brief.md 자동 생성 (M0 4단계의 레이더 담당분).
titles/script 등 AI 산출물은 Phase 2에서 같은 폴더에 추가된다."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from . import config, metrics as M

RECIPE = {"R1": "포맷 이식", "R2": "주제 이식", "R3": "각도 반전", "R4": "시리즈화", "R5": "롱폼↔쇼츠", "R6": "해외→한국"}


def slug(s: str, n: int = 28) -> str:
    s = re.sub(r"[^\w가-힣]+", "_", s).strip("_")
    return s[:n]


def build_briefs(con, out_root: Path, today: str) -> list[Path]:
    q = json.loads((config.EXPORTS_DIR / "production_queue.json").read_text(encoding="utf-8"))
    rpm = config.load_rpm()
    out = []
    for item in q:
        v = con.execute("""SELECT v.*, c.title ct, c."group" cg, c.source src,
                                  (SELECT subs FROM channel_daily d WHERE d.channel_id=v.channel_id ORDER BY date DESC LIMIT 1) subs
                           FROM videos v LEFT JOIN channels c USING(channel_id) WHERE video_id=?""", (item["id"],)).fetchone()
        if not v:
            continue
        recent = [r[0] for r in con.execute("SELECT views FROM videos WHERE channel_id=? ORDER BY published_at DESC LIMIT 30", (v["channel_id"],))]
        med = M.median(recent)
        mult = M.outlier_multiple(v["views"], med)
        lo, hi = M.rpm_for(rpm, v["category_id"], v["title"], bool(v["is_short"]), config.FINANCE_KW, config.HEALTH_KW)
        d = out_root / f"{slug(item.get('group') or '미지정', 10)}_{slug(v['title'])}"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "brief.md"
        p.write_text(f"""# ⓒ brief — {v['title']}
> 생성: 레이더 자동 ({today}) · 생산 큐 Issue #{item.get('issue')}

| 항목 | 값 |
|---|---|
| 원본 | https://www.youtube.com/watch?v={v['video_id']} |
| 채널 | {v['ct']} (구독 {v['subs'] or '비공개'}) |
| 업로드 | {(v['published_at'] or '')[:10]} · {'쇼츠' if v['is_short'] else '롱폼'} {v['duration_s'] // 60}분 |
| 조회 | {v['views']:,} (채널 최근 30편 중앙값 {int(med or 0):,} → **{mult or 0:.1f}배**) |
| 레시피 | {item.get('recipe')} {RECIPE.get(item.get('recipe') or '', '')} |
| 매핑 그룹 | {item.get('group') or '미지정'} |
| 예상 RPM | {int(lo):,}~{int(hi):,}원 / 1,000회 (**추정**, config/rpm_kr.yaml) |
| 상태 | {item.get('status')} |

## 재가공 원칙
- 원본 영상·음성·썸네일 **재사용 금지**. 구조·주제만 차용 (기획서 §0-1-3)
- 원본의 사실 주장은 **직접 확인 전까지 인용 금지** → factcheck.md (로컬 CC, Brave/NotebookLM)
""", encoding="utf-8")
        out.append(p)
    return out
