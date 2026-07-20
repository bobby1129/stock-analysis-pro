# -*- coding: utf-8 -*-
"""分析维度层 — 资金面"""

from collectors.flow import volume_stats, northbound, shareholder_changes


def analyze(symbol: str) -> dict:
    """资金面分析：成交额统计 + 北向持股 + 股东变动"""
    vol = volume_stats(symbol, period=20)
    nb = northbound(symbol)
    sh = shareholder_changes(symbol)
    
    # 生成信号
    signals = []
    warnings = []
    
    # 成交量分析
    if "stats" in vol:
        stats = vol["stats"]
        vr = stats.get("volume_ratio", 1.0)
        if vr > 2.0:
            signals.append(f"显著放量(量比{vr:.1f})")
        elif vr > 1.5:
            signals.append(f"温和放量(量比{vr:.1f})")
        elif vr < 0.5:
            warnings.append(f"极度缩量(量比{vr:.1f})")
    
    # 北向资金分析
    if "summary" in nb:
        summary = nb["summary"]
        ratio = summary.get("ratio", {}).get("current", 0)
        if ratio > 5:
            signals.append(f"北向重仓({ratio:.1f}%)")
        elif ratio > 3:
            signals.append(f"北向关注({ratio:.1f}%)")
        
        trend = nb.get("trend", {})
        up_days = trend.get("up_days_5d", 0)
        if up_days >= 4:
            signals.append(f"北向5日连续增持({up_days}天)")
        elif up_days <= 1:
            warnings.append(f"北向5日偏卖({up_days}天)")
    
    # 股东变动分析
    if sh.get("changes"):
        changes = sh["changes"]
        increase_count = sum(1 for c in changes if c.get("change_type") == "增持")
        decrease_count = sum(1 for c in changes if c.get("change_type") == "减持")
        
        if increase_count > decrease_count:
            signals.append(f"股东增持({increase_count}次)")
        elif decrease_count > increase_count:
            warnings.append(f"股东减持({decrease_count}次)")
    
    return {
        "volume_stats": vol,
        "northbound": nb,
        "shareholder_changes": sh,
        "signals": signals,
        "warnings": warnings,
    }
