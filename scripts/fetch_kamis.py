#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KAMIS Open-API(periodProductList)로 국내 원물 시세를 가져와 JSON으로 저장한다.

인증키는 환경변수(KAMIS_CERT_KEY, KAMIS_CERT_ID)에서 읽는다.
GitHub Actions에서는 repository secrets로 주입한다.

주의: KAMIS periodProductList는 "중도매인 판매가격/도매가격" 계열 데이터다.
배추/딸기(가락시장 경락가격), 계란(ekapepia.com), 밤(forestinfo.or.kr),
고춧가루-도매(data.go.kr 건고추 경락가)는 이 API로 커버되지 않아 여기서는 제외했다.
이 4개 품목은 fetch_manual_sources.py(또는 기존 브라우저 조사 방식)로 별도 갱신하거나,
당분간 수동 갱신을 유지해야 한다.
"""
import os
import sys
import json
import datetime
import urllib.request
import urllib.parse

KAMIS_BASE = "http://www.kamis.or.kr/service/price/xml.do"

# code -> (itemcategorycode, itemcode, kindcode, productrankcode, productclscode, countrycode)
# productclscode: 01=소매, 02=도매
ITEM_CONFIG = {
    "111": {"name": "쌀(국산)",        "itemcategorycode": "100", "itemcode": "111", "kindcode": "01", "productrankcode": "04", "productclscode": "02", "countrycode": "1101"},
    "141": {"name": "콩(백태/대립종)",  "itemcategorycode": "100", "itemcode": "141", "kindcode": "01", "productrankcode": "04", "productclscode": "02", "countrycode": "1101"},
    "151": {"name": "고구마",          "itemcategorycode": "100", "itemcode": "151", "kindcode": "00", "productrankcode": "04", "productclscode": "02", "countrycode": "1101"},
    "312": {"name": "참깨",            "itemcategorycode": "300", "itemcode": "312", "kindcode": "01", "productrankcode": "04", "productclscode": "02", "countrycode": "1101"},
    "313": {"name": "들깨",            "itemcategorycode": "300", "itemcode": "313", "kindcode": "01", "productrankcode": "04", "productclscode": "02", "countrycode": "1101"},
    "248": {"name": "고춧가루(소매)",   "itemcategorycode": "200", "itemcode": "248", "kindcode": "00", "productrankcode": "04", "productclscode": "01", "countrycode": "1101"},
    "651": {"name": "멸치액젓",        "itemcategorycode": "600", "itemcode": "651", "kindcode": "00", "productrankcode": "04", "productclscode": "01", "countrycode": "1101"},
    "652": {"name": "천일염",          "itemcategorycode": "600", "itemcode": "652", "kindcode": "00", "productrankcode": "04", "productclscode": "01", "countrycode": "1101"},
}

# 가락시장 경락가격(배추/딸기)은 별도 action(price/market/period.do)이며
# 공식 Open-API 명세에 없어 이 스크립트에서는 시도만 하고 실패시 건너뛴다.
# (marketcode=1: 가락시장)
AUCTION_CONFIG = {
    "211": {"name": "배추", "itemcode": "21100", "productrankcode": "1"},
    "226": {"name": "딸기(설향)", "itemcode": "22607", "productrankcode": "1"},
}


def fetch_period_product(cert_key, cert_id, cfg, startday, endday):
    params = {
        "action": "periodProductList",
        "p_cert_key": cert_key,
        "p_cert_id": cert_id,
        "p_returntype": "json",
        "p_startday": startday,
        "p_endday": endday,
        "p_productclscode": cfg["productclscode"],
        "p_itemcategorycode": cfg["itemcategorycode"],
        "p_itemcode": cfg["itemcode"],
        "p_kindcode": cfg["kindcode"],
        "p_productrankcode": cfg["productrankcode"],
        "p_countrycode": cfg["countrycode"],
        "p_convert_kg_yn": "Y",
    }
    url = KAMIS_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  [WARN] JSON 파싱 실패 (raw 앞부분): {raw[:200]}", file=sys.stderr)
        return None


def main():
    cert_key = os.environ.get("KAMIS_CERT_KEY")
    cert_id = os.environ.get("KAMIS_CERT_ID")
    if not cert_key or not cert_id:
        print("ERROR: KAMIS_CERT_KEY / KAMIS_CERT_ID 환경변수가 필요합니다.", file=sys.stderr)
        sys.exit(1)

    today = datetime.date.today()
    startday = (today - datetime.timedelta(days=400)).isoformat()  # 전년비 계산 위해 넉넉히 400일
    endday = today.isoformat()

    result = {}
    for code, cfg in ITEM_CONFIG.items():
        print(f"[{code}] {cfg['name']} 조회 중...")
        data = fetch_period_product(cert_key, cert_id, cfg, startday, endday)
        if not data:
            print(f"  -> 실패, 건너뜀")
            continue
        condition = data.get("condition")
        if isinstance(condition, list) and condition and condition[0].get("code") not in (None, "000"):
            print(f"  -> API 오류: {condition}")
            continue
        items = data.get("data", {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        points = []
        for it in items:
            regday = it.get("regday", "").replace("-", "").replace("/", "")
            price_raw = (it.get("price") or "").replace(",", "").strip()
            if not regday or not price_raw or price_raw in ("-", ""):
                continue
            try:
                price = float(price_raw)
            except ValueError:
                continue
            # regday가 MM/DD 형식으로만 오는 경우 연도(yyyy)를 별도 필드에서 보강
            yyyy = it.get("yyyy") or str(today.year)
            if len(regday) <= 5:
                regday = f"{yyyy}{regday.replace('/', '')}"
            points.append((regday, price))
        points = sorted(set(points))
        result[code] = {"name": cfg["name"], "points": points}
        print(f"  -> {len(points)}개 포인트 수집")

    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "kamis_latest.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"저장 완료: {out_path}")


if __name__ == "__main__":
    main()
