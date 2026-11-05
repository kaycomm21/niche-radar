"""Phase 2 외부 AI·검색 연동 (키가 있을 때만 동작).

- Gemini (env GEMINI_API_KEY, 선택 GEMINI_MODEL): 후보 영상의 '내 채널 적합도 0~20' + 그룹 판정 → ai_teardown 캐시
- Brave Search (env BRAVE_API_KEY): 후보 주제가 유튜브 밖 뉴스에서도 뜨는지 → 📣 이슈화 보강
두 API 모두 호출마다 quota_log 에 기록하고, 하루 상한을 넘기지 않는다. 키는 로그·예외에 출력하지 않는다.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from . import config

GEMINI_DAILY_CAP = int(os.environ.get("RADAR_GEMINI_CAP", "60"))
BRAVE_DAILY_CAP = int(os.environ.get("RADAR_BRAVE_CAP", "30"))
BRAVE_MONTHLY_CAP = 950          # 기획서 §B: 월 950회 도달 시 자동 정지


def load_bibles() -> dict[str, str]:
    out = {}
    for line in (config.ROOT / "config" / "channel_bibles.yaml").read_text(encoding="utf-8").splitlines():
        m = re.match(r'^\s*"([^"]+)"\s*:\s*"(.+)"\s*$', line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def _log(con, date: str, endpoint: str) -> None:
    con.execute("""INSERT INTO quota_log(date, job, endpoint, units, calls) VALUES (?, 'ai', ?, 0, 1)
                   ON CONFLICT(date, job, endpoint) DO UPDATE SET calls=calls+1""", (date, endpoint))


def _calls(con, date_prefix: str, endpoint: str) -> int:
    r = con.execute("SELECT COALESCE(SUM(calls),0) FROM quota_log WHERE date LIKE ? AND endpoint=?", (date_prefix + "%", endpoint)).fetchone()
    return int(r[0])


def _post(url: str, body: dict, headers: dict | None = None, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode())["error"]
            msg = f"{err.get('status', '')} {err.get('message', '')[:300]}"
        except Exception:  # noqa: BLE001
            msg = ""
        raise RuntimeError(f"HTTP {e.code} {msg}") from None      # URL(키 포함) 노출 금지


def _get(url: str, headers: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}") from None


FIT_PROMPT = """너는 유튜브 다채널 운영사의 편성 PD다. 아래 '터진 영상'을 우리 채널 중 하나로 재가공(원본 재사용 금지, 주제·구조만 차용)할 때
가장 맞는 채널과 적합도를 판정해라. 얼굴 출연·현장 촬영이 필수면 적합도를 낮춰라. 맞는 채널이 없으면 group 은 null.

[우리 채널]
{bibles}

[터진 영상]
제목: {title}
채널: {channel}
태그: {tags}
길이: {dur}초 · {fmt}

JSON 만 출력: {{"group": "채널명 또는 null", "fit": 0~20 정수, "angle": "우리 채널용 각도 한 문장", "reason": "판정 이유 한 문장"}}"""


def gemini_fit(con, today: str, videos: list[dict]) -> int:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return 0
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={urllib.parse.quote(key)}"
    bibles = "\n".join(f"- {k}: {v}" for k, v in load_bibles().items())
    done = 0
    for v in videos:
        if _calls(con, today, "gemini") >= GEMINI_DAILY_CAP:
            break
        if con.execute("SELECT 1 FROM ai_teardown WHERE video_id=?", (v["video_id"],)).fetchone():
            continue                      # 같은 영상 재분석 금지 (캐시)
        prompt = FIT_PROMPT.format(bibles=bibles, title=v["title"], channel=v.get("channel_title") or "",
                                   tags=", ".join(json.loads(v.get("tags") or "[]")[:10]), dur=v.get("duration_s") or 0,
                                   fmt="쇼츠" if v.get("is_short") else "롱폼")
        _log(con, today, "gemini")
        try:
            r = _post(url, {"contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}})
            text = r["candidates"][0]["content"]["parts"][0]["text"]
            d = json.loads(text)
            d["fit"] = max(0, min(20, int(d.get("fit", 0))))
            if d.get("group") not in load_bibles():
                d["group"] = None
        except Exception as e:  # noqa: BLE001
            print(f"  gemini 실패 {v['video_id']}: {e}")
            if "HTTP 4" in str(e):     # 인증·결제·쿼터 오류는 반복 호출해도 같음 → 즉시 중단
                break
            continue
        con.execute("INSERT OR REPLACE INTO ai_teardown(video_id, model, created_at, json) VALUES (?,?,?,?)",
                    (v["video_id"], model, datetime.now(timezone.utc).isoformat(timespec="seconds"), json.dumps(d, ensure_ascii=False)))
        done += 1
    con.commit()
    return done


def brave_buzz(con, today: str, queries: list[tuple[str, str]]) -> dict[str, int]:
    """queries: [(video_id, 검색어)] → {video_id: 지난 24시간 웹/뉴스 결과 수}. 결과는 ai_teardown 에 병합."""
    key = os.environ.get("BRAVE_API_KEY", "").strip()
    out: dict[str, int] = {}
    if not key:
        return out
    for vid, q in queries:
        if _calls(con, today, "brave") >= BRAVE_DAILY_CAP or _calls(con, today[:7], "brave") >= BRAVE_MONTHLY_CAP:
            print("  brave 상한 도달 — 중단")
            break
        _log(con, today, "brave")
        try:
            r = _get("https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": q, "freshness": "pd", "count": 20, "country": "KR"}),
                     {"Accept": "application/json", "X-Subscription-Token": key})
        except Exception as e:  # noqa: BLE001
            print(f"  brave 실패: {e}")
            continue
        n = len((r.get("web") or {}).get("results", [])) + len((r.get("news") or {}).get("results", []))
        out[vid] = n
        row = con.execute("SELECT json FROM ai_teardown WHERE video_id=?", (vid,)).fetchone()
        d = json.loads(row[0]) if row else {}
        d["buzz_24h"] = n
        con.execute("INSERT OR REPLACE INTO ai_teardown(video_id, model, created_at, json) VALUES (?,?,?,?)",
                    (vid, "brave", datetime.now(timezone.utc).isoformat(timespec="seconds"), json.dumps(d, ensure_ascii=False)))
    con.commit()
    return out


def search_query(title: str) -> str:
    """제목에서 해시태그·특수문자 제거 후 핵심 단어 6개."""
    t = re.sub(r"#\S+|\[[^\]]*\]|\([^)]*\)|[|!?\"'“”‘’…·~]", " ", title or "")
    return " ".join(t.split()[:6])
