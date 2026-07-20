# -*- coding: utf-8 -*-
"""分析维度层 — 估值面"""

from collectors.quote import realtime
from collectors.finance import indicators


def analyze(symbol: str, basic: dict = None) -> dict:
    """估值分析：PE/PB/市值/换手率/PEG
    
    Args:
        symbol: 股票代码
        basic: 预获取的实时行情数据 (可选, 避免重复请求)
    """
    rt = basic if basic else realtime(symbol)
    
    pe = rt.get("pe", 0)
    pb = rt.get("pb", 0)
    total_mv = rt.get("total_mv", 0)
    circ_mv = rt.get("circ_mv", 0)
    turnover = rt.get("turnover_rate", 0)
    
    signals = []
    warnings = []
    
    # 简单估值判断
    if pe < 15:
        signals.append(f"低PE({pe:.1f})")
    elif pe > 100:
        warnings.append(f"高PE({pe:.1f})")
    
    if pb < 2:
        signals.append(f"低PB({pb:.1f})")
    elif pb > 10:
        warnings.append(f"高PB({pb:.1f})")
    
    if turnover > 5:
        warnings.append(f"高换手({turnover:.1f}%)")
    elif turnover < 0.5:
        signals.append(f"低换手({turnover:.1f}%)")
    
    # PEG (PE / 净利增速)
    peg = None
    try:
        fin_data = indicators(symbol)
        np_growth = fin_data.get("net_profit_growth", 0)
        if pe > 0 and np_growth > 0:
            peg = pe / np_growth
            if peg < 1:
                signals.append(f"PEG低估({peg:.2f})")
            elif peg > 2:
                warnings.append(f"PEG偏高({peg:.2f})")
    except Exception:
        pass  # PEG 计算失败不影响其他指标
    
    return {
        "pe": pe,
        "pb": pb,
        "total_mv": total_mv,
        "circ_mv": circ_mv,
        "turnover_rate": turnover,
        "peg": round(peg, 2) if peg else None,
        "signals": signals,
        "warnings": warnings,
    }
