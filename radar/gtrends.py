"""구글 트렌드(한국 실시간 급상승 검색어 RSS) → 내 채널 그룹 매핑 → 콘텐츠 기획안.
RSS: https://trends.google.com/trending/rss?geo=KR (구글 공식 공개 피드, 키 불필요)
기획안: GEMINI_API_KEY 가 있으면 AI, 없으면 규칙 기반 템플릿."""
from __future__ import annotations

import json
import re
import urllib.request
import xml.etree.ElementTree as ET

from .collect import assign_group

RSS = "https://trends.google.com/trending/rss?geo=KR"
NS = {"ht": "https://trends.google.com/trending/rss"}


def fetch(url: str = RSS, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ccs-radar/1.0)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def parse(xml: str) -> list[dict]:
    root = ET.fromstring(xml)
    out = []
    for it in root.iter("item"):
        def t(tag):
            el = it.find(tag, NS)
            return el.text.strip() if el is not None and el.text else None
        news = []
        for n in it.findall("ht:news_item", NS):
            news.append({"title": (n.findtext("ht:news_item_title", default="", namespaces=NS) or "").strip(),
                         "url": n.findtext("ht:news_item_url", default="", namespaces=NS),
                         "source": n.findtext("ht:news_item_source", default="", namespaces=NS)})
        title = (it.findtext("title") or "").strip()
        traffic = t("ht:approx_traffic")
        out.append({"kw": title, "traffic": traffic, "traffic_n": int(re.sub(r"\D", "", traffic or "0") or 0),
                    "pub": it.findtext("pubDate"), "picture": t("ht:picture"), "news": news[:3]})
    return out


TEMPLATES = {
    "경제적자유구역": ["'{kw}' 뉴스, 내 지갑에는 무슨 일이? 3분 정리", "{kw} 때문에 손해 보는 사람 vs 이득 보는 사람", "{kw}, 지금 개인이 확인할 체크리스트 3가지"],
    "히스토리X": ["{kw}의 뒤에 숨은 진짜 역사", "역사는 반복된다: {kw}와 꼭 닮은 과거 사건", "{kw}, 100년 전에도 똑같은 일이 있었다"],
    "지혜의숲": ["{kw}을(를) 보며 생각한 인생의 지혜", "{kw} 같은 일이 생겼을 때 오래 산 사람들의 조언"],
    None: ["{kw}, 지금 왜 다들 검색할까? 핵심만 정리", "{kw} 총정리: 사실 / 쟁점 / 앞으로"],
}


def rule_plan(item: dict) -> dict:
    g = assign_group(item["kw"] + " " + " ".join(n["title"] for n in item["news"]))
    titles = [x.format(kw=item["kw"]) for x in TEMPLATES.get(g, TEMPLATES[None])]
    return {"group": g, "titles": titles, "hook": f"지금 '{item['kw']}'를 검색한 사람이 수만 명입니다. 뉴스만 봐서는 모르는 핵심을 정리합니다.",
            "outline": ["무슨 일인가 (사실만, 출처 표기)", "왜 지금 화제인가", "내 삶·지갑과의 연결고리", "오해와 사실", "한 줄 정리 + 다음 편 예고"],
            "life": "이슈(48시간 내 생산할 때만 가치)", "by": "규칙 기반"}


PROMPT = """너는 한국 유튜브 다채널 운영사의 기획 PD다. 아래 '구글 급상승 검색어'를 우리 채널용 콘텐츠로 기획해라.
사실은 아래 뉴스 제목 범위 안에서만 쓰고, 추측은 '확인 필요'로 표시해라. 정치 인물 평가·비방 금지.
[우리 채널] {bibles}
[검색어] {kw} (검색량 {traffic})
[관련 뉴스] {news}
JSON만: {{"group":"채널명 또는 null","titles":["제목 5개"],"hook":"첫 3초 후킹 한 문장","outline":["비트 5~7개"],"life":"이슈|에버그린","blog_angle":"블로그 글 각도 한 문장","risk":"주의점 한 문장"}}"""


def ai_plan(item: dict) -> dict:
    from .ai import load_bibles
    from .llm import gemini_json
    d = gemini_json(PROMPT.format(bibles="; ".join(f"{k}: {v}" for k, v in load_bibles().items()), kw=item["kw"],
                                  traffic=item["traffic"], news=" / ".join(n["title"] for n in item["news"])), temperature=0.5)
    d["by"] = "Gemini"
    return d


def build(items: list[dict], use_ai: bool, ai_cap: int = 10) -> list[dict]:
    out = []
    for i, it in enumerate(sorted(items, key=lambda x: -x["traffic_n"])):
        plan = None
        if use_ai and i < ai_cap:
            try:
                plan = ai_plan(it)
            except Exception as e:  # noqa: BLE001
                print(f"  AI 기획 실패({it['kw']}): {e}")
        out.append({**it, "plan": plan or rule_plan(it)})
    return out


def run(out_path, today: str) -> int:
    import os
    try:
        items = parse(fetch())
    except Exception as e:  # noqa: BLE001
        print(f"구글 트렌드 수집 실패: {e}")
        return 0
    data = {"date": today, "source": RSS, "items": build(items, __import__("radar.llm", fromlist=["x"]).available())}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"구글 트렌드 {len(items)}건")
    return len(items)
