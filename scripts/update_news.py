#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
매일 index.html 의 두 뉴스 탭을 갱신한다.
  - 원물 수매 이슈  : NEWS_DATA      (품목 코드별 기사 목록)
  - 가격인상 동향   : HIKE_NEWS_DATA (카테고리별 가격 인상 사례)

뉴스는 네이버 검색 API(뉴스)로 가져온다. 환경변수 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 없으면 건너뛴다.
(GitHub Secrets 로 등록. 코드나 저장소에 키를 적지 말 것.)

원칙
  - 기존에 사람이 정리해 둔 기사·요약은 지우지 않고, 새 기사를 앞쪽에 추가한다(중복 제거, 오래된 것만 정리).
  - 새 기사의 요약은 검색 결과의 짧은 발췌문(스니펫)을 그대로 줄여서 쓴다. 기사 본문을 읽고 쓴 요약이 아니다.
  - 가격인상 카드의 회사·인상률·카테고리는 제목/스니펫에서 규칙으로 추출한 값이라 틀릴 수 있다.
  - 페이지가 값을 innerHTML 로 그대로 넣으므로, 가져온 텍스트는 태그를 제거하고 HTML 이스케이프한다. URL 은 http(s)만 허용한다.
  - API 호출이 실패하거나 결과가 없으면 index.html 을 바꾸지 않는다.
"""
import os
import re
import sys
import json
import html
import time
import subprocess
import datetime
import email.utils
import urllib.request
import urllib.parse
import urllib.error

ROOT = os.path.join(os.path.dirname(__file__), "..")
INDEX_PATH = os.path.join(ROOT, "index.html")
NAVER_URL = "https://openapi.naver.com/v1/search/news.json"

FETCH_MAX_AGE_DAYS = 14      # 새로 가져오는 기사는 최근 N일 이내만
KEEP_DAYS = 120              # 이보다 오래된 기사는 목록에서 정리
MAX_NEWS_PER_ITEM = 6
MAX_HIKE_PER_CAT = 8
SUMMARY_MAX = 140

KST = datetime.timezone(datetime.timedelta(hours=9))

# ───────────── 원물 수매 이슈: 품목별 검색 설정 ─────────────
TOPIC = re.compile(r"수매|수급|작황|출하|비축|계약재배|가격|값|재배|생산|APC|산지|공판")
NEWS_ITEMS = {
    "111": {"name": "쌀", "q": ["쌀 수매", "쌀값 수급 비축"], "kw": r"쌀|벼|햅쌀"},
    "141": {"name": "콩(백태/대립종)", "q": ["콩 수매 백태", "서리태 수매 전략작물"], "kw": r"콩|백태|서리태|대두"},
    "151": {"name": "고구마", "q": ["고구마 수매 가격"], "kw": r"고구마"},
    "211": {"name": "배추", "q": ["배추 수급 가격", "배추 수매 비축"], "kw": r"배추"},
    "226": {"name": "딸기(설향)", "q": ["딸기 수매 가격", "설향 딸기 출하"], "kw": r"딸기"},
    "248": {"name": "고춧가루", "q": ["고추 수매", "건고추 가격 수급", "고춧가루 가격"], "kw": r"고추|고춧가루"},
    "312": {"name": "참깨", "q": ["참깨 수매 가격"], "kw": r"참깨"},
    "313": {"name": "들깨", "q": ["들깨 수매 가격"], "kw": r"들깨"},
    "651": {"name": "멸치액젓", "q": ["멸치액젓 가격", "액젓 가격 인상"], "kw": r"액젓|멸치"},
    "652": {"name": "천일염", "q": ["천일염 가격 수급", "천일염 수매 비축"], "kw": r"천일염|소금"},
    "9903": {"name": "계란", "q": ["계란 가격 수급", "달걀 가격"], "kw": r"계란|달걀"},
    # '밤'은 일상어(하룻밤 등)와 겹쳐서 수매·작황 같은 말이 같이 있어야 인정한다.
    "9905": {
        "name": "밤(국산)", "q": ["밤 수매 가격 농협", "국산 밤 작황"],
        "kw": r"(?<![가-힣])밤(?:[이가을를은는의도에과와]|(?![가-힣]))|알밤|군밤",
        "need": r"수매|작황|산지|생산|농협|공판",
    },
}

# ───────────── 가격인상 동향 설정 ─────────────
HIKE_QUERIES = [
    "식품 가격 인상", "라면 가격 인상", "과자 가격 인상", "김치 가격 인상", "두부 가격 인상",
    "장류 가격 인상", "참치캔 가격 인상", "음료 가격 인상", "만두 간편식 가격 인상", "제과 초콜릿 가격 인상",
]
HIKE_RISE = re.compile(r"인상|올린|올려|올랐|오른다|↑")
HIKE_CATS = [  # (카테고리, 키워드) — 위에서부터 먼저 맞는 것을 쓴다
    ("김치", r"김치"),
    ("두부", r"두부"),
    ("참치·장류", r"참치|통조림|수산캔|꽁치|고추장|된장|쌈장|간장|장류|식용유|참기름|들기름|식용유지"),
    ("라면", r"라면|짜장|우동|면류"),
    ("음료", r"음료|커피|탄산|주스|생수|이온|차음료"),
    ("과자·스낵", r"과자|스낵|감자칩|새우깡|쿠키"),
    ("간편식·베이커리", r"만두|간편식|냉동|밀키트|즉석|빵|베이커리|햄버거|도시락"),
    ("제과", r"제과|초콜릿|초코|사탕|젤리|껌|캔디"),
]
COMPANIES = [
    "풀무원", "농심", "오뚜기", "삼양식품", "삼양", "팔도", "동원F&B", "동원", "사조", "CJ제일제당", "CJ", "대상",
    "롯데웰푸드", "롯데칠성", "롯데", "해태", "크라운해태", "오리온", "빙그레", "매일유업", "남양유업", "하이트진로",
    "오비맥주", "코카콜라", "동서식품", "청정원", "샘표", "해찬들", "종가", "비비고", "SPC", "파리바게뜨",
    "뚜레쥬르", "이마트", "홈플러스", "프리미엄", "하림", "닭고기", "서울우유", "일화", "광동제약", "웅진",
]

OUTLETS = {  # 도메인 → 매체명(일부). 없으면 도메인 그대로 쓴다.
    "heraldcorp.com": "헤럴드경제", "ajunews.com": "아주경제", "etoday.co.kr": "이투데이", "newspim.com": "뉴스핌",
    "edaily.co.kr": "이데일리", "fnnews.com": "파이낸셜뉴스", "etnews.com": "전자신문", "newsis.com": "뉴시스",
    "yna.co.kr": "연합뉴스", "hankyung.com": "한국경제", "mk.co.kr": "매일경제", "chosun.com": "조선일보",
    "joongang.co.kr": "중앙일보", "donga.com": "동아일보", "hani.co.kr": "한겨레", "khan.co.kr": "경향신문",
    "sedaily.com": "서울경제", "asiae.co.kr": "아시아경제", "mt.co.kr": "머니투데이", "news1.kr": "뉴스1",
    "kyongbuk.co.kr": "경북일보", "farminsight.net": "팜인사이트", "nongmin.com": "농민신문", "agrinet.co.kr": "한국농어민신문",
    "mtn.co.kr": "MTN", "sbs.co.kr": "SBS", "kbs.co.kr": "KBS", "mbc.co.kr": "MBC", "ytn.co.kr": "YTN",
    "kmib.co.kr": "국민일보", "segye.com": "세계일보", "munhwa.com": "문화일보", "dt.co.kr": "디지털타임스",
    "ajunews.com": "아주경제", "biz.chosun.com": "조선비즈", "thebell.co.kr": "더벨", "foodnews.co.kr": "식품저널",
}


# ───────────── 텍스트 정리 ─────────────
def clean_text(s):
    """검색 결과 문자열에서 태그를 지우고 엔티티를 풀어 일반 텍스트로 만든다."""
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def esc(s):
    """페이지가 innerHTML 로 그대로 넣으므로 <, >, & 를 이스케이프한다."""
    return html.escape(s, quote=False)


def safe_url(u):
    u = (u or "").strip()
    if not re.match(r"^https?://", u, re.I):
        return None
    return u.replace('"', "%22").replace("'", "%27").replace("<", "%3C").replace(">", "%3E").replace(" ", "%20")


def shorten(s, n):
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def norm_title(t):
    return re.sub(r"[^0-9A-Za-z가-힣]", "", t or "")


def outlet_of(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    host = re.sub(r"^(www|m|news)\.", "", host)
    for dom, name in OUTLETS.items():
        if host == dom or host.endswith("." + dom):
            return name
    return host


def parse_pubdate(s):
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(KST).date()
    except Exception:  # noqa: BLE001
        return None


# ───────────── 네이버 검색 API ─────────────
def naver_search(cid, secret, query, display=30):
    url = NAVER_URL + "?" + urllib.parse.urlencode({"query": query, "display": display, "start": 1, "sort": "date"})
    req = urllib.request.Request(url, headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret})
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            print(f"  [WARN] '{query}' 조회 실패 HTTP {e.code}", file=sys.stderr)
            return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            print(f"  [WARN] '{query}' 조회 실패 {e!r}", file=sys.stderr)
            return None
    return None


def fetch_articles(search, query, today):
    """검색해서 최근 기사 목록(dict)으로 정리한다."""
    payload = search(query)
    out = []
    for it in (payload or {}).get("items", []):
        d = parse_pubdate(it.get("pubDate"))
        if not d or (today - d).days > FETCH_MAX_AGE_DAYS or d > today:
            continue
        url = safe_url(it.get("originallink") or it.get("link"))
        title = clean_text(it.get("title"))
        if not url or not title:
            continue
        out.append({
            "date": d, "title": title, "snippet": clean_text(it.get("description")),
            "url": url, "source": outlet_of(url),
        })
    return out


# ───────────── JS 리터럴 읽기/쓰기 ─────────────
def match_bracket(text, i):
    """text[i] 의 여는 괄호에 대응하는 닫는 괄호 위치(문자열·주석 안의 괄호는 무시)."""
    depth, j, n = 0, i, len(text)
    while j < n:
        c = text[j]
        if c in "'\"`":
            q = c
            j += 1
            while j < n and text[j] != q:
                if text[j] == "\\":
                    j += 1
                j += 1
        elif text.startswith("//", j):
            k = text.find("\n", j)
            j = n if k < 0 else k
            continue
        elif text.startswith("/*", j):
            j = text.index("*/", j) + 2
            continue
        elif c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise ValueError("괄호 짝을 찾지 못함")


def locate_const(text, name):
    m = re.search(r"const " + re.escape(name) + r"\s*=\s*", text)
    if not m:
        raise ValueError(f"{name} 선언을 찾지 못함")
    start = m.end()
    return start, match_bracket(text, start) + 1


def parse_js_literal(src):
    try:
        return json.loads(src)           # 이전 실행에서 JSON 형태로 저장된 경우
    except json.JSONDecodeError:
        pass
    r = subprocess.run(
        ["node", "-e", 'let s=require("fs").readFileSync(0,"utf8");console.log(JSON.stringify(eval("("+s+")")))'],
        input=src, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    if r.returncode != 0:
        raise ValueError("JS 리터럴을 읽지 못함: " + r.stderr[:200])
    return json.loads(r.stdout)


def to_js_literal(obj):
    s = json.dumps(obj, ensure_ascii=False, indent=2)
    return s.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


# ───────────── 원물 수매 이슈 ─────────────
def collect_news(search, today):
    result = {}
    for code, cfg in NEWS_ITEMS.items():
        kw = re.compile(cfg["kw"])
        need = re.compile(cfg["need"]) if cfg.get("need") else None
        seen, picked = set(), []
        for q in cfg["q"]:
            for a in fetch_articles(search, q, today):
                if not kw.search(a["title"]):
                    continue
                blob = a["title"] + " " + a["snippet"]
                if not TOPIC.search(blob) or (need and not need.search(blob)):
                    continue
                key = norm_title(a["title"])[:40]
                if key in seen:
                    continue
                seen.add(key)
                picked.append(a)
            time.sleep(0.3)
        picked.sort(key=lambda a: a["date"], reverse=True)
        result[code] = picked[:MAX_NEWS_PER_ITEM]
        print(f"[news:{code}] {cfg['name']}: 새 기사 후보 {len(result[code])}건")
    return result


def merge_news(existing, fresh, today):
    cutoff = today - datetime.timedelta(days=KEEP_DAYS)
    out = dict(existing)
    for code, arts in fresh.items():
        entry = out.get(code) or {"signal": None, "articles": []}
        old = entry.get("articles", [])
        seen_url = {a.get("url") for a in old}
        seen_title = {norm_title(a.get("title", ""))[:40] for a in old}
        new = []
        for a in arts:
            if a["url"] in seen_url or norm_title(a["title"])[:40] in seen_title:
                continue
            new.append({
                "date": a["date"].isoformat(), "source": esc(a["source"]), "title": esc(a["title"]),
                "url": a["url"], "summary": esc(shorten(a["snippet"], SUMMARY_MAX)),
            })
        merged = new + old
        merged = [a for a in merged if str(a.get("date", "9999")) >= cutoff.isoformat()]
        merged.sort(key=lambda a: str(a.get("date", "")), reverse=True)
        entry["articles"] = merged[:MAX_NEWS_PER_ITEM]
        out[code] = entry
    return out


# ───────────── 가격인상 동향 ─────────────
def hike_fields(a):
    blob = a["title"] + " " + a["snippet"]
    if not HIKE_RISE.search(a["title"]):
        return None
    cat = next((c for c, kw in HIKE_CATS if re.search(kw, a["title"])), None) \
        or next((c for c, kw in HIKE_CATS if re.search(kw, blob)), None)
    if not cat:
        return None
    company = next((c for c in COMPANIES if c in a["title"]), None) or next((c for c in COMPANIES if c in blob), "업계")
    pct = "-"
    rng = re.search(r"(\d+(?:\.\d+)?)\s*[~∼]\s*(\d+(?:\.\d+)?)\s*%", a["title"])
    one = re.search(r"(\d+(?:\.\d+)?)\s*%", a["title"])
    if rng:
        pct = f"{rng.group(1)}~{rng.group(2)}%↑"
    elif one:
        pct = f"{'평균 ' if '평균' in a['title'] else ''}{one.group(1)}%↑"
    return {"cat": cat, "company": company, "pct": pct}


def collect_hike(search, today):
    cands, seen = [], set()
    for q in HIKE_QUERIES:
        for a in fetch_articles(search, q, today):
            f = hike_fields(a)
            if not f:
                continue
            key = norm_title(a["title"])[:40]
            event = (f["company"], f["cat"], f["pct"]) if f["pct"] != "-" else None
            if key in seen or (event and event in seen):
                continue
            seen.add(key)
            if event:
                seen.add(event)
            cands.append((a, f))
        time.sleep(0.3)
    cands.sort(key=lambda x: x[0]["date"], reverse=True)
    print(f"[hike] 새 사례 후보 {len(cands)}건")
    return cands


def hike_date(s):
    m = re.match(r"(\d{4})\.(\d{2})\.(\d{2})", str(s or ""))
    return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def merge_hike(existing, cands, today):
    cutoff = today - datetime.timedelta(days=KEEP_DAYS)
    groups = {g["cat"]: {"cat": g["cat"], "items": list(g.get("items", []))} for g in existing}
    order = [g["cat"] for g in existing]
    seen_url = {it.get("url") for g in groups.values() for it in g["items"]}
    seen_title = {norm_title(it.get("product", ""))[:40] for g in groups.values() for it in g["items"]}
    for a, f in cands:
        if a["url"] in seen_url or norm_title(a["title"])[:40] in seen_title:
            continue
        g = groups.get(f["cat"])
        if g is None:
            g = groups[f["cat"]] = {"cat": f["cat"], "items": []}
            order.append(f["cat"])
        g["items"].append({
            "company": esc(f["company"]), "product": esc(shorten(a["title"], 70)), "pct": esc(f["pct"]),
            "date": a["date"].strftime("%Y.%m.%d") + " 보도", "source": esc(a["source"]), "url": a["url"],
            "summary": esc(shorten(a["snippet"], SUMMARY_MAX)),
        })
    result = []
    for cat in order:
        items = groups[cat]["items"]
        keep = [it for it in items if (hike_date(it.get("date")) is None or hike_date(it.get("date")) >= cutoff)]
        keep.sort(key=lambda it: hike_date(it.get("date")) or today, reverse=True)
        if keep:
            result.append({"cat": cat, "items": keep[:MAX_HIKE_PER_CAT]})
    return result


# ───────────── 메인 ─────────────
def apply_update(text, news_fresh, hike_cands, today):
    """index.html 텍스트에 갱신을 반영해 새 텍스트를 돌려준다."""
    iso = today.isoformat()

    s, e = locate_const(text, "NEWS_DATA")
    news = parse_js_literal(text[s:e])
    news = merge_news(news, news_fresh, today)
    text = text[:s] + to_js_literal(news) + text[e:]

    s, e = locate_const(text, "HIKE_NEWS_DATA")
    hike = parse_js_literal(text[s:e])
    hike = merge_hike(hike, hike_cands, today)
    text = text[:s] + to_js_literal(hike) + text[e:]

    for name in ("NEWS_AS_OF", "HIKE_NEWS_AS_OF"):
        text, n = re.subn(r"(const " + name + r"\s*=\s*')[^']*(')", r"\g<1>" + iso + r"\g<2>", text, count=1)
        if n != 1:
            raise ValueError(f"{name} 선언을 찾지 못함")
    return text


def main():
    cid = os.environ.get("NAVER_CLIENT_ID", "").strip()
    secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        print("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 미설정 — 뉴스 갱신을 건너뜁니다.")
        return

    today = datetime.datetime.now(KST).date()
    calls = {"n": 0, "ok": 0}

    def search(q):
        calls["n"] += 1
        r = naver_search(cid, secret, q)
        if r is not None:
            calls["ok"] += 1
        return r

    news_fresh = collect_news(search, today)
    hike_cands = collect_hike(search, today)
    if calls["ok"] == 0:
        print("모든 검색이 실패해 index.html 을 바꾸지 않습니다.", file=sys.stderr)
        return

    text = open(INDEX_PATH, encoding="utf-8").read()
    try:
        new_text = apply_update(text, news_fresh, hike_cands, today)
    except Exception as e:  # noqa: BLE001
        print(f"뉴스 반영 실패 — index.html 을 바꾸지 않습니다: {e}", file=sys.stderr)
        return
    open(INDEX_PATH, "w", encoding="utf-8").write(new_text)
    print(f"완료: 검색 {calls['ok']}/{calls['n']}건 성공, 기준일 {today.isoformat()}")


if __name__ == "__main__":
    main()
