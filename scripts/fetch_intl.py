#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국제 원료(원당/소맥/대두유/옥수수) 선물 시세를 Yahoo Finance 공개 차트 API에서 가져온다.
aT 식품산업통계정보(FIS)의 국제원료가격 페이지는 별도 Open-API가 없어(서버 렌더링 페이지),
대신 동일 계열의 연속선물(front-month) 데이터를 제공하는 Yahoo Finance를 사용한다.

주의: aT FIS의 특정 인도월 계약가와는 롤오버 시점에 따라 소폭 차이가 날 수 있다.
"""
import sys
import json
import urllib.request

TICKERS = {
    "sugar": "SB=F",   # ICE 11번 설탕, 센트/lb
    "wheat": "ZW=F",   # CBOT 밀, 센트/부셸
    "soyoil": "ZL=F",  # CBOT 대두유, 센트/lb
    "corn": "ZC=F",    # CBOT 옥수수, 센트/부셸
}

def fetch_chart(ticker, range_="1y", interval="1wk"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_}&interval={interval}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def main():
    result = {}
    for code, ticker in TICKERS.items():
        print(f"[{code}] {ticker} 조회 중...")
        try:
            data = fetch_chart(ticker)
        except Exception as e:
            print(f"  -> 실패: {e}", file=sys.stderr)
            continue
        try:
            chart_result = data["chart"]["result"][0]
            timestamps = chart_result["timestamp"]
            closes = chart_result["indicators"]["quote"][0]["close"]
        except (KeyError, IndexError, TypeError):
            print(f"  -> 응답 파싱 실패")
            continue
        points = []
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            import datetime
            d = datetime.datetime.utcfromtimestamp(ts).strftime("%Y%m%d")
            points.append((d, round(close, 2)))
        result[code] = {"ticker": ticker, "points": points}
        print(f"  -> {len(points)}개 포인트 수집")

    import os
    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "intl_latest.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"저장 완료: {out_path}")


if __name__ == "__main__":
    main()
