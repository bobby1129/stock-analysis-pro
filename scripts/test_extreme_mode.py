# -*- coding: utf-8 -*-
"""S6 自测: 极端行情触发判断 + 归因/结构/历史对照/持仓应对(mock LLM+RSS+K线) + 落盘 + 模板渲染。
缓存/历史写入临时目录, 不污染真实cache。"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis import llm_interpret as li
from analysis import review_history as rh
from analysis import extreme_mode as em

failures = []
def check(name, cond, detail=""):
    print(("✅" if cond else "❌") + f" {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(name)

tmpdir = tempfile.mkdtemp(prefix="s6_test_")
old_cache, old_hist = em.CACHE_DIR, rh.HISTORY_DIR
em.CACHE_DIR = tmpdir
rh.HISTORY_DIR = os.path.join(tmpdir, "hist")
os.makedirs(rh.HISTORY_DIR)

# ── mock 网络层 ──
em._rss_titles = lambda q, limit=6: [f"{q}相关新闻标题A", f"{q}相关新闻标题B"]

llm_calls = {"n": 0}
def mock_llm_json(prompt, max_tokens=3500, attempts=3):
    llm_calls["n"] += 1
    if "今天市场为什么" in prompt:
        return {"why": "外围市场大跌叠加获利盘回吐，市场普跌缩量，题材股杀跌明显。"}
    if "持仓应对" in prompt or "per_stock" in prompt:
        return {"overall": "极端杀跌不追杀，仓位重的利用反抽降低题材敞口。",
                "per_stock": {"603893": "逻辑未破坏，急跌不割，观察3800支撑。",
                              "999999": "不存在的票应被过滤"}}
    return {}
li._call_llm_json = mock_llm_json

# mock K线(日K兜底): 500根, 构造两根相似大跌日
import random
random.seed(42)
kl = []
close = 3500.0
for i in range(400):
    close *= (1 + random.uniform(-0.012, 0.012))
    kl.append([f"2025-{(i//30)%12+1:02d}-{i%28+1:02d}", close*0.999, close, close*1.005, close*0.995, 1e8])
# 插入两根大跌日(-2.4%, -2.1%), 其后有反弹
for pos, drop in ((200, -0.024), (300, -0.021)):
    c0 = kl[pos][2]
    c1 = c0 * (1 + drop)
    kl[pos][2] = c1
    kl[pos][1] = c0 * 0.995
    for j in range(pos+1, min(pos+6, len(kl))):
        kl[j][2] = kl[j][2]
    # 后一日反弹1%
    kl[pos+1][2] = c1 * 1.01
import plans.daily_report as dr
dr._fetch_index_kline = lambda code, days=60: [k for k in kl]

# ── 1. 触发判断(纯规则) ──
# 10-29 真实大跌日数据 → 应触发多条
r_crash = {"date": "20261029",
           "indices": [{"name": "上证指数", "code": "sh000001", "price": 3651.4, "change_pct": -0.82},
                       {"name": "创业板指", "code": "sz399006", "price": 2517.6, "change_pct": -4.45}],
           "breadth": {"up": 781, "down": 4727, "limit_up": 39, "limit_down": 41, "max_lianban": 4},
           "macro": {"total_market_amount": 15565.17}}
tr = em.check_triggers(r_crash)
check("大跌日触发(创业板-4.45%+上涨家数781+跌停41)", len(tr) == 3, str(tr))
check("触发文案含数字", any("781" in t for t in tr) and any("-4.45" in t for t in tr))

# 平静日 → 不触发
r_calm = {"date": "20261028",
          "indices": [{"name": "上证指数", "code": "sh000001", "price": 3680.0, "change_pct": 0.3},
                      {"name": "创业板指", "code": "sz399006", "price": 2630.0, "change_pct": 0.5}],
          "breadth": {"up": 2800, "down": 2400, "limit_up": 45, "limit_down": 3},
          "macro": {"total_market_amount": 16000}}
check("平静日不触发", em.check_triggers(r_calm) == [])

# 大涨日: 涨停>150 + 上涨家数>4000 + 上证+2.5%
r_boom = {"date": "20261027",
          "indices": [{"name": "上证指数", "code": "sh000001", "price": 3700.0, "change_pct": 2.5}],
          "breadth": {"up": 4300, "down": 800, "limit_up": 160, "limit_down": 1},
          "macro": {"total_market_amount": 16000}}
tr2 = em.check_triggers(r_boom)
check("大涨日触发3条(上证+2.5/家数4300/涨停160)", len(tr2) == 3, str(tr2))

# 边界: 恰好±2%不触发(≥才触发→2.0触发)
r_edge = {"date": "20261026", "indices": [{"name": "上证指数", "code": "sh000001", "change_pct": -1.99}],
          "breadth": {"up": 1000, "down": 4000, "limit_up": 30, "limit_down": 30}, "macro": {}}
check("边界1.99%/家数1000/跌停30不触发", em.check_triggers(r_edge) == [])
r_edge2 = {"date": "20261025", "indices": [{"name": "上证指数", "code": "sh000001", "change_pct": -2.0}],
           "breadth": {"up": 999, "down": 4000, "limit_up": 30, "limit_down": 31}, "macro": {}}
check("边界-2.0%/999家/跌停31触发3条", len(em.check_triggers(r_edge2)) == 3)

# 数据缺失不误报
check("空数据不触发", em.check_triggers({"date": "20261024", "indices": [], "breadth": {}, "macro": {}}) == [])

# ── 2. attach_extreme 全链路(mock) ──
r_crash["portfolio"] = [{"code": "603893", "name": "瑞芯微", "change_pct": -7.86,
                         "thesis": "逻辑: AIoT SoC龙头…\n假设: …\n失效: …"}]
r_crash["concepts_change"] = [{"name": "AI算力", "change_pct": 1.2, "net": 5.0},
                              {"name": "华为链", "change_pct": 0.8, "net": 3.0}]
r_crash["concepts_decline"] = [{"name": "锂电池", "change_pct": -5.1, "net": -20.0}]
em.attach_extreme(r_crash, verbose=False)
ex = r_crash["extreme"]
check("触发标记+3条triggers", ex["triggered"] and len(ex["triggers"]) == 3)
a = ex["analysis"]
check("归因why生成", a.get("why") and "外围" in a["why"])
check("归因新闻挂载", len(a.get("news", [])) > 0)
st = a["structure"]
check("结构拆解: 涨跌停/分化/领跌", st["limit_down"] == 41 and st["top_losers"][0]["name"] == "锂电池")
check("结构拆解: 权重题材分化判定", st["divergence"] and "弱于权重" in st["divergence"])
hh = a["holdings_hint"]
check("持仓应对: overall+per_stock(过滤非持仓码)", hh and "603893" in str(hh["per_stock"]) and "999999" not in str(hh["per_stock"]))
check("持仓应对: 名称映射", "瑞芯微" in str(hh["per_stock"]))
check("持仓应对: 免责声明", hh["disclaimer"])

# 历史对照: 情绪库空 → 日K兜底
hist = a.get("history")
check("历史对照走日K兜底", hist and hist.get("source") == "kline", str(hist)[:100] if hist else "None")
if hist and hist.get("source") == "kline":
    check("日K兜底统计字段齐全", all(k in hist["stat"] for k in ("n", "next1_avg", "next5_avg")) and hist["stat"]["n"] >= 2,
          json.dumps(hist["stat"], ensure_ascii=False))

# 缓存命中: 重跑0次LLM
llm_calls["n"] = 0
em.attach_extreme(r_crash, verbose=False)
check("极端模式缓存命中(0次LLM)", llm_calls["n"] == 0)

# 平静日: 只挂占位, 不调LLM
llm_calls["n"] = 0
r_calm["portfolio"] = []
em.attach_extreme(r_calm, verbose=False)
check("平静日占位不触发", r_calm["extreme"] == {"triggered": False, "triggers": [], "analysis": None} and llm_calls["n"] == 0)

# LLM宕机 → why/hint降级None, structure/history仍在
li._call_llm_json = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))
r_boom["portfolio"] = [{"code": "000001", "name": "平安银行", "change_pct": 3.0, "thesis": ""}]
r_boom["concepts_change"] = []
r_boom["concepts_decline"] = []
em.attach_extreme(r_boom, verbose=False)
ab = r_boom["extreme"]["analysis"]
check("LLM宕机: why/hint降级None", r_boom["extreme"]["triggered"] and ab.get("why") is None and ab.get("holdings_hint") is None)
check("LLM宕机: structure仍在", ab.get("structure"))
li._call_llm_json = mock_llm_json

# RSS宕机(mock抛异常已由_rss_titles容错; 再测整体_rss_titles抛)
em._rss_titles = lambda q, limit=6: (_ for _ in ()).throw(RuntimeError("rss down"))
r_rss = json.loads(json.dumps({k: v for k, v in r_crash.items() if k != "extreme"}))
r_rss["date"] = "20261023"
em.attach_extreme(r_rss, verbose=False)
# RSS异常被_rss_titles内部try捕获? 我们mock直接抛 → _why中for循环会炸 → attach_extreme捕获归因降级
ar = r_rss["extreme"]["analysis"]
check("RSS宕机: 归因降级但结构/历史仍在", ar.get("structure") and "why" not in ar or ar.get("why") is None)
em._rss_titles = lambda q, limit=6: [f"{q}相关新闻标题A", f"{q}相关新闻标题B"]

# ── 3. 情绪库历史对照(mock历史文件) ──
def _mk_day(yyyymmdd, up, sh_pct, amount=15000.0):
    rec = {"date": f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}",
           "sentiment": {"up_count": up, "total_amount": amount,
                         "amount_vs_ma20": None,
                         "indices": {"sh000001": {"close": 3500 + sh_pct * 10, "pct": sh_pct}}},
           "guidance": {"assertions": [], "stock_tips": {}}}
    with open(os.path.join(rh.HISTORY_DIR, f"{yyyymmdd}.json"), "w") as f:
        json.dump(rec, f, ensure_ascii=False)
# 7个相似日(up~700-900), 之后各有次日数据
for i, d in enumerate(("20260901", "20260903", "20260904", "20260908", "20260909", "20260910", "20260911")):
    _mk_day(d, 700 + i * 30, -1.5 + i * 0.3)
r_lib = json.loads(json.dumps({k: v for k, v in r_crash.items() if k != "extreme"}))
r_lib["date"] = "20261029"
lib_hist = em._history("20261029", r_lib, verbose=False)
check("情绪库相似日≥2走library", lib_hist and lib_hist["source"] == "library" and len(lib_hist["days"]) >= 2,
      str(lib_hist)[:150] if lib_hist else "None")
if lib_hist and lib_hist["source"] == "library":
    check("library含次1日表现", any(d["next1"] is not None for d in lib_hist["days"]))

# ── 4. 落盘接线 ──
r_crash2 = json.loads(json.dumps({k: v for k, v in r_crash.items()}))
rh.save_from_result({"date": "20261029", "indices": r_crash["indices"], "breadth": r_crash["breadth"],
                     "macro": r_crash["macro"], "portfolio": [], "extreme": r_crash["extreme"]})
saved = rh.load("20261029")
check("落盘extreme.triggered=True", saved["extreme"]["triggered"] is True)
check("落盘extreme含triggers/analysis", len(saved["extreme"]["triggers"]) == 3 and saved["extreme"]["analysis"]["why"])
# 未触发重跑不覆盖已触发记录(rh原有保留逻辑)
rh.save_from_result({"date": "20261029", "indices": [], "breadth": {}, "macro": {}, "portfolio": []})
saved2 = rh.load("20261029")
check("重跑不覆盖已触发extreme", saved2["extreme"]["triggered"] is True)

# ── 5. 模板渲染 ──
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")))
tpl = env.get_template("review_report.html")
# 最小data: 触发场景
data_full = {"fetch_time": "2026-10-29 15:30", "date": "20261029",
             "indices": r_crash["indices"], "macro": r_crash["macro"], "breadth": r_crash["breadth"],
             "portfolio": [], "watchlist": [], "concepts_fund": [], "concepts_change": [],
             "extreme": r_crash["extreme"]}
html = tpl.render(data=data_full)
check("模板: 专区标题+徽章", "🌪 极端行情模式" in html and "extreme-badge" in html and "781" in html)
check("模板: 归因+新闻", "今天为什么" in html and "外围" in html and "相关新闻标题A" in html)
check("模板: 结构拆解", "结构拆解" in html and "锂电池" in html and "弱于权重" in html)
check("模板: 历史对照(日K统计表)", "历史对照" in html and "ex-hist-table" in html and "次日平均" in html)
check("模板: 持仓应对+免责", "持仓应对" in html and "瑞芯微" in html and "不构成投资决策" in html)
check("模板: 现有元素保留(市场情绪)", "市场情绪" in html)
# library表格分支
ex_lib = json.loads(json.dumps(r_crash["extreme"]))
ex_lib["analysis"]["history"] = lib_hist
data_lib = dict(data_full, extreme=ex_lib)
html_lib = tpl.render(data=data_lib)
check("模板: library分支渲染", "情绪库相似日" in html_lib and "2026-09-01" in html_lib)
# 未触发 → 整块不渲染
data_none = dict(data_full, extreme={"triggered": False, "triggers": [], "analysis": None})
html_none = tpl.render(data=data_none)
check("模板: 未触发不渲染专区", "极端行情模式" not in html_none)
# extreme缺失(旧数据兼容)
data_old = {k: v for k, v in data_full.items() if k != "extreme"}
html_old = tpl.render(data=data_old)
check("模板: extreme缺失兼容", "极端行情模式" not in html_old and len(html_old) > 1000)
# why/history/hint缺失降级渲染
ex_min = {"triggered": True, "triggers": ["跌停 41家 > 30"],
          "analysis": {"structure": {"limit_up": 39, "limit_down": 41, "up": 781, "down": 4727}}}
html_min = tpl.render(data=dict(data_full, extreme=ex_min))
check("模板: 仅structure也能渲染", "极端行情模式" in html_min and "今天为什么" not in html_min)

# 恢复
em.CACHE_DIR, rh.HISTORY_DIR = old_cache, old_hist
import shutil; shutil.rmtree(tmpdir)
print()
if failures:
    print(f"❌ {len(failures)}项失败: {failures}")
    sys.exit(1)
print("🎉 全部通过")
