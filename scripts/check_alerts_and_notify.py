#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
index.html의 DATA/INTL_DATA에서 급등/급락(alert) 상태를 읽어,
'새로 급등/급락이 시작된' 품목이 있으면 그 품목을 관심 품목으로 등록한
구독자에게 이메일로 알려준다.

구독자 목록은 Google Apps Script 웹 앱(SUBSCRIBE_SHEET_API_URL)에서 GET으로 가져온다.

이메일 발송은 SendGrid API(HTTP)를 사용한다. 처음엔 food-trend-analyzer와 동일하게
회사 그룹웨어 SMTP로 직접 발송했지만, GitHub Actions 공용 러너가 쓰는 IP가 거의 매번
스팸 차단 목록(Spamhaus 등)에 걸려 있어서 메일 서버가 연결 자체를 계속 거부했다
(예: "Your ip is filtered by RBL ..." — 여러 날, 여러 IP에서 반복 확인됨, 가끔이 아니라
사실상 상시 발생하는 문제였다). SendGrid는 자체 평판 좋은 발신 인프라로 API를 통해
보내므로 이 문제에서 자유롭다.

반복 발송을 막기 위해 data/alert_state.json 에 "마지막으로 통보한 alert 상태"를
품목별로 저장해두고, 그 값과 달라졌을 때만(= 급등/급락이 새로 시작되거나 종류가
바뀌었을 때만) 이메일을 보낸다.
"""
import os
import re
import sys
import json
import urllib.request
import urllib.parse
import urllib.error

ROOT = os.path.join(os.path.dirname(__file__), "..")
INDEX_PATH = os.path.join(ROOT, "index.html")
STATE_PATH = os.path.join(ROOT, "data", "alert_state.json")

DASHBOARD_URL = "https://sunnymkt.github.io/commodity-price-dashboard/"


def load_dashboard_items():
    """index.html에서 DATA(국내)와 INTL_DATA(국제)를 읽어
    {code: {name, latest_price, unit, week_chg_pct, month_chg_pct, yoy_chg_pct, alert, points}} 형태로 합쳐 반환."""
    txt = open(INDEX_PATH, encoding="utf-8").read()
    items = {}

    m = re.search(r"const DATA = (\{.*?\});\s*\n", txt, re.S)
    data = json.loads(m.group(1))
    for code, it in data.items():
        items[code] = {
            "name": it.get("name"),
            "latest_price": it.get("latest_price"),
            "unit": "원/kg" if (it.get("unit") or "").startswith("kg") else ("원/" + (it.get("unit") or "")),
            "week_chg_pct": it.get("week_chg_pct"),
            "month_chg_pct": it.get("month_chg_pct"),
            "yoy_chg_pct": it.get("yoy_chg_pct"),
            "alert": it.get("alert"),
            "points": it.get("points") or [],
        }

    # INTL_DATA는 JSON이 아닌 JS 객체 리터럴이라 코드별 블록을 텍스트로 찾는다.
    intl_codes = ["sugar", "wheat", "soyoil", "corn"]
    for code in intl_codes:
        mm = re.search(
            rf"{code}:\s*\{{\s*name:\s*'([^']*)'.*?price:\s*([\-\d.]+),\s*asof:\s*'(\d+)',\s*"
            rf"day_chg_pct:\s*([\-\d.]+),\s*week_chg_pct:\s*([\-\d.]+),\s*month_chg_pct:\s*([\-\d.]+),\s*ytd_chg_pct:\s*([\-\d.]+),",
            txt, re.S,
        )
        if not mm:
            continue
        name, price, asof, day_c, week_c, month_c, ytd_c = mm.groups()
        yoy_mm = re.search(rf"{code}:\s*\{{.*?yoy_chg_pct:\s*([\-\d.]+)\s*\}}", txt, re.S)
        yoy_c = float(yoy_mm.group(1)) if yoy_mm else None
        alert = None
        if yoy_c is not None:
            if yoy_c >= 20:
                alert = "급등"
            elif yoy_c <= -20:
                alert = "급락"
        # 주의: 여기서 쓰는 code('sugar'/'wheat'/'soyoil'/'corn')는 대시보드 프론트엔드의
        # INTL_ORDER 코드와 반드시 동일해야 한다. 접두어(intl_ 등)를 붙이면 구독자가
        # 관심 품목으로 등록한 코드(예: 'wheat')와 매칭되지 않아 알림이 영영 발송되지 않는다.
        items[code] = {
            "name": name,
            "latest_price": float(price),
            "unit": "원/kg (환율 환산)",
            "week_chg_pct": float(week_c),
            "month_chg_pct": float(month_c),
            "yoy_chg_pct": yoy_c,
            "alert": alert,
            "points": [],
        }
    return items


def fetch_subscribers(api_url):
    req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fmt_price(v):
    if v is None:
        return "-"
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def fmt_pct(v):
    if v is None:
        return "-"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.1f}%"


def quickchart_url(name, points):
    """최근 포인트를 QuickChart.io 라인차트 이미지 URL로 변환 (이메일 본문 임베드용)."""
    if not points:
        return None
    pts = points[-30:]  # 최근 구간만
    labels = [p[0][4:6] + "/" + p[0][6:8] for p in pts]
    values = [p[1] for p in pts]
    chart_config = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [{
                "label": name,
                "data": values,
                "borderColor": "#2a78d6",
                "backgroundColor": "rgba(42,120,214,0.12)",
                "fill": True,
                "pointRadius": 0,
                "borderWidth": 2,
            }],
        },
        "options": {
            "plugins": {"legend": {"display": False}, "title": {"display": True, "text": name}},
            "scales": {"x": {"ticks": {"maxTicksLimit": 8}}},
        },
    }
    qs = urllib.parse.quote(json.dumps(chart_config))
    return f"https://quickchart.io/chart?w=480&h=240&c={qs}"


def build_email_html(email, alerting_items):
    rows = []
    for code, it, prev_alert in alerting_items:
        chart_img = quickchart_url(it["name"], it["points"])
        chart_html = f'<p><img src="{chart_img}" alt="{it["name"]} 추이 그래프" style="max-width:480px;width:100%;border-radius:8px;border:1px solid #e1e0d9;" /></p>' if chart_img else ""
        badge_color = "#d03b3b" if it["alert"] == "급락" else "#c2660a"
        rows.append(f"""
        <div style="margin-bottom:28px;padding:16px;border:1px solid #e1e0d9;border-radius:12px;">
          <h3 style="margin:0 0 6px;font-size:16px;">
            {it['name']}
            <span style="font-size:12px;font-weight:700;color:#fff;background:{badge_color};padding:3px 8px;border-radius:999px;margin-left:6px;">{it['alert']}</span>
          </h3>
          <p style="margin:0 0 8px;color:#52514e;font-size:13px;">
            현재가 <b>{fmt_price(it['latest_price'])}{it['unit']}</b>
            · 전주 {fmt_pct(it['week_chg_pct'])}
            · 전월 {fmt_pct(it['month_chg_pct'])}
            · 전년동기 <b>{fmt_pct(it['yoy_chg_pct'])}</b>
          </p>
          {chart_html}
        </div>""")
    body = "".join(rows)
    return f"""
    <div style="font-family:'Malgun Gothic',sans-serif;max-width:560px;margin:0 auto;">
      <h2 style="color:#1a2340;">🔔 관심 원물 시세 변화 알림</h2>
      <p style="color:#52514e;font-size:13px;">회원님이 등록하신 관심 품목 중 아래 품목의 전년동기 대비 가격이 급등/급락 기준(±20%)을 새로 넘었습니다.</p>
      {body}
      <p style="margin-top:24px;font-size:12px;color:#898781;">
        전체 대시보드는 <a href="{DASHBOARD_URL}">여기서</a> 확인하실 수 있습니다.<br/>
        더 이상 알림을 받고 싶지 않으시면 대시보드의 '관심원물 시세 추이 알림받기' 버튼에서 구독 해지를 눌러주세요.
      </p>
    </div>"""


def send_email(subject, html_body, recipient, api_key, from_email, from_name):
    """SendGrid Mail Send API(v3)로 이메일을 발송한다. HTTP 기반이라
    GitHub Actions 러너의 발신 IP 평판과 무관하게 안정적으로 전달된다."""
    payload = {
        "personalizations": [{"to": [{"email": recipient}]}],
        "from": {"email": from_email, "name": from_name} if from_name else {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_body}],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"SendGrid API 오류 {e.code}: {body}") from e


def main():
    sheet_api_url = os.environ.get("SUBSCRIBE_SHEET_API_URL", "").strip()
    if not sheet_api_url:
        print("SUBSCRIBE_SHEET_API_URL 미설정 — 알림 발송 단계를 건너뜁니다.")
        return

    sendgrid_api_key = os.environ.get("SENDGRID_API_KEY", "").strip()
    sendgrid_from = os.environ.get("SENDGRID_FROM", "").strip()
    sendgrid_from_name = os.environ.get("SENDGRID_FROM_NAME", "NH FOOD 원물시세").strip()
    if not sendgrid_api_key or not sendgrid_from:
        print("SENDGRID_API_KEY / SENDGRID_FROM 미설정 — 알림 발송 단계를 건너뜁니다.")
        return

    items = load_dashboard_items()
    state = load_state()

    # 상태 변화(알림 새로 시작/종류 변경) 감지
    changed_codes = []
    new_state = {}
    for code, it in items.items():
        new_state[code] = it["alert"]
        prev = state.get(code)
        if it["alert"] and it["alert"] != prev:
            changed_codes.append(code)

    if not changed_codes:
        print("급등/급락 상태 변화 없음 — 발송할 알림 없음.")
        save_state(new_state)
        return

    print(f"상태 변화 감지: {changed_codes}")

    try:
        subscribers = fetch_subscribers(sheet_api_url)
    except Exception as e:
        print(f"구독자 목록 조회 실패: {e}", file=sys.stderr)
        save_state(new_state)
        return

    sent_count = 0
    # 품목별 발송 성공 여부를 추적해, 발송에 실패한 품목은 상태를 갱신하지 않고
    # 다음 실행에서 다시 "새로운 변화"로 인식되어 재시도되도록 한다(SMTP 설정 오류 등으로
    # 메일이 실제로 나가지 않았는데도 '이미 통보함'으로 기록되어 영영 재시도가 안 되는 것을 방지).
    send_ok = {}
    for sub in subscribers:
        email = sub.get("email")
        watched = set(sub.get("items") or [])
        matched = [c for c in changed_codes if c in watched]
        if not email or not matched:
            continue
        alerting_items = [(c, items[c], state.get(c)) for c in matched]
        html_body = build_email_html(email, alerting_items)
        names = ", ".join(items[c]["name"] for c in matched)
        subject = f"[NH FOOD 원물시세] {names} 급등/급락 알림"
        try:
            send_email(subject, html_body, email, sendgrid_api_key, sendgrid_from, sendgrid_from_name)
            sent_count += 1
            print(f"  -> {email} 발송 완료 ({names})")
            for c in matched:
                send_ok.setdefault(c, True)
        except Exception as e:
            print(f"  -> {email} 발송 실패: {e}", file=sys.stderr)
            for c in matched:
                send_ok[c] = False

    print(f"총 {sent_count}건 발송")

    for c in changed_codes:
        if send_ok.get(c) is False:
            new_state[c] = state.get(c)  # 실패한 품목은 이전 상태 유지 → 다음 실행에서 재시도
    save_state(new_state)


if __name__ == "__main__":
    main()
