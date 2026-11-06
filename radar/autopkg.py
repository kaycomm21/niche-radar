"""🎬 Cue → 생산 패키지 자동 생성 (Gemini). 클라우드 세션에서 손으로 만들던 패키지 01~10 과 같은 형식.
출력: exports/packages/<날짜>_<영상ID>/ script.md · storyboard.json · meta.json · shorts.md · factcheck.md · titles.md
또한 해외 인기 영상 '한국화 기획안'(localize) 생성."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from . import config
from .ai import load_bibles
from .llm import ai_json, gemini_json

RECIPES = {"R1": "포맷 이식: 원본의 제목·전개 공식을 다른 주제에", "R2": "주제 이식: 같은 주제를 내 채널 포맷으로",
           "R3": "각도 반전: 반론·심화·후속", "R4": "시리즈화", "R5": "롱폼↔쇼츠", "R6": "해외→한국 로컬라이즈"}

PKG_PROMPT = """너는 한국 유튜브 채널 '{group}'의 메인 작가다. 아래 '터진 원본'을 참고해 우리 채널용 새 영상 패키지를 만들어라.
원본 영상·대사·구성을 베끼지 말고 주제와 공식만 차용(재가공 레시피: {recipe}). 얼굴 출연 없이 내레이션+B롤로 제작 가능해야 한다.
[채널 바이블] {bible}
[원본] 제목: {title} / 채널: {channel} / 태그: {tags}
[규칙]
- 내레이션 대본 2,700~3,200자(공백 포함, TTS 약 8~9분). 사실 주장은 일반적으로 알려진 것만, 구체 수치·날짜는 반드시 [확인 필요] 표시
- 투자·건강·법률 주제는 시작과 끝에 면책 문장. 정치 인물 평가·비방 금지. 실존 인물 사생활 금지
- 섹션 7~9개, 각 섹션에 B롤 묘사(얼굴·로고 없는 장면) 1~3개
JSON만:
{{"titles":["제목 5개"],"thumbnail_texts":["썸네일 문구 3개(8자 내외)"],"hooks":["첫 3초 후킹 3개"],
"sections":[{{"name":"섹션명","broll":["B롤 묘사"],"narration":"내레이션(문단은 줄바꿈)"}}],
"tags":["태그 15개"],"fact_checks":["확인 필요한 주장"],"shorts":[{{"title":"쇼츠 제목","text":"140~180자 내레이션"}}],"disclaimer":"면책 문장 또는 빈 문자열"}}"""


def _script_md(pkg: dict, group: str, src: dict) -> str:
    titles = pkg.get("titles")
    title = (titles[0] if isinstance(titles, list) and titles else None) or src.get("title") or "제목 미정"
    L = [f"# ⓒ 대본 AUTO — {title}", f"> 채널: {group} · 자동 생성(Gemini) · 근거: {src.get('title')} ({src.get('channel')})",
         "> 상태: **AI 초안 — factcheck.md 의 [확인 필요] 처리 전 사용 금지**", "", "---", ""]
    t = 0
    for s in pkg.get("sections") or []:
        L.append(f"## [{t // 60}:{t % 60:02d}] {s['name']}")
        if s.get("broll"):
            L.append(f"(B롤: {', '.join(s['broll'])})")
        L += ["", s["narration"].strip(), ""]
        t += int(len(s["narration"]) / 5.5)
    L += ["---", "## 제작 메모", "| 항목 | 내용 |", "|---|---|", f"| 사실 확인 | factcheck.md {len(pkg.get('fact_checks', []))}건 |"]
    return "\n".join(L) + "\n"


def make_package(item: dict, video: dict | None, out_root: Path | None = None) -> Path:
    from .storyboard import build
    group = item.get("group") or "경제적자유구역"
    bibles = load_bibles()
    src = {"title": item.get("title"), "channel": item.get("channel"), "tags": ", ".join(json.loads((video or {}).get("tags") or "[]")[:10])}
    pkg = ai_json(PKG_PROMPT.format(group=group, recipe=RECIPES.get(item.get("recipe") or "R2", "R2"), bible=bibles.get(group, ""),
                                        title=src["title"], channel=src["channel"], tags=src["tags"]), temperature=0.7, quality=True)  # 대본 = 품질 우선 → Claude Opus
    slug = re.sub(r"[^\w-]", "", str(item["id"]))[:20]
    if not pkg.get("titles") or not pkg.get("sections"):   # AI 응답 불량이면 빈 패키지를 만들지 않는다
        raise ValueError("AI 응답에 titles/sections 없음 — 다시 실행하세요")
    d = (out_root or config.EXPORTS_DIR / "packages") / f"{date.today().isoformat()}_{slug}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "script.md").write_text(_script_md(pkg, group, src), encoding="utf-8")
    build(d / "script.md", d, pkg["titles"], pkg.get("tags", []), pkg.get("disclaimer") or None)
    (d / "titles.md").write_text("\n".join(["# 제목·썸네일·후킹", "## 제목", *[f"{i+1}. {x}" for i, x in enumerate(pkg["titles"])],
                                            "## 썸네일 문구", *[f"- {x}" for x in pkg.get("thumbnail_texts", [])],
                                            "## 첫 3초", *[f"- {x}" for x in pkg.get("hooks", [])]]) + "\n", encoding="utf-8")
    (d / "shorts.md").write_text("\n".join([f"# ⓒ 쇼츠 {len(pkg.get('shorts', []))}편 (R5)", ""] +
                                           [f"## 쇼츠 {i+1}. {s['title']}\n\n{s['text']}\n" for i, s in enumerate(pkg.get("shorts", []))]), encoding="utf-8")
    (d / "factcheck.md").write_text("\n".join(["# 팩트체크 목록 (로컬 CC 또는 웹 검색으로 출처 확인 → 대본 수정)", "| # | 주장 | 판정 | 출처 |", "|---|---|---|---|"] +
                                              [f"| {i+1} | {x} | ⏳ |  |" for i, x in enumerate(pkg.get("fact_checks", []))]) + "\n", encoding="utf-8")
    (d / "source.json").write_text(json.dumps({"queue_item": item, "video": {k: (video or {}).get(k) for k in ("video_id", "title", "views", "published_at")}}, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


LOC_PROMPT = """너는 해외 유튜브 대박 영상을 한국 시청자용으로 재기획하는 PD다(R6 로컬라이즈). 원본 번역·짜깁기 금지, 주제와 공식만 차용.
[우리 채널] {bibles}
[해외 영상] {title} / {channel} / 조회 {views}
JSON만: {{"ko_title_meaning":"원제 뜻","why_hit":"왜 터졌나 한 문장","group":"맞는 채널명 또는 null","ko_titles":["한국판 제목 3개"],"ko_angle":"한국 맥락으로 바꾸는 법 한 문장","fit":0~10}}"""


def localize(con, today: str, top: int = 12) -> dict:
    rows = con.execute("""SELECT DISTINCT v.video_id, v.title, v.views, c.category_id FROM chart_daily c JOIN videos v USING(video_id)
                          WHERE c.date=? AND c.category_id LIKE '%:%' AND c.format='long' AND v.lang='other' ORDER BY c.rank LIMIT ?""", (today, top * 2)).fetchall()
    bibles = "; ".join(f"{k}: {v}" for k, v in load_bibles().items())
    out = {}
    for vid, title, views, _ in rows[:top]:
        ch = con.execute("SELECT c.title FROM videos v LEFT JOIN channels c USING(channel_id) WHERE video_id=?", (vid,)).fetchone()
        try:
            out[vid] = gemini_json(LOC_PROMPT.format(bibles=bibles, title=title, channel=(ch[0] if ch else ""), views=views), temperature=0.6)
        except Exception as e:  # noqa: BLE001
            print(f"  한국화 기획 실패 {vid}: {e}")
            break   # 한도·과금 오류 시 나머지 호출 낭비 방지(CC 판정: PA 제안 기각)
    return out
