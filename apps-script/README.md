# 관심원물 급등·급락 알림 (Apps Script)

대시보드의 **관심원물 알림 구독**과 **급등·급락 알림 메일**을 담당하는 Google Apps Script 코드입니다.
(`Code.gs` = Apps Script 편집기에 붙여넣는 파일. 이 저장소에는 운영 중인 버전을 기록용으로 보관합니다.)

## 전체 흐름

```
GitHub Actions (매일 07:30 KST)
  fetch_kamis.py / fetch_intl.py / fetch_at_recent.py  → data/*.json
  update_dashboard.py                                  → index.html (DATA 갱신)
        │
        ▼  GitHub Pages
대시보드(index.html)  ── [구독하기] ──►  Apps Script 웹 앱 (doPost)  ──►  구독자 시트
        │
        ▼
Apps Script 트리거 (매일 오전 9시대)  checkAndSend()
  index.html 의 DATA 를 읽어 품목별 전년동기 대비 판정 → 구독자별 메일 발송 (MailApp)
```

- 메일은 **Apps Script(Google 계정)** 에서 발송합니다. GitHub Actions 쪽 `check_alerts_and_notify.py`(SendGrid)는
  `SENDGRID_API_KEY` 등이 등록되어 있지 않으면 건너뜁니다. 둘을 동시에 켜면 같은 알림이 이중 발송될 수 있습니다.

## 설치 (한 번만)

1. 새 Google 스프레드시트 → 확장 프로그램 → Apps Script → `Code.gs` 전체를 붙여넣고 저장
2. `CONFIG`의 `DATA_URL`, `DASHBOARD_URL`, `ALLOWED_DOMAINS` 확인
3. `testSend` 실행 → 권한 승인 → 내 메일로 샘플 도착 확인
4. `setupTrigger` 실행 → 매일 오전 9시대 자동 실행 등록
5. 배포 → 새 배포 → 웹 앱(실행: 나, 액세스: 모든 사용자) → `/exec` URL 복사
6. `index.html` 의 `SUBSCRIBE_API_URL` 에 그 URL 입력

> `Code.gs` 를 수정한 뒤에는 편집기에 다시 붙여넣고 저장하면 트리거(메일 발송)에 바로 반영됩니다.
> 구독 접수(`doPost`) 코드를 바꿨다면 배포 관리 → 새 버전으로 다시 배포해야 합니다(URL은 유지).

## 판정 기준과 설정 (`CONFIG`)

| 설정 | 의미 |
|---|---|
| `SURGE_PCT` / `DROP_PCT` | 전년동기 대비 급등(+20%) / 급락(-20%) 기준 |
| `ONLY_AT_SOURCES` | `true`면 가격 출처가 검증된 품목(`yoy_src: 'at'`)만 판정 |
| `YOY_MAX_GAP_DAYS` | 1년 전 같은 날 자료가 없을 때 허용하는 최대 날짜 차이 |
| `YOY_MAX_SPREAD_PCT` | 1년 전 같은 시기 값이 이 비율 넘게 들쭉날쭉하면 판정 보류 |
| `ALLOWED_DOMAINS` | 구독 허용 메일 도메인(빈 배열이면 제한 없음) |
| `CHART_DAYS` | 메일 그래프에 보여줄 최근 기간(일) |

- 같은 상태(급등/급락)가 이어지는 동안은 다시 보내지 않고, 정상으로 돌아왔다가 다시 넘으면 다시 알립니다(`발송이력` 시트).
- 가격은 대시보드와 같이 1kg 기준으로 환산해 보여줍니다(계란은 조사 단위 그대로).

## 가격 출처

| 품목 | 출처 | 전년동기 비교 |
|---|---|---|
| 쌀(111) · 콩(141) · 고구마(151) · 참깨(312) · 들깨(313) · 고춧가루(소매, 248) · 건고추 화건 도매(248D) | 한국농수산식품유통공사 `최근일자 도·소매가격정보` API (`fetch_at_recent.py`) | API가 주는 1년 전 가격 사용 → 알림 판정 대상 |
| 배추(211) | 같은 API — 계절별 품종 자동 전환(봄·여름(고랭지)·가을·월동) | 같은 품종의 1년 전 가격 사용 |
| 딸기(226, 설향) | 같은 API — 시즌(약 11~4월)에만 조사 | 시즌 중에만 판정, 비수기에는 건너뜀 |
| 멸치액젓 · 천일염 | 이 API에 자료 없음 — 대체 출처 검토 중 | 알림 판정 제외 |
| 계란 · 밤 | 수동 갱신 | 알림 판정 제외 |

- **배추 품종 선택**: 최근 7일 안에 조사된 품종 중 월별 우선순위(`CABBAGE_SEASON_PREF`)에 맞는 품종을 씁니다. 품종이 바뀌면 가격 수준이 달라지는 것이 정상이며,
  전년동기 비교는 항상 같은 품종의 1년 전 가격과 합니다.
- **오래된 값 차단**: 최근 조사일이 21일(`STALE_DAYS`, `MAX_STALE_DAYS`)보다 오래된 품목은 대시보드 갱신과 알림 판정에서 모두 건너뜁니다(딸기 비수기 등).

연결되는 품목은 `scripts/fetch_at_recent.py` 의 `TARGETS` 에 추가합니다(실행 로그의 `[탐색]` 줄에서 품종·등급 코드 확인).

## 인증키

- 공공데이터포털 인증키는 GitHub Secrets 의 `DATA_GO_KR_KEY` 로만 사용합니다. 코드·문서·채팅에 적지 않습니다.

## 문제 확인

- 메일이 안 올 때: Apps Script 왼쪽 **실행** 메뉴에서 `checkAndSend` 실행 기록과 로그 확인
- 그래프가 빠질 때: 로그의 `chart attempt N failed` 줄 확인(실패하면 단순한 형태로 자동 재시도)
- 구독이 안 들어올 때: 스프레드시트 `구독자` 시트 확인, 웹 앱 액세스 권한이 **모든 사용자**인지 확인
