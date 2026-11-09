# -*- coding: utf-8 -*-
"""국제원료 탭에도 주간·월간 토글을 추가하고, 주간·월간 뷰 코드를 국산원물·국제원료 공용으로 교체한다.
(여러 번 실행해도 안전. 기존 HISTORY 데이터는 그대로 보존)  사용: python period_view_patch/apply_intl.py"""
import os, re, sys
here = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(here, "..", "index.html")
t = open(path, encoding="utf-8", newline="").read()
if "createPeriodView" in t:
    print("이미 적용되어 있음"); sys.exit(0)
nl = "\r\n" if "\r\n" in t else "\n"
js = open(os.path.join(here, "pv2.js"), encoding="utf-8").read().replace("\r\n", "\n").replace("\n", nl)

marker = "// ===== 주간·월간 시세 뷰"
call = "initPeriodView();"
s = t.find(marker)
e = t.rfind(call)
assert s != -1 and e > s, "기존 주간·월간 뷰 코드를 찾지 못함(apply.py 먼저 적용)"
region = t[s:e]
hm = re.search(r"const HISTORY = \{.*?\};[ \t]*\r?\n", region, re.S)
hist_line = hm.group(0).rstrip("\r\n") + nl if hm else "const HISTORY = {};" + nl
t = t[:s] + hist_line + js + t[e:]

grid = '      <div class="grid" id="intlGrid"></div>'
assert t.count(grid) == 1, "국제원료 그리드 위치를 찾지 못함"
bar = ('      <div class="pv-bar"><div><span class="pv-lbl">시세 보기</span><span class="pv-seg" id="piG"><button data-v="d" class="on">주간 종가 카드</button><button data-v="w">주간</button><button data-v="m">월간</button></span></div>'
       '<div id="piM" style="display:none"><span class="pv-lbl">셀 표시</span><span class="pv-seg"><button data-v="p" class="on">전기 대비</button><button data-v="y">전년 동기</button><button data-v="a">평균가</button></span></div></div>' + nl +
       '      <div id="piBox" style="display:none"></div>' + nl)
t = t.replace(grid, bar + grid, 1)
assert t.count(".pv-on #cardGrid,") == 1
t = t.replace(".pv-on #cardGrid,", ".pv-on #cardGrid, .pv-on #intlGrid,", 1)
open(path, "w", encoding="utf-8", newline="").write(t)
print("적용 완료")
