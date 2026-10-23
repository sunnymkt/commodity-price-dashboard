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
}


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
        ("cond[vrty_cd::EQ]", cfg["vrty_cd"]),
        ("cond[grd_cd::EQ]", cfg["grd_cd"]),
    ]
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
        row = max(rows, key=lambda r: r.get("exmn_ymd", ""))   # 가장 최근 조사일 행
        rec = {
            "name": cfg["name"],
            "basis": cfg["basis"],
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
        print(f"  -> {rec['exmn_ymd']} {rec['prc']:,.0f} (1년 전 {rec['yy1']}, 1개월 전 {rec['mm1']})")

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


if __name__ == "__main__":
    main()
