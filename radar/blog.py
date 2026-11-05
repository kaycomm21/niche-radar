"""✍️ 블로그 스튜디오: 키워드 → 글 / 막 쓴 초안 → 사람이 쓴 듯한 글 + 사진 자동 배치 + 내 유튜브 임베드.
입력: GitHub Issue 본문 (```json 설정``` + '## 초안' 이하 자유 텍스트 + 첨부 사진). 출력: exports/blog/<날짜>_<슬러그>/
  wordpress.html (그대로 붙여넣기) · naver.txt (네이버 에디터용, [사진 n] 위치 표시) · meta.json (제목·설명·태그) · review.md (검수 체크리스트)
"""
from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path

from . import config
from .llm import gemini_json

IMG = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)|<img[^>]+src=\"(https?://[^\"]+)\"")
YT = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/)([\w-]{11})")


def parse_issue(body: str) -> dict:
    m = re.search(r"```json\s*(\{.*?\})\s*```", body, re.S)
    cfg = json.loads(m.group(1)) if m else {}
    draft = ""
    dm = re.search(r"##\s*초안\s*\n(.*)", body, re.S)
    if dm:
        draft = IMG.sub("", dm.group(1)).strip()
    images = [a or b for a, b in IMG.findall(body)]
    if cfg.get("package"):                      # 📦 생산 패키지 대본 → 블로그 글 (영상 1편 = 글 1편)
        sp = config.ROOT / cfg["package"] / "script.md"
        if sp.exists():
            txt = sp.read_text(encoding="utf-8")
            txt = re.sub(r"^\(B롤:.*\)$|^>.*$|^#.*$", "", txt, flags=re.M)
            draft = (draft + "\n\n" + txt.split("## 제작 메모")[0]).strip()
            cfg["mode"] = "rewrite"
    return {**cfg, "draft": draft or cfg.get("draft", ""), "images": images}


STYLE = """[문체 규칙 — 사람이 쓴 블로그처럼]
- 1인칭 경험자 말투("~했어요", "~더라고요"), 문단은 2~4문장, 한 문단에 한 가지 생각
- AI 티 나는 표현 금지: "결론적으로", "~라고 할 수 있습니다", "다양한", "중요합니다" 반복, 과한 이모지, 뻔한 서론
- 구체적인 숫자·예시·장면을 넣되, 확인 안 된 사실은 만들지 말고 fact_checks 에 '확인 필요'로 적기
- 글쓴이 경험이 들어가야 할 자리에 [✍️ 직접 경험 한 줄] 표시를 2곳 남기기 (구글 E-E-A-T, 네이버 C-Rank 대응)
- 검색 의도에 바로 답하는 첫 문단, 소제목은 질문형·키워드 포함"""

PROMPT = """너는 16년 차 행사 기획자이자 유튜버인 블로거의 대필 에디터다.
{task}
{style}
[대상 플랫폼] {platforms} · 분량 약 {length}자 · 톤: {tone}
[사진] {n_img}장 — 섹션마다 어울리는 사진 설명(image_hint)을 붙여라
JSON만 출력:
{{"title":"검색형 제목(32자 이내, 키워드 앞쪽)","alt_titles":["대안 2개"],"slug":"영문-소문자-하이픈","meta_description":"120자 이내",
"tags":["태그 10개"],"intro":"첫 문단","sections":[{{"h2":"소제목","paragraphs":["문단",...],"image_hint":"이 자리에 어울리는 사진"}}],
"checklist":["독자가 바로 할 일 3~5개"],"faq":[{{"q":"질문","a":"답"}}],"outro":"마무리 문단(유튜브 영상으로 자연스럽게 연결)","fact_checks":["확인 필요한 사실 주장"]}}"""


def make_prompt(cfg: dict) -> str:
    if cfg.get("mode") == "rewrite" and cfg.get("draft"):
        task = f"아래 '막 쓴 초안'의 내용·경험·주장을 살려서, 구조를 잡고 읽기 좋은 블로그 글로 다시 써라. 초안에 없는 사실은 추가하지 마라.\n[초안]\n{cfg['draft'][:8000]}"
    else:
        task = f"키워드 '{cfg.get('keyword', '')}'로 검색하는 사람이 끝까지 읽고 저장하고 싶은 블로그 글을 써라. 핵심 키워드는 제목·첫 문단·소제목 1개에 자연스럽게."
        if cfg.get("draft"):
            task += f"\n[참고 메모]\n{cfg['draft'][:3000]}"
    return PROMPT.format(task=task, style=STYLE, platforms=", ".join(cfg.get("platforms") or ["wordpress", "naver"]),
                         length=cfg.get("length", 2500), tone=cfg.get("tone", "친근한 전문가"), n_img=len(cfg.get("images", [])))


def place_images(n_sections: int, images: list[str]) -> dict[int, list[str]]:
    """사진을 섹션에 고르게 배치: 섹션 i 의 소제목 바로 아래. 남는 사진은 마지막 섹션 뒤."""
    out: dict[int, list[str]] = {}
    if not images or not n_sections:
        return {n_sections: list(images)} if images else {}
    for k, url in enumerate(images):
        i = min(n_sections - 1, k * n_sections // len(images)) if len(images) <= n_sections else (k if k < n_sections else n_sections)
        out.setdefault(i, []).append(url)
    return out


def youtube_block(url: str | None, channel_url: str | None) -> tuple[str, str]:
    m = YT.search(url or "")
    if not m:
        return "", ""
    vid = m.group(1)
    sub = f'<p><a href="{html.escape(channel_url)}?sub_confirmation=1" target="_blank" rel="noopener">▶ 유튜브 채널 구독하고 새 영상 받아보기</a></p>' if channel_url else ""
    h = (f'<h2>영상으로 더 자세히 보기</h2>\n<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden">'
         f'<iframe src="https://www.youtube.com/embed/{vid}" title="YouTube video" style="position:absolute;top:0;left:0;width:100%;height:100%" '
         f'frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>\n{sub}')
    t = f"\n■ 영상으로 더 자세히 보기\n(네이버 에디터에서 '동영상 → 유튜브 링크'로 넣으세요) https://www.youtube.com/watch?v={vid}\n" + (f"▶ 구독하기: {channel_url}?sub_confirmation=1\n" if channel_url else "")
    return h, t


def render(post: dict, cfg: dict) -> tuple[str, str]:
    imgs = place_images(len(post.get("sections", [])), cfg.get("images", []))
    e = html.escape
    H = [f"<p>{e(post.get('intro', ''))}</p>"]
    T = [post.get("intro", ""), ""]
    n = 0
    for i, s in enumerate(post.get("sections", [])):
        H.append(f"<h2>{e(s['h2'])}</h2>")
        T.append(f"■ {s['h2']}")
        for url in imgs.get(i, []):
            n += 1
            alt = e(s.get("image_hint") or s["h2"])
            H.append(f'<figure><img src="{e(url)}" alt="{alt}" loading="lazy" /><figcaption>{alt}</figcaption></figure>')
            T.append(f"[사진 {n}: {s.get('image_hint') or s['h2']}]")
        for p in s.get("paragraphs", []):
            H.append(f"<p>{e(p)}</p>")
            T.append(p)
        T.append("")
    for url in imgs.get(len(post.get("sections", [])), []):
        n += 1
        H.append(f'<figure><img src="{e(url)}" alt="" loading="lazy" /></figure>')
        T.append(f"[사진 {n}]")
    if post.get("checklist"):
        H.append("<h2>오늘 바로 해볼 것</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in post["checklist"]) + "</ul>")
        T += ["■ 오늘 바로 해볼 것"] + [f"✔ {x}" for x in post["checklist"]] + [""]
    if post.get("faq"):
        H.append("<h2>자주 묻는 질문</h2>" + "".join(f"<h3>Q. {e(f['q'])}</h3><p>{e(f['a'])}</p>" for f in post["faq"]))
        T += ["■ 자주 묻는 질문"] + [f"Q. {f['q']}\nA. {f['a']}" for f in post["faq"]] + [""]
    H.append(f"<p>{e(post.get('outro', ''))}</p>")
    T.append(post.get("outro", ""))
    yh, yt = youtube_block(cfg.get("youtube"), cfg.get("channel_url"))
    if yh:
        H.append(yh)
        T.append(yt)
    return "\n".join(H), "\n".join(T)


def review_md(post: dict, cfg: dict) -> str:
    fc = post.get("fact_checks") or []
    return "\n".join([f"# 검수 체크리스트 — {post.get('title')}", "",
                      "| # | 할 일 | 완료 |", "|---|---|---|",
                      "| 1 | `[✍️ 직접 경험 한 줄]` 2곳을 내 경험으로 채우기 (안 채우면 발행 금지) | ☐ |",
                      "| 2 | 아래 사실 확인 항목 출처 확인 또는 삭제 | ☐ |",
                      "| 3 | 사진 위치·설명 확인 (네이버는 [사진 n] 자리에 직접 올리기) | ☐ |",
                      "| 4 | 제목·대안 제목 중 선택, 태그 확인 | ☐ |",
                      "| 5 | 같은 주제로 이번 주 이미 쓴 글이 없는지 (주 2~3편 원칙) | ☐ |", "",
                      "## 사실 확인 필요", *([f"- {x}" for x in fc] or ["- 없음"]), "",
                      f"> 생성 모드: {cfg.get('mode')} · 키워드: {cfg.get('keyword') or '-'} · 사진 {len(cfg.get('images', []))}장"])


def run(body: str, number: str, out_root: Path | None = None) -> Path:
    cfg = parse_issue(body)
    post = gemini_json(make_prompt(cfg), temperature=0.8)
    wp, nv = render(post, cfg)
    slug = re.sub(r"[^a-z0-9-]", "", (post.get("slug") or "post").lower())[:50] or "post"
    d = (out_root or config.EXPORTS_DIR / "blog") / f"{date.today().isoformat()}_{slug}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "wordpress.html").write_text(wp, encoding="utf-8")
    (d / "naver.txt").write_text(f"{post.get('title')}\n\n{nv}\n\n#{' #'.join(t.replace(' ', '') for t in post.get('tags', []))}\n", encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({k: post.get(k) for k in ("title", "alt_titles", "slug", "meta_description", "tags")} | {"issue": number, "mode": cfg.get("mode")}, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "review.md").write_text(review_md(post, cfg), encoding="utf-8")
    return d
