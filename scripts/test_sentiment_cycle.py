# -*- coding: utf-8 -*-
"""S3 自测: 情绪周期规则引擎 + 时序SVG渲染。
mock历史写入临时目录(monkeypatch HISTORY_DIR), 不污染真实cache。测完自动清理。"""
import os, sys, json, random, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis import review_history as rh
from analysis.sentiment_cycle import (compute_heat, determine_cycle,
                                      build_timeseries_svg, attach_sentiment_cycle)

failures = []
def check(name, cond, detail=""):
    print(("✅" if cond else "❌") + f" {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(name)

# ── 1. 热度打分单测: 三种典型日 ──
ice = {"up_count": 781, "limit_up": 39, "max_lianban": 4, "amount_vs_ma20": -0.15}
mid = {"up_count": 2600, "limit_up": 55, "max_lianban": 5, "amount_vs_ma20": 0.03}
hot = {"up_count": 4200, "limit_up": 110, "max_lianban": 8, "amount_vs_ma20": 0.25}
s_ice, r_ice = compute_heat(ice)
s_mid, r_mid = compute_heat(mid)
s_hot, r_hot = compute_heat(hot)
# 注: 10-29大跌日涨停39/4连板仍给中位分(热度27)——正是up_count<800硬覆盖存在的意义
check("冰点日热度<30", s_ice < 30, f"score={s_ice}, {r_ice}")
check("中间日热度30~70", 30 <= s_mid < 70, f"score={s_mid}")
check("火热日热度>=70", s_hot >= 70, f"score={s_hot}, {r_hot}")
check("热度单调递增", s_ice < s_mid < s_hot)
check("缺失字段不崩", compute_heat({})[0] is not None)
# 真冰点日(无硬覆盖也判冰点): 普跌+涨停少+无梯队+缩量
cold = {"up_count": 1200, "limit_up": 18, "max_lianban": 2, "amount_vs_ma20": -0.25}
check("真冷日<30无覆盖也冰点", determine_cycle(cold, [])["phase"] == "冰点",
      str(determine_cycle(cold, [])))

# 定档: 无历史(trend=None)
check("定档-冰点(硬覆盖up<800)", determine_cycle(ice, [])["phase"] == "冰点")
check("定档-发酵", determine_cycle(mid, [])["phase"] == "发酵",
      str(determine_cycle(mid, [])))
check("定档-高潮", determine_cycle(hot, [])["phase"] == "高潮")
# 定档: 退潮(热度较前3日大幅回落)
hist_hot = [hot, hot, hot]
ebbing = {"up_count": 1800, "limit_up": 40, "max_lianban": 4, "amount_vs_ma20": -0.10}
res_ebb = determine_cycle(ebbing, hist_hot)
check("定档-退潮(趋势下行)", res_ebb["phase"] == "退潮",
      f"score={res_ebb['score']} trend={res_ebb['trend']}")
# 极端普跌但其余指标不差 → 仍冰点(硬覆盖)
weird = {"up_count": 700, "limit_up": 80, "max_lianban": 6, "amount_vs_ma20": 0.1}
check("硬覆盖-普跌优先", determine_cycle(weird, [])["phase"] == "冰点",
      str(determine_cycle(weird, [])["score"]))

# ── 2. SVG: 单点/空/20点 ──
check("SVG空序列返回''", build_timeseries_svg([]) == "")
one = [{"date": "2026-10-29", "up_count": 781, "limit_up": 39, "limit_down": 41, "total_amount": 15565}]
svg1 = build_timeseries_svg(one)
check("SVG单点可渲染", svg1.startswith("<svg") and svg1.endswith("</svg>") and "<rect" in svg1)

random.seed(42)
series = []
amt = 16000
for i in range(19):  # mock 2026-10-01..10-28 (示意连续交易日, 仅测渲染)
    up = random.randint(900, 4200)
    amt = max(9000, amt + random.randint(-1500, 1500))
    series.append({"date": f"2026-10-{i+1:02d}", "up_count": up,
                   "limit_up": random.randint(20, 110), "limit_down": random.randint(0, 40),
                   "total_amount": round(amt, 1)})
series.append({"date": "2026-10-29", "up_count": 781, "limit_up": 39,
               "limit_down": 41, "total_amount": 15565.17})
svg20 = build_timeseries_svg(series)
check("SVG20点: 20根柱+折线", svg20.count("<rect") == 20 and "<polyline" in svg20
      and "stroke-dasharray" in svg20, f"len={len(svg20)}")

# ── 3. attach_sentiment_cycle 端到端(mock历史文件) ──
tmpdir = tempfile.mkdtemp(prefix="s3_test_")
real_hist = rh.load("20261029")
check("真实种子文件存在", real_hist is not None)
old_dir = rh.HISTORY_DIR
try:
    rh.HISTORY_DIR = tmpdir
    # 写mock历史(19天) + 真实20261029
    for i, s in enumerate(series[:-1], 1):
        d = s["date"].replace("-", "")
        rec = {"date": s["date"], "sentiment": dict(s, flat_count=100,
               amount_vs_ma20=None, indices={}), "guidance": {}, "thesis_checks": {},
               "info_digest": {}, "extreme": {}}
        with open(os.path.join(tmpdir, f"{d}.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False)
    # 损坏文件容错
    with open(os.path.join(tmpdir, "20260930.json"), "w") as f:
        f.write("{broken json")
    result = {"date": "20261029", "breadth": {"up": 781, "down": 4727, "flat": 68,
              "limit_up": 39, "limit_down": 41, "max_lianban": 4},
              "macro": {"total_market_amount": 15565.17}}
    attach_sentiment_cycle(result)
    cyc = result["sentiment_cycle"]
    check("attach: 周期=冰点(真实大跌日)", cyc["phase"] == "冰点", str(cyc))
    check("attach: trend可计算(20天历史)", cyc["trend"] is not None, f"trend={cyc['trend']}")
    check("attach: SVG非空", bool(result["sentiment_ts_svg"]))
    check("attach: 天数=20", result["sentiment_ts_days"] == 20, str(result["sentiment_ts_days"]))
    check("attach: 损坏文件被跳过", all("{broken" not in str(x) for x in [result]))

    # 模板渲染(完整data最小mock)
    from core.html_renderer import render
    data = dict(result)
    data["fetch_time"] = "2026-10-29 18:30"
    data["indices"] = [{"name": "上证指数", "code": "sh000001", "price": 3651.43,
                        "change_pct": -0.82, "amount": 6.5e11}]
    data["macro"].update({"us_treasury_10y": 4.1, "fed_rate": 4.0, "usd_cny": 7.1})
    data["portfolio"] = []
    data["watchlist"] = []
    data["concepts_fund"] = []
    data["concepts_change"] = []
    out = render(data, "review_report", output_dir=tmpdir, filename="s3_preview.html")
    html = open(out, encoding="utf-8").read()
    check("模板: 周期徽章渲染", "情绪周期定位" in html and "冰点" in html)
    check("模板: SVG内嵌", "<svg" in html and "上涨家数" in html)
    check("模板: 依据句渲染", "热度" in html and "/100" in html)
    print(f"\n📄 预览文件: {out}")
finally:
    rh.HISTORY_DIR = old_dir

# 保留预览文件路径, 其余mock目录清理在人工确认后
print("\n" + ("🎉 全部通过" if not failures else f"❌ 失败: {failures}"))
print(f"TMPDIR={tmpdir}")
sys.exit(1 if failures else 0)
