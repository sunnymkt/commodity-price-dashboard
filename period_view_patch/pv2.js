// ===== 주간·월간 시세 뷰 (국산원물·국제원료 공용) =====
// 일/주 단위 시세(points)를 주·월로 집계해 히트맵 표로 보여준다. 데이터가 없는 기간은 '–' 로 두고 보간하지 않는다.
function createPeriodView(cfg) {
  const P = cfg.prefix;                                   // 요소 id 접두어
  const $ = id => document.getElementById(P + id);
  const box = $('Box'), root = document.getElementById(cfg.root);
  if (!box || !root) return;
  const st = { g: 'd', m: 'p', open: null };
  const pd = s => new Date(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8));
  const mondayOf = d => { const x = new Date(d); x.setDate(x.getDate() - (x.getDay() + 6) % 7); x.setHours(0, 0, 0, 0); return x; };
  const keyOf = d => st.g === 'w' ? mondayOf(d).getTime() : new Date(d.getFullYear(), d.getMonth(), 1).getTime();
  const pct = (a, b) => (b ? (a - b) / b * 100 : null);
  const sg = v => (v > 0 ? '+' : '') + v.toFixed(1) + '%';
  const f = v => v >= 100 ? Math.round(v).toLocaleString('ko-KR') : v.toFixed(cfg.dec != null ? cfg.dec : 1);
  const tint = (p, mx) => (p == null || Math.abs(p) < 0.05) ? 'transparent'
    : `rgba(${p > 0 ? '208,59,59' : '42,120,214'},${(Math.min(Math.abs(p) / mx, 1) * 0.55).toFixed(2)})`;
  // 일별 이력: (국산원물) HISTORY(원 단위, 백필+누적)와 item.points(이미 1kg 환산) 를 합친다. item.points 값이 우선.
  const allPoints = (item, code) => {
    const m = new Map();
    if (cfg.useHistory) {
      const div = item.kg_divisor || 1;
      ((typeof HISTORY !== 'undefined' && HISTORY[code]) || []).forEach(([s, v]) => m.set(s, v / div));
    }
    (item.points || []).forEach(([s, v]) => m.set(s, v));
    return [...m.entries()].sort();
  };

  function aggregate(item, code) {
    const m = new Map();
    allPoints(item, code).forEach(([s, v]) => {
      const k = keyOf(pd(s));
      if (!m.has(k)) m.set(k, []);
      m.get(k).push(v);
    });
    const out = new Map();
    m.forEach((a, k) => out.set(k, { t: new Date(k), avg: a.reduce((x, y) => x + y, 0) / a.length, min: Math.min(...a), max: Math.max(...a) }));
    return out;
  }
  function yoyValue(item, t, aggMap) {
    const prev = new Date(t); prev.setFullYear(prev.getFullYear() - 1);
    const hit = aggMap.get(keyOf(prev));
    if (hit) return hit.avg;
    let best = null, bd = 1e15;
    (item.yoy_points || []).forEach(([s, v]) => { const dd = Math.abs(pd(s) - prev); if (dd < bd) { bd = dd; best = v; } });
    return bd <= (st.g === 'w' ? 10 : 20) * 864e5 ? best : null;
  }
  function slots(endDate, n) {
    const out = [], e = st.g === 'w' ? mondayOf(endDate) : new Date(endDate.getFullYear(), endDate.getMonth(), 1);
    for (let i = n - 1; i >= 0; i--) {
      const t = new Date(e);
      if (st.g === 'w') t.setDate(t.getDate() - 7 * i); else t.setMonth(t.getMonth() - i);
      out.push(t);
    }
    return out;
  }
  function label(t) {
    if (st.g === 'w') {
      const j = new Date(t.getFullYear(), 0, 1);
      return [Math.ceil(((t - j) / 864e5 + j.getDay() + 1) / 7) + '주', `${t.getMonth() + 1}/${t.getDate()}`];
    }
    return [`${t.getMonth() + 1}월`, String(t.getFullYear())];
  }

  function draw() {
    $('G').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.v === st.g));
    const on = st.g !== 'd';
    root.classList.toggle('pv-on', on);
    box.style.display = on ? '' : 'none';
    $('M').style.display = on ? '' : 'none';
    if (!on) return;
    const entries = cfg.entries();
    const rows = entries.map(([code, it]) => ({ code, it, pts: allPoints(it, code), a: aggregate(it, code) }));
    const lastDate = rows.reduce((a, r) => r.pts.length && r.pts[r.pts.length - 1][0] > a ? r.pts[r.pts.length - 1][0] : a, '');
    const endDate = pd(lastDate);
    const n = st.g === 'w' ? 8 : 12, mx = cfg.mx[st.g === 'w' ? 0 : 1];
    const cols = slots(endDate, n);

    const chg = rows.map(r => {
      const c = r.a.get(cols[n - 1].getTime()), p = r.a.get(cols[n - 2].getTime());
      return c && p ? pct(c.avg, p.avg) : null;
    }).filter(v => v != null);
    const up = chg.filter(v => v >= 1).length, dn = chg.filter(v => v <= -1).length;
    let h = `<div class="pv-kpis"><div class="pv-kpi">${st.g === 'w' ? '지난주' : '지난달'} 대비 상승<b class="pv-up">${up}품목</b></div>`
      + `<div class="pv-kpi">보합<b>${chg.length - up - dn}품목</b></div><div class="pv-kpi">하락<b class="pv-dn">${dn}품목</b></div>`
      + `<div class="pv-kpi" title="이번 기간과 직전 기간 값이 모두 있어 증감을 계산할 수 있는 품목 수">집계 대상 품목<br><span style="font-size:10px">(이번·직전 기간 값 모두 있음)</span><b>${chg.length}/${rows.length}</b></div></div>`;
    h += `<div class="pv-card"><table><thead><tr><th class="nm">품목</th><th class="now">${cfg.nowHead}</th>`;
    cols.forEach((t, i) => { const [a, b] = label(t); h += `<th class="${i === n - 1 ? 'cur' : ''}">${a}<small>${b}${i === n - 1 ? ' 진행' : ''}</small></th>`; });
    h += `</tr></thead><tbody>`;
    rows.forEach(({ code, it, pts, a }) => {
      const cur = a.get(cols[n - 1].getTime()), pr = a.get(cols[n - 2].getTime());
      const d = cur && pr ? pct(cur.avg, pr.avg) : null;
      const thin = pts.length < 20;
      const last = pts.length ? pts[pts.length - 1][1] : null;
      h += `<tr class="pv-row ${st.open === code ? 'open' : ''}" data-code="${code}" data-name="${it.name}"><td class="nm"><b>${it.name}${thin ? '<span class="pv-tag">누적 중</span>' : ''}</b><small>${cfg.unitText(it)}</small></td>`
        + `<td class="now"><b>${last == null ? '–' : cfg.nowText(it, last)}</b><small class="${d > 0 ? 'pv-up' : 'pv-dn'}">${d == null ? '' : sg(d)}</small></td>`;
      cols.forEach((t, i) => {
        const x = a.get(t.getTime());
        if (!x) { h += `<td class="c"><div class="pv-cell na ${i === n - 1 ? 'cur' : ''}">–</div></td>`; return; }
        let pv = null; for (let k = i - 1; k >= 0 && pv == null; k--) { const y = a.get(cols[k].getTime()); if (y) pv = y.avg; }
        const p = pv ? pct(x.avg, pv) : null, y = yoyValue(it, t, a), yp = y ? pct(x.avg, y) : null;
        let big, sm, bg;
        if (st.m === 'p') { big = p != null ? sg(p) : f(x.avg); sm = p != null ? f(x.avg) : '기준'; bg = tint(p, mx); }
        else if (st.m === 'y') { big = yp != null ? sg(yp) : '–'; sm = f(x.avg); bg = tint(yp, mx * 3); }
        else { big = f(x.avg); sm = p != null ? sg(p) : ''; bg = tint(p, mx); }
        h += `<td class="c"><div class="pv-cell ${i === n - 1 ? 'cur' : ''}" style="background:${bg}">${big}<small>${sm}</small></div></td>`;
      });
      h += `</tr>`;
      if (st.open === code) h += `<tr class="pv-det" data-name="${it.name}"><td colspan="${n + 2}">${detail(it, a)}</td></tr>`;
    });
    box.innerHTML = h + `</tbody></table></div><div class="pv-hint">${cfg.hint}</div>`;
    box.querySelectorAll('tr.pv-row').forEach(r => r.onclick = () => { st.open = st.open === r.dataset.code ? null : r.dataset.code; draw(); });
    bindChart();
    applySearch();
  }

  let CH = null;
  function detail(it, aggMap) {
    const pts = [...aggMap.values()].sort((a, b) => a.t - b.t).slice(st.g === 'w' ? -26 : -12);
    if (pts.length < 2) return `<div class="pv-dp"><div class="pv-read">아직 ${st.g === 'w' ? '주' : '월'}간 차트를 그릴 만큼 이력이 쌓이지 않았습니다(현재 ${pts.length}개 기간).</div></div>`;
    const W = 720, H = 220, L = 52, R = 12, T = 12, B = 26;
    const lo = Math.min(...pts.map(x => x.min)), hi = Math.max(...pts.map(x => x.max));
    const pad = (hi - lo) * 0.12 || hi * 0.02 || 1, y0 = lo - pad, y1 = hi + pad;
    const X = i => L + (W - L - R) * i / (pts.length - 1), Y = v => T + (H - T - B) * (1 - (v - y0) / (y1 - y0));
    let g = '';
    for (let k = 0; k <= 4; k++) { const v = y0 + (y1 - y0) * k / 4, yy = Y(v); g += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" stroke="var(--gridline)"/><text x="${L - 6}" y="${yy + 4}" font-size="10" text-anchor="end" fill="var(--text-muted)">${f(v)}</text>`; }
    const step = Math.ceil(pts.length / 8);
    pts.forEach((x, i) => { if (i % step === 0 || i === pts.length - 1) g += `<text x="${X(i)}" y="${H - 8}" font-size="10" text-anchor="middle" fill="var(--text-muted)">${label(x.t)[0]}</text>`; });
    const band = pts.map((x, i) => `${X(i)},${Y(x.max)}`).join(' ') + ' ' + pts.slice().reverse().map((x, i) => `${X(pts.length - 1 - i)},${Y(x.min)}`).join(' ');
    const line = pts.map((x, i) => `${i ? 'L' : 'M'}${X(i)},${Y(x.avg)}`).join('');
    const cur = pts[pts.length - 1], prv = pts[pts.length - 2];
    const yv = yoyValue(it, cur.t, aggMap);
    const hiP = pts.reduce((m, x) => x.avg > m.avg ? x : m), loP = pts.reduce((m, x) => x.avg < m.avg ? x : m);
    const cl = v => v == null ? '' : v > 0 ? 'pv-up' : 'pv-dn';
    const sv = (l, v, c) => `<div><span>${l}</span><b class="${c || ''}">${v}</b></div>`;
    CH = { pts, X };
    return `<div class="pv-dp"><div><h4>${it.name} · ${st.g === 'w' ? '주간' : '월간'} 평균 <small style="color:var(--text-muted);font-weight:400">${cfg.unitText(it)}</small></h4>`
      + `<svg viewBox="0 0 ${W} ${H}" id="${P}Chart">${g}<polygon points="${band}" fill="var(--series-1)" opacity=".13"/><path d="${line}" fill="none" stroke="var(--series-1)" stroke-width="2.2" stroke-linejoin="round"/>`
      + pts.map((x, i) => `<circle cx="${X(i)}" cy="${Y(x.avg)}" r="${i === pts.length - 1 ? 4 : 2}" fill="var(--series-1)"/>`).join('')
      + `<line id="${P}Cur" x1="0" x2="0" y1="${T}" y2="${H - B}" stroke="var(--text-muted)" stroke-dasharray="3 3" opacity="0"/></svg>`
      + `<div class="pv-read" id="${P}Read">차트에 마우스를 올리면 기간별 평균·고저가 표시됩니다 · 음영 = 기간 내 최저~최고</div></div>`
      + `<div><h4>요약</h4><div class="pv-stat">${sv('현재 평균', f(cur.avg))}${sv(st.g === 'w' ? '전주 대비' : '전월 대비', sg(pct(cur.avg, prv.avg)), cl(pct(cur.avg, prv.avg)))}`
      + `${sv('전년 동기 대비', yv ? sg(pct(cur.avg, yv)) : '–', yv ? cl(pct(cur.avg, yv)) : '')}${sv('구간 변동폭', ((hiP.max - loP.min) / loP.min * 100).toFixed(1) + '%')}`
      + `${sv('구간 최고', f(hiP.avg))}${sv('구간 최저', f(loP.avg))}</div></div></div>`;
  }
  function bindChart() {
    const svg = $('Chart'); if (!svg || !CH) return;
    const { pts, X } = CH;
    svg.onmousemove = e => {
      const r = svg.getBoundingClientRect(), x = (e.clientX - r.left) / r.width * 720;
      let bi = 0, bd = 1e9; pts.forEach((_, i) => { const d = Math.abs(X(i) - x); if (d < bd) { bd = d; bi = i; } });
      const q = pts[bi], pr = pts[bi - 1], [l, s] = label(q.t), c = $('Cur');
      c.setAttribute('x1', X(bi)); c.setAttribute('x2', X(bi)); c.setAttribute('opacity', 1);
      $('Read').innerHTML = `<b>${l}</b> (${s}~) 평균 <b>${f(q.avg)}</b> · 고 ${f(q.max)} / 저 ${f(q.min)}`
        + (pr ? ` · 전기 <span class="${q.avg >= pr.avg ? 'pv-up' : 'pv-dn'}">${sg(pct(q.avg, pr.avg))}</span>` : '');
    };
  }
  function applySearch() {
    const q = (document.getElementById('itemSearch').value || '').trim().toLowerCase();
    box.querySelectorAll('tr.pv-row, tr.pv-det').forEach(tr => { tr.style.display = !q || (tr.dataset.name || '').toLowerCase().includes(q) ? '' : 'none'; });
  }
  document.getElementById('itemSearch').addEventListener('input', applySearch);
  $('G').querySelectorAll('button').forEach(b => b.onclick = () => { st.g = b.dataset.v; st.open = null; draw(); });
  $('M').querySelectorAll('button').forEach(b => b.onclick = () => { st.m = b.dataset.v; $('M').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); draw(); });
  draw();
}
function initPeriodView() {
  // 국산원물
  createPeriodView({
    prefix: 'pv', root: 'tabPanel-status', entries: dataEntries, useHistory: true, mx: [4, 8],
    nowHead: '현재가', unitText: it => `원/${it.unit}`, nowText: (it, v) => `${fmtPrice(it.latest_price != null ? it.latest_price : v)}원`,
    hint: "※ 조사된 값만 집계하며 빈 기간(–)은 보간하지 않습니다. '누적 중' 품목은 매일 자동 수집으로 이력이 쌓이면서 채워집니다. 행을 누르면 상세 차트가 펼쳐집니다.",
  });
  // 국제원료
  createPeriodView({
    prefix: 'pi', root: 'tabPanel-intl', entries: intlEntries, useHistory: false, mx: [5, 12], dec: 2,
    nowHead: '최근 종가', unitText: it => it.unit, nowText: (it, v) => `${v.toFixed(2)} ${it.unit}`,
    hint: '※ Yahoo Finance 주간 종가를 주·월로 평균한 값입니다(카드의 aT FIS 종가·등락률과는 소스가 달라 소폭 차이가 날 수 있음). 환율은 반영하지 않은 달러 기준입니다. 행을 누르면 상세 차트가 펼쳐집니다.',
  });
}
