"""YouTube Data API v3 클라이언트.

- RealYouTube: 실제 API (env YOUTUBE_API_KEY). 키는 절대 로그·예외 메시지에 넣지 않는다.
- FakeYouTube: 키가 없을 때 쓰는 fixture 모드. 실제 API와 같은 JSON 모양을 결정적으로 생성한다.
두 클래스 모두 호출 '전에' Quota.spend() 를 불러 유닛을 기록한다.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from .quota import Quota

API = "https://www.googleapis.com/youtube/v3/"


class ChartNotFound(Exception):
    """해당 카테고리에 인기 차트가 없음 (API 404)."""


class ApiError(RuntimeError):
    pass


class RealYouTube:
    def __init__(self, key: str, quota: Quota, timeout: int = 30):
        self._key = key
        self.quota = quota
        self.timeout = timeout

    def _get(self, endpoint: str, params: dict) -> dict:
        self.quota.spend(endpoint)
        q = urllib.parse.urlencode({**params, "key": self._key})
        url = API + endpoint.split(".")[0] + "?" + q
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            try:
                reason = json.loads(body)["error"]["errors"][0].get("reason", "")
            except Exception:  # noqa: BLE001
                reason = ""
            if e.code == 404 or reason in ("chartNotFound", "notFound"):
                raise ChartNotFound(endpoint) from None
            # URL(키 포함)은 메시지에 넣지 않는다
            raise ApiError(f"{endpoint} HTTP {e.code} {reason}") from None

    def channels(self, ids: list[str]) -> list[dict]:
        d = self._get("channels.list", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids), "maxResults": 50})
        return d.get("items", [])

    def playlist_items(self, playlist_id: str, max_results: int = 30) -> list[dict]:
        try:
            d = self._get("playlistItems.list", {"part": "contentDetails", "playlistId": playlist_id, "maxResults": max_results})
        except ChartNotFound:
            return []
        return d.get("items", [])

    def videos(self, ids: list[str]) -> list[dict]:
        d = self._get("videos.list", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids), "maxResults": 50})
        return d.get("items", [])

    def most_popular(self, category_id: str, page_token: str | None = None) -> tuple[list[dict], str | None]:
        p = {"part": "snippet,statistics,contentDetails", "chart": "mostPopular", "regionCode": "KR",
             "maxResults": 50, "hl": "ko"}
        if category_id != "0":
            p["videoCategoryId"] = category_id
        if page_token:
            p["pageToken"] = page_token
        d = self._get("videos.list", p)
        return d.get("items", []), d.get("nextPageToken")

    def search(self, q: str, max_results: int = 25) -> list[dict]:
        d = self._get("search.list", {"part": "snippet", "q": q, "type": "video", "regionCode": "KR",
                                      "maxResults": max_results, "order": "viewCount"})
        return d.get("items", [])


# ---------------------------------------------------------------- fixture 모드
TITLE_BANK = {
    "경제적자유구역": ["금리 인하가 내 대출에 미치는 진짜 영향", "월급 300으로 1억 모으는 현실 루트", "ETF 하나로 노후 끝내는 법", "부동산 하락장, 지금 사도 될까", "연금 수령 전에 꼭 알아야 할 세금 3가지"],
    "지혜의숲": ["곁에 두면 안 되는 사람의 5가지 특징", "70세 이후 후회하는 것 3가지", "마음이 편안해지는 부처님 말씀", "노후에 돈보다 중요한 것", "인생 조언 | 잠들기 전 듣는 지혜"],
    "히스토리X": ["로마 제국이 망한 진짜 이유", "조선 최악의 왕은 누구였나", "2차 세계대전 미국편 몰아보기", "고구려가 강했던 결정적 이유", "몽골 제국은 어떻게 세계를 정복했나"],
    "음악플레이리스트": ["warm & cozy lofi playlist", "Funky slap bass BGM for work", "새벽 감성 playlist 2시간", "city night drive playlist", "집중 잘 되는 bass groove"],
    "레트로TV": ["90년대 문방구 추억의 간식 TOP10", "80s japanese city pop playlist", "그때 그 시절 레트로 광고 모음", "추억의 과자 맞히기 퀴즈"],
    "국뽕두그릇": ["한국 응급실에 실려간 외국인 반응", "일본이 인정한 한국 신도시", "한국 국밥에 빠진 미국 아빠들"],
    "부자아이": ["초등학생 용돈 교육 이렇게 하세요", "유대인 부모의 자녀 경제교육법", "금쪽이 경제교실 용돈은 어디로"],
    "새시대유감": ["이번 주 이슈 3분 요약", "지금 바로 신청하면 받는 지원금", "모르면 손해 보는 제도 정리"],
    "깡통봇": ["AI가 부른 슬픈 노래", "로봇의 하루 애니메이션"],
    "REDPANG": ["Baby animals song for kids", "Wheels on the bus nursery rhyme", "Colors and fruits learning song"],
    "춘식이만식이": ["쌍둥이 육아 웃긴 순간 모음", "38개월 쌍둥이의 하루 브이로그"],
    "웃GO": ["회사 회식 콩트", "해장 콩트 #shorts", "AI 코미디 쇼츠"],
    "진영논리": ["오늘의 정치 브리핑 LIVE", "이번 판결의 진짜 의미"],
    None: ["오늘 난리 난 영상", "역대급 반전 결말", "이거 모르면 손해", "직접 해봤습니다", "1위 찍은 이유"],
}
GROUP_CAT = {"경제적자유구역": "25", "지혜의숲": "22", "히스토리X": "27", "음악플레이리스트": "10", "레트로TV": "24",
             "국뽕두그릇": "24", "부자아이": "27", "새시대유감": "25", "깡통봇": "10", "REDPANG": "27",
             "춘식이만식이": "22", "웃GO": "23", "진영논리": "25"}


def _h(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


class FakeYouTube:
    """결정적 가짜 API. 같은 날짜·같은 입력이면 항상 같은 응답."""

    N_CHART_CHANNELS = 80

    def __init__(self, quota: Quota, today: date, seed_channels: dict[str, dict] | None = None):
        self.quota = quota
        self.today = today
        self.seed = seed_channels or {}
        self._channels = self._make_channels()

    # ---- 가상 세계
    def _make_channels(self) -> dict[str, dict]:
        chs = {}
        for cid, info in self.seed.items():
            chs[cid] = {"title": info.get("channel") or cid, "group": info.get("group"),
                        "subs0": info.get("subs") or 10000 + _h(cid) % 90000}
        for i in range(self.N_CHART_CHANNELS):
            cid = f"UCfixture{i:04d}xxxxxxxxxxxxx"[:24]
            groups = list(GROUP_CAT) + [None] * 4
            chs[cid] = {"title": f"차트채널 {i:02d}", "group": groups[_h(cid) % len(groups)],
                        "subs0": 3000 + _h(cid, "s") % 2_000_000}
        for cid, c in chs.items():
            r = random.Random(_h(cid))
            c["growth"] = r.uniform(-0.0005, 0.004)          # 일 구독 성장률
            c["every"] = r.choice([1, 2, 3, 4, 7])           # 업로드 간격(일)
            c["short_ratio"] = r.choice([0, 0, 0.2, 0.5, 0.8])
            c["base_views"] = max(300, int(c["subs0"] * r.uniform(0.02, 0.3)))
            c["cat"] = GROUP_CAT.get(c["group"], r.choice(["22", "24", "23", "20", "26", "28"]))
        return chs

    def _subs(self, cid: str, d: date) -> int:
        c = self._channels[cid]
        days = (d - date(2026, 1, 1)).days
        return int(c["subs0"] * math.exp(c["growth"] * days))

    def _channel_videos(self, cid: str, upto: date, n: int = 40) -> list[dict]:
        c = self._channels[cid]
        out = []
        start = upto - timedelta(days=c["every"] * (n - 1))
        k0 = (start - date(2026, 1, 1)).days // c["every"]
        for k in range(k0, k0 + n):
            pub = date(2026, 1, 1) + timedelta(days=k * c["every"])
            if pub > upto:
                break
            vid = "v" + hashlib.sha256(f"{cid}{k}".encode()).hexdigest()[:10]
            r = random.Random(_h(vid))
            is_short = r.random() < c["short_ratio"]
            mult = r.lognormvariate(0, 0.6)
            if r.random() < 0.06:
                mult *= r.uniform(4, 15)                        # 터진 영상
            out.append({"id": vid, "cid": cid, "pub": pub, "short": is_short,
                        "dur": r.randint(20, 59) if is_short else r.randint(300, 1800),
                        "peak": int(c["base_views"] * mult * (3 if is_short else 1)),
                        "tau": r.uniform(2, 8),
                        "title": r.choice(TITLE_BANK.get(c["group"], TITLE_BANK[None])) + (" #shorts" if is_short else "")})
        return out

    def _views(self, v: dict, d: date) -> int:
        age = (d - v["pub"]).days + 1
        if age <= 0:
            return 0
        return int(v["peak"] * (1 - math.exp(-age / v["tau"])))

    def _video_item(self, v: dict) -> dict:
        views = self._views(v, self.today)
        r = random.Random(_h(v["id"], "e"))
        c = self._channels[v["cid"]]
        return {
            "kind": "youtube#video", "id": v["id"],
            "snippet": {"publishedAt": f"{v['pub'].isoformat()}T09:00:00Z", "channelId": v["cid"],
                        "title": v["title"], "description": "", "channelTitle": c["title"],
                        "tags": [c["group"] or "일반"], "categoryId": c["cat"], "defaultAudioLanguage": "ko",
                        "thumbnails": {"medium": {"url": f"https://i.ytimg.com/vi/{v['id']}/mqdefault.jpg"}}},
            "contentDetails": {"duration": f"PT{v['dur'] // 60}M{v['dur'] % 60}S"},
            "statistics": {"viewCount": str(views), "likeCount": str(int(views * r.uniform(0.01, 0.05))),
                           "commentCount": str(int(views * r.uniform(0.0005, 0.004) * (1 + (self.today - v['pub']).days * 0.02)))},
        }

    def _all_videos(self) -> dict[str, dict]:
        if not hasattr(self, "_vcache"):
            self._vcache = {v["id"]: v for cid in self._channels for v in self._channel_videos(cid, self.today)}
        return self._vcache

    # ---- API 흉내
    def channels(self, ids: list[str]) -> list[dict]:
        self.quota.spend("channels.list")
        out = []
        for cid in ids:
            if cid not in self._channels:
                continue
            c = self._channels[cid]
            vids = self._channel_videos(cid, self.today, 40)
            out.append({"kind": "youtube#channel", "id": cid,
                        "snippet": {"title": c["title"], "customUrl": "@" + cid[-6:].lower(), "country": "KR",
                                    "publishedAt": "2020-01-01T00:00:00Z",
                                    "thumbnails": {"default": {"url": f"https://yt3.ggpht.com/{cid}"}}},
                        "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid[2:]}},
                        "statistics": {"subscriberCount": str(self._subs(cid, self.today)),
                                       "viewCount": str(sum(self._views(v, self.today) for v in vids) * 20),
                                       "videoCount": str(200 + len(vids)), "hiddenSubscriberCount": False}})
        return out

    def playlist_items(self, playlist_id: str, max_results: int = 30) -> list[dict]:
        self.quota.spend("playlistItems.list")
        cid = "UC" + playlist_id[2:]
        if cid not in self._channels:
            return []
        vids = sorted(self._channel_videos(cid, self.today, 40), key=lambda v: v["pub"], reverse=True)[:max_results]
        return [{"contentDetails": {"videoId": v["id"], "videoPublishedAt": f"{v['pub'].isoformat()}T09:00:00Z"}} for v in vids]

    def videos(self, ids: list[str]) -> list[dict]:
        self.quota.spend("videos.list")
        allv = self._all_videos()
        return [self._video_item(allv[i]) for i in ids if i in allv]

    def most_popular(self, category_id: str, page_token: str | None = None) -> tuple[list[dict], str | None]:
        self.quota.spend("videos.list")
        if category_id in ("19", "29"):
            raise ChartNotFound(category_id)
        recent = [v for v in self._all_videos().values()
                  if 0 <= (self.today - v["pub"]).days <= 7
                  and (category_id == "0" or self._channels[v["cid"]]["cat"] == category_id)]
        recent.sort(key=lambda v: self._views(v, self.today) - self._views(v, self.today - timedelta(days=1)), reverse=True)
        recent = recent[:200]
        page = int(page_token or 0)
        chunk = recent[page * 50:(page + 1) * 50]
        nxt = str(page + 1) if (page + 1) * 50 < len(recent) else None
        return [self._video_item(v) for v in chunk], nxt

    def search(self, q: str, max_results: int = 25) -> list[dict]:
        self.quota.spend("search.list")
        hits = [v for v in self._all_videos().values() if q in v["title"]][:max_results]
        return [{"id": {"videoId": v["id"]}, "snippet": {"channelId": v["cid"], "title": v["title"]}} for v in hits]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
