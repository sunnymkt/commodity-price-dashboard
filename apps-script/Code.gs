/**
 * 원물 시세 대시보드 — 관심원물 급등·급락 알림 메일 (Google Apps Script)
 *
 * 구성
 *  1) doPost  : 대시보드의 [구독하기]/[구독 해지] 요청을 받아 '구독자' 시트에 저장
 *  2) checkAndSend : 매일 아침 DATA를 읽어 구독자별 관심 품목의 급등·급락을 판정하고 메일 발송
 *  3) setupTrigger : 매일 오전 9시(KST) 자동 실행 트리거 등록 (최초 1회 수동 실행)
 *
 * 판정 기준은 대시보드(yoyLightTier)와 동일: 전년동기 대비 +20% 이상 급등, -20% 이하 급락
 *
 * 설치 순서는 아래 README 참고 (스프레드시트 > 확장 프로그램 > Apps Script 에 붙여넣기)
 */

const CONFIG = {
  // 대시보드 DATA를 읽어올 주소. DATA가 들어있는 index.html 또는 JSON 파일의 "공개 접근 가능한" URL
  DATA_URL: 'https://sunnymkt.github.io/commodity-price-dashboard/',
  // 메일 하단 '대시보드 열기' 링크
  DASHBOARD_URL: 'https://sunnymkt.github.io/commodity-price-dashboard/',
  // 구독 허용 이메일 도메인 (빈 배열이면 제한 없음). 아무나 타인 메일을 구독 등록하는 것을 막기 위함
  ALLOWED_DOMAINS: ['nhfood.co.kr'],
  SURGE_PCT: 20,
  DROP_PCT: -20,
  SENDER_NAME: '원물 시세 알림',
  SUB_SHEET: '구독자',
  STATE_SHEET: '발송이력',
  ONLY_AT_SOURCES: true, // true면 가격 출처가 검증된 API(최근일자 도·소매가격, yoy_src='at') 품목만 급등·급락을 판정. 나머지는 이력 정리가 끝날 때까지 알림 제외
  MAX_STALE_DAYS: 21,    // 최근 조사일이 오늘보다 이 일수 넘게 오래된 품목(비수기·조사 중단)은 알림 판정에서 제외
  YOY_MAX_GAP_DAYS: 21, // 전년동기 비교: '1년 전 같은 날' 자료가 없을 때 허용하는 최대 날짜 차이(일). 넘으면 판정 제외
  YOY_MAX_SPREAD_PCT: 10, // 1년 전 같은 시기(±7일) 가격이 이 비율(%) 넘게 들쭉날쭉하면 자료를 믿기 어렵다고 보고 그 품목은 판정 보류
  CHART_DAYS: 180, // 메일 그래프에 보여줄 최근 기간(일)
};

/* ───────────── 1) 구독 / 해지 (웹 앱) ───────────── */

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    const email = String(body.email || '').trim().toLowerCase();
    const items = Array.isArray(body.items) ? body.items.map(String) : [];

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return json_({ ok: false, error: 'invalid_email' });
    const domain = email.split('@')[1];
    if (CONFIG.ALLOWED_DOMAINS.length && CONFIG.ALLOWED_DOMAINS.indexOf(domain) < 0) {
      return json_({ ok: false, error: 'domain_not_allowed' });
    }

    const lock = LockService.getScriptLock();
    lock.waitLock(10000);
    try {
      upsertSubscriber_(email, items);
    } finally {
      lock.releaseLock();
    }
    return json_({ ok: true });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

function doGet() {
  return ContentService.createTextOutput('commodity alert api ok');
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function sheet_(name, header) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.appendRow(header);
    sh.setFrozenRows(1);
  }
  return sh;
}

function upsertSubscriber_(email, items) {
  const sh = sheet_(CONFIG.SUB_SHEET, ['email', 'items', 'updatedAt']);
  const last = sh.getLastRow();
  const emails = last > 1 ? sh.getRange(2, 1, last - 1, 1).getValues().map(r => String(r[0]).toLowerCase()) : [];
  const idx = emails.indexOf(email);

  if (items.length === 0) {
    // 구독 해지: 구독 행과 발송 이력 삭제
    if (idx >= 0) sh.deleteRow(idx + 2);
    const st = loadState_();
    Object.keys(st).forEach(k => { if (k.indexOf(email + '|') === 0) delete st[k]; });
    saveState_(st);
    return;
  }
  const row = [email, items.join(','), new Date()];
  if (idx >= 0) sh.getRange(idx + 2, 1, 1, 3).setValues([row]);
  else sh.appendRow(row);
}

function loadSubscribers_() {
  const sh = sheet_(CONFIG.SUB_SHEET, ['email', 'items', 'updatedAt']);
  const last = sh.getLastRow();
  if (last < 2) return [];
  return sh.getRange(2, 1, last - 1, 2).getValues()
    .map(r => ({ email: String(r[0]).trim(), items: String(r[1]).split(',').map(s => s.trim()).filter(Boolean) }))
    .filter(s => s.email && s.items.length);
}

/* 발송 이력: "이메일|품목코드" → 마지막으로 알린 상태(급등/급락). 같은 상태가 이어지는 동안은 재발송하지 않음 */
function loadState_() {
  const sh = sheet_(CONFIG.STATE_SHEET, ['key', 'tier', 'sentAt']);
  const last = sh.getLastRow();
  const st = {};
  if (last > 1) sh.getRange(2, 1, last - 1, 2).getValues().forEach(r => { st[String(r[0])] = String(r[1]); });
  return st;
}

function saveState_(st) {
  const sh = sheet_(CONFIG.STATE_SHEET, ['key', 'tier', 'sentAt']);
  const last = sh.getLastRow();
  if (last > 1) sh.getRange(2, 1, last - 1, 3).clearContent();
  const keys = Object.keys(st);
  if (keys.length) {
    const now = new Date();
    sh.getRange(2, 1, keys.length, 3).setValues(keys.map(k => [k, st[k], now]));
  }
}

/* ───────────── 2) 판정 + 메일 발송 ───────────── */

function checkAndSend() { run_(false, null); }

/** 본인 메일로 발송 테스트 (급등·급락이 없으면 첫 품목으로 샘플 발송, 발송 이력은 건드리지 않음) */
function testSend() { run_(true, Session.getEffectiveUser().getEmail()); }

function run_(isTest, testTo) {
  const data = fetchData_();
  // 1kg 기준 환산(대시보드와 동일) 후, 전년동기(1년 전 같은 날) 대비를 가격 이력에서 직접 계산
  Object.keys(data).forEach(c => { data[c] = applyTrueYoy_(toKgView_(data[c])); });
  const flagged = {};
  Object.keys(data).forEach(code => {
    const it = data[code];
    const pct = it.yoy_chg_pct;
    if (pct == null) return;
    if (pct >= CONFIG.SURGE_PCT) flagged[code] = '급등';
    else if (pct <= CONFIG.DROP_PCT) flagged[code] = '급락';
  });

  if (isTest) {
    if (!Object.keys(flagged).length) {
      const ok = Object.keys(data).filter(c => data[c].yoy_chg_pct != null);
      if (ok.length) flagged[ok[0]] = '테스트';
    }
    sendMail_(testTo, Object.keys(flagged).map(c => ({ code: c, tier: flagged[c], item: data[c] })));
    return;
  }

  const state = loadState_();
  loadSubscribers_().forEach(sub => {
    const toSend = [];
    sub.items.forEach(code => {
      const key = sub.email + '|' + code;
      const tier = flagged[code];
      if (!tier) { delete state[key]; return; }       // 정상 복귀 → 이력 초기화(다음 급등락 때 다시 알림)
      if (state[key] !== tier) {
        toSend.push({ code, tier, item: data[code] });
        state[key] = tier;
      }
    });
    if (toSend.length) {
      try { sendMail_(sub.email, toSend); }
      catch (err) { toSend.forEach(t => delete state[sub.email + '|' + t.code]); console.error(sub.email, err); }
    }
  });
  saveState_(state);
}

function fetchData_() {
  const res = UrlFetchApp.fetch(CONFIG.DATA_URL, { muteHttpExceptions: true, followRedirects: true });
  if (res.getResponseCode() !== 200) throw new Error('DATA_URL 응답 오류: ' + res.getResponseCode());
  const text = res.getContentText('UTF-8');
  if (/\.json(\?|$)/i.test(CONFIG.DATA_URL)) return JSON.parse(text);
  const m = text.match(/^const DATA = (\{.*\});\s*$/m); // index.html 안의 한 줄짜리 DATA 선언
  if (!m) throw new Error('DATA를 찾지 못했습니다. DATA_URL을 확인하세요.');
  return JSON.parse(m[1]);
}

/* ───────────── 메일 본문 ───────────── */

const COLOR = { up: '#d32f2f', down: '#1565c0', flat: '#757575', navy: '#1e3a5f' };

/** 대시보드와 동일하게 1kg 기준으로 환산 (계란 등 개수 단위는 그대로 둠) */
function kgDivisor_(unit) {
  unit = String(unit || '');
  if (/^구\d+/.test(unit)) return null;
  const m = unit.match(/^kg.*?(\d+)$/);
  if (m) return parseInt(m[1], 10);
  if (unit.indexOf('kg') === 0) return 1;
  return null;
}

function toKgView_(item) {
  const div = kgDivisor_(item.unit);
  if (!div || div === 1) return item;
  const conv = v => (v == null ? v : v / div);
  const out = Object.assign({}, item);
  out.unit = 'kg';
  out.latest_price = conv(item.latest_price);
  out.yoy_price = conv(item.yoy_price);
  out.points = (item.points || []).map(p => [p[0], conv(p[1])]);
  out.yoy_points = (item.yoy_points || []).map(p => [p[0], conv(p[1])]);
  return out;
}

function unitSuffix_(unit) {
  unit = String(unit || '');
  if (unit.indexOf('kg') === 0) return '원/kg';
  const m = unit.match(/^구(\d+)/);
  return m ? '원/' + m[1] + '구' : '원';
}
function unitPer_(unit) {
  unit = String(unit || '');
  if (unit.indexOf('kg') === 0) return '1kg당 ';
  const m = unit.match(/^구(\d+)/);
  return m ? m[1] + '구당 ' : '';
}

function signColor_(p) { return p > 0 ? COLOR.up : (p < 0 ? COLOR.down : COLOR.flat); }
function arrow_(p) { return p > 0 ? '▲' : (p < 0 ? '▼' : '–'); }
function absPct_(p) { return Math.abs(p); }

function pill_(label, pct) {
  const txt = pct == null ? '-' : arrow_(pct) + ' ' + absPct_(pct) + '%';
  const col = pct == null ? COLOR.flat : signColor_(pct);
  return '<td align="center" width="33%" style="padding:8px 4px;border:1px solid #e3e3e3;border-radius:8px">' +
    '<div style="font-size:11px;color:#777">' + label + '</div>' +
    '<div style="font-size:16px;font-weight:700;color:' + col + '">' + txt + '</div></td>';
}

function plotWindow_(item) {
  const pts = item.points || [];
  if (pts.length < 2) return null;
  const last = parseYmd_(pts[pts.length - 1][0]);
  const from = new Date(last.getTime() - CONFIG.CHART_DAYS * 86400000);
  let win = pts.filter(p => parseYmd_(p[0]) >= from);
  if (win.length < 2) win = pts.slice(-30);
  return win;
}
function parseYmd_(s) { s = String(s); return new Date(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8)); }

/* ───────────── 전년동기 비교 ───────────── */

function oneYearBefore_(d) {
  const x = new Date(d.getFullYear() - 1, d.getMonth(), d.getDate());
  return x.getMonth() === d.getMonth() ? x : new Date(d.getFullYear() - 1, d.getMonth() + 1, 0); // 2/29 → 2/28
}

/** 최근 이력(points)과 전년 이력(yoy_points)을 합친 날짜순 가격표 */
function pricePool_(item) {
  const m = {};
  (item.yoy_points || []).forEach(p => { m[String(p[0])] = p[1]; });
  (item.points || []).forEach(p => { m[String(p[0])] = p[1]; });
  return Object.keys(m).sort().map(k => ({ ymd: k, t: parseYmd_(k).getTime(), p: m[k] }));
}

function nearest_(pool, target, maxGapDays) {
  let best = null, bestGap = Infinity;
  pool.forEach(e => {
    const g = Math.abs(e.t - target.getTime()) / 86400000;
    if (g < bestGap) { best = e; bestGap = g; }
  });
  return best && bestGap <= maxGapDays ? { entry: best, gap: Math.round(bestGap) } : null;
}

/**
 * 전년동기 대비 = (최근 조사일 가격) ÷ (정확히 1년 전 같은 날 가격) − 1
 * 같은 날 자료가 없으면 가장 가까운 조사일(YOY_MAX_GAP_DAYS 이내)을 쓰고, 그것도 없으면 판정에서 제외(null)
 */
function applyTrueYoy_(item) {
  // 최근일자 도·소매가격 API(yoy_src='at')는 1년 전 가격을 API가 직접 주므로 그 값을 그대로 쓴다
  if (item.yoy_src === 'at' && item.yoy_price != null && item.yoy_date && item.latest_price != null) {
    const o = Object.assign({}, item);
    const ageDays = (new Date().getTime() - parseYmd_(item.latest_date).getTime()) / 86400000;
    if (ageDays > CONFIG.MAX_STALE_DAYS) {          // 비수기·조사 중단 품목은 오래된 값으로 알리지 않는다
      o.yoy_chg_pct = null; o.yoy_stale = true;
      return o;
    }
    o.yoy_chg_pct = Math.round((item.latest_price / item.yoy_price - 1) * 1000) / 10;
    o.yoy_gap = 0;
    o.yoy_pool = pricePool_(item);
    return o;
  }
  const out = Object.assign({}, item);
  out.yoy_chg_pct = null; out.yoy_date = null; out.yoy_price = null; out.yoy_gap = null; out.yoy_pool = null;
  if (CONFIG.ONLY_AT_SOURCES) return out;   // 출처가 검증되지 않은 품목은 전년동기 판정에서 제외
  if (item.latest_price == null || !item.latest_date) return out;
  const pool = pricePool_(item);
  const hit = nearest_(pool, oneYearBefore_(parseYmd_(item.latest_date)), CONFIG.YOY_MAX_GAP_DAYS);
  if (!hit || !hit.entry.p) return out;
  // 안전장치: 1년 전 같은 시기 값이 서로 크게 어긋나면(서로 다른 출처가 섞인 경우 등) 잘못된 급등·급락을 알리지 않도록 보류
  const tgt = oneYearBefore_(parseYmd_(item.latest_date)).getTime();
  const around = pool.filter(e => Math.abs(e.t - tgt) / 86400000 <= 7 && e.p > 0).map(e => e.p);
  if (around.length >= 2 && (Math.max.apply(null, around) / Math.min.apply(null, around) - 1) * 100 > CONFIG.YOY_MAX_SPREAD_PCT) {
    out.yoy_unstable = true;
    return out;
  }
  out.yoy_date = hit.entry.ymd;
  out.yoy_price = hit.entry.p;
  out.yoy_gap = hit.gap;
  out.yoy_chg_pct = Math.round((item.latest_price / hit.entry.p - 1) * 1000) / 10;
  out.yoy_pool = pool;
  return out;
}

/** 그래프의 각 날짜에 대응하는 "1년 전 같은 날" 가격 (없으면 null → 선이 끊김) */
function lastYearSeries_(win, pool) {
  return win.map(p => {
    const hit = nearest_(pool || [], oneYearBefore_(parseYmd_(p[0])), 7);
    return hit ? hit.entry.p : null;
  });
}

/** 그래프를 만든다. 일부 옵션이 Apps Script에서 거부되어도 메일에서 그래프가 사라지지 않도록 단계적으로 다시 시도한다 */
function chartBlob_(item, win, color) {
  const modes = [
    { styled: true, prev: true },    // 1) 모든 옵션(한글 월 눈금용 여백 지정, 점선 등)
    { styled: false, prev: true },   // 2) 세부 스타일 옵션 없이
    { styled: false, prev: false },  // 3) 올해 가격선만
    { styled: false, prev: false, legacy: true },  // 4) 처음에 잘 동작했던 가장 단순한 형태
  ];
  let lastErr = null;
  for (let i = 0; i < modes.length; i++) {
    try {
      return { blob: buildChart_(item, win, color, modes[i]), styled: modes[i].styled };
    } catch (e) {
      lastErr = e;
      console.error('chart attempt ' + (i + 1) + ' failed: ' + e);
      Utilities.sleep(700);   // 일시적인 서버 오류일 수 있어 잠시 쉬고 다시 시도
    }
  }
  throw lastErr;
}

function buildChart_(item, win, color, mode) {
  if (mode.legacy) {
    const dt0 = Charts.newDataTable()
      .addColumn(Charts.ColumnType.DATE, '날짜')
      .addColumn(Charts.ColumnType.NUMBER, '가격');
    win.forEach(p => dt0.addRow([parseYmd_(p[0]), p[1]]));
    return Charts.newLineChart().setDataTable(dt0.build())
      .setLegendPosition(Charts.Position.NONE).setColors([color]).setDimensions(600, 260)
      .build().getAs('image/png');
  }
  let prev = mode.prev ? lastYearSeries_(win, item.yoy_pool) : win.map(() => null);
  // 1년 전 이력이 거의 없으면(새 API로 막 전환한 품목) 1년 전 가격을 가로선으로 보여준다
  if (mode.prev && prev.filter(v => v != null).length < 3 && item.yoy_price != null) prev = win.map(() => item.yoy_price);
  // 빈 칸(null)이 있으면 가장 가까운 앞쪽 값으로 채워 차트 오류를 막는다
  let carry = prev.find(v => v != null);
  prev = prev.map(v => { if (v != null) carry = v; return carry; });
  const hasPrev = mode.prev && prev.some(v => v != null);

  const prices = win.map(p => p[1]).concat(hasPrev ? prev.filter(v => v != null) : []);
  const lo = Math.min.apply(null, prices), hi = Math.max.apply(null, prices);
  const pad = Math.max((hi - lo) * 0.15, hi * 0.03);
  const step = Math.pow(10, Math.max(0, String(Math.round(hi)).length - 3));
  const min = Math.max(0, Math.floor((lo - pad) / step) * step);
  const max = Math.ceil((hi + pad) / step) * step;

  const dt = Charts.newDataTable()
    .addColumn(Charts.ColumnType.STRING, '날짜')
    .addColumn(Charts.ColumnType.NUMBER, '최근 가격');
  if (hasPrev) dt.addColumn(Charts.ColumnType.NUMBER, '1년 전 같은 시기 가격');
  win.forEach((p, i) => dt.addRow(hasPrev ? [String(p[0]), p[1], prev[i]] : [String(p[0]), p[1]]));

  let b = Charts.newLineChart()
    .setDataTable(dt.build())
    .setLegendPosition(Charts.Position.TOP)
    .setColors([color, '#8a8a8a'])
    .setDimensions(600, 300)
    .setBackgroundColor('#ffffff')
    .setOption('vAxis.viewWindow.min', min)
    .setOption('vAxis.viewWindow.max', max);
  if (mode.styled) {
    b = b
      .setOption('chartArea.left', 60)
      .setOption('chartArea.top', 40)
      .setOption('chartArea.width', 520)
      .setOption('chartArea.height', 230)
      .setOption('hAxis.textPosition', 'none')      // 영문 월 표시를 숨기고, 한글 월 눈금은 메일 본문에서 그림
      .setOption('vAxis.format', '#,###')
      .setOption('vAxis.textStyle.fontSize', 11)
      .setOption('vAxis.gridlines.color', '#e6e6e6')
      .setOption('legend.textStyle.fontSize', 12)
      .setOption('series.0.lineWidth', 4)
      .setOption('series.1.lineWidth', 2)
      .setOption('series.1.lineDashStyle', [6, 4]);
  }
  return b.build().getAs('image/png');
}

/** 그래프 아래 한글 월 눈금 (그래프의 가로 위치와 맞추기 위해 % 폭으로 계산) */
function monthTicksHtml_(win) {
  const n = win.length, W = 600, L = 60, PW = 520;
  const frac = i => (L + (i + 0.5) / n * PW) / W;
  const pct = x => (x * 100).toFixed(2) + '%';
  const all = [];
  let prev = '';
  win.forEach((p, i) => {
    const ym = String(p[0]).slice(0, 6);
    if (ym !== prev) { all.push({ i: i, y: +ym.slice(0, 4), m: +ym.slice(4, 6) }); prev = ym; }
  });
  const kept = [];
  all.forEach(t => {
    if (!kept.length) { kept.push(t); return; }
    const gap = frac(t.i) - frac(kept[kept.length - 1].i);
    if (gap >= 0.075) kept.push(t);
    else if (kept.length === 1) kept[0] = t;      // 첫 달이 며칠 안 되면 다음 달 눈금으로 대체
  });
  let html = '<table width="100%" style="table-layout:fixed;border-collapse:collapse"><tr>' +
    '<td style="width:' + pct(frac(kept[0].i)) + ';padding:0"></td>';
  kept.forEach((t, k) => {
    const next = k + 1 < kept.length ? frac(kept[k + 1].i) : 1;
    const label = (k === 0 || t.m === 1) ? String(t.y).slice(2) + '년 ' + t.m + '월' : t.m + '월';
    html += '<td style="width:' + pct(next - frac(t.i)) + ';padding:0 0 0 3px;border-left:1px solid #bdbdbd;' +
      'font-size:11px;color:#666;white-space:nowrap;text-align:left">' + label + '</td>';
  });
  return html + '</tr></table>';
}

function cardHtml_(t, cid, win, styled) {
  const it = t.item, pct = it.yoy_chg_pct;
  const isTest = t.tier === '테스트';
  const up = t.tier === '급등';
  const barColor = isTest ? '#546e7a' : (up ? COLOR.up : COLOR.down);
  const bg = isTest ? '#f3f5f7' : (up ? '#fdeeee' : '#eaf2fc');
  const emoji = isTest ? '⚪' : (up ? '🔴' : '🔵');
  const title = esc_(it.name) + (isTest ? ' · 샘플' : ' ' + t.tier);
  const numColor = signColor_(pct);
  const suffix = unitSuffix_(it.unit);
  const diff = (it.latest_price != null && it.yoy_price != null) ? it.latest_price - it.yoy_price : null;
  const verb = pct > 0 ? '올랐어요' : (pct < 0 ? '내렸어요' : '같아요');
  const diffTxt = diff == null ? '' : ' (' + unitPer_(it.unit) + (diff > 0 ? '+' : (diff < 0 ? '-' : '')) + fmtNum_(Math.abs(diff)) + '원)';
  const sentence = esc_(it.name) + ' 가격이 1년 전 같은 시기(' + fmtDate_(it.yoy_date) + ')보다 ' +
    '<b style="color:' + numColor + '">' + absPct_(pct) + '% ' + verb + '</b>' + diffTxt + '.';
  const link = it.source_url ? ' · <a href="' + esc_(it.source_url) + '" style="color:#1565c0">출처 보기</a>' : '';

  const priceRow = '<table width="100%" style="border-collapse:separate;border-spacing:6px 0;margin:0 -6px"><tr>' +
    '<td align="center" width="34%" style="padding:10px 4px;background:#f7f7f7;border-radius:8px">' +
    '<div style="font-size:11px;color:#777">지금 (' + fmtDate_(it.latest_date) + ')</div>' +
    '<div style="font-size:20px;font-weight:800;color:#222">' + fmtNum_(it.latest_price) + '<span style="font-size:11px;font-weight:400"> ' + suffix + '</span></div></td>' +
    '<td align="center" width="34%" style="padding:10px 4px;background:#f7f7f7;border-radius:8px">' +
    '<div style="font-size:11px;color:#777">1년 전 (' + fmtDate_(it.yoy_date) + ')</div>' +
    '<div style="font-size:20px;font-weight:800;color:#555">' + fmtNum_(it.yoy_price) + '<span style="font-size:11px;font-weight:400"> ' + suffix + '</span></div></td>' +
    '<td align="center" width="32%" style="padding:10px 4px;background:' + bg + ';border-radius:8px">' +
    '<div style="font-size:11px;color:#777">차이</div>' +
    '<div style="font-size:20px;font-weight:800;color:' + numColor + '">' +
    (diff == null ? '-' : (diff > 0 ? '+' : (diff < 0 ? '-' : '')) + fmtNum_(Math.abs(diff))) +
    '<span style="font-size:11px;font-weight:400"> 원</span></div></td></tr></table>';

  const pills = '<table width="100%" style="border-collapse:separate;border-spacing:6px 0;margin:10px -6px 0"><tr>' +
    pill_('어제보다', it.day_chg_pct) + pill_('1주 전보다', it.week_chg_pct) + pill_('1개월 전보다', it.month_chg_pct) + '</tr></table>';

  let chart = '';
  if (win) {
    chart = '<div style="margin-top:14px;font-size:13px;font-weight:700;color:#333">최근 가격 추이 ' +
      '<span style="font-weight:400;color:#777">(' + fmtDate_(win[0][0]) + ' ~ ' + fmtDate_(win[win.length - 1][0]) + ')</span></div>' +
      '<img src="cid:' + cid + '" width="100%" style="display:block;width:100%;height:auto;margin-top:4px" alt="가격 추이 그래프">' +
      (styled === false ? '' : monthTicksHtml_(win)) +
      '<div style="font-size:11px;color:#777;margin-top:6px">굵은 실선 = 올해 가격 · 회색 점선 = 1년 전 같은 시기의 실제 가격 (두 선이 벌어질수록 변화가 큽니다)</div>';
  }

  return '<table width="100%" style="border-collapse:separate;border-spacing:0;border:2px solid ' + barColor + ';border-radius:12px;margin:0 0 20px">' +
    '<tr><td style="background:' + barColor + ';color:#fff;padding:12px 16px;font-size:18px;font-weight:700;border-radius:9px 9px 0 0">' + emoji + ' ' + title + '</td></tr>' +
    '<tr><td style="padding:16px;background:' + bg + '">' +
    '<div style="font-size:12px;color:#555">1년 전 같은 시기 대비</div>' +
    '<div style="font-size:42px;font-weight:800;line-height:1.15;color:' + numColor + '">' + arrow_(pct) + ' ' + (pct > 0 ? '+' : (pct < 0 ? '-' : '')) + absPct_(pct) + '%</div>' +
    '<div style="font-size:14px;color:#333;margin-top:6px;line-height:1.5">' + sentence + '</div></td></tr>' +
    '<tr><td style="padding:14px 16px 6px">' + priceRow + pills + chart + '</td></tr>' +
    '<tr><td style="padding:6px 16px 14px;font-size:11px;color:#888;line-height:1.6">' +
    (it.yoy_gap > 0 ? '※ 1년 전 같은 날 조사 자료가 없어 가장 가까운 조사일(' + fmtDate_(it.yoy_date) + ')과 비교했어요.<br>' : '') +
    '조사 기준: ' + esc_(it.basis || '') + link + '</td></tr></table>';
}

function sendMail_(to, list) {
  const inline = {};
  const wins = {};
  const styledOf = {};
  list.forEach((t, i) => {
    const cid = 'chart' + i;
    const win = plotWindow_(t.item);
    if (!win) return;
    const color = t.tier === '급등' ? COLOR.up : (t.tier === '급락' ? COLOR.down : signColor_(t.item.yoy_chg_pct));
    try { const r = chartBlob_(t.item, win, color); inline[cid] = r.blob.setName(cid + '.png'); wins[cid] = win; styledOf[cid] = r.styled; }
    catch (e) { console.error('chart', e); }
  });

  const hasTest = list.some(t => t.tier === '테스트');
  const asOf = list.map(t => String(t.item.latest_date || '')).sort().pop();

  const summary = list.length < 2 ? '' :
    '<table width="100%" style="border-collapse:collapse;margin:0 0 18px;font-size:14px">' +
    list.map(t => {
      const c = t.tier === '급등' ? COLOR.up : (t.tier === '급락' ? COLOR.down : COLOR.flat);
      return '<tr><td style="padding:8px 4px;border-bottom:1px solid #eee"><b>' + esc_(t.item.name) + '</b></td>' +
        '<td align="right" style="padding:8px 4px;border-bottom:1px solid #eee;color:' + c + ';font-weight:700">' +
        arrow_(t.item.yoy_chg_pct) + ' ' + fmtPct_(t.item.yoy_chg_pct) + ' ' + esc_(t.tier) + '</td></tr>';
    }).join('') + '</table>';

  const cards = list.map((t, i) => cardHtml_(t, 'chart' + i, wins['chart' + i] || null, styledOf['chart' + i])).join('');

  const html = '<div style="font-family:Arial,\'Malgun Gothic\',sans-serif;max-width:640px;margin:0 auto;color:#222">' +
    '<div style="background:' + COLOR.navy + ';color:#fff;padding:18px 20px;border-radius:12px 12px 0 0">' +
    '<div style="font-size:12px;opacity:.8">NH FOOD 원물 시세</div>' +
    '<div style="font-size:20px;font-weight:700;margin-top:2px">관심 품목 급등·급락 알림</div>' +
    '<div style="font-size:12px;margin-top:4px;opacity:.85">조사 기준일 ' + fmtDate_(asOf) + '</div></div>' +
    '<div style="padding:16px 4px 0">' +
    (hasTest ? '<div style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:10px 12px;font-size:13px;margin:0 0 14px">' +
      '※ 테스트 메일입니다. 지금은 급등·급락 품목이 없어 샘플 1건을 보냈어요.</div>' : '') +
    '<div style="font-size:13px;color:#555;margin:0 0 14px;line-height:1.6">관심 품목 가격이 <b>1년 전 같은 시기</b>보다 크게 변하면 알려드려요. ' +
    '<span style="color:' + COLOR.up + ';font-weight:700">▲ 급등</span> = +' + CONFIG.SURGE_PCT + '% 이상, ' +
    '<span style="color:' + COLOR.down + ';font-weight:700">▼ 급락</span> = ' + CONFIG.DROP_PCT + '% 이하</div>' +
    summary + cards +
    (CONFIG.DASHBOARD_URL.indexOf('REPLACE') === 0 ? '' :
      '<div style="text-align:center;margin:8px 0 16px"><a href="' + esc_(CONFIG.DASHBOARD_URL) + '" ' +
      'style="display:inline-block;background:' + COLOR.navy + ';color:#fff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:700">대시보드에서 자세히 보기</a></div>') +
    '<p style="font-size:11px;color:#999;line-height:1.5">알림 해지는 대시보드의 [관심원물 시세 추이 알림받기]에서 할 수 있어요. ' +
    '가격은 대시보드와 같이 1kg 기준으로 환산해 보여드립니다(계란은 조사 단위 그대로).</p></div></div>';

  const emoji = t => t.tier === '급등' ? '🔴' : (t.tier === '급락' ? '🔵' : '⚪');
  const names = list.map(t => emoji(t) + ' ' + t.item.name + ' ' + t.tier + ' ' + fmtPct_(t.item.yoy_chg_pct)).join(', ');
  const subject = '[원물 시세 알림] ' + (names.length > 70 ? names.slice(0, 67) + '…' : names);

  MailApp.sendEmail({ to: to, subject: subject, htmlBody: html, name: CONFIG.SENDER_NAME, inlineImages: inline });
}

/* ───────────── 3) 트리거 ───────────── */

/** 최초 1회 실행: 매일 오전 9시(KST)에 checkAndSend 실행 */
function setupTrigger() {
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'checkAndSend') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('checkAndSend').timeBased().everyDays(1).atHour(9).inTimezone('Asia/Seoul').create();
}

/* ───────────── 유틸 ───────────── */

function esc_(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}
function fmtNum_(n) { return n == null ? '-' : String(Math.round(Number(n))).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
function fmtPct_(p) { return p == null ? '-' : (p > 0 ? '+' : '') + p + '%'; }
function fmtDate_(d) { const s = String(d || ''); return s.length === 8 ? s.slice(0, 4) + '.' + s.slice(4, 6) + '.' + s.slice(6, 8) : s; }

/*
 * README — 설치 순서
 * 1. Google 스프레드시트를 새로 만들고 확장 프로그램 > Apps Script 를 연다.
 * 2. 이 코드를 붙여넣고 CONFIG의 DATA_URL / DASHBOARD_URL / ALLOWED_DOMAINS 를 채운다.
 * 3. testSend 를 한 번 실행해 권한(메일 발송·외부 요청·스프레드시트)을 승인하고, 본인 메일로 샘플이 오는지 확인한다.
 * 4. setupTrigger 를 한 번 실행해 매일 오전 9시 자동 실행을 등록한다.
 * 5. 배포 > 새 배포 > 유형 "웹 앱" > 실행 사용자: 나, 액세스 권한: 모든 사용자 → 발급된 /exec URL을 복사한다.
 * 6. 대시보드 코드의 SUBSCRIBE_API_URL('REPLACE_WITH_APPS_SCRIPT_WEB_APP_URL')을 그 URL로 교체한다.
 */
