# -*- coding: utf-8 -*-
"""주간·월간 뷰가 HISTORY(백필+누적 이력)를 쓰도록 index.html 을 보완한다(여러 번 실행해도 안전).
사용: python period_view_patch/apply_history.py   (apply.py 적용 후)"""
import os, sys
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "index.html")
t = open(path, encoding="utf-8", newline="").read()
if "allPoints" in t:
    print("이미 적용되어 있음"); sys.exit(0)
nl = "\r\n" if "\r\n" in t else "\n"
subs = [
 ("function initPeriodView() {",
  "const HISTORY = {};" + nl + "function initPeriodView() {"),
 ("  const pd = s => new Date(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8));",
  "  const pd = s => new Date(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8));" + nl +
  "  // 일별 이력: HISTORY(원 단위, 백필+누적)와 DATA.points(이미 1kg 환산) 를 합친다. DATA 값이 우선." + nl +
  "  const allPoints = (item, code) => {" + nl +
  "    const div = item.kg_divisor || 1, m = new Map();" + nl +
  "    ((typeof HISTORY !== 'undefined' && HISTORY[code]) || []).forEach(([s, v]) => m.set(s, v / div));" + nl +
  "    (item.points || []).forEach(([s, v]) => m.set(s, v));" + nl +
  "    return [...m.entries()].sort();" + nl +
  "  };"),
 ("  function aggregate(item) {", "  function aggregate(item, code) {"),
 ("(item.points || []).forEach(([s, v]) => {", "allPoints(item, code).forEach(([s, v]) => {"),
 ("a: aggregate(it) }", "a: aggregate(it, code) }"),
 ("const thin = (it.points || []).length < 20;", "const thin = allPoints(it, code).length < 20;"),
]
for a, b in subs:
    assert t.count(a) == 1, "예상과 다른 구조: " + a[:40]
    t = t.replace(a, b, 1)
open(path, "w", encoding="utf-8", newline="").write(t)
print("적용 완료")
