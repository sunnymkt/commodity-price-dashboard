#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KAMIS Open-API(periodProductList)로 국산원물 과거 일별 시세를 한 번에 채워 data/history.json 에 합친다.
(data.go.kr 기간별 API 가 아직 신청/승인 전일 때 쓰는 대체 경로.)

KAMIS 응답에는 품종·등급·지역·시장별 행이 섞여 있으므로, 대시보드가 실제로 쓰는 최근 가격(data/at_recent.json 의 prc)과
가장 가깝게 이어지는 (품종·등급·지역·시장) 조합 하나를 자동으로 골라 그 시계열만 저장한다.
최근 가격과 5% 넘게 어긋나면 그 품목은 저장하지 않는다(다른 기준의 값이 섞이는 것을 방지).

인증키: 환경변수 KAMIS_CERT_KEY, KAMIS_CERT_ID  (kamis.or.kr 로그인 > Open-API 신청 후 발급)
사용법
  python scripts/backfill_kamis.py --probe     # 품목별 응답 조합만 확인(저장 안 함)
  python scripts/backfill_kamis.py             # 백필 실행
  python scripts/update_dashboard.py           # index.html 의 HISTORY 에 반영
옵션: --days 400  --only 313,111  --force
"""
import os, sys, json, time, argparse, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_kamis import fetch_period_product, extract_items  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "data", "history.json")
AT = os.path.join(ROOT, "data", "at_recent.json")

# 대시보드 코드 -> KAMIS 조회 조건 (productclscode 01 소매 / 02 도매(중도매인 판매가격))
CONFIG = {
    "111":  {"name": "쌀(국산)",        "itemcategorycode": "100", "itemcode": "111", "productclscode": "02"},
    "141":  {"name": "콩",              "itemcategorycode": "100", "itemcode": "141", "productclscode": "02"},
    "151":  {"name": "고구마",          "itemcategorycode": "100", "itemcode": "151", "productclscode": "02"},
    "312":  {"name": "참깨",            "itemcategorycode": "300", "itemcode": "312", "productclscode": "02"},
    "313":  {"name": "들깨",            "itemcategorycode": "300", "itemcode": "313", "productclscode": "02"},
    "248":  {"name": "고춧가루(소매)",  "itemcategorycode": "200", "itemcode": "248", "productclscode": "01"},
    "248D": {"name": "건고추 도매",     "itemcategorycode": "200", "itemcode": "241", "productclscode": "02"},
    "211":  {"name": "배추",            "itemcategorycode": "200", "itemcode": "211", "productclscode": "02"},
    "226":  {"name": "딸기",            "itemcategorycode": "200", "itemcode": "226", "productclscode": "02"},
}


def rows_for(cfg, start, end, key, cid):
    c = dict(cfg)
    c.update({"kindcode": "", "productrankcode": "", "countrycode": ""})
    data = fetch_period_product(key, cid, c, start, end)
    if not data:
        return None
    return extract_items(data) or []


def num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None


def group_series(rows, year_hint):
    """행 → {조합키: {yyyymmdd: 가격}}. 평년(과거 5년 평균) 행은 제외."""
    out = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        county = str(r.get("countyname") or "").strip()
        if county == "평년":
            continue
        p = num(r.get("price"))
        d = str(r.get("regday") or "").replace("-", "").replace("/", "")
        if p is None or not d:
            continue
        if len(d) <= 5:
            d = f"{r.get('yyyy') or year_hint}{d}"
        k = (str(r.get("kindname") or ""), str(r.get("productrankname") or ""), county, str(r.get("marketname") or ""))
        out.setdefault(k, {})[d] = p
    return out


def nearest(series, ymd, max_days=4):
    t = datetime.datetime.strptime(ymd, "%Y%m%d")
    best = None
    for d, v in series.items():
        gap = abs((datetime.datetime.strptime(d, "%Y%m%d") - t).days)
        if gap <= max_days and (best is None or gap < best[0]):
            best = (gap, d, v)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    key, cid = os.environ.get("KAMIS_CERT_KEY", "").strip(), os.environ.get("KAMIS_CERT_ID", "").strip()
    if not key or not cid:
        sys.exit("KAMIS_CERT_KEY / KAMIS_CERT_ID 환경변수가 필요합니다.")
    only = {c for c in a.only.split(",") if c}
    today = datetime.date.today()
    at = json.load(open(AT, encoding="utf-8")) if os.path.exists(AT) else {}
    hist = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}

    for code, cfg in CONFIG.items():
        if only and code not in only:
            continue
        days = 15 if a.probe else a.days
        start = (today - datetime.timedelta(days=days)).isoformat()
        print(f"[{code}] {cfg['name']} 조회 중({start}~)...")
        rows = rows_for(cfg, start, today.isoformat(), key, cid)
        if not rows:
            print("  -> 자료 없음/조회 실패")
            continue
        groups = group_series(rows, today.year)
        ref = at.get(code) or {}
        prc, ymd = ref.get("prc"), ref.get("exmn_ymd")
        scored = []
        for k, s in groups.items():
            hit = nearest(s, ymd) if ymd else None
            diff = abs(hit[2] - prc) / prc * 100 if (hit and prc) else None
            scored.append((diff if diff is not None else 1e9, k, s, hit))
        scored.sort(key=lambda x: x[0])
        if a.probe:
            print(f"  응답 {len(rows)}행, 조합 {len(groups)}개 (현재 대시보드 가격 {prc} @ {ymd})")
            for diff, k, s, hit in scored[:6]:
                last = max(s) if s else ''
                print(f"   품종={k[0]} 등급={k[1]} 지역={k[2]} 시장={k[3]} | 최근 {last} {s.get(last)} | 대시보드 대비 {'-' if diff > 1e8 else f'{diff:.1f}%'}")
            time.sleep(1)
            continue
        diff, k, s, hit = scored[0]
        if diff is None or diff > 1e8 or (diff > 5 and not a.force):
            print(f"  -> [건너뜀] 대시보드 현재가와 이어지는 조합을 찾지 못함 (가장 가까운 차이 {'없음' if diff > 1e8 else f'{diff:.1f}%'})")
            continue
        dates = sorted(s)
        print(f"  -> 선택: 품종={k[0]} 등급={k[1]} 지역={k[2]} 시장={k[3]} | {len(s)}일 ({dates[0]}~{dates[-1]}) | 현재가 차이 {diff:.1f}%")
        merged = {p[0]: p[1] for p in hist.get(code, [])}
        for d, v in s.items():
            merged.setdefault(d, v)          # 이미 있는 값(실수집·다른 소스)은 덮어쓰지 않음
        hist[code] = [[d, merged[d]] for d in sorted(merged)]
        time.sleep(1.5)
    if not a.probe:
        json.dump(hist, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
        print("저장 완료:", OUT)


if __name__ == "__main__":
    main()
