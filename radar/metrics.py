"""지표 계산 (순수 함수 — 단위 테스트 대상). 모든 산식은 화면에 공개되는 FORMULAS 와 일치해야 한다."""
from __future__ import annotations

import math
from statistics import median as _median

FORMULAS = {
    "outlier": "아웃라이어 배수 = 영상 조회수 ÷ 같은 채널 최근 30편(같은 포맷, 5편 미만이면 전체) 조회수 중앙값",
    "label_fire": "🔥 조회수 터짐 = 아웃라이어 배수 ≥ 3, 또는 업로드 7일 이내 국내 인기 차트 진입",
    "label_money": "💰 수익화 터짐 = 롱폼(8분 이상) + 고RPM(카테고리 RPM 상한 ≥ 5,000원 또는 금융·건강 키워드) + 업로드 30일 이내 + 배수 ≥ 2. 구독자 10만 미만 채널이면 '작은 채널 대박' 가중",
    "label_issue": "📣 이슈화(유튜브 지표만, Brave 미사용) = 24시간 조회 증가가 추적 영상 상위 5% + 24시간 댓글 증가율 ≥ 10%",
    "rework": "재가공 가치 점수 = 터짐 강도 25 + 수익성 20 + 내 채널 적합도 20(AI, Phase 2) + 재현 난이도(역) 15 + 수명 10 + 정책 안전 10. Phase 1은 AI 항목 제외 80점 만점",
    "grade": "투명 등급 = 성장률 30 + 조회 효율 25 + 참여율 20 + 업로드 일관성 15 + 아웃라이어 빈도 10 (각 항목은 유니버스 내 백분위 × 배점, 데이터가 없는 항목은 빼고 100점으로 환산). S≥85 A≥70 B≥55 C≥40 D<40",
    "forecast": "Holt 선형 지수평활(α·β 격자 탐색, 오차제곱합 최소) — 모델 예측이며 보장 아님. 일별 데이터 7일 이상일 때만 계산",
    "revenue": "예상 광고 수익(월) = 최근 30일 업로드 롱폼 조회 × 카테고리 RPM(하한~상한) ÷ 1000 + 쇼츠 조회 × 쇼츠 RPM ÷ 1000. 추정치(실제 수익과 크게 다를 수 있음)",
    "fake": "⚠️ 이상 신호 = 최근 영상 평균 조회 ÷ 구독자 < 5% (NoxInfluencer 공개 기준 인용) 또는 30일 구독 증가 대비 조회 증가 정체",
}

LONG_MIN_S = 480
REUSE_KW = ["하이라이트", "명장면", "직캠", "full ver", "풀영상", "reaction", "리액션", "반응 모음", "몰래카메라 모음", "모음집", "클립 모음"]
RISK_KW = ["무조건", "100%", "반드시 오른다", "폭등 확정", "완치", "사기꾼", "범죄자", "탄핵", "구속"]
POLITICS_KW = ["정치", "대통령", "국회", "여당", "야당", "판결", "검찰", "민주당", "국민의힘"]
FACE_KW = ["브이로그", "vlog", "먹방", "인터뷰", "직접 해봤", "리뷰", "언박싱", "현장", "몰카", "챌린지"]
FACELESS_KW = ["playlist", "플레이리스트", "bgm", "오디오북", "명언", "몰아보기", "역사", "정리", "요약", "이유", "lofi", "모음"]
ISSUE_CATS = {"25", "17", "24"}
EVERGREEN_CATS = {"27", "28", "26", "10", "22"}


def median(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return float(_median(xs)) if xs else None


def outlier_multiple(views: int | None, med: float | None) -> float | None:
    if views is None or not med or med <= 0:
        return None
    return views / med


def percentile_rank(values: list[float], x: float) -> float:
    """0~1. 값 목록에서 x 이하 비율 (동률 절반 처리)."""
    vs = [v for v in values if v is not None]
    if not vs:
        return 0.5
    below = sum(1 for v in vs if v < x)
    equal = sum(1 for v in vs if v == x)
    return (below + 0.5 * equal) / len(vs)


def rpm_for(rpm: dict, category_id: str | None, title: str, is_short: bool, finance_kw, health_kw) -> tuple[float, float]:
    if is_short:
        return rpm.get("shorts", (30, 120))
    lo, hi = rpm.get(str(category_id), rpm.get("default", (800, 2500)))
    t = (title or "").lower()
    if any(k.lower() in t for k in finance_kw):
        m = rpm.get("kw_finance", (1.6, 1.6))
        lo, hi = lo * m[0], hi * m[1]
    elif any(k.lower() in t for k in health_kw):
        m = rpm.get("kw_health", (1.3, 1.3))
        lo, hi = lo * m[0], hi * m[1]
    return lo, hi


def labels(v: dict) -> list[str]:
    """v: multiple, chart_within_7d, duration_s, is_short, rpm_hi, money_kw, age_days, subs, views_24h_pct, comments_24h_growth."""
    out = []
    mult = v.get("multiple") or 0
    if mult >= 3 or v.get("chart_within_7d"):
        out.append("fire")
    if (not v.get("is_short") and (v.get("duration_s") or 0) >= LONG_MIN_S
            and ((v.get("rpm_hi") or 0) >= 5000 or v.get("money_kw"))
            and (v.get("age_days") if v.get("age_days") is not None else 999) <= 30 and mult >= 2):
        out.append("money")
    if (v.get("views_24h_pct") or 0) >= 0.95 and (v.get("comments_24h_growth") or 0) >= 0.10:
        out.append("issue")
    return out


def _has(text: str, kws) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in kws)


def rework_score(v: dict) -> dict:
    """재가공 가치 점수. 반환: {total, max, parts:{...}, excluded, reasons:[...]}"""
    title = v.get("title") or ""
    parts: dict[str, float | None] = {}
    reasons: list[str] = []
    mult = v.get("multiple") or 0
    # 터짐 강도 25: 배수(로그, 10배=20점) + 차트 순위 보너스, 상한 25
    s = 20 * min(1.0, math.log10(max(mult, 1)) / 1.0) if mult else 0
    cr = v.get("chart_rank")
    if cr:
        s = max(s, 25 if cr <= 10 else 20 if cr <= 50 else 12)
    if (v.get("views_24h_pct") or 0) >= 0.9:
        s += 5
    parts["burst"] = round(min(25, s), 1)
    # 수익성 20: RPM 상한(6,000원=만점 기준) × 길이 적합도
    rpm_hi = v.get("rpm_hi") or 0
    dur = v.get("duration_s") or 0
    fit = 0.25 if v.get("is_short") else (1.0 if dur >= LONG_MIN_S else 0.6)
    parts["money"] = round(20 * min(1.0, rpm_hi / 6000) * fit, 1)
    # 내 채널 적합도 20: AI(Gemini) 판정 — Phase 1 미산정
    parts["fit"] = None
    # 재현 난이도(역) 15
    rep = 8
    if _has(title, FACELESS_KW) or v.get("group") in ("음악플레이리스트", "히스토리X", "지혜의숲", "경제적자유구역"):
        rep += 5
    if _has(title, FACE_KW):
        rep -= 6
        reasons.append("얼굴 출연·현장 촬영 신호")
    if v.get("category_id") in ("17", "20"):
        rep -= 3
    parts["replicable"] = float(max(0, min(15, rep)))
    # 수명 10
    issue = v.get("category_id") in ISSUE_CATS or "issue" in (v.get("labels") or [])
    if not issue and v.get("category_id") in EVERGREEN_CATS:
        parts["life"] = 10.0
    elif issue:
        parts["life"] = 7.0 if (v.get("age_days") or 99) <= 2 else 3.0
        reasons.append("이슈성 — 48시간 내 생산할 때만 가치")
    else:
        parts["life"] = 6.0
    # 정책 안전 10
    excluded = False
    pol = 10.0
    if _has(title, REUSE_KW):
        pol, excluded = 0.0, True
        reasons.append("재사용 콘텐츠(짜깁기) 의존 포맷 → 큐 제외")
    else:
        if _has(title, RISK_KW):
            pol -= 5
            reasons.append("단정·비방 표현")
        if _has(title, POLITICS_KW) or v.get("group") == "진영논리":
            pol -= 4
            reasons.append("정치 소재(광고 제한·분쟁 위험)")
    parts["policy"] = max(0.0, pol)
    total = sum(x for x in parts.values() if x is not None)
    if excluded:
        total = 0.0
    return {"total": round(total, 1), "max": 80, "parts": parts, "excluded": excluded, "reasons": reasons}


def suggest_recipe(v: dict) -> tuple[str, str]:
    title = v.get("title") or ""
    if v.get("lang") == "other":
        return "R6", "해외 대박 주제를 한국 맥락으로 로컬라이즈"
    if v.get("is_short"):
        return "R5", "쇼츠 대박 → 롱폼(8분+) 확장으로 수익화"
    if (v.get("multiple") or 0) >= 10:
        return "R4", "1편 대박 → 5편 시리즈 기획"
    if v.get("source") == "seed":
        return "R2", "터진 주제를 내 채널 포맷으로"
    if "이유" in title or "진짜" in title:
        return "R1", "제목·전개 공식을 다른 주제에 이식"
    return "R3", "반론·심화·후속 각도로 재해석"


# ------------------------------------------------------------- 등급
GRADE_WEIGHTS = {"growth": 30, "efficiency": 25, "engagement": 20, "consistency": 15, "outlier_freq": 10}


def grade_letter(score: float) -> str:
    return "S" if score >= 85 else "A" if score >= 70 else "B" if score >= 55 else "C" if score >= 40 else "D"


def grade(features: dict, universe: dict[str, list[float]]) -> dict:
    """features: {growth, efficiency, engagement, consistency, outlier_freq} (None=데이터 없음).
    universe: 같은 키의 유니버스 전체 값 목록 (백분위 계산용)."""
    parts, wsum = {}, 0
    for k, w in GRADE_WEIGHTS.items():
        x = features.get(k)
        if x is None:
            parts[k] = None
            continue
        parts[k] = round(w * percentile_rank(universe.get(k, []), x), 1)
        wsum += w
    raw = sum(p for p in parts.values() if p is not None)
    score = round(raw * 100 / wsum, 1) if wsum else None
    return {"score": score, "letter": grade_letter(score) if score is not None else None,
            "parts": parts, "coverage": wsum}


def upload_consistency(publish_days: list[int]) -> float | None:
    """최근 업로드 간격(일)의 규칙성 0~1: 1/(1+변동계수). 30일 업로드 수 반영은 호출부에서."""
    if len(publish_days) < 3:
        return None
    ds = sorted(publish_days)
    gaps = [b - a for a, b in zip(ds, ds[1:])]
    mean = sum(gaps) / len(gaps)
    if mean <= 0:
        return 1.0
    var = sum((g - mean) ** 2 for g in gaps) / len(gaps)
    return 1 / (1 + math.sqrt(var) / mean)


# ------------------------------------------------------------- Holt 예측
def holt_fit(ys: list[float], alpha: float, beta: float) -> tuple[float, float, float]:
    level, trend = ys[0], ys[1] - ys[0]
    sse = 0.0
    for y in ys[1:]:
        pred = level + trend
        sse += (y - pred) ** 2
        new_level = alpha * y + (1 - alpha) * (level + trend)
        trend = beta * (new_level - level) + (1 - beta) * trend
        level = new_level
    return level, trend, sse


def holt_forecast(ys: list[float], horizons=(30, 90, 365)) -> dict | None:
    ys = [float(y) for y in ys if y is not None]
    if len(ys) < 7:
        return None
    best = None
    grid = [i / 10 for i in range(1, 10)]
    for a in grid:
        for b in grid:
            lv, tr, sse = holt_fit(ys, a, b)
            if best is None or sse < best[2]:
                best = (lv, tr, sse, a, b)
    lv, tr, _, a, b = best
    return {"alpha": a, "beta": b, "level": lv, "trend_per_day": tr,
            "forecast": {str(h): max(0.0, lv + tr * h) for h in horizons}}


def milestone_days(current: float, trend_per_day: float, target: float, max_days: int = 3650) -> int | None:
    """목표 도달까지 일수. 감소 추세이거나 10년 넘게 걸리면 None (예측 의미 없음)."""
    if current >= target:
        return 0
    if trend_per_day <= 0:
        return None
    d = math.ceil((target - current) / trend_per_day)
    return d if d <= max_days else None
