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

## 6. 관심원물 시세 추이 이메일 알림 설정

대시보드에서 ☆(관심 품목)로 등록한 품목에 급등/급락이 새로 발생하면, 구독한 이메일로
가격 추이 그래프와 변화 내용을 자동 발송하는 기능입니다. 아래 순서로 한 번만 설정하면 됩니다.

### 6-1. 구독자 저장용 Google 시트 + Apps Script 배포

1. [sheets.google.com](https://sheets.google.com)에서 새 스프레드시트를 만든다 (이름 예: `원물시세_알림구독자`).
2. 메뉴 `확장 프로그램 > Apps Script`로 들어간다.
3. 기본으로 열린 `Code.gs`의 내용을 전부 지우고, 이 저장소의 `apps-script/Code.gs` 내용을 그대로 붙여넣는다.
4. 우측 상단 `배포 > 새 배포` 클릭 → 유형 선택(⚙️) `웹 앱` 선택.
   - 설명: 아무거나(예: `v1`)
   - 실행 계정: **나**
   - 액세스 권한: **전체 공개(익명 사용자 포함)**
5. `배포` 클릭 → 발급된 웹 앱 URL(`https://script.google.com/macros/s/.../exec`)을 복사해둔다.
   - 처음 배포 시 Google 계정 권한 승인 화면이 뜨면 본인 계정으로 승인한다.

### 6-2. 대시보드에 구독 API 주소 연결

`index.html`에서 아래 줄을 찾아, 6-1에서 복사한 웹 앱 URL로 교체한다.

```js
const SUBSCRIBE_API_URL = 'REPLACE_WITH_APPS_SCRIPT_WEB_APP_URL';
```

### 6-3. GitHub Secrets 등록

저장소 > Settings > Secrets and variables > Actions 에 아래를 등록한다.

| Secret 이름 | 값 |
|---|---|
| `SUBSCRIBE_SHEET_API_URL` | 6-1에서 발급받은 웹 앱 URL (위 `SUBSCRIBE_API_URL`과 동일한 값) |
| `SMTP_HOST` | 회사 그룹웨어 SMTP 서버 주소 (`food-trend-analyzer` 저장소에 이미 등록된 값과 동일하게) |
| `SMTP_PORT` | 보통 587 (또는 465) |
| `SMTP_USER` | 발신 계정 |
| `SMTP_PASSWORD` | 발신 계정 비밀번호(또는 앱 비밀번호) |
| `SMTP_FROM` | 발신 표시 주소 (비워두면 `SMTP_USER` 사용) |

`food-trend-analyzer` 저장소에서 이미 같은 방식으로 주간 리포트를 정상 발송 중이므로, 그때 사용한 값을
그대로 이 저장소 Secrets에도 등록하면 됩니다(Secrets는 저장소별로 따로 등록해야 합니다).

### 6-4. 동작 방식

- 매일 자동 실행(`update-prices.yml`)의 마지막 단계에서 `scripts/check_alerts_and_notify.py`가 실행됩니다.
- 이 스크립트는 `data/alert_state.json`에 저장된 "어제까지의 급등/급락 상태"와 오늘 계산된 상태를 비교해,
  **새로 급등/급락이 시작되거나 종류가 바뀐 품목**만 골라냅니다(매일 반복 발송 방지).
- 그 품목을 관심 품목으로 등록한 구독자에게만, 해당 품목의 그래프(QuickChart.io로 생성)와 가격 변화를
  이메일로 보냅니다.
- 구독/해지는 대시보드의 "📧 관심원물 시세 추이 알림받기" 버튼에서 이메일만 입력하면 되고,
  관심 품목(☆) 목록은 그 시점에 브라우저에 저장된 목록을 그대로 사용합니다(관심 품목을 바꿨다면
  다시 구독 버튼을 눌러 갱신해야 최신 목록으로 반영됩니다).

## 참고: 스크립트 구성

- `scripts/fetch_kamis.py` — KAMIS Open-API로 국내 8개 품목 가격 수집 → `data/kamis_latest.json`
- `scripts/fetch_intl.py` — Yahoo Finance로 국제 4개 원료 주간 종가 수집 → `data/intl_latest.json`
- `scripts/update_dashboard.py` — 위 두 JSON을 `index.html`의 `DATA`/`INTL_DATA`에 병합하고
  전일/전주/전월/전년동기 변화율과 급등·급락 alert를 재계산
- `scripts/check_alerts_and_notify.py` — 급등/급락 상태 변화를 감지해 구독자에게 이메일 발송
- `apps-script/Code.gs` — 구독자(이메일+관심품목) 저장용 Google Apps Script 웹 앱 코드
- `.github/workflows/update-prices.yml` — 위 스크립트들을 매일 실행하는 워크플로
