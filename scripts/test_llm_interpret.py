# -*- coding: utf-8 -*-
"""S4 自测: LLM解读流水线(mock LLM逻辑测试) + 模板渲染验证。
mock缓存/历史写入临时目录, 不污染真实cache。真实LLM冒烟单测见 test_s4_live.py。"""
import os, sys, json, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis import llm_interpret as li
from analysis import review_history as rh

failures = []
def check(name, cond, detail=""):
    print(("✅" if cond else "❌") + f" {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(name)

THESIS = ("逻辑: 测试逻辑。\n假设: ①测试假设A ②测试假设B\n"
          "失效: 测试失效条件X; 测试失效条件Y。")

def mk_stock(code, name, ann=None, rep=None, news=None, thesis=THESIS):
    s = {"code": code, "name": name, "thesis": thesis,
         "announcements": ann or [], "research_reports": rep or [], "news": news or []}
    return s

# ── 1. 正文抓取(真实网络, 无LLM) ──
txt = li.fetch_announcement_text("AN202610261830950116")   # 瑞芯微三季报(已验证art_code)
check("公告PDF正文抓取", txt and len(txt) > 500 and "第三季度" in txt, f"{len(txt or '')}字")
check("art_code为None返回None", li.fetch_announcement_text(None) is None)
check("坏art_code返回None不抛", li.fetch_announcement_text("AN_BROKEN_XX") is None)
ntxt = li.fetch_news_text("https://nonexistent.invalid/x.html")
check("坏新闻url返回None不抛", ntxt is None)

# ── 2. mock LLM: 两段式流水线逻辑 ──
tmpdir = tempfile.mkdtemp(prefix="s4_test_")
old_cache, old_hist = li.CACHE_DIR, rh.HISTORY_DIR
li.CACHE_DIR = tmpdir
rh.HISTORY_DIR = os.path.join(tmpdir, "hist")
os.makedirs(rh.HISTORY_DIR)

calls = {"n": 0}
def mock_llm_json(prompt, max_tokens=3500, attempts=3):
    calls["n"] += 1
    if "初筛分级" in prompt or "做初筛分级" in prompt or "分级标准" in prompt:
        # 初筛: 条目1=major需正文, 条目2=noise, 条目3=neutral
        return [{"i": 1, "level": "major", "need_content": True},
                {"i": 2, "level": "noise", "need_content": False},
                {"i": 3, "level": "neutral", "need_content": False}]
    # 判定
    return {"verdict": "weakened", "reason": "测试弱化依据",
            "evidence": ["测试公告标题"],
            "interps": [{"i": 1, "interp": "测试解读一句话", "impact": "利空"}]}

stock = mk_stock("603893", "瑞芯微",
                 ann=[{"title": "测试公告标题", "date": "2026-10-29", "art_code": None},
                      {"title": "关于召开董事会的通知", "date": "2026-10-29", "art_code": None}],
                 news=[{"title": "测试新闻标题", "date": "2026-10-29", "url": None, "media": "测试"}])
result = {"date": "20261029", "portfolio": [stock]}
li._call_llm_json = mock_llm_json
li._fetch_contents = lambda items, levels, verbose=False: {}   # 正文抓取已在1单独验证
li.attach_interpretations(result, verbose=False)

tc = result["thesis_checks"]["603893"]
check("判定verdict回写", tc["verdict"] == "weakened", str(tc))
check("条目level回写(公告1=major)", stock["announcements"][0]["level"] == "major")
check("条目level回写(公告2=noise)", stock["announcements"][1]["level"] == "noise")
check("major条目interp+impact回写",
      stock["announcements"][0].get("interp") == "测试解读一句话"
      and stock["announcements"][0].get("impact") == "利空")
check("info_digest只收major", len(result["info_digest"]["603893"]) == 1
      and result["info_digest"]["603893"][0]["impact"] == "利空")
check("LLM调用2次(初筛+判定)", calls["n"] == 2, f"n={calls['n']}")

# 缓存命中: 同输入重跑不调LLM
calls["n"] = 0
stock2 = mk_stock("603893", "瑞芯微",
                  ann=[{"title": "测试公告标题", "date": "2026-10-29", "art_code": None},
                       {"title": "关于召开董事会的通知", "date": "2026-10-29", "art_code": None}],
                  news=[{"title": "测试新闻标题", "date": "2026-10-29", "url": None, "media": "测试"}])
result2 = {"date": "20261029", "portfolio": [stock2]}
li.attach_interpretations(result2, verbose=False)
check("缓存命中0次LLM", calls["n"] == 0, f"n={calls['n']}")
check("缓存verdict一致", result2["thesis_checks"]["603893"]["verdict"] == "weakened")

# 输入变化→缓存失效重调
calls["n"] = 0
stock3 = mk_stock("603893", "瑞芯微",
                  ann=[{"title": "测试公告标题", "date": "2026-10-29", "art_code": None},
                       {"title": "新增大订单公告", "date": "2026-10-30", "art_code": None}],
                  news=[])
result3 = {"date": "20261029", "portfolio": [stock3]}
li.attach_interpretations(result3, verbose=False)
check("输入变化重调LLM", calls["n"] == 2, f"n={calls['n']}")

# 无thesis票跳过
stock4 = {"code": "000001", "name": "平安银行", "thesis": "",
          "announcements": [{"title": "x", "date": "2026-10-29"}],
          "research_reports": [], "news": []}
result4 = {"date": "20261029", "portfolio": [stock4]}
calls["n"] = 0
li.attach_interpretations(result4, verbose=False)
check("无thesis跳过不调LLM", calls["n"] == 0 and stock4.get("thesis_missing") is True)

# 无信息条目→unchanged不调LLM
stock5 = mk_stock("002709", "天赐材料", ann=[], rep=[], news=[])
result5 = {"date": "20261029", "portfolio": [stock5]}
calls["n"] = 0
li.attach_interpretations(result5, verbose=False)
check("无条目直接unchanged", calls["n"] == 0
      and result5["thesis_checks"]["002709"]["verdict"] == "unchanged")

# LLM抛异常→降级不崩
def boom(prompt, max_tokens=3500, attempts=3):
    raise RuntimeError("mock LLM down")
stock6 = mk_stock("600183", "生益科技",
                  ann=[{"title": "测试", "date": "2026-10-29", "art_code": None}])
result6 = {"date": "20261029", "portfolio": [stock6]}
li._call_llm_json = boom
li.attach_interpretations(result6, verbose=False)
check("LLM失败降级不崩", result6.get("llm_interpret_degraded") is True
      and "600183" not in result6["thesis_checks"])

# verdict历史注入(mock_llm恢复, 写入昨日weakened历史, 检查prompt包含历史)
li._call_llm_json = mock_llm_json
yest = {"date": "2026-10-28", "sentiment": {}, "guidance": {},
        "thesis_checks": {"603893": {"verdict": "weakened", "reason": "昨日已弱化"}},
        "info_digest": {}, "extreme": {}}
with open(os.path.join(rh.HISTORY_DIR, "20261028.json"), "w", encoding="utf-8") as f:
    json.dump(yest, f, ensure_ascii=False)
h = li._verdict_history("603893", "20261029")
check("verdict历史读取", len(h) == 1 and "昨日已弱化" in h[0], str(h))
h5 = None
prompts_seen = []
def spy_llm(prompt, max_tokens=3500, attempts=3):
    prompts_seen.append(prompt)
    return mock_llm_json(prompt)
li._call_llm_json = spy_llm
stock7 = mk_stock("603893", "瑞芯微",
                  ann=[{"title": "另一条测试公告", "date": "2026-10-29", "art_code": None}])
result7 = {"date": "20261029", "portfolio": [stock7]}
li.attach_interpretations(result7, verbose=False)
check("判定prompt注入历史", any("昨日已弱化" in p for p in prompts_seen))

# ── 3. 模板渲染(mock数据) ──
from core.html_renderer import render
data = {
    "fetch_time": "2026-10-29 18:30", "date": "20261029",
    "indices": [{"name": "上证指数", "code": "sh000001", "price": 3651.43,
                 "change_pct": -0.82, "amount": 6.5e11}],
    "macro": {"total_market_amount": 15565.17, "us_treasury_10y": 4.1,
              "fed_rate": 4.0, "usd_cny": 7.1},
    "breadth": {"up": 781, "down": 4727, "flat": 68, "limit_up": 39, "limit_down": 41},
    "portfolio": [
        {"code": "603893", "name": "瑞芯微", "note": "AIoT SoC", "price": 175.0,
         "change_pct": -3.2, "pe": 45.0, "pb": 8.0, "total_mv": 700.0,
         "volume": 3e7, "amount": 5e9, "amplitude": 4.0, "volume_ratio": 1.1,
         "chg_5d": -5.0, "chg_20d": -12.0,
         "thesis": THESIS,
         "thesis_check": {"verdict": "weakened", "reason": "测试弱化依据",
                          "evidence": ["测试公告标题"]},
         "announcements": [{"title": "测试公告标题", "date": "2026-10-29",
                            "level": "major", "interp": "测试解读一句话", "impact": "利空"},
                           {"title": "召开董事会通知", "date": "2026-10-29", "level": "noise"}],
         "research_reports": [], "news": []},
        {"code": "002709", "name": "天赐材料", "note": "电解液", "price": 40.0,
         "change_pct": 1.2, "pe": 10.0, "pb": 2.0, "total_mv": 800.0,
         "volume": 5e7, "amount": 2e9, "amplitude": 3.0, "volume_ratio": 0.9,
         "chg_5d": 2.0, "chg_20d": 8.0,
         "thesis": THESIS,
         "thesis_check": {"verdict": "unchanged", "reason": "今日无重大信息", "evidence": []},
         "announcements": [], "research_reports": [], "news": []},
    ],
    "watchlist": [], "concepts_fund": [], "concepts_change": [],
    "thesis_checks": {
        "603893": {"name": "瑞芯微", "verdict": "weakened", "reason": "测试弱化依据",
                   "evidence": ["测试公告标题"]},
        "002709": {"name": "天赐材料", "verdict": "unchanged", "reason": "今日无重大信息",
                   "evidence": []},
    },
    "info_digest": {},
    "thesis_history": {"603893": [{"date": "2026-10-28", "verdict": "weakened",
                                   "reason": "昨日已弱化"}]},
}
out = render(data, "review_report", output_dir=tmpdir, filename="s4_preview.html")
html = open(out, encoding="utf-8").read()
check("模板: 顶部警示区渲染", "持仓逻辑警示" in html and "🟡 逻辑弱化" in html)
check("模板: 警示区只含weakened票", html.index("瑞芯微") < html.index("天赐材料"))
check("模板: 逻辑状态行徽章", html.count("逻辑状态") == 0 and html.count("thesis-badge") >= 3)
check("模板: major解读+影响标签", "测试解读一句话" in html and "impact-tag 利空" in html)
check("模板: noise条目淡化", 'style="color:#aaa;"' in html)
check("模板: 底部档案折叠+自动open", "持仓逻辑档案" in html and "<details open>" in html)
check("模板: 档案含thesis原文", "测试失效条件X" in html)
check("模板: 近5日判定历史", "近5日判定" in html and "昨日已弱化" in html)
print(f"\n📄 预览文件: {out}")

li.CACHE_DIR, rh.HISTORY_DIR = old_cache, old_hist
print("\n" + ("🎉 全部通过" if not failures else f"❌ 失败: {failures}"))
print(f"TMPDIR={tmpdir}")
sys.exit(1 if failures else 0)
