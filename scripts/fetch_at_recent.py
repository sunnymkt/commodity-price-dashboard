#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한국농수산식품유통공사 '최근일자 도,소매가격정보' API(data.go.kr)로
고춧가루(소매)·건고추(중도매) 시세를 가져와 data/at_recent.json 에 저장한다.

이 API는 응답 한 줄에 최근 조사일 가격과 함께 1일 전 / 1주일 전 / 1개월 전 / 1년 전 가격이 들어 있어,
과거 이력을 쌓지 않아도 전년동기·전월 대비를 바로 계산할 수 있다.

인증키는 환경변수 DATA_GO_KR_KEY 에서 읽는다(GitHub Secrets 로 주입). 코드나 저장소에 키를 적지 말 것.
포털에서 받은 Encoding 키(%2B, %3D 등이 들어 있는 형태)와 Decoding 키 둘 다 사용할 수 있다.

품종·등급을 고정해서 호출한다(서로 다른 품종·등급이 섞여 비교되는 것을 막기 위함).
"""
import os
import sys
import json
import time
import datetime
import urllib.request
import urllib.parse
import urllib.error

API_URL = "https://apis.data.go.kr/B552845/recent/price"

# 대시보드 DATA 의 품목 코드 → 조회 조건
#   se_cd: 01 소매 / 02 중도매,  vrty_cd 00: 고춧가루 국산 / 건고추 화건,  grd_cd 04: 상품
TARGETS = {
    "248": {
        "name": "고춧가루(소매)",
        "basis": "소매(국산·상품, 전국 평균)",
        "se_cd": "01", "item_cd": "248", "vrty_cd": "00", "grd_cd": "04",
    },
    "248D": {
        "name": "건고추(화건) 도매",
        "basis": "중도매(화건·상품) — 고춧가루 원료 가격 지표",
        "se_cd": "02", "item_cd": "241", "vrty_cd": "00", "grd_cd": "04",
    },
    "313": {
        "name": "들깨",
        "basis": "중도매(국산·상품, 전국 평균)",
        "se_cd": "02", "item_cd": "313", "vrty_cd": "01", "grd_cd": "04",
    },
    "111": {
        "name": "쌀(국산)",
        "basis": "중도매(20kg·상품, 전국 평균)",
        "se_cd": "02", "item_cd": "111", "vrty_cd": "01", "grd_cd": "04",
    },
    "141": {
        "name": "콩(백태/대립종)",
        "basis": "중도매(흰콩 국산·상품, 전국 평균)",
        "se_cd": "02", "item_cd": "141", "vrty_cd": "01", "grd_cd": "04",
    },
    "151": {
        "name": "고구마",
        "basis": "중도매(밤고구마·상품, 전국 평균)",
        "se_cd": "02", "item_cd": "151", "vrty_cd": "00", "grd_cd": "04",
    },
    "312": {
        "name": "참깨",
        "basis": "중도매(백색 국산·상품, 전국 평균)",
        "se_cd": "02", "item_cd": "312", "vrty_cd": "01", "grd_cd": "04",
    },
    "226": {
        "name": "딸기(설향)",
        "basis": "중도매(설향·상품, 전국 평균) — 시즌(약 11~4월)에만 조사",
        "se_cd": "02", "item_cd": "226", "vrty_cd": "00", "grd_cd": "04",
    },
    # 배추는 품종(01 봄 / 02 여름(고랭지) / 03 가을 / 06 월동)이 계절마다 바뀌므로 품종을 고정하지 않고
    # 최근 조사 중인 품종 가운데 계절에 맞는 것을 pick_row() 가 고른다.
    "211": {
        "name": "배추",
        "basis": "중도매({vrty}·상품, 전국 평균)",
        "se_cd": "02", "item_cd": "211", "grd_cd": "04",
        "auto_variety": True,
    },
}

# 배추 품종 선택: 최근 ACTIVE_WINDOW_DAYS 일 안에 조사된 품종 중, 월별 우선순위에 맞는 첫 품종을 쓴다.
# 우선순위에 맞는 품종이 없으면 가장 최근에 조사된 품종을 쓴다.
ACTIVE_WINDOW_DAYS = 7
CABBAGE_SEASON_PREF = {
    1: ["06", "03"], 2: ["06", "03"], 3: ["06", "01"], 4: ["01", "06"],
    5: ["01", "06"], 6: ["01", "02"], 7: ["02", "01"], 8: ["02"],
    9: ["02", "03"], 10: ["03", "02"], 11: ["03", "06"], 12: ["06", "03"],
}

# 아직 연결하지 않은 품목의 (품종·등급·단위) 조합을 로그에만 출력한다(데이터에는 영향 없음).
# 로그를 보고 TARGETS 에 추가할 품종·등급을 정한다.  (품목코드, 이름, 구분: 01 소매 / 02 중도매)
DISCOVER = []


def encoded_key(raw):
    """이미 URL 인코딩된 키(%가 들어 있음)는 그대로, 아니면 인코딩해서 쓴다."""
    return raw if "%" in raw else urllib.parse.quote(raw, safe="")


def call_api(key, cfg):
    params = [
        ("returnType", "JSON"),
        ("pageNo", "1"),
        ("numOfRows", "20"),
        ("cond[se_cd::EQ]", cfg["se_cd"]),
        ("cond[item_cd::EQ]", cfg["item_cd"]),
    ]
    if cfg.get("vrty_cd"):
        params.append(("cond[vrty_cd::EQ]", cfg["vrty_cd"]))
    if cfg.get("grd_cd"):
        params.append(("cond[grd_cd::EQ]", cfg["grd_cd"]))
    query = "serviceKey=" + encoded_key(key) + "&" + "&".join(
        urllib.parse.quote(k, safe="") + "=" + urllib.parse.quote(v, safe="") for k, v in params
    )
    req = urllib.request.Request(API_URL + "?" + query, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(1, 5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError) as e:
            wait = 2 ** attempt
            print(f"  [WARN] 요청 실패({e!r}), {wait}초 후 재시도 ({attempt}/4)", file=sys.stderr)
            time.sleep(wait)
    return None


def to_float(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def extract_rows(payload):
    body = (payload or {}).get("response", {}).get("body", {})
    header = (payload or {}).get("response", {}).get("header", {})
    if str(header.get("resultCode")) not in ("0", "00", "000"):
        print(f"  -> API 오류: {header}", file=sys.stderr)
        return []
    items = body.get("items")
    if not items:
        return []
    rows = items.get("item") if isinstance(items, dict) else items
    if isinstance(rows, dict):
        rows = [rows]
    return rows or []


def pick_row(cfg, rows):
    """응답 행 중 사용할 한 줄을 고른다. 품종 고정 품목은 가장 최근 조사일 행, 배추는 계절에 맞는 품종 행."""
    latest = lambda r: r.get("exmn_ymd", "")
    if not cfg.get("auto_variety"):
        return max(rows, key=latest)
    newest = max(latest(r) for r in rows)
    cutoff = (datetime.datetime.strptime(newest, "%Y%m%d") - datetime.timedelta(days=ACTIVE_WINDOW_DAYS)).strftime("%Y%m%d")
    active = [r for r in rows if latest(r) >= cutoff]
    for code in CABBAGE_SEASON_PREF.get(int(newest[4:6]), []):
        hit = [r for r in active if r.get("vrty_cd") == code]
        if hit:
            return max(hit, key=latest)
    return max(active, key=latest)


def discover(key):
    """연결 전 품목의 조회 가능한 조합을 로그로 남긴다. 실패해도 본 작업에는 영향이 없도록 예외를 삼킨다."""
    if not DISCOVER:
        return
    print("--- [탐색] 아직 연결하지 않은 품목의 조회 가능 조합 ---")
    for item_cd, name, se_cd in DISCOVER:
        try:
            rows = extract_rows(call_api(key, {"se_cd": se_cd, "item_cd": item_cd}))
        except Exception as e:  # noqa: BLE001
            print(f"[탐색] {name}({item_cd}) 조회 실패: {e!r}")
            continue
        if not rows:
            print(f"[탐색] {name}({item_cd}, 구분 {se_cd}): 데이터 없음")
            continue
        for r in rows:
            print(f"[탐색] {name}({item_cd}) {r.get('se_nm')} / 품종 {r.get('vrty_cd')} {r.get('vrty_nm')} / "
                  f"등급 {r.get('grd_cd')} {r.get('grd_nm')} / 단위 {r.get('unit_sz')}{r.get('unit')} / "
                  f"조사일 {r.get('exmn_ymd')} / 현재 {r.get('exmn_dd_prc')} / 1개월전 {r.get('mm1_bfr_prc')} / 1년전 {r.get('yy1_bfr_prc')}")
        time.sleep(0.5)


def main():
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        print("DATA_GO_KR_KEY 미설정 — 최근일자 도·소매가격 수집을 건너뜁니다.")
        return

    result = {}
    for code, cfg in TARGETS.items():
        print(f"[{code}] {cfg['name']} 조회 중...")
        payload = call_api(key, cfg)
        rows = extract_rows(payload)
        if not rows:
            print("  -> 데이터 없음, 건너뜀")
            continue
        row = pick_row(cfg, rows)
        rec = {
            "name": cfg["name"],
            "basis": cfg["basis"].replace("{vrty}", str(row.get("vrty_nm") or "")),
            "vrty_cd": row.get("vrty_cd"),
            "vrty_nm": row.get("vrty_nm"),
            "exmn_ymd": row.get("exmn_ymd"),
            "unit": row.get("unit"),
            "unit_sz": row.get("unit_sz"),
            "prc": to_float(row.get("exmn_dd_prc")),
            "dd1": to_float(row.get("dd1_bfr_prc")),
            "ww1": to_float(row.get("ww1_bfr_prc")),
            "mm1": to_float(row.get("mm1_bfr_prc")),
            "yy1": to_float(row.get("yy1_bfr_prc")),
            "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        if rec["prc"] is None or not rec["exmn_ymd"]:
            print("  -> 가격 파싱 실패, 건너뜀")
            continue
        result[code] = rec
        print(f"  -> {rec['exmn_ymd']} {rec['prc']:,.0f} [{rec['vrty_nm']}] (1년 전 {rec['yy1']}, 1개월 전 {rec['mm1']})")

    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "at_recent.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    # 일부만 성공해도 성공한 항목은 기존 파일 내용에 덮어써서 보존한다.
    old = {}
    if os.path.exists(out_path):
        try:
            with open(out_path, encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            old = {}
    old.update(result)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(old, f, ensure_ascii=False, indent=2)
    print(f"저장 완료: {out_path} ({len(result)}개 갱신)")
    try:
        discover(key)
    except Exception as e:  # noqa: BLE001
        print(f"[탐색] 건너뜀: {e!r}")


if __name__ == "__main__":
    main()
