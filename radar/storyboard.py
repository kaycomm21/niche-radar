"""대본(md) → storyboard.json(B롤 샷리스트) + meta.json(제목·설명·챕터·태그) 자동 변환.
대본 형식: '## [m:ss] 섹션명' 헤더, '(B롤: ...)' 지시, '(자막: ...)' 지시, 본문 = 내레이션."""
from __future__ import annotations

import json
import re
from pathlib import Path

SEC = re.compile(r"^## \[(\d+):(\d\d)\]\s*(.+)$")
BROLL = re.compile(r"^\(B롤:\s*(.+?)\)\s*$")
CAPTION = re.compile(r"\((?:화면 )?자막:\s*(.+?)\)")
CHARS_PER_SEC = 5.5      # 공백 포함 글자/초, Google TTS 한국어 1.0배 대략치 (make_episode 실측 후 보정)

# B롤 한국어 지시 → Flow/Veo 영문 프롬프트 키워드 (얼굴·로고·실존 인물 금지)
STYLE = "cinematic b-roll, 16:9, soft natural light, no text, no logos, no recognizable faces"


def parse(md: str) -> dict:
    title = re.search(r"^# ⓒ 대본 \d+ — (.+)$", md, re.M)
    channel = re.search(r"채널:\s*([^·\n]+)", md)
    body = md.split("\n---\n", 2)[1] if "\n---\n" in md else md
    secs, cur = [], None
    for line in body.splitlines():
        m = SEC.match(line.strip())
        if m:
            cur = {"start_s": int(m.group(1)) * 60 + int(m.group(2)), "name": m.group(3).strip(), "broll": [], "captions": [], "narration": []}
            secs.append(cur)
            continue
        if cur is None or line.startswith("## 제작 메모"):
            if line.startswith("## 제작 메모"):
                break
            continue
        b = BROLL.match(line.strip())
        if b:
            cur["broll"] += [x.strip() for x in b.group(1).split(",")]
            continue
        for c in CAPTION.findall(line):
            cur["captions"].append(c.strip())
        text = CAPTION.sub("", line).strip()
        if text and not text.startswith("("):
            cur["narration"].append(text.replace("**", ""))
    return {"title": title.group(1).strip() if title else "", "channel": channel.group(1).strip() if channel else "", "sections": secs}


def storyboard(doc: dict) -> dict:
    shots, n = [], 0
    for s in doc["sections"]:
        narr = " ".join(s["narration"])
        dur = max(4.0, len(narr) / CHARS_PER_SEC)
        brolls = s["broll"] or ["abstract background matching the topic"]
        per = dur / len(brolls)
        for i, b in enumerate(brolls):
            n += 1
            shots.append({"shot": n, "section": s["name"], "start_hint_s": round(s["start_s"] + i * per, 1),
                          "duration_s": round(per, 1), "broll_ko": b,
                          "prompt_en": f"{b} — {STYLE}", "on_screen_text": s["captions"][:1] or None,
                          "narration_excerpt": narr[:80]})
    return {"title": doc["title"], "channel": doc["channel"], "est_total_s": round(sum(x["duration_s"] for x in shots)),
            "note": "prompt_en 의 한국어 B롤 묘사는 Flow/Veo 입력 전 영어로 다듬을 것. 얼굴·로고·실존 인물 금지.", "shots": shots}


def meta(doc: dict, titles: list[str], tags: list[str], disclaimer: str | None) -> dict:
    # 챕터 시각 = 내레이션 누적 길이로 추정 (렌더 후 실제 오디오 길이로 다시 맞출 것)
    chapters, t = [], 0.0
    for s in doc["sections"]:
        chapters.append(f"{int(t) // 60}:{int(t) % 60:02d} {re.sub(r'[*`]', '', s['name'])}")
        t += len(" ".join(s["narration"])) / CHARS_PER_SEC
    hook = " ".join(doc["sections"][0]["narration"][:3]) if doc["sections"] else ""
    desc = "\n".join([hook, "", "⏱ 목차", *chapters, "", *( [disclaimer] if disclaimer else [] ),
                      "", "#" + " #".join(t.replace(" ", "") for t in tags[:3])])
    return {"title": titles[0], "title_alternatives": titles[1:], "description": desc, "tags": tags[:15], "chapters": chapters,
            "category_id": "27", "default_language": "ko", "privacy": "private", "made_for_kids": False}


def build(md_path: Path, out_dir: Path, titles: list[str], tags: list[str], disclaimer: str | None = None) -> tuple[Path, Path]:
    doc = parse(md_path.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    sp, mp = out_dir / "storyboard.json", out_dir / "meta.json"
    sp.write_text(json.dumps(storyboard(doc), ensure_ascii=False, indent=1), encoding="utf-8")
    mp.write_text(json.dumps(meta(doc, titles, tags, disclaimer), ensure_ascii=False, indent=1), encoding="utf-8")
    return sp, mp
