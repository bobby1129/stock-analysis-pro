# -*- coding: utf-8 -*-
"""S5 自测: 研判验证+断言生成(mock LLM) + 落盘接线 + 模板渲染。
mock缓存/历史写入临时目录, 不污染真实cache。"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis import llm_interpret as li
from analysis import review_history as rh
from analysis import verify_guidance as vg

failures = []
def check(name, cond, detail=""):
    print(("✅" if cond else "❌") + f" {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(name)

tmpdir = tempfile.mkdtemp(prefix="s5_test_")
old_cache, old_hist = vg.CACHE_DIR, rh.HISTORY_DIR
vg.CACHE_DIR = tmpdir
rh.HISTORY_DIR = os.path.join(tmpdir, "hist")
os.makedirs(rh.HISTORY_DIR)

# ── mock LLM ──
calls = {"n": 0}
def mock_llm_json(prompt, max_tokens=3500, attempts=3):
    calls["n"] += 1
    if "可验证的断言" in prompt or "明日可验证断言" in prompt:
        return ["上证指数明日收涨", "两市成交额维持1.5万亿以上", "AI算力方向资金延续净流入"]
    # 验证
    return {"asserts": [{"i": 1, "verdict": "hit", "actual": "上证收涨0.8%"},
                        {"i": 2, "verdict": "miss", "actual": "成交额1.2万亿低于1.5万亿"},
                        {"i": 99, "verdict": "bogus", "actual": "越界序号"}],
            "tips": [{"code": "603893", "verdict": "hit", "actual": "跌7.9%, 偏空提示正确"},
                     {"code": "999999", "verdict": "hit", "actual": "不存在的票忽略"}]}
li._call_llm_json = mock_llm_json

# ── 1. 断言生成 ──
result = {"date": "20261029",
          "indices": [{"name": "上证指数", "code": "sh000001", "price": 3651.4, "change_pct": -0.82,
                       "technical_indicators": {"short_term": {"score": -15, "advice": "🔴 短线偏空"}}}],
          "breadth": {"up": 781, "down": 4727, "limit_up": 39, "limit_down": 41, "max_lianban": 4},
          "macro": {"total_market_amount": 15565.17},
          "sentiment_cycle": {"phase": "冰点", "score": 22},
          "concepts_fund": [{"name": "AI算力", "net": 12.3}],
          "portfolio": [{"code": "603893", "name": "瑞芯微", "price": 190.1, "change_pct": 2.5}]}
vg.generate_assertions(result, verbose=False)
check("断言生成3条", result["assertions_today"] == ["上证指数明日收涨", "两市成交额维持1.5万亿以上", "AI算力方向资金延续净流入"])
calls["n"] = 0
vg.generate_assertions(result, verbose=False)
check("断言缓存命中0次LLM", calls["n"] == 0 and len(result["assertions_today"]) == 3)

# 无指引→跳过
r_noguid = {"date": "20261029", "indices": [], "breadth": {}, "macro": {}, "portfolio": []}
calls["n"] = 0
vg.generate_assertions(r_noguid, verbose=False)
check("无规则指引跳过断言", calls["n"] == 0 and r_noguid["assertions_today"] == [])

# LLM宕机→降级空(换日期避开缓存)
li._call_llm_json = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))
r_boom = dict(result, date="20261021")
vg.generate_assertions(r_boom, verbose=False)
check("断言LLM失败降级空列表", r_boom["assertions_today"] == [])
li._call_llm_json = mock_llm_json

# ── 2. 无昨日记录→跳过验证 ──
r_v = dict(result)
vg.verify_previous(r_v, verbose=False)
check("无历史记录跳过验证", r_v["verification"] is None)

# ── 3. 写入昨日记录后验证 ──
prev = {"date": "2026-10-28", "sentiment": {}, "guidance": {
    "market_view": [],
    "assertions": ["上证指数今日收涨", "两市成交额维持1.5万亿以上", "AI算力方向资金延续净流入"],
    "stock_tips": {"603893": {"name": "瑞芯微", "score": -55, "advice": "🔴 短线偏空，建议减仓或离场",
                              "price": 206.3, "change_pct": -1.0}}},
    "thesis_checks": {}, "info_digest": {}, "extreme": {}}
with open(os.path.join(rh.HISTORY_DIR, "20261028.json"), "w", encoding="utf-8") as f:
    json.dump(prev, f, ensure_ascii=False)

r_v = dict(result)
vg.verify_previous(r_v, verbose=False)
v = r_v["verification"]
check("验证读昨日3断言", v and len(v["rows"]) == 3, str(v and len(v["rows"])))
check("hit/miss判定回写", v["rows"][0]["verdict"] == "hit" and v["rows"][1]["verdict"] == "miss")
check("越界序号未混入", all(r["text"] in prev["guidance"]["assertions"] for r in v["rows"]))
check("actual截断回写", v["rows"][0]["actual"] == "上证收涨0.8%")
check("提示验证1条(不存在票忽略)", len(v["tip_rows"]) == 1 and v["tip_rows"][0]["code"] == "603893"
      and v["tip_rows"][0]["verdict"] == "hit")
check("prev_date记录", v["prev_date"] == "2026-10-28")
hr = v["hit_rate"]
# 今日: 断言hit+miss+unclear(i=3漏判) + 提示hit → 计数的hit2/miss1/unclear不计 → 2/3=67%
check("命中率统计(今日2hit/1miss,unclear不计)", hr["d5"]["hit"] == 2 and hr["d5"]["total"] == 3
      and hr["d5"]["pct"] == 67, str(hr))

# 缓存命中
calls["n"] = 0
r_v2 = dict(result)
vg.verify_previous(r_v2, verbose=False)
check("验证缓存命中0次LLM", calls["n"] == 0 and r_v2["verification"]["rows"][0]["verdict"] == "hit")

# unclear兜底(mock返回缺i=3)
check("LLM漏判条目按unclear兜底", v["rows"][2]["verdict"] == "unclear")

# 验证LLM失败→降级None
li._call_llm_json = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))
r_v3 = dict(result, date="20261030")
vg.verify_previous(r_v3, verbose=False)
check("验证LLM失败降级None", r_v3["verification"] is None)
li._call_llm_json = mock_llm_json

# ── 4. 命中率滚动统计(历史verification) ──
for d, hit, miss in [("20261022", 3, 1), ("20261023", 2, 2), ("20261024", 4, 0)]:
    rec = {"date": d[:4]+"-"+d[4:6]+"-"+d[6:], "sentiment": {}, "guidance": {"assertions": ["x"], "stock_tips": {}},
           "verification": {"prev_date": "?",
                            "rows": [{"text": "a", "verdict": "hit", "actual": ""}] * hit +
                                    [{"text": "b", "verdict": "miss", "actual": ""}] * miss +
                                    [{"text": "c", "verdict": "unclear", "actual": ""}],
                            "tip_rows": []},
           "thesis_checks": {}, "info_digest": {}, "extreme": {}}
    with open(os.path.join(rh.HISTORY_DIR, d + ".json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)
hr = vg._hit_rates("20261029", v)
# 历史3日: (3+2+4)hit/(4+4+4)total=9/12, 加今日2/3 → 11/15=73%
check("滚动命中率含历史(11/15=73%)", hr["d20"]["hit"] == 11 and hr["d20"]["total"] == 15
      and hr["d20"]["pct"] == 73, str(hr["d20"]))

# ── 5. 落盘接线 ──
r_save = dict(result)
r_save["verification"] = v
path = rh.save_from_result(r_save)
saved = json.load(open(path, encoding="utf-8"))
check("assertions落盘", saved["guidance"]["assertions"] == result["assertions_today"])
check("verification落盘", saved["verification"]["rows"][0]["verdict"] == "hit")
# 同日重跑(无S5结果)不覆盖已有
r_resave = {"date": "20261029", "indices": result["indices"], "breadth": result["breadth"],
            "macro": result["macro"], "portfolio": []}
rh.save_from_result(r_resave)
saved2 = json.load(open(path, encoding="utf-8"))
check("重跑保留旧assertions/verification", saved2["guidance"]["assertions"] == result["assertions_today"]
      and saved2["verification"]["rows"][0]["verdict"] == "hit")

# ── 6. 模板渲染 ──
from core.html_renderer import render
data = {"fetch_time": "2026-10-29 18:30", "date": "20261029",
        "indices": [{"name": "上证指数", "code": "sh000001", "price": 3651.43, "change_pct": -0.82,
                     "amount": 6.5e11,
                     "technical_indicators": {"short_term": {"score": -15, "advice": "🔴 短线偏空，注意控制仓位"},
                                              "kdj": {}, "rsi": {}, "macd": {}, "ma": {}, "vol_price": {}, "levels": {}}}],
        "macro": {"total_market_amount": 15565.17}, "breadth": result["breadth"],
        "portfolio": [], "watchlist": [], "concepts_fund": [], "concepts_change": [],
        "verification": v, "assertions_today": result["assertions_today"]}
html_path = os.path.join(tmpdir, "s5_preview.html")
html = render(data, "review_report", output_dir=tmpdir, filename="s5_preview.html")
html_txt = open(html if isinstance(html, str) and os.path.exists(html) else html_path, encoding="utf-8").read()
check("验证板块渲染", "昨日研判验证" in html_txt and "2026-10-28" in html_txt)
check("断言逐条渲染", html_txt.count("vf-row") >= 4 and "上证收涨0.8%" in html_txt)
check("命中率渲染", "近5日命中率" in html_txt and "67%" in html_txt)
check("今日断言盒渲染", "今日断言（明日验证）" in html_txt and "AI算力方向资金延续净流入" in html_txt)
check("无verification整块不渲染", "昨日研判验证" not in render(dict(data, verification=None), "review_report", output_dir=tmpdir, filename="s5_none.html"))

# 无命中率数据(total=0)显示—
v0 = {"prev_date": "2026-10-28", "rows": [{"text": "a", "verdict": "unclear", "actual": ""}], "tip_rows": [],
      "hit_rate": {"d5": {"hit": 0, "total": 0, "pct": None}, "d20": {"hit": 0, "total": 0, "pct": None}}}
h0 = render(dict(data, verification=v0), "review_report", output_dir=tmpdir, filename="s5_zero.html")
h0_txt = open(h0 if os.path.exists(str(h0)) else os.path.join(tmpdir, "s5_zero.html"), encoding="utf-8").read()
check("命中率无数据渲染—", "近5日命中率: <b>—" in h0_txt.replace("</b>", "</b>"))

vg.CACHE_DIR, rh.HISTORY_DIR = old_cache, old_hist
import shutil; shutil.rmtree(tmpdir, ignore_errors=True)
print(("\n🎉 全部通过 " if not failures else f"\n💥 失败{len(failures)}项: {failures}"))
sys.exit(1 if failures else 0)
