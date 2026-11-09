# -*- coding: utf-8 -*-
"""index.html 에 주간·월간 시세 뷰를 추가한다(여러 번 실행해도 안전). 사용: python period_view_patch/apply.py"""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(here, "..", "index.html")
t = open(path, encoding="utf-8", newline="").read()
if "initPeriodView" in t:
    print("이미 적용되어 있음"); sys.exit(0)
nl = "\r\n" if "\r\n" in t else "\n"
rd = lambda n: open(os.path.join(here, n), encoding="utf-8").read().replace("\r\n", "\n").replace("\n", nl)
css, js = rd("pv.css"), rd("pv.js")
html = ('    <div class="pv-bar"><div><span class="pv-lbl">시세 보기</span><span class="pv-seg" id="pvG"><button data-v="d" class="on">일별 카드</button><button data-v="w">주간</button><button data-v="m">월간</button></span></div>'
        '<div id="pvM" style="display:none"><span class="pv-lbl">셀 표시</span><span class="pv-seg"><button data-v="p" class="on">전기 대비</button><button data-v="y">전년 동기</button><button data-v="a">평균가</button></span></div></div>' + nl +
        '    <div id="pvBox" style="display:none"></div>' + nl)
card = '    <div class="grid" id="cardGrid"></div>'
tail = "maybeAutoPopupAlarm();" + nl + "</script>"
assert t.count(card) == 1 and t.count(tail) == 1 and "</style>" in t, "index.html 구조가 예상과 달라 적용하지 않음"
t = t.replace("</style>", css + "</style>", 1)
t = t.replace(card, html + card, 1)
t = t.replace(tail, "maybeAutoPopupAlarm();" + nl + js + "initPeriodView();" + nl + "</script>", 1)
open(path, "w", encoding="utf-8", newline="").write(t)
print("적용 완료")
