"""공용 Gemini 호출 (키: env GEMINI_API_KEY — GitHub Secret). 키는 출력·예외에 넣지 않는다."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


class NoKey(RuntimeError):
    pass


def gemini_json(prompt: str, temperature: float = 0.6, timeout: int = 120) -> dict:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise NoKey("GEMINI_API_KEY 없음")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={urllib.parse.quote(key)}"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": temperature}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini HTTP {e.code}") from None
    return json.loads(d["candidates"][0]["content"]["parts"][0]["text"])
