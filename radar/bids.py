"""🏛 입찰레이더: 조달청 나라장터 입찰공고(용역) 공식 오픈API → 행사·축제 공고 수집 → 수주 적합도 → 제안서 초안.

키: env DATA_GO_KR_KEY (공공데이터포털 '조달청_나라장터 입찰공고정보서비스' 활용신청 후 발급, 일반 인증키 Decoding)
엔드포인트는 env BID_API_BASE / BID_API_OP 로 바꿀 수 있다 (포털 활용가이드 기준).
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config

BASE = os.environ.get("BID_API_BASE", "https://apis.data.go.kr/1230000/ad/BidPublicInfoService")
OP = os.environ.get("BID_API_OP", "getBidPblancListInfoServcPPSSrch")
KEYWORDS = ["축제", "페스티벌", "행사", "공연", "기념식", "개막", "불꽃", "콘서트", "박람회", "체육대회", "문화제", "한마당", "대행", "연출"]
HOME = "대구|경북|경상북도|포항|경주|구미|영천|경산|안동|김천|상주|영주|문경|칠곡|달성|청도|성주|고령|의성|군위|예천|봉화|울진|영덕|청송|영양|울릉"
NEAR = "부산|울산|경남|경상남도|창원|김해|충북|강원"
OTHER = "부산|울산|서울|경기|인천|광주광역|대전|세종|강원|충청|충북|충남|전라|전북|전남|경남|경상남도|제주"
STRONG = "축제|페스티벌|개막|폐막|불꽃|체전|체육대회|공연|콘서트|기념식|개회식|폐회식"


def load_projects() -> dict[str, str]:
    out = {}
    for line in (config.ROOT / "config" / "my_projects.yaml").read_text(encoding="utf-8").splitlines():
        m = re.match(r'^\s*"([^"]+)"\s*:\s*"(.+)"\s*$', line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def _num(x) -> int | None:
    try:
        return int(float(str(x).replace(",", ""))) if x not in (None, "") else None
    except ValueError:
        return None


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y%m%d%H%M"):
        try:
            return datetime.strptime(s.strip(), f)
        except ValueError:
            pass
    return None


def fetch(key: str, days: int = 14, rows: int = 100) -> list[dict]:
    end = datetime.now()
    begin = end - timedelta(days=days)
    seen, out = set(), []
    for kw in KEYWORDS:
        q = {"serviceKey": key, "pageNo": 1, "numOfRows": rows, "type": "json", "inqryDiv": 1,
             "inqryBgnDt": begin.strftime("%Y%m%d0000"), "inqryEndDt": end.strftime("%Y%m%d2359"), "bidNtceNm": kw}
        url = f"{BASE}/{OP}?" + urllib.parse.urlencode(q, safe="%")
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 — 키워드 하나 실패로 전체 중단 안 함
            print(f"  입찰 API 실패({kw}): {type(e).__name__}")
            continue
        body = (d.get("response") or {}).get("body") or {}
        items = body.get("items") or []
        if isinstance(items, dict):
            items = items.get("item") or []
        if isinstance(items, dict):
            items = [items]
        for it in items:
            k = (it.get("bidNtceNo"), it.get("bidNtceOrd"))
            if k not in seen:
                seen.add(k)
                out.append(it)
    return out


def score(it: dict, today: date, projects: dict[str, str]) -> dict:
    name = it.get("bidNtceNm", "")
    org = f"{it.get('ntceInsttNm', '')} {it.get('dminsttNm', '')}"
    budget = _num(it.get("asignBdgtAmt")) or _num(it.get("presmptPrce"))
    close = _dt(it.get("bidClseDt"))
    method = it.get("cntrctCnclsMthdNm") or ""
    parts, why = {}, []
    other = re.search(OTHER, org)        # '해운대구'처럼 '대구'가 들어간 타 지역 오인 방지
    parts["region"] = 25 if (re.search(HOME, org) and not other) else (10 if re.search(NEAR, org) else 0)
    if parts["region"] == 25:
        why.append("대구·경북 (홈그라운드)")
    if budget is None:
        parts["budget"] = 8
    elif 100_000_000 <= budget <= 1_000_000_000:
        parts["budget"] = 25
    elif budget > 1_000_000_000:
        parts["budget"] = 15
    elif budget >= 50_000_000:
        parts["budget"] = 12
    else:
        parts["budget"] = 5
    parts["method"] = 20 if "협상" in method else 5
    if "협상" in method:
        why.append("협상에 의한 계약 = 제안서 평가 (기획력 승부)")
    parts["topic"] = 20 if re.search(STRONG, name) else (10 if re.search("행사|박람회|대행|연출|문화", name) else 0)
    hits = [v for k, v in projects.items() if k in name]
    parts["experience"] = 10 if hits else 0
    if hits:
        why.append("유사 실적: " + hits[0])
    dleft = (close.date() - today).days if close else None
    parts["deadline"] = -50 if dleft is not None and dleft < 0 else (10 if dleft is None or dleft >= 10 else 5 if dleft >= 5 else -10)
    total = max(0, min(100, sum(parts.values())))
    return {"no": f"{it.get('bidNtceNo')}-{it.get('bidNtceOrd', '00')}", "name": name, "org": it.get("ntceInsttNm"), "demand": it.get("dminsttNm"),
            "budget": budget, "method": method, "kind": it.get("ntceKindNm"), "posted": it.get("bidNtceDt"), "close": it.get("bidClseDt"),
            "open": it.get("opengDt"), "dleft": dleft, "url": it.get("bidNtceDtlUrl") or f"https://www.g2b.go.kr/", "score": total,
            "parts": parts, "why": why, "matches": hits}


def build(raw: list[dict], today: date) -> list[dict]:
    projects = load_projects()
    items = [score(it, today, projects) for it in raw]
    items = [x for x in items if x["dleft"] is None or x["dleft"] >= 0]
    return sorted(items, key=lambda x: (-x["score"], x["dleft"] if x["dleft"] is not None else 99))


def fixture(today: date) -> list[dict]:
    """키 없을 때 테스트용 (화면에는 '예시 데이터' 표시)."""
    def mk(no, name, org, budget, method, days):
        c = datetime.combine(today + timedelta(days=days), datetime.min.time()) + timedelta(hours=10)
        return {"bidNtceNo": no, "bidNtceOrd": "000", "bidNtceNm": name, "ntceInsttNm": org, "dminsttNm": org,
                "asignBdgtAmt": str(budget), "cntrctCnclsMthdNm": method, "bidClseDt": c.strftime("%Y-%m-%d %H:%M:%S"),
                "bidNtceDt": today.strftime("%Y-%m-%d 09:00:00"), "ntceKindNm": "일반", "bidNtceDtlUrl": "https://www.g2b.go.kr/"}
    return [mk("R26BK00000001", "2027 포항국제불빛축제 기획·운영 대행 용역", "경상북도 포항시", 1_800_000_000, "협상에 의한 계약", 21),
            mk("R26BK00000002", "제62회 경북도민체육대회 개·폐회식 행사 대행", "경상북도 체육회", 650_000_000, "협상에 의한 계약", 12),
            mk("R26BK00000003", "2026 시민 화합 한마당 공연 운영", "부산광역시 해운대구", 90_000_000, "적격심사", 6),
            mk("R26BK00000004", "청사 조경 유지관리 용역", "서울특별시", 40_000_000, "최저가", 9)]


def run(out_path: Path, today: date) -> dict:
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if key:
        raw, mode = fetch(key), "live"
    else:
        raw, mode = fixture(today), "fixture"
    items = build(raw, today)
    data = {"date": today.isoformat(), "mode": mode, "count": len(items), "items": items[:200],
            "formula": "적합도 = 지역(대구·경북 25 / 인접 10) + 예산(1~10억 25) + 계약방식(협상 20) + 주제(축제·개폐회식 등 20) + 실적유사 10 + 마감여유(10일↑ 10, 3일 미만 -10)"}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    snap = config.DB_PATH.parent / "bids_state.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(json.dumps({x["no"]: x for x in items}, ensure_ascii=False), encoding="utf-8")
    print(f"입찰 공고 {len(items)}건 ({mode})")
    return data


PROPOSAL_PROMPT = """너는 16년 차 행사·축제 기획사 기획총괄이다. 아래 나라장터 공고에 낼 기술제안서의 '초안 뼈대'를 만들어라.
과업지시서는 아직 못 읽었으니 공고명·기관·예산으로 추론한 부분은 반드시 [과업지시서 확인] 표시. 수치는 만들지 말고 비율·항목만.
[공고] {name} / 기관 {org} / 수요기관 {demand} / 예산 {budget}원 / 계약방식 {method} / 마감 {close}
[우리 유사 실적] {matches}
JSON만: {{"one_line":"제안 한 줄 컨셉","situation":["과업 이해 포인트 5개"],"concepts":[{{"name":"컨셉명","slogan":"슬로건","core":"핵심 아이디어 2문장"}} x3],
"toc":["제안서 목차(협상계약 기술평가 일반 항목 반영) 10~14개"],"program":["주요 프로그램 구성 6~10개"],
"budget_split":[{{"item":"항목","ratio":"%"}}],"schedule":["추진 일정 단계 6개"],"risks":["리스크와 대응 4개"],"questions":["과업지시서·질의응답에서 확인할 것 5개"]}}"""


def proposal(item: dict, out_root: Path | None = None) -> Path:
    from .llm import available, gemini_json
    projects = load_projects()
    matches = [v for k, v in projects.items() if k in (item.get("name") or "")] or list(projects.values())[:3]
    if available():
        p = gemini_json(PROPOSAL_PROMPT.format(name=item.get("name"), org=item.get("org"), demand=item.get("demand"), budget=item.get("budget"),
                                               method=item.get("method"), close=item.get("close"), matches="; ".join(matches)), temperature=0.7)
        by = "Gemini"
    else:
        p = {"one_line": f"{item.get('name')} — [컨셉 미정: AI 키 연결 후 자동 생성]", "situation": ["[과업지시서 확인] 행사 목적", "대상·규모", "장소·동선", "예산 구조", "평가 기준"],
             "concepts": [], "toc": ["Ⅰ. 제안 개요", "Ⅱ. 과업 이해 및 분석", "Ⅲ. 기본 컨셉", "Ⅳ. 세부 프로그램", "Ⅴ. 무대·연출 계획", "Ⅵ. 운영·안전 계획", "Ⅶ. 홍보 계획", "Ⅷ. 추진 일정", "Ⅸ. 예산 계획", "Ⅹ. 수행 조직 및 실적"],
             "program": [], "budget_split": [], "schedule": [], "risks": [], "questions": []}
        by = "규칙 기반 템플릿"
    slug = re.sub(r"[^\w-]", "", str(item.get("no")))[:30]
    d = (out_root or config.EXPORTS_DIR / "proposals") / f"{date.today().isoformat()}_{slug}"
    d.mkdir(parents=True, exist_ok=True)
    L = [f"# ⓒ 제안서 초안 — {item.get('name')}", f"> 기관 {item.get('org')} · 예산 {item.get('budget') or '-'}원 · {item.get('method')} · 마감 {item.get('close')} · 생성: {by}",
         f"> 공고: {item.get('url')}", "", f"## 한 줄 컨셉\n{p.get('one_line', '')}", "", "## 과업 이해", *[f"- {x}" for x in p.get("situation", [])], "",
         "## 컨셉 3안", *[f"### {i+1}. {c.get('name')} — {c.get('slogan')}\n{c.get('core')}" for i, c in enumerate(p.get("concepts", []))], "",
         "## 제안서 목차", *[f"{i+1}. {x}" for i, x in enumerate(p.get("toc", []))], "", "## 주요 프로그램", *[f"- {x}" for x in p.get("program", [])], "",
         "## 예산 배분(비율)", "| 항목 | 비율 |", "|---|---|", *[f"| {b.get('item')} | {b.get('ratio')} |" for b in p.get("budget_split", [])], "",
         "## 추진 일정", *[f"- {x}" for x in p.get("schedule", [])], "", "## 리스크·대응", *[f"- {x}" for x in p.get("risks", [])], "",
         "## 과업지시서·질의에서 확인할 것", *[f"- [ ] {x}" for x in p.get("questions", [])], "", "## 유사 실적 (자동 매칭)", *[f"- {m}" for m in matches]]
    (d / "proposal.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (d / "source.json").write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
    return d
