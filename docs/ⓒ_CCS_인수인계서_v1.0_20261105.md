# ⓒ CCS (Creative Craft Studio) 인수인계서 v1.0 — 2026-11-05

> 다음 세션(클라우드 CC·로컬 CC·AG)이 이 문서 하나로 이어서 개발·유지보수할 수 있도록 정리.
> 저장소 `kaycomm21/niche-radar` (공개) · 사이트 https://kaycomm21.github.io/niche-radar/ · 사용자: 김영근 PD (코딩 배경 없음, 한국어 보고)

## 1. 한눈에 보기
| 항목 | 값 |
|---|---|
| 구조 | Python(표준 라이브러리 + google-auth) 수집·분석 → 정적 JSON → Vite+React+TS 웹 (GitHub Pages) |
| 서버 | 없음. GitHub Actions 가 매일 06:17 KST 실행, SQLite 는 `data` 브랜치에 gzip 1개(force-push) |
| 비용 | YouTube API 무료(하루 10,000유닛 중 약 2,700~4,700 사용) · GitHub 무료(공개) · AI = Vertex AI → **GCP 크레딧(₩113k) 차감**, 예산 알림 ₩30,000/월 |
| 테스트 | `python -m pytest -q` (48개) · `cd web && npm ci && npm run build` |
| 디자인 | Gruvbox Material 다크 (bg #141617 · fg #D4BE98 · accent #E78A4E), Cue 버튼 핫핑크 |

## 2. Secrets (Settings → Secrets → Actions)
| 이름 | 상태 | 용도 |
|---|---|---|
| `YOUTUBE_API_KEY` | ✅ | 수집 |
| `GCP_SA_KEY` | ✅ (ccs-vertex 서비스계정, roles/aiplatform.user) | **AI 주력** (Vertex AI, us-central1, gemini-2.5-flash) |
| `GEMINI_API_KEY` | ⚠️ 선불 크레딧 소진(HTTP 402) — 예비 | AI Studio 경로 (GCP_SA_KEY 없을 때만) |
| `DATA_GO_KR_KEY` | ❌ 미등록 | 🏛 입찰레이더 실데이터 (없으면 예시 4건) |
| `BRAVE_API_KEY` | ❌ 미등록(선택) | 📣 외부 언급 |

## 3. 메뉴 ↔ 코드 ↔ 데이터
| 메뉴 | 웹 (web/src/pages.tsx) | 백엔드 (radar/) | 출력 |
|---|---|---|---|
| 🎯 월천 관제탑 | CockpitPage | — (브라우저 localStorage) | — |
| 🏠 홈 | HomeBoard | export.py | home.json |
| 🎬 오늘의 생산 큐 | Home | export.py, metrics.py | queue.json |
| 📦 생산 패키지 | PackagesPage | autopkg.py, storyboard.py | exports/packages/*, packages.json |
| 🔍 채널 검색 | SearchPage | addchannel.py + analyze.yml | search.json |
| 🌐 인기 차트 / 🚀 급상승 / 🏆 순위 / 채널 상세 / ⚖️ 비교 | ChartPage 등 | collect.py, export.py, metrics.py | charts/surging/rankings/channels/*.json |
| 🌍 해외 레퍼런스 | OverseasPage | collect_foreign_charts, autopkg.localize | overseas.json (+data/localize.json) |
| 📈 트렌드 | TrendPage | trends.py, gtrends.py | trends.json, gtrends.json |
| ✍️ 글공방 | BlogStudio | blog.py + blog.yml | exports/blog/* |
| 🏛 입찰레이더 | BidsPage | bids.py (+config/my_projects.yaml) | bids.json, exports/proposals/* |
| 🐷 부자아이 공방 | KidsPage | kids.py + blog.yml | exports/kids/* |
| 💰 수익 계산기 | CalcPage | config/rpm_kr.yaml | — |

공통 AI: `radar/llm.py` (Vertex 우선 → AI Studio), 호출 간 7초(`GEMINI_MIN_INTERVAL`). 채점은 `radar/ai.py` (하루 60회, 성공만 계산).

## 4. 워크플로 (.github/workflows)
| 파일 | 트리거 | 하는 일 |
|---|---|---|
| daily.yml | 매일 21:17 UTC(06:17 KST) · 수동 | 모드 `auto`(수집) / `export`(화면+AI) / **`web`(화면만, 약 1분 — 디자인 배포용)** / `fixture` → 입찰·트렌드·한국화 → DB 저장 → 자동 패키지·제안서·brief 커밋 → Pages 배포 → 실주소 점검 |
| verdict.yml | Issue 열림(주인, `radar-verdict`) · 수동 | 판정 기록(밀린 것까지 따라잡기) → Cue 자동 패키지 → 제안서 → 화면 재생성 |
| analyze.yml | Issue(`radar-analyze`) · 수동 | 채널 추가·수집(@핸들 3유닛) |
| blog.yml | Issue(`radar-blog` / `radar-kids`) | 글공방 / 부자아이 세트 생성·커밋·Issue 링크 |
| ci.yml | push | pytest + 웹 빌드 |
| gemini-check.yml | 수동 | Vertex·AI Studio 진단 (키 미출력) |

## 5. 운영 루틴 (영근님)
1. 매일: 🎯 관제탑 '오늘의 3가지' → 🎬 오늘의 생산 큐 판정(Cue → GitHub **초록 Create**)
2. 📦 생산 패키지 → factcheck 처리 → 로컬 CC 로 렌더·비공개 업로드 (`exports/2026-11-04/ⓒ_HANDOFF_로컬CC_생산지시서_v1.0_20261104.md`)
3. 글공방 주 2~3편 (`[✍️ 직접 경험 한 줄]` 2곳 직접 채우기)
4. 월말: 관제탑 수입 입력

## 6. 남은 일 (우선순위)
| # | 할 일 | 비고 |
|---|---|---|
| 1 | **11/6 06:17 첫 예약 실행 확인** (21:17 UTC cron) · AI 적합도 채점 정상(오늘은 402 실패 로그가 상한을 채워 0건) | `gh run list -w daily.yml` |
| 2 | `DATA_GO_KR_KEY` 등록 → 입찰 API 실호출 검증. 엔드포인트/필드명은 포털 활용가이드로 확인 (`BID_API_BASE`, `BID_API_OP` env 로 변경 가능, `radar/bids.py`) | AG 지시서 블록 3 |
| 3 | 판정 기준 보정: 급상승 배수 노이즈(20배 기준도 862건) → 11/11 `python -m radar calibrate` 재실행 후 '배수 × log(조회)' 정렬·채널 중앙값 1,000 미만 제외 검토 | docs/…판정보정리포트 |
| 4 | M4 내 채널 실측(OAuth, 로컬 실행): `python -m radar oauth-init --name <채널>` → `mychannel` → 실측 RPM 자동 반영 | radar/mychannel.py |
| 5 | 슈퍼챗·라이브 순위 (Phase 3 승인, 감시 채널 ≤10) | 쿼터 주의 |
| 6 | 블로그판 레이더(네이버 검색광고 키워드도구·데이터랩·서치콘솔) / 워드프레스 예약 발행 | 키 필요 |
| 7 | 저장소 이름 `ccs` 변경 시: 웹은 자동 추종, 문서·워크플로의 하드코딩 `kaycomm21/niche-radar` (docs, verdict 코멘트 링크) 일괄 치환 | 옛 Pages 주소 끊김 |
| 8 | 월천 관제탑 데이터는 브라우저 localStorage → 기기 간 공유 필요 시 Firebase(copper-guide) 이전 | — |
| 9 | 쌍둥이 성장노트 웹앱: 기획서 `cc-cloud-credit` 저장소 `06_쌍둥이발달앱/` (브랜치 claude/sleepy-maxwell-u92t03) §8 블록으로 새 세션 시작 | 별도 프로젝트 |

## 7. 알려진 한계·주의
- 남의 채널 과거 데이터는 API 가 주지 않음 → 11/4부터 누적 (일별 표·예측은 7일 이후 의미).
- 큰 채널 구독자 수는 API 가 3자리 반올림 → 일별 +0 가능 (화면에 설명 있음).
- 유니버스 순위·등급은 추적 채널(약 1,700) 내 상대평가. '- Topic' 자동생성 채널은 제외(e094c73).
- 블링·플레이보드·녹스 실제 화면은 클라우드 세션 네트워크 차단으로 미열람 → 기능은 검색 기반 재현. 새 세션에서 도메인 허용 확인 후 실사 비교 권장.
- 아이 데이터·키를 공개 저장소에 올리지 말 것 (CCS 저장소는 공개).
- 파일명 규칙: 산출물 `ⓒ_` 접두 + 날짜 (Claude=ⓒ, GPT=ⓖ, AG=ⓐ).

## 8. 새 세션 시작 블록 (복붙)
```
kaycomm21/niche-radar 저장소(CCS · Creative Craft Studio)를 이어서 개발·유지보수한다. 사용자는 코딩 배경 없는 한국인 PD, 한국어로 결론→근거→다음 행동, 표 위주로 보고.
먼저 docs/ⓒ_CCS_인수인계서_v1.0_20261105.md 를 읽고 §6 '남은 일' 1번(최근 daily-radar 실행·AI 채점 확인)부터 진행해라.
규칙: 키·토큰 출력 금지, 커밋 전 python -m pytest -q 와 web 빌드 통과, 디자인만 바꿀 땐 daily.yml mode=web 로 배포, AI 는 radar/llm.py(Vertex 우선) 경유.
```
