/**
 * NH FOOD 원물 시세 대시보드 - 관심품목 알림 구독 백엔드
 *
 * 사용법:
 * 1. 구독 정보를 저장할 새 Google 스프레드시트를 만든다.
 * 2. 확장 프로그램 > Apps Script 메뉴로 들어가 이 코드를 붙여넣는다.
 * 3. 배포 > 새 배포 > 유형: 웹 앱
 *    - 실행 계정: 나
 *    - 액세스 권한: 전체 공개(익명 사용자 포함)
 *    로 배포하고, 발급된 웹 앱 URL(.../exec 로 끝남)을 복사한다.
 * 4. 이 URL을 index.html의 SUBSCRIBE_API_URL 상수에 붙여넣는다.
 * 5. 같은 URL을 GitHub 저장소 Secrets에 SUBSCRIBE_SHEET_API_URL 로도 등록한다
 *    (알림 발송 스크립트가 구독자 목록을 읽어올 때 사용).
 */

const SHEET_NAME = 'subscribers';

function getSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow(['email', 'items', 'updated_at']);
  }
  return sheet;
}

// GET: 구독자 전체 목록을 JSON으로 반환 (알림 발송 스크립트가 호출)
function doGet(e) {
  const sheet = getSheet_();
  const values = sheet.getDataRange().getValues();
  const rows = values.slice(1); // 헤더 제외
  const result = rows
    .filter(r => r[0])
    .map(r => ({
      email: String(r[0]).trim(),
      items: String(r[1] || '').split(',').map(s => s.trim()).filter(Boolean),
      updated_at: r[2] instanceof Date ? r[2].toISOString() : String(r[2] || ''),
    }));
  return ContentService.createTextOutput(JSON.stringify(result))
    .setMimeType(ContentService.MimeType.JSON);
}

// POST: 대시보드에서 보낸 구독 신청(이메일 + 관심품목 코드 목록)을 저장/갱신
function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const email = String(data.email || '').trim().toLowerCase();
    const items = Array.isArray(data.items) ? data.items.filter(Boolean) : [];

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return jsonOut_({ ok: false, error: 'invalid email' });
    }

    const sheet = getSheet_();
    const values = sheet.getDataRange().getValues();
    let rowIndex = -1;
    for (let i = 1; i < values.length; i++) {
      if (String(values[i][0]).trim().toLowerCase() === email) { rowIndex = i + 1; break; }
    }
    const now = new Date();
    if (items.length === 0) {
      // 관심품목이 빈 배열로 오면 구독 해지로 간주하고 행을 삭제
      if (rowIndex > 0) sheet.deleteRow(rowIndex);
      return jsonOut_({ ok: true, unsubscribed: true });
    }
    if (rowIndex > 0) {
      sheet.getRange(rowIndex, 2).setValue(items.join(','));
      sheet.getRange(rowIndex, 3).setValue(now);
    } else {
      sheet.appendRow([email, items.join(','), now]);
    }
    return jsonOut_({ ok: true });
  } catch (err) {
    return jsonOut_({ ok: false, error: String(err) });
  }
}

function jsonOut_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
