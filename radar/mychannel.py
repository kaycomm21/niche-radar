"""M4 내 채널 실측 (YouTube Analytics API, OAuth) — **영근님 PC(로컬)에서 실행**.

왜 로컬인가: 내 채널 수익·시청지속은 내 구글 계정 로그인(OAuth)이 필요하고, 그 토큰은 클라우드/공개 저장소에 두면 안 된다.

사용법 (채널마다 1회):
  1) GCP 콘솔 → API 및 서비스 → 'YouTube Analytics API' 사용 설정 → OAuth 클라이언트 ID(데스크톱 앱) 생성
  2) env RADAR_OAUTH_CLIENT_ID / RADAR_OAUTH_CLIENT_SECRET 설정
  3) python -m radar oauth-init --name 경제적자유구역   → 브라우저 로그인 → 토큰이 ~/.niche_radar/tokens.json 에 저장 (저장소 밖)
  4) python -m radar mychannel --days 28               → exports/mychannel/<날짜>.json + config/rpm_measured.yaml(실측 RPM)
"""
from __future__ import annotations

import http.server
import json
import os
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, timedelta
from pathlib import Path

from . import config

TOKENS = Path(os.environ.get("RADAR_TOKENS", Path.home() / ".niche_radar" / "tokens.json"))
SCOPES = "https://www.googleapis.com/auth/yt-analytics.readonly https://www.googleapis.com/auth/yt-analytics-monetary.readonly https://www.googleapis.com/auth/youtube.readonly"
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
REPORTS = "https://youtubeanalytics.googleapis.com/v2/reports"
METRICS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,estimatedRevenue"


def _client() -> tuple[str, str]:
    cid, sec = os.environ.get("RADAR_OAUTH_CLIENT_ID", ""), os.environ.get("RADAR_OAUTH_CLIENT_SECRET", "")
    if not cid or not sec:
        raise SystemExit("RADAR_OAUTH_CLIENT_ID / RADAR_OAUTH_CLIENT_SECRET 환경변수가 필요합니다 (모듈 설명 참고)")
    return cid, sec


def _post_form(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def oauth_init(name: str, port: int = 8765) -> None:
    """로컬 루프백으로 인증 코드를 받아 refresh_token 저장 (구글 권장 방식)."""
    cid, sec = _client()
    redirect = f"http://127.0.0.1:{port}/"
    url = AUTH + "?" + urllib.parse.urlencode({"client_id": cid, "redirect_uri": redirect, "response_type": "code",
                                              "scope": SCOPES, "access_type": "offline", "prompt": "consent"})
    got: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            got.update(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write("인증 완료. 이 창을 닫아도 됩니다.".encode())

        def log_message(self, *a):
            pass

    print("브라우저에서 해당 채널의 구글 계정으로 로그인하세요:\n" + url)
    webbrowser.open(url)
    http.server.HTTPServer(("127.0.0.1", port), H).handle_request()
    if "code" not in got:
        raise SystemExit("인증 코드를 받지 못했습니다")
    tok = _post_form(TOKEN, {"code": got["code"][0], "client_id": cid, "client_secret": sec, "redirect_uri": redirect, "grant_type": "authorization_code"})
    TOKENS.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(TOKENS.read_text()) if TOKENS.exists() else {}
    data[name] = {"refresh_token": tok["refresh_token"]}
    TOKENS.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    os.chmod(TOKENS, 0o600)
    print(f"저장 완료: {name} → {TOKENS} (이 파일은 절대 저장소에 올리지 마세요)")


def _access_token(refresh: str) -> str:
    cid, sec = _client()
    return _post_form(TOKEN, {"refresh_token": refresh, "client_id": cid, "client_secret": sec, "grant_type": "refresh_token"})["access_token"]


def _report(token: str, params: dict) -> dict:
    req = urllib.request.Request(REPORTS + "?" + urllib.parse.urlencode(params), headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def rows_to_dicts(resp: dict) -> list[dict]:
    cols = [h["name"] for h in resp.get("columnHeaders", [])]
    return [dict(zip(cols, r)) for r in resp.get("rows", [])]


def summarize(name: str, totals: dict, videos: list[dict]) -> dict:
    """실측 RPM(원) = 예상수익 ÷ 조회 × 1000. 수익 데이터가 없으면(수익화 전) None."""
    views = totals.get("views") or 0
    rev = totals.get("estimatedRevenue")
    rpm = round(rev / views * 1000, 1) if rev and views else None
    med = sorted(v.get("views", 0) for v in videos)
    median = med[len(med) // 2] if med else None
    return {"channel": name, "views": views, "revenue": rev, "rpm": rpm, "median_video_views": median,
            "avg_view_pct": totals.get("averageViewPercentage"), "videos": videos}


def run(days: int = 28, out_dir: Path | None = None) -> list[dict]:
    if not TOKENS.exists():
        raise SystemExit("토큰 없음 — 먼저 python -m radar oauth-init --name <채널명>")
    end = date.today() - timedelta(days=2)          # Analytics 는 1~2일 지연
    start = end - timedelta(days=days - 1)
    out = []
    for name, t in json.loads(TOKENS.read_text()).items():
        tok = _access_token(t["refresh_token"])
        base = {"ids": "channel==MINE", "startDate": start.isoformat(), "endDate": end.isoformat(), "metrics": METRICS}
        totals = (rows_to_dicts(_report(tok, base)) or [{}])[0]
        vids = rows_to_dicts(_report(tok, {**base, "dimensions": "video", "sort": "-views", "maxResults": 50}))
        out.append(summarize(name, totals, vids))
    out_dir = out_dir or (config.EXPORTS_DIR / "mychannel")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{date.today().isoformat()}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    measured = [f'"{o["channel"]}": [{o["rpm"]}, {o["rpm"]}]   # {start}~{end} 실측' for o in out if o["rpm"]]
    if measured:
        (config.ROOT / "config" / "rpm_measured.yaml").write_text(
            "# M4 실측 RPM (원/1,000회) — python -m radar mychannel 이 자동 생성. 내 채널 그룹 영상의 RPM 가정치를 대체한다.\n" + "\n".join(measured) + "\n", encoding="utf-8")
    return out
