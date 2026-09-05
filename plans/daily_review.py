# -*- coding: utf-8 -*-
"""宏观市场概览计划 — 国际环境 → 国内经济 → 事件驱动 → 综合研判"""

import sys
import os
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.macro import global_macro, domestic_macro, zt_pool
from analysis.macro import analyze_global, analyze_domestic, analyze_event, synthesize
from collectors.economic_calendar import load_economic_calendar


def run(date=None, verbose=True):
    """执行宏观市场概览

    Args:
        date: YYYYMMDD, 默认今天
        verbose: 是否打印进度

    Returns:
        dict: 完整宏观分析报告
    """
    result = {"date": date or datetime.now().strftime("%Y%m%d"), "timestamp": datetime.now().isoformat()}

    # 1. 国际宏观
    if verbose:
        print("📡 采集国际宏观数据...", file=sys.stderr)
    raw_global = global_macro()
    result["global_raw"] = raw_global
    result["global"] = analyze_global(raw_global)

    # 2. 国内宏观
    if verbose:
        print("📡 采集国内宏观数据...", file=sys.stderr)
    time.sleep(0.5)
    raw_domestic = domestic_macro()
    result["domestic_raw"] = raw_domestic
    result["domestic"] = analyze_domestic(raw_domestic)

    # 3. 事件驱动 (涨停复盘)
    if verbose:
        print("📡 采集涨停复盘数据...", file=sys.stderr)
    time.sleep(0.5)
    raw_event = zt_pool(date=date)
    result["event_raw"] = raw_event
    result["event"] = analyze_event(raw_event)

    # 4. 经济日历
    if verbose:
        print("📅 加载经济日历...", file=sys.stderr)
    result["economic_calendar"] = load_economic_calendar(days_ahead=14)

    # 5. 综合研判
    result["synthesize"] = synthesize(result["global"], result["domestic"], result["event"])

    if verbose:
        print("✅ 宏观市场概览完成", file=sys.stderr)

    return result


def format_report(data: dict) -> str:
    """格式化宏观报告为文本"""
    lines = []
    sep = "=" * 50

    lines.append(sep)
    lines.append(f"  📊 宏观市场概览 — {data.get('date', '')}")
    lines.append(sep)

    # ── 综合研判 ──
    syn = data.get("synthesize", {})
    lines.append(f"\n【综合研判】{syn.get('outlook', 'N/A')} (得分: {syn.get('score', 0):+d})")
    lines.append(f"  操作建议: {syn.get('action', '')}")

    sigs = syn.get("signals", [])
    warns = syn.get("warnings", [])
    if sigs:
        lines.append(f"  ✅ {' | '.join(sigs[:8])}")
    if warns:
        lines.append(f"  ⚠️ {' | '.join(warns[:8])}")

    # ── 国际环境 ──
    g = data.get("global", {})
    lines.append(f"\n【国际环境】{g.get('environment', 'N/A')}")

    us_10y = g.get("us_10y_yield", {})
    if us_10y.get("value") is not None:
        lines.append(f"  美债10Y: {us_10y['value']}% ({us_10y.get('date', '')})")

    fed = g.get("fed_rate", {})
    if fed.get("value") is not None:
        lines.append(f"  美联储利率: {fed['value']}%")

    for c in g.get("commodities", []):
        pct_str = f"{c['change_pct']:+.2f}%" if c.get("change_pct") is not None else ""
        lines.append(f"  {c['name']}: {c['price']} {pct_str}")

    g_sigs = g.get("signals", [])
    g_warns = g.get("warnings", [])
    if g_sigs:
        for s in g_sigs[:3]:
            lines.append(f"  ✅ {s}")
    if g_warns:
        for w in g_warns[:3]:
            lines.append(f"  ⚠️ {w}")

    # ── 国内经济 ──
    d = data.get("domestic", {})
    lines.append(f"\n【国内经济】周期: {d.get('cycle', 'N/A')} | 流动性: {d.get('liquidity', 'N/A')}")

    cpi = d.get("cpi", {})
    if cpi.get("value") is not None:
        lines.append(f"  CPI: {cpi['value']} ({cpi.get('date', '')})")

    pmi = d.get("pmi_manufacturing", {})
    if pmi.get("value") is not None:
        lines.append(f"  制造业PMI: {pmi['value']} ({pmi.get('date', '')})")

    pmi_nm = d.get("pmi_non_manufacturing", {})
    if pmi_nm.get("value") is not None:
        lines.append(f"  非制造业PMI: {pmi_nm['value']}")

    m2 = d.get("m2_yoy", {})
    if m2.get("value") is not None:
        lines.append(f"  M2同比: {m2['value']}%")

    lpr = d.get("lpr", {})
    if lpr.get("1y"):
        lines.append(f"  LPR: 1Y={lpr['1y']}%, 5Y={lpr['5y']}% ({lpr.get('date', '')})")

    d_sigs = d.get("signals", [])
    d_warns = d.get("warnings", [])
    if d_sigs:
        for s in d_sigs[:4]:
            lines.append(f"  ✅ {s}")
    if d_warns:
        for w in d_warns[:4]:
            lines.append(f"  ⚠️ {w}")

    # ── 事件驱动 (涨停复盘) ──
    e = data.get("event", {})
    lines.append(f"\n【事件驱动】情绪: {e.get('sentiment', 'N/A')} | 涨停: {e.get('zt_count', 0)}只")

    mh = e.get("max_height", 0)
    mhs = e.get("max_height_stocks", [])
    if mh > 0:
        lines.append(f"  最高连板: {mh}板 ({', '.join(mhs)})")

    dist = e.get("height_distribution", {})
    if dist:
        dist_str = " ".join(f"{h}板×{c}" for h, c in sorted(dist.items(), reverse=True))
        lines.append(f"  连板分布: {dist_str}")

    sectors = e.get("hot_sectors", {})
    if sectors:
        sector_str = ", ".join(f"{s}({c})" for s, c in list(sectors.items())[:5])
        lines.append(f"  热门方向: {sector_str}")

    cont = e.get("continuation", {})
    if cont:
        lines.append(f"  昨日涨停今日: 均涨{cont.get('avg_pct', 0):.1f}%, 上涨占比{cont.get('up_ratio', 0):.0f}% ({cont.get('count', 0)}只)")

    strong = e.get("strong_count", 0)
    if strong:
        lines.append(f"  强势涨停: {strong}只")

    e_sigs = e.get("signals", [])
    e_warns = e.get("warnings", [])
    if e_sigs:
        for s in e_sigs[:4]:
            lines.append(f"  ✅ {s}")
    if e_warns:
        for w in e_warns[:4]:
            lines.append(f"  ⚠️ {w}")

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="宏观市场概览")
    parser.add_argument("--date", help="日期 YYYYMMDD, 默认今天")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    args = parser.parse_args()

    data = run(date=args.date)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(format_report(data))
