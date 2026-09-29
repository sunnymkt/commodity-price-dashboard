#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data/kamis_latest.json, data/intl_latest.json 을 index.html의
DATA / INTL_DATA 객체에 병합하고, day/week/month/yoy 변화율과
alert(급등/급락) 필드를 재계산한다.

이 스크립트는 국내 8개 품목(KAMIS periodProductList 커버 품목)과
국제 4개 원료(Yahoo Finance)만 자동 갱신한다.
배추/딸기(가락시장 경락가), 계란, 밤, 고춧가루(도매/건고추)는
자동 소스가 없어 그대로 유지되며, 필요 시 기존 방식(브라우저 조사)으로
수동 갱신해야 한다. NEWS_DATA/HIKE_NEWS_DATA(뉴스)도 이 스크립트가
건드리지 않는다 — 사람의 판단이 필요한 영역이라 의도적으로 제외했다.
"""
import re
import os
import sys
import json
import bisect
import datetime

ROOT = os.path.join(os.path.dirname(__file__), "..")
INDEX_PATH = os.path.join(ROOT, "index.html")
KAMIS_JSON = os.path.join(ROOT, "data", "kamis_latest.json")
INTL_JSON = os.path.join(ROOT, "data", "intl_latest.json")


def to_date(s):
    return datetime.datetime.strptime(s, "%Y%m%d").date()


def find_nearest(points, target_date, max_diff_days=10):
    """points: sorted list of (yyyymmdd_str, price). target_date: datetime.date"""
    if not points:
        return None
    dates = [to_date(p[0]) for p in points]
    idx = bisect.bisect_left(dates, target_date)
    candidates = []
    if idx < len(dates):
        candidates.append(idx)
    if idx > 0:
        candidates.append(idx - 1)
    best = None
    best_diff = None
    for i in candidates:
        diff = abs((dates[i] - target_date).days)
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best = i
    if best is None or best_diff > max_diff_days:
        return None
    return points[best]


def pct(new, old):
    if old in (None, 0):
        return None
    return round((new - old) / old * 100, 1)


def merge_domestic():
    if not os.path.exists(KAMIS_JSON):
        print("kamis_latest.json 없음 — 국내 데이터 갱신 건너뜀")
        return
    with open(KAMIS_JSON, encoding="utf-8") as f:
        fetched = json.load(f)

    txt = open(INDEX_PATH, encoding="utf-8").read()
    m = re.search(r"const DATA = (\{.*?\});\s*\n", txt, re.S)
    data = json.loads(m.group(1))

    for code, fdata in fetched.items():
        if code not in data:
            continue
        new_points = [(d, p) for d, p in fdata["points"]]
        if not new_points:
            continue
        existing = data[code].get("points", [])
        # 날짜(date)를 키로 쓰는 dict 병합 — 같은 날짜가 다시 들어오면 새 값으로 덮어써서
        # 같은 날짜에 서로 다른 값이 중복 저장되는 일이 없도록 한다.
        merged = {(p[0] if isinstance(p, list) else p[0]): (p[1] if isinstance(p, list) else p[1]) for p in existing}
        for d, p in new_points:
            merged[d] = p
        merged_points = sorted(merged.items())
        data[code]["points"] = [list(p) for p in merged_points]

        latest_date, latest_price = merged_points[-1]
        ld = to_date(latest_date)

        day_pt = find_nearest(merged_points[:-1], ld - datetime.timedelta(days=1), max_diff_days=4)
        week_pt = find_nearest(merged_points, ld - datetime.timedelta(days=7), max_diff_days=3)
        month_pt = find_nearest(merged_points, ld - datetime.timedelta(days=30), max_diff_days=5)

        data[code]["latest_date"] = latest_date
        data[code]["latest_price"] = latest_price
        data[code]["day_chg_pct"] = pct(latest_price, day_pt[1]) if day_pt else 0.0
        data[code]["week_chg_pct"] = pct(latest_price, week_pt[1]) if week_pt else 0.0
        data[code]["month_chg_pct"] = pct(latest_price, month_pt[1]) if month_pt else 0.0

        yoy_points = data[code].get("yoy_points")
        if yoy_points:
            yoy_pt = find_nearest([tuple(p) for p in yoy_points], ld - datetime.timedelta(days=365), max_diff_days=10)
            if yoy_pt:
                data[code]["yoy_date"] = yoy_pt[0]
                data[code]["yoy_price"] = yoy_pt[1]
                yoy_chg = pct(latest_price, yoy_pt[1])
                data[code]["yoy_chg_pct"] = yoy_chg
                if yoy_chg is not None and yoy_chg >= 15:
                    data[code]["alert"] = "급등"
                elif yoy_chg is not None and yoy_chg <= -15:
                    data[code]["alert"] = "급락"
                else:
                    data[code]["alert"] = None

        data[code]["detail_min_price"] = latest_price
        data[code]["detail_max_price"] = latest_price
        print(f"[{code}] {data[code].get('name')} latest={latest_date} {latest_price} "
              f"day%={data[code]['day_chg_pct']} week%={data[code]['week_chg_pct']} "
              f"month%={data[code]['month_chg_pct']} yoy%={data[code].get('yoy_chg_pct')}")

    new_json = json.dumps(data, ensure_ascii=False)
    txt = txt[: m.start(1)] + new_json + txt[m.end(1):]
    open(INDEX_PATH, "w", encoding="utf-8").write(txt)


def merge_intl():
    if not os.path.exists(INTL_JSON):
        print("intl_latest.json 없음 — 국제 데이터 갱신 건너뜀")
        return
    with open(INTL_JSON, encoding="utf-8") as f:
        fetched = json.load(f)

    txt = open(INDEX_PATH, encoding="utf-8").read()

    for code, fdata in fetched.items():
        points = fdata["points"]
        if not points:
            continue
        # INTL_DATA는 JSON이 아닌 JS 객체 리터럴이라, 각 품목의 points 배열
        # 마지막 항목 뒤에 텍스트로 새 포인트를 이어붙이는 방식으로 갱신한다.
        block_match = re.search(
            rf'"{code}":\s*\{{.*?points:\s*\[(.*?)\],\s*yoy_points:', txt, re.S
        ) or re.search(
            rf"{code}:\s*\{{.*?points:\s*\[(.*?)\],\s*yoy_points:", txt, re.S
        )
        if not block_match:
            print(f"[intl:{code}] points 블록을 찾지 못함 — 건너뜀")
            continue
        existing_points_str = block_match.group(1)
        # 이미 있는 날짜는 중복 추가하지 않도록 확인
        new_fragment_parts = []
        for d, p in points:
            marker = f'"{d}"'
            if marker not in existing_points_str:
                new_fragment_parts.append(f'["{d}", {p}]')
        if not new_fragment_parts:
            print(f"[intl:{code}] 추가할 신규 포인트 없음")
            continue
        new_fragment = ", ".join(new_fragment_parts)
        old_full = f"points: [{existing_points_str}]"
        new_full = f"points: [{existing_points_str}, {new_fragment}]"
        txt = txt.replace(old_full, new_full, 1)
        print(f"[intl:{code}] {len(new_fragment_parts)}개 포인트 추가")

        # 최신값으로 price/asof/day/week/month 갱신은 aT FIS 스냅샷 수동 갱신을 권장.
        # (Yahoo 연속선물과 aT FIS 인도월 계약가 차이가 있어 여기서는 차트 포인트만 갱신)

    open(INDEX_PATH, "w", encoding="utf-8").write(txt)


def main():
    merge_domestic()
    merge_intl()
    print("완료. index.html이 갱신되었습니다.")


if __name__ == "__main__":
    main()
