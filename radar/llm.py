"""공용 AI 호출. 키는 출력·예외에 넣지 않는다.

- gemini_json: 대량·단순 작업 (적합도 채점 60건/일, 한국화, 트렌드) — Vertex Gemini(GCP_SA_KEY) → AI Studio(GEMINI_API_KEY)
- ai_json(quality=True): 품질 우선 소량 작업 (생산 패키지 대본, 입찰 제안서, 글공방, 부자아이) — Vertex 의 Claude Opus
  (같은 GCP_SA_KEY, Model Garden 에서 Claude 사용 설정 필요). 실패·거절·미설정이면 자동으로 Gemini 로 대체.
  env: CLAUDE_MODEL(기본 claude-opus-5-5) · CLAUDE_REGION(기본 global) · CLAUDE_EFFORT(기본 medium) · CLAUDE_DISABLE=1 로 끄기
"""
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


_claude_down = [False]          # 한 번 4xx(미설정·권한·결제)면 이번 실행 동안은 다시 시도하지 않음


def _extract_json(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j < i:
        raise ValueError("JSON 없음")
    return json.loads(t[i:j + 1])


def claude_json(prompt: str, timeout: int = 600) -> dict:
    """Vertex AI 의 Claude (Anthropic 공식 SDK, anthropic[vertex]). 서비스계정 GCP_SA_KEY 로 인증."""
    sa = os.environ.get("GCP_SA_KEY", "").strip()
    if not sa:
        raise NoKey("GCP_SA_KEY 없음")
    from anthropic import AnthropicVertex
    from google.oauth2 import service_account
    info = json.loads(sa)
    cred = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    client = AnthropicVertex(project_id=info["project_id"], region=os.environ.get("CLAUDE_REGION", "global"),
                             credentials=cred, timeout=timeout, max_retries=1)
    with client.messages.stream(
        model=os.environ.get("CLAUDE_MODEL", "claude-opus-5-5"),
        max_tokens=32000,
        output_config={"effort": os.environ.get("CLAUDE_EFFORT", "medium")},
        messages=[{"role": "user", "content": prompt + "\n\n설명 없이 JSON 객체 하나만 출력."}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("Claude refusal")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("Claude max_tokens 도달 (응답 잘림)")
    return _extract_json("".join(b.text for b in msg.content if b.type == "text"))


def ai_json(prompt: str, temperature: float = 0.6, quality: bool = False, timeout: int = 120) -> dict:
    """quality=True 면 Claude Opus 우선, 한 번이라도 실패하면 이번 실행은 Gemini. 반환 dict 에 _model 키로 실제 사용 모델 기록."""
    if quality and not _claude_down[0] and os.environ.get("CLAUDE_DISABLE") != "1" and os.environ.get("GCP_SA_KEY", "").strip():
        try:
            d = claude_json(prompt)
            d["_model"] = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
            return d
        except Exception as e:  # noqa: BLE001 — 어떤 실패든 Gemini 로 대체 (파이프라인 중단 금지)
            code = getattr(e, "status_code", None)
            _claude_down[0] = True      # 미설정·쿼터 0(429)·거절 등 → 이번 실행은 Gemini 로만 (재시도 시간 낭비 방지)
            print(f"  Claude 실패 → Gemini 대체: {type(e).__name__} {code or ''} {str(e)[:200]}")
    d = gemini_json(prompt, temperature=temperature, timeout=timeout)
    d["_model"] = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    return d
