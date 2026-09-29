# 원물 시세 자동 업데이트 설정 가이드

GitHub Actions로 매일 자동으로 국내·국제 원물 시세를 갱신하도록 구성했습니다.
아래 단계를 순서대로 진행하면 이후에는 사람이 사이트를 열어 확인하지 않아도
매일 아침(KST 07:30) 자동으로 `index.html`이 갱신되고 커밋됩니다.

## 자동화 범위

| 구분 | 자동화 여부 | 비고 |
|---|---|---|
| 쌀·콩·고구마·참깨·들깨·고춧가루(소매)·멸치액젓·천일염 (8종) | ✅ 자동 | KAMIS Open-API(`periodProductList`) |
| 원당·소맥·대두유·옥수수 (국제 4종) | ✅ 자동(차트 데이터만) | Yahoo Finance 공개 API. 스냅샷 가격(전일/전주/전월/연초대비/52주 최고저)은 aT FIS 인도월 계약가와 차이가 날 수 있어 수동 확인 권장 |
| 배추·딸기 (가락시장 경락가격) | ❌ 수동 | KAMIS 경락가격은 Open-API 미제공 페이지라 브라우저 조사 필요 |
| 계란 | ❌ 수동 | ekapepia.com(축산물품질평가원) 별도 사이트, API 미확인 |
| 밤(국산) | ❌ 수동 | 산림조합 forestinfo.or.kr, API 없음 |
| 고춧가루(도매·건고추) | ❌ 수동 | data.go.kr 공공데이터포털 API 검토 필요(현재 미연동) |
| 뉴스/가격인상 동향(NEWS_DATA, HIKE_NEWS_DATA) | ❌ 수동(의도적) | 사람의 판단(관련성·중요도)이 필요한 영역이라 자동화 대상에서 제외 |

즉, 매일 가격 데이터의 상당수(8+4종)는 완전 자동화되고, 나머지 5종 가격과 뉴스는
지금처럼 가끔 Claude에게 "업데이트 해줘"라고 요청하면 됩니다. 자동화 범위를 넓히고
싶으면 알려주세요 — data.go.kr 건고추 API, ekapepia 스크래핑 등을 추가로 붙일 수 있습니다.

## 1. KAMIS Open-API 인증키 발급

1. https://www.kamis.or.kr 회원가입
2. 고객센터 > Open-API > Open-API 이용신청 (https://www.kamis.or.kr/customer/reference/openapi_write.do)
3. 승인 후 발급되는 `인증키(cert_key)`와 `요청자id(cert_id)`를 메모해둔다
   - 공공데이터포털(data.go.kr)에서 신청하면 승인 대기 없이 즉시 발급 가능

## 2. GitHub 저장소 만들고 이 폴더 올리기

로컬 `commodity-price-dashboard` 폴더는 이미 git 저장소로 초기화되어 있습니다.
GitHub에서 새 저장소를 만든 뒤(예: `commodity-price-dashboard`), 아래 명령으로 연결합니다.

```bash
cd commodity-price-dashboard
git remote add origin https://github.com/<계정명>/<저장소명>.git
git add -A
git commit -m "chore: 시세 자동화 스크립트 추가"
git branch -M main
git push -u origin main
```

## 3. GitHub Secrets에 KAMIS 인증키 등록

저장소 > Settings > Secrets and variables > Actions > New repository secret

- `KAMIS_CERT_KEY` : 발급받은 인증키
- `KAMIS_CERT_ID` : 발급받은 요청자id

## 4. Actions 활성화 확인

저장소 > Actions 탭에서 "원물 시세 자동 업데이트" 워크플로가 보이면 정상입니다.
바로 테스트하려면 Actions 탭 > 해당 워크플로 > "Run workflow"로 수동 실행해볼 수 있습니다.
이후에는 매일 KST 07:30에 자동 실행되어, 변경된 내용이 있으면 자동으로 커밋·푸시됩니다.

## 5. (선택) GitHub Pages로 라이브 공개

저장소 > Settings > Pages > Source를 "Deploy from a branch", 브랜치 `main`, 폴더 `/ (root)`로
설정하면 `https://<계정명>.github.io/<저장소명>/` 에서 최신 버전을 바로 볼 수 있습니다.
이 경우 Claude Artifact 게시본과는 별개로, 매일 자동 갱신되는 진짜 "라이브" 대시보드가 생깁니다.

## 참고: 스크립트 구성

- `scripts/fetch_kamis.py` — KAMIS Open-API로 국내 8개 품목 가격 수집 → `data/kamis_latest.json`
- `scripts/fetch_intl.py` — Yahoo Finance로 국제 4개 원료 주간 종가 수집 → `data/intl_latest.json`
- `scripts/update_dashboard.py` — 위 두 JSON을 `index.html`의 `DATA`/`INTL_DATA`에 병합하고
  전일/전주/전월/전년동기 변화율과 급등·급락 alert를 재계산
- `.github/workflows/update-prices.yml` — 위 세 스크립트를 매일 실행하는 워크플로
