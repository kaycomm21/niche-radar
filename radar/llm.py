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


def available() -> bool:
    return bool(os.environ.get("GCP_SA_KEY", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip())


def _vertex_token(sa_json: str) -> tuple[str, str]:
    """서비스계정 JSON → OAuth 액세스 토큰 (google-auth). 반환: (토큰, 프로젝트ID)"""
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    info = json.loads(sa_json)
    cred = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    cred.refresh(Request())
    return cred.token, info["project_id"]


def gemini_json(prompt: str, temperature: float = 0.6, timeout: int = 120) -> dict:
    """우선순위: ① GCP_SA_KEY (Vertex AI, GCP 크레딧 차감) ② GEMINI_API_KEY (AI Studio)."""
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": temperature}}
    sa = os.environ.get("GCP_SA_KEY", "").strip()
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if sa:
        token, project = _vertex_token(sa)
        region = os.environ.get("VERTEX_REGION", "us-central1")
        url = f"https://{region}-aiplatform.googleapis.com/v1/projects/{project}/locations/{region}/publishers/google/models/{model}:generateContent"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    elif key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={urllib.parse.quote(key)}"
        headers = {"Content-Type": "application/json"}
    else:
        raise NoKey("GCP_SA_KEY / GEMINI_API_KEY 없음")
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
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
