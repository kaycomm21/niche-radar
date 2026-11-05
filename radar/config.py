"""경로·상수·설정 파일 로더. 외부 라이브러리 없이 표준 라이브러리만 사용."""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("RADAR_DATA_DIR", ROOT / "data"))
DB_PATH = Path(os.environ.get("RADAR_DB", DATA_DIR / "radar.db"))
WEB_DATA_DIR = Path(os.environ.get("RADAR_WEB_DATA", ROOT / "web" / "public" / "data"))
EXPORTS_DIR = Path(os.environ.get("RADAR_EXPORTS", ROOT / "exports"))
SEED_PATH = ROOT / "seed" / "refs_channels_verified_20261017.json"
RPM_PATH = ROOT / "config" / "rpm_kr.yaml"

# 하루 쿼터 예산 (YouTube 기본 10,000 중 여유 20%)
QUOTA_BUDGET = int(os.environ.get("RADAR_QUOTA_BUDGET", "8000"))
SEARCH_DAILY_CAP = 20          # search.list(100유닛) 하루 최대 호출 수
UNIVERSE_CAP = 2000            # 유니버스 채널 상한
CHART_PAGES = int(os.environ.get("RADAR_CHART_PAGES", "4"))   # 카테고리당 최대 4페이지 × 50 = 200위
RECENT_PER_CHANNEL = 30        # 채널 최근 영상 수 (아웃라이어 중앙값 기준)

# 데이터 보존 (README '보존 정책' 참고)
SNAPSHOT_RETENTION_DAYS = int(os.environ.get("RADAR_SNAPSHOT_DAYS", "365"))   # channel_daily
VIDEO_SNAPSHOT_DAYS = 14       # video_daily (업로드 30일 이내 영상의 일별 스냅샷, 14일 보존)
CHART_RETENTION_DAYS = 30      # chart_daily (순위 변동·주간 비교용)
STALE_DAYS = 30                # 30일 동안 갱신 못 한 채널·영상 메타데이터는 삭제

REGION = "KR"
# 국내 인기 차트 카테고리 ("0" = 전체). 일부 카테고리는 차트가 없을 수 있음(404 → 건너뜀)
CHART_CATEGORIES = {
    "0": "전체", "1": "영화/애니", "2": "자동차", "10": "음악", "15": "반려동물",
    "17": "스포츠", "20": "게임", "22": "인물/블로그", "23": "코미디",
    "24": "엔터테인먼트", "25": "뉴스/정치", "26": "노하우/스타일", "27": "교육",
    "28": "과학기술", "19": "여행",
}
CATEGORY_NAMES = {**CHART_CATEGORIES, "29": "비영리"}
# 해외 레퍼런스 차트 (한국화 재생산용): (지역, 카테고리, 이름) — 지역당 최대 2페이지(100위)
FOREIGN_CHARTS = [("US", "0", "🇺🇸 미국 전체"), ("US", "27", "🇺🇸 미국 교육"), ("US", "28", "🇺🇸 미국 과학기술"),
                  ("US", "22", "🇺🇸 미국 인물/블로그"), ("JP", "0", "🇯🇵 일본 전체"), ("GB", "0", "🇬🇧 영국 전체")]

FINANCE_KW = ["금리", "주식", "부동산", "재테크", "투자", "경제", "연금", "세금", "코인", "ETF", "대출", "환율", "배당", "stock", "invest", "money"]
HEALTH_KW = ["건강", "질병", "혈압", "당뇨", "다이어트", "영양", "치매", "health"]

# 차트에서 들어온 채널(그룹 없음)을 내 채널 그룹으로 매핑하는 키워드 규칙
GROUP_RULES = {
    "경제적자유구역": FINANCE_KW,
    "히스토리X": ["역사", "조선", "고려", "전쟁", "제국", "왕조", "history", "war", "empire"],
    "지혜의숲": ["인생", "지혜", "명언", "노후", "조언", "철학", "스님", "마음"],
    "음악플레이리스트": ["playlist", "플레이리스트", "lofi", "bgm", "music for"],
    "레트로TV": ["추억", "레트로", "90년대", "80년대", "city pop", "시티팝"],
    "국뽕두그릇": ["해외반응", "외국인 반응", "일본반응", "외국반응"],
    "부자아이": ["용돈", "경제교육", "아이 경제", "자녀 교육"],
    "웃GO": ["콩트", "코미디", "웃긴"],
    "REDPANG": ["nursery", "kids song", "동요", "유아"],
}


def load_rpm(path: Path = RPM_PATH) -> dict[str, tuple[float, float]]:
    """rpm_kr.yaml 의 '"키": [하한, 상한]' 줄만 읽는 최소 파서."""
    out: dict[str, tuple[float, float]] = {}
    pat = re.compile(r'^\s*"([^"]+)"\s*:\s*\[\s*([\d.]+)\s*,\s*([\d.]+)\s*\]')
    for line in path.read_text(encoding="utf-8").splitlines():
        m = pat.match(line)
        if m:
            out[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    return out
