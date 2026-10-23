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
AT_JSON = os.path.join(ROOT, "data", "at_recent.json")
ALERT_PCT = 20   # 전년동기 대비 급등/급락 기준(±%)


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

        # 전년동기 비교: '최근 이력(points)'에 이미 1년 전 데이터가 들어 있으므로 그것을 우선 사용하고,
        # 과거 스냅샷(yoy_points)은 보완용으로만 쓴다.
        # (예전에는 yoy_points에서만 찾아서, 스냅샷이 끝난 뒤(2025-08-25 이후)로는 매칭이 실패해
        #  yoy_date/yoy_price/yoy_chg_pct/alert 가 갱신되지 않고 옛 값으로 굳어 있었다.)
        pool = {p[0]: p[1] for p in (data[code].get("yoy_points") or [])}
        pool.update({d: p for d, p in merged_points})
        yoy_pt = find_nearest(sorted(pool.items()), ld - datetime.timedelta(days=365), max_diff_days=10)
        if yoy_pt:
            data[code]["yoy_date"] = yoy_pt[0]
            data[code]["yoy_price"] = yoy_pt[1]
            yoy_chg = pct(latest_price, yoy_pt[1])
            data[code]["yoy_chg_pct"] = yoy_chg
            if yoy_chg is not None and yoy_chg >= 20:
                data[code]["alert"] = "급등"
            elif yoy_chg is not None and yoy_chg <= -20:
                data[code]["alert"] = "급락"
            else:
                data[code]["alert"] = None
        else:
            # 1년 전 자료가 없으면 옛 값을 그대로 두지 않고 비운다
            # (오래된 전년 값이 최신 가격과 섞여 잘못된 급등/급락 판정을 내는 것을 방지)
            data[code]["yoy_date"] = None
            data[code]["yoy_price"] = None
            data[code]["yoy_chg_pct"] = None
            data[code]["alert"] = None

        data[code]["detail_min_price"] = latest_price
        data[code]["detail_max_price"] = latest_price
        print(f"[{code}] {data[code].get('name')} latest={latest_date} {latest_price} "
              f"day%={data[code]['day_chg_pct']} week%={data[code]['week_chg_pct']} "
              f"month%={data[code]['month_chg_pct']} yoy%={data[code].get('yoy_chg_pct')}")

    new_json = json.dumps(data, ensure_ascii=False)
    txt = txt[: m.start(1)] + new_json + txt[m.end(1):]
    open(INDEX_PATH, "w", encoding="utf-8").write(txt)


def one_year_before(d):
    try:
        return d.replace(year=d.year - 1)
    except ValueError:          # 2/29 → 2/28
        return d.replace(year=d.year - 1, day=28)


def merge_at_recent():
    """data/at_recent.json(한국농수산식품유통공사 '최근일자 도,소매가격정보')을 DATA 에 반영한다.

    이 API는 최근 조사일 가격과 1일/1주/1개월/1년 전 가격을 한 번에 주므로,
    전년동기·전월 대비를 과거 이력 없이 바로 계산한다(yoy_src='at' 표시).
    대상: 고춧가루(소매, 248), 건고추 화건 도매(248D).
    처음 적용할 때는 서로 다른 출처가 섞여 있던 예전 이력(points/yoy_points)을 이 API 값으로 교체하고,
    이후에는 매일 최신 가격을 이어 붙인다.
    """
    if not os.path.exists(AT_JSON):
        print("at_recent.json 없음 — 최근일자 도·소매가격 반영 건너뜀")
        return
    with open(AT_JSON, encoding="utf-8") as f:
        fetched = json.load(f)

    txt = open(INDEX_PATH, encoding="utf-8").read()
    m = re.search(r"const DATA = (\{.*?\});\s*\n", txt, re.S)
    data = json.loads(m.group(1))

    for code, f in fetched.items():
        if code not in data:
            print(f"[at:{code}] DATA 에 없는 품목 — 건너뜀")
            continue
        latest = f.get("prc")
        ymd = f.get("exmn_ymd")
        if latest is None or not ymd:
            continue
        ld = to_date(ymd)
        d = data[code]
        yy1, mm1, ww1, dd1 = f.get("yy1"), f.get("mm1"), f.get("ww1"), f.get("dd1")
        yoy_date = one_year_before(ld).strftime("%Y%m%d")

        if d.get("yoy_src") != "at":
            # 최초 전환: 예전 이력을 비우고, API가 알려주는 시점별 가격으로 시작 이력을 만든다.
            seeds = []
            if yy1 is not None:
                seeds.append((yoy_date, yy1))
            if mm1 is not None:
                seeds.append(((ld - datetime.timedelta(days=30)).strftime("%Y%m%d"), mm1))
            if ww1 is not None:
                seeds.append(((ld - datetime.timedelta(days=7)).strftime("%Y%m%d"), ww1))
            if dd1 is not None:
                seeds.append(((ld - datetime.timedelta(days=1)).strftime("%Y%m%d"), dd1))
            seeds.append((ymd, latest))
            d["points"] = [list(p) for p in sorted(set(seeds))]
            d["yoy_points"] = [[yoy_date, yy1]] if yy1 is not None else []
        else:
            merged = {p[0]: p[1] for p in d.get("points", [])}
            merged[ymd] = latest
            d["points"] = [list(p) for p in sorted(merged.items())]
            if yy1 is not None:
                yp = {p[0]: p[1] for p in (d.get("yoy_points") or [])}
                yp[yoy_date] = yy1
                d["yoy_points"] = [list(p) for p in sorted(yp.items())]

        d["yoy_src"] = "at"
        d["latest_date"] = ymd
        d["latest_price"] = latest
        d["unit"] = f"kg{str(f.get('unit_sz') or 1).strip()}"      # 예: kg1(소매), kg30(30kg 중도매)
        d["basis"] = f.get("basis") or d.get("basis")
        d["day_chg_pct"] = pct(latest, dd1) if dd1 else 0.0
        d["week_chg_pct"] = pct(latest, ww1) if ww1 else 0.0
        d["month_chg_pct"] = pct(latest, mm1) if mm1 else 0.0
        if yy1:
            d["yoy_date"] = yoy_date
            d["yoy_price"] = yy1
            d["yoy_chg_pct"] = pct(latest, yy1)
            chg = d["yoy_chg_pct"]
            d["alert"] = "급등" if chg >= ALERT_PCT else ("급락" if chg <= -ALERT_PCT else None)
        else:
            d["yoy_date"] = d["yoy_price"] = d["yoy_chg_pct"] = None
            d["alert"] = None
        d["detail_min_price"] = latest
        d["detail_max_price"] = latest
        print(f"[at:{code}] {d.get('name')} latest={ymd} {latest} yoy%={d.get('yoy_chg_pct')} month%={d['month_chg_pct']}")

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
    merge_at_recent()
    merge_intl()
    print("완료. index.html이 갱신되었습니다.")


if __name__ == "__main__":
    main()
