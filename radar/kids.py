"""🐷 부자아이 공방: 금융 개념 1개 → 그림책 원고(12장면) · 활동지 · 부모 가이드 · 쇼츠 대본.
입력: GitHub Issue (```json {"action":"kids","concept":..,"age":..}```). 출력: exports/kids/<날짜>_<slug>/"""
from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path

from . import config
from .llm import gemini_json

AGES = {"3-5": "만 3~5세(유아): 문장 짧게, 의성어·반복, 숫자는 5 이하", "6-7": "만 6~7세(예비 초등): 10 이하 숫자, 선택과 기다림",
        "8-10": "초등 저학년: 용돈·저축·필요와 욕구", "11-13": "초등 고학년: 이자·예산·광고 읽기·투자 기초"}

PROMPT = """너는 유아·어린이 금융교육 그림책 작가이자 초등 교사다. 개념 '{concept}'을 {age_desc} 아이에게 가르치는 세트를 만들어라.
- 한국 가정의 일상 장면(시장, 편의점, 저금통, 쌍둥이 형제 '단우와 도하' 같은 등장인물 가능), 겁주기·소비 죄책감 금지, 특정 은행·상품·브랜드 금지
- 그림책은 12장면, 장면마다 그림 지시(삽화 프롬프트용)와 짧은 글
JSON만: {{"title":"책 제목","one_line":"핵심 메시지","scenes":[{{"no":1,"text":"본문","illustration":"그림 지시"}}],
"worksheet":[{{"q":"활동/문항","type":"색칠|선잇기|빈칸|그리기|역할놀이","answer":"정답 또는 예시"}}],
"parent_guide":["부모가 할 말·놀이 5개"],"shorts":[{{"title":"쇼츠 제목","text":"130~170자"}}],"keywords":["태그 10개"]}}"""


def run(body: str, number: str, out_root: Path | None = None) -> Path:
    m = re.search(r"```json\s*(\{.*?\})\s*```", body, re.S)
    cfg = json.loads(m.group(1)) if m else {}
    age = cfg.get("age", "3-5")
    k = gemini_json(PROMPT.format(concept=cfg.get("concept", "저축"), age_desc=AGES.get(age, AGES["3-5"])), temperature=0.8)
    slug = re.sub(r"[^\w-]", "", cfg.get("concept", "kids"))[:20] or "kids"
    d = (out_root or config.EXPORTS_DIR / "kids") / f"{date.today().isoformat()}_{slug}_{age}"
    d.mkdir(parents=True, exist_ok=True)
    book = [f"# {k['title']}", f"> {k.get('one_line', '')} · 대상 {AGES.get(age)}", ""]
    for s in k.get("scenes", []):
        book += [f"## 장면 {s['no']}", s["text"], f"*🎨 그림: {s['illustration']}*", ""]
    (d / "picturebook.md").write_text("\n".join(book), encoding="utf-8")
    e = html.escape
    rows = "".join(f"<li><b>[{e(w.get('type', ''))}]</b> {e(w['q'])}<div class='blank'></div></li>" for w in k.get("worksheet", []))
    (d / "worksheet.html").write_text(f"""<!doctype html><html lang="ko"><meta charset="utf-8"><title>{e(k['title'])} 활동지</title>
<style>body{{font-family:sans-serif;max-width:720px;margin:24px auto;font-size:18px}}li{{margin:18px 0}}.blank{{border-bottom:2px dashed #aaa;height:60px}}@media print{{button{{display:none}}}}</style>
<h1>🐷 {e(k['title'])}</h1><p>이름: ________ 날짜: ________</p><ol>{rows}</ol><button onclick="print()">인쇄하기</button></html>""", encoding="utf-8")
    (d / "answers_and_guide.md").write_text("\n".join(["# 정답·부모 가이드", "## 정답/예시", *[f"- {w['q']} → {w.get('answer', '')}" for w in k.get("worksheet", [])],
                                                      "## 부모 가이드", *[f"- {x}" for x in k.get("parent_guide", [])]]), encoding="utf-8")
    (d / "shorts.md").write_text("\n".join(["# 쇼츠 (부자아이 채널)", *[f"## {s['title']}\n{s['text']}\n" for s in k.get("shorts", [])], "", "태그: " + ", ".join(k.get("keywords", []))]), encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"title": k["title"], "concept": cfg.get("concept"), "age": age, "issue": number}, ensure_ascii=False), encoding="utf-8")
    return d
