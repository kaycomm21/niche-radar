"""공용 Gemini 호출 (키: env GEMINI_API_KEY — GitHub Secret). 키는 출력·예외에 넣지 않는다."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


class NoKey(RuntimeError):
    pass


_last = [0.0]


def throttle() -> None:
    """무료 등급 분당 호출 제한 대비: 호출 간 최소 간격 (env GEMINI_MIN_INTERVAL 초, 기본 7초 ≈ 분당 8회)."""
    import time
    gap = float(os.environ.get("GEMINI_MIN_INTERVAL", "7"))
    wait = _last[0] + gap - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()


def gemini_json(prompt: str, temperature: float = 0.6, timeout: int = 120) -> dict:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise NoKey("GEMINI_API_KEY 없음")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={urllib.parse.quote(key)}"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": temperature}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    throttle()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:   # 구글 오류 메시지(키 미포함)를 그대로 보여 준다
            err = json.loads(e.read().decode())["error"]
            msg = f"{err.get('status', '')} {err.get('message', '')[:300]}"
        except Exception:  # noqa: BLE001
            msg = ""
        raise RuntimeError(f"Gemini HTTP {e.code} {msg}") from None
    return json.loads(d["candidates"][0]["content"]["parts"][0]["text"])
