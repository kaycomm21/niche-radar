# ⓒ AG 지시서 — CCS AI 연결 (GCP 무료 크레딧 사용) v1.0 (2026-11-05)

> 목적: Gemini API 선불 크레딧이 소진(HTTP 402)되어 AI 기능이 멈춤 → **GCP 크레딧으로 결제되는 Vertex AI** 로 전환.
> CCS 코드는 `GCP_SA_KEY` 가 있으면 Vertex AI 를 우선 사용하도록 이미 바뀌어 있음 (커밋 d18f9fe).

## 블록 1 — Vertex AI 서비스계정 연결 (추천, GCP 크레딧 차감)
```
GCP 프로젝트 copper-guide-480206-b0 에서 아래를 순서대로 실행하고, 각 단계 결과를 한 줄씩 보고해줘. 키 파일 내용은 절대 출력하지 마.
1) gcloud config set project copper-guide-480206-b0
2) gcloud services enable aiplatform.googleapis.com
3) gcloud iam service-accounts create ccs-vertex --display-name="CCS Vertex AI"
4) gcloud projects add-iam-policy-binding copper-guide-480206-b0 --member="serviceAccount:ccs-vertex@copper-guide-480206-b0.iam.gserviceaccount.com" --role="roles/aiplatform.user"
5) gcloud iam service-accounts keys create "%TEMP%\ccs-vertex.json" --iam-account=ccs-vertex@copper-guide-480206-b0.iam.gserviceaccount.com
6) gh secret set GCP_SA_KEY --repo kaycomm21/niche-radar < "%TEMP%\ccs-vertex.json"
7) 키 파일 삭제: del "%TEMP%\ccs-vertex.json"  (GitHub Secret 에만 남김)
8) Cloud 콘솔 → 결제 → 크레딧 화면에서 현재 크레딧 잔액·만료일·'Vertex AI 적용 가능 여부'를 확인해 보고
9) Cloud 콘솔 → 결제 → 예산 및 알림 → 예산 '₩30,000/월', 50%·90%·100% 이메일 알림 생성 (크레딧 소진 후 카드 과금 방지용 경보)
10) gh workflow run gemini-check.yml --repo kaycomm21/niche-radar  → 1분 뒤 로그에서 'Vertex OK' 확인해 보고
```

## 블록 2 — (선택) AI Studio 무료 등급 키로 교체
> Vertex 가 안 될 때만. 결제 미연결 '새 프로젝트'에서 만든 키 = 무료 등급(분당·일일 한도 있음, 입력이 구글 학습에 쓰일 수 있음).
```
브라우저로 https://aistudio.google.com/apikey 에 접속해 'Create API key' → '새 프로젝트에서 만들기'(결제 연결 안 된 프로젝트)로 키를 만들고,
gh secret set GEMINI_API_KEY --repo kaycomm21/niche-radar 로 기존 값을 교체해줘. 키 값은 출력하지 마.
끝나면 gh workflow run gemini-check.yml --repo kaycomm21/niche-radar 실행 후 결과(HTTP 200 여부)를 보고해줘.
```

## 블록 3 — 입찰레이더 실데이터 키 (영근님이 포털 신청 후)
```
공공데이터포털(data.go.kr)에서 '조달청_나라장터 입찰공고정보서비스' 활용신청이 승인되면, 마이페이지의 일반 인증키(Decoding)를
gh secret set DATA_GO_KR_KEY --repo kaycomm21/niche-radar 로 등록하고, gh workflow run daily.yml --repo kaycomm21/niche-radar -f mode=export 실행 후
https://kaycomm21.github.io/niche-radar/#/bids 에서 '예시 데이터' 배너가 사라졌는지 확인해 보고해줘.
```

## 비용 추정 (확인 필요 — 가격표는 구글 공식 페이지 기준으로 재확인)
| 항목 | 하루 호출 | 비고 |
|---|---|---|
| 적합도 채점 | ≤60 | 짧은 출력 |
| 구글 트렌드·해외 한국화 기획 | ≤22 | 중간 |
| 자동 패키지·제안서·블로그·부자아이 | 수 건 | 긴 출력(대본) |
→ Flash 모델 기준 **월 수천~수만 원 수준 추정** — 매달 들어오는 GCP 크레딧(₩113,451 잔액) 안에서 운영 목표. 예산 알림(블록 1-9)으로 초과 감시.
