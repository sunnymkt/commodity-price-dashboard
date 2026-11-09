#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국산원물 과거 일별 시세를 한 번에 채워 data/history.json 에 저장한다(1회성 백필).

대상: fetch_at_recent.TARGETS 의 품목(쌀·콩·고구마·배추·참깨·들깨·고춧가루·건고추·딸기).
소스: 공공데이터포털 '한국농수산식품유통공사 기간별 도·소매 가격' 계열 API(B552845).
  - 소매(se_cd 01): periodRetail
  - 중도매(se_cd 02): ENDPOINTS 에 적은 후보를 순서대로 시도해 자료가 나오는 첫 엔드포인트를 쓴다.
키는 환경변수 DATA_GO_KR_KEY (fetch_at_recent.py 와 동일).

사용법
  1) python scripts/backfill_history.py --probe     # 응답 필드·조합만 확인(파일 저장 안 함)
  2) python scripts/backfill_history.py             # 백필 실행(검증 통과한 품목만 저장)
  3) python scripts/update_dashboard.py             # index.html 의 HISTORY 에 반영
옵션: --days 400 (기본)  --only 313,111  --force (기준 불일치 경고 무시)

안전장치: 백필 값의 최근 겹치는 날짜 가격이 at_recent.json 의 현재가와 5% 넘게 다르면(= 소스·단위 기준이 다름)
그 품목은 저장하지 않는다. 대시보드의 현재가와 이어지지 않는 이력이 섞이는 것을 막기 위함.
"""
import os, sys, json, time, argparse, datetime, urllib.request, urllib.parse, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_at_recent import TARGETS, CABBAGE_SEASON_PREF, encoded_key, to_float, extract_rows  # noqa: E402

BASE = "https://apis.data.go.kr/B552845/"
ENDPOINTS = {"01": ["periodRetail"], "02": ["periodWholesale", "periodMiddle", "perRegion"]}
PRICE_KEYS = ("exmn_dd_avg_prc", "exmn_dd_prc", "avg_prc", "prc")      # kg 환산이 아닌 '조사 단위' 가격 우선
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "data", "history.json")
AT = os.path.join(ROOT, "data", "at_recent.json")
WINDOW = 90


def call(endpoint, key, cfg, start, end, page):
    params = [("returnType", "JSON"), ("pageNo", str(page)), ("numOfRows", "1000"),
              ("cond[se_cd::EQ]", cfg["se_cd"]), ("cond[item_cd::EQ]", cfg["item_cd"]),
              ("cond[exmn_ymd::GTE]", start), ("cond[exmn_ymd::LTE]", end)]
    if cfg.get("vrty_cd"):
        params.append(("cond[vrty_cd::EQ]", cfg["vrty_cd"]))
    if cfg.get("grd_cd"):
        params.append(("cond[grd_cd::EQ]", cfg["grd_cd"]))
    q = "serviceKey=" + encoded_key(key) + "&" + "&".join(
        urllib.parse.quote(k, safe="") + "=" + urllib.parse.quote(v, safe="") for k, v in params)
    req = urllib.request.Request(BASE + endpoint + "?" + q, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(1, 5):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return {"_http": e.code}
            time.sleep(2 ** attempt)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError):
            time.sleep(2 ** attempt)
    return None


def fetch_range(endpoint, key, cfg, start, end):
    rows, page = [], 1
    while True:
        p = call(endpoint, key, cfg, start, end, page)
        if not p or "_http" in p:
            return rows if page > 1 else None
        got = extract_rows(p)
        rows += got
        total = to_float(((p.get("response") or {}).get("body") or {}).get("totalCount")) or 0
        if not got or len(rows) >= total:
            return rows
        page += 1
        time.sleep(0.3)


def pick_price(r):
    for k in PRICE_KEYS:
        v = to_float(r.get(k))
        if v is not None:
            return v
    return None


def daily(cfg, rows):
    """응답 행 → {yyyymmdd: 가격}. 같은 날 여러 행(지역·시장·품종)은 평균, 배추는 계절에 맞는 품종만."""
    by = {}
    for r in rows:
        d = str(r.get("exmn_ymd") or "").replace("-", "")
        if len(d) == 8:
            by.setdefault(d, []).append(r)
    out = {}
    for d, lst in by.items():
        if cfg.get("auto_variety"):
            pick = []
            for code in CABBAGE_SEASON_PREF.get(int(d[4:6]), []):
                pick = [r for r in lst if r.get("vrty_cd") == code]
                if pick:
                    break
            lst = pick or lst
        nat = [r for r in lst if str(r.get("sigungu_nm") or r.get("signgu_nm") or "").strip() in ("전국", "평균", "전국평균")]
        use = nat or lst
        vals = [v for v in (pick_price(r) for r in use) if v is not None]
        if vals:
            out[d] = round(sum(vals) / len(vals), 1)
    return out


def probe(key, only):
    today = datetime.date.today()
    s, e = (today - datetime.timedelta(days=10)).strftime("%Y%m%d"), today.strftime("%Y%m%d")
    for code, cfg in TARGETS.items():
        if only and code not in only:
            continue
        for ep in ENDPOINTS[cfg["se_cd"]]:
            p = call(ep, key, cfg, s, e, 1)
            rows = extract_rows(p) if p and "_http" not in p else []
            print(f"[{code}] {cfg['name']} / {ep}: " + (f"{len(rows)}행" if rows else f"자료 없음 (응답 {json.dumps(p, ensure_ascii=False)[:200] if p else '실패'})"))
            if rows:
                print("   필드:", sorted(rows[0].keys()))
                for r in rows[:2]:
                    print("   예시:", json.dumps(r, ensure_ascii=False))
                combos = {}
                for r in rows:
                    k = (r.get("vrty_nm"), r.get("grd_nm"), r.get("sigungu_nm") or r.get("signgu_nm"), r.get("mrkt_nm"), f"{r.get('unit_sz')}{r.get('unit')}")
                    combos[k] = combos.get(k, 0) + 1
                for k, n in list(combos.items())[:8]:
                    print(f"   조합 {n}행: 품종={k[0]} 등급={k[1]} 지역={k[2]} 시장={k[3]} 단위={k[4]}")
                break
        time.sleep(0.5)


def raw_get(path, key, params):
    """진단용: 상태코드와 응답 본문 앞부분을 그대로 돌려준다."""
    q = "serviceKey=" + encoded_key(key) + "&" + "&".join(
        urllib.parse.quote(k, safe="") + "=" + urllib.parse.quote(v, safe="") for k, v in params)
    req = urllib.request.Request(BASE + path + "?" + q, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        return 0, repr(e)


def diagnose(key):
    """엔드포인트 경로·파라미터 중 어디서 400 이 나는지 단계별로 확인한다(키는 출력하지 않음)."""
    today = datetime.date.today()
    s, e = (today - datetime.timedelta(days=10)).strftime("%Y%m%d"), today.strftime("%Y%m%d")
    base = [("returnType", "JSON"), ("pageNo", "1"), ("numOfRows", "3")]
    eq = [("cond[se_cd::EQ]", "01"), ("cond[item_cd::EQ]", "248")]
    rng = [("cond[exmn_ymd::GTE]", s), ("cond[exmn_ymd::LTE]", e)]
    paths = ["recent/price", "periodRetail/price", "periodRetail", "periodRetail/retail", "perRegion/price", "perRegion",
             "periodWholesale/price", "periodWholesale", "periodMiddle/price", "periodMiddle"]
    for path in paths:
        for label, prm in (("조건없음", base), ("품목조건", base + eq), ("품목+기간", base + eq + rng)):
            code, body = raw_get(path, key, prm)
            body = " ".join(body.split())[:230]
            print(f"[{path}] {label}: HTTP {code} :: {body}")
        print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diagnose", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--days", type=int, default=400)
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        sys.exit("DATA_GO_KR_KEY 환경변수가 필요합니다.")
    only = {c for c in a.only.split(",") if c}
    if a.diagnose:
        return diagnose(key)
    if a.probe:
        return probe(key, only)

    at = json.load(open(AT, encoding="utf-8")) if os.path.exists(AT) else {}
    hist = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    today = datetime.date.today()
    for code, cfg in TARGETS.items():
        if only and code not in only:
            continue
        print(f"[{code}] {cfg['name']} 백필 중...")
        series, used = {}, None
        for ep in ENDPOINTS[cfg["se_cd"]]:
            ok = True
            tmp = {}
            end = today
            while end > today - datetime.timedelta(days=a.days):
                start = max(end - datetime.timedelta(days=WINDOW), today - datetime.timedelta(days=a.days))
                rows = fetch_range(ep, key, cfg, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
                if rows is None:
                    ok = False
                    break
                tmp.update(daily(cfg, rows))
                end = start - datetime.timedelta(days=1)
                time.sleep(0.4)
            if ok and tmp:
                series, used = tmp, ep
                break
        if not series:
            print("  -> 자료 없음/엔드포인트 확인 필요 (--probe 로 확인)")
            continue
        dates = sorted(series)
        print(f"  -> {used}: {len(series)}일 ({dates[0]}~{dates[-1]})")
        ref = at.get(code)
        if ref and ref.get("prc") and ref.get("exmn_ymd") in series:
            diff = abs(series[ref["exmn_ymd"]] - ref["prc"]) / ref["prc"] * 100
            print(f"  -> 현재가 대조 {ref['exmn_ymd']}: 백필 {series[ref['exmn_ymd']]:,.0f} vs 현재 {ref['prc']:,.0f} (차이 {diff:.1f}%)")
            if diff > 5 and not a.force:
                print("  -> [건너뜀] 기준이 달라 보임. 저장하지 않음(--force 로 강행 가능)")
                continue
        elif ref:
            print("  -> [참고] 최근 조사일과 겹치는 날짜가 없어 현재가 대조를 못 했습니다.")
        merged = {p[0]: p[1] for p in hist.get(code, [])}
        merged.update(series)
        hist[code] = [[d, merged[d]] for d in sorted(merged)]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(hist, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print("저장 완료:", OUT)


if __name__ == "__main__":
    main()
