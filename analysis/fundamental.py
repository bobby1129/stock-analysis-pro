# -*- coding: utf-8 -*-
"""分析维度层 — 基本面（增强版）"""

from collectors.finance import indicators, dividend_history, profit_forecast, rd_expense_history


def analyze(symbol: str) -> dict:
    """基本面分析：盈利能力/财务健康/成长能力/现金流质量/周转效率/分红历史/一致预期/综合评分"""
    data = indicators(symbol)
    divs = dividend_history(symbol, limit=3)
    forecast = profit_forecast(symbol)
    rd_history = rd_expense_history(symbol, periods=4)
    
    signals = []
    warnings = []
    
    # === 提取基础指标 ===
    roe = data.get("roe", 0)
    gm = data.get("gross_margin", 0)
    nm = data.get("net_margin", 0)
    debt = data.get("debt_ratio", 0)
    current = data.get("current_ratio", 0)
    rev_g = data.get("revenue_growth", 0)
    np_g = data.get("net_profit_growth", 0)
    eps = data.get("eps", 0)
    nav_ps = data.get("nav_per_share", 0)
    ocf_ps = data.get("ocf_per_share", 0)
    
    # === 新增指标 ===
    inv_turnover = data.get("inventory_turnover", 0)
    inv_turnover_days = data.get("inventory_turnover_days", 0)
    recv_turnover_days = data.get("receivable_turnover_days", 0)
    roe_history = data.get("roe_history", [])
    revenue_history = data.get("revenue_history", [])
    net_profit_history = data.get("net_profit_history", [])
    
    # === 1. 盈利能力 ===
    if roe > 15:
        signals.append(f"高ROE({roe:.1f}%)")
    elif roe < 5:
        warnings.append(f"低ROE({roe:.1f}%)")
    
    if gm > 50:
        signals.append(f"高毛利({gm:.1f}%)")
    elif gm < 20:
        warnings.append(f"低毛利({gm:.1f}%)")
    
    # === 2. 财务健康 ===
    if debt < 30:
        signals.append(f"低负债({debt:.1f}%)")
    elif debt > 70:
        warnings.append(f"高负债({debt:.1f}%)")
    
    if current > 2:
        signals.append(f"流动性好(流动比率{current:.1f})")
    elif current < 1:
        warnings.append(f"流动性差(流动比率{current:.1f})")
    
    # === 3. 成长能力 ===
    if rev_g > 30:
        signals.append(f"营收高增({rev_g:.1f}%)")
    elif rev_g < 0:
        warnings.append(f"营收下滑({rev_g:.1f}%)")
    
    if np_g > 30:
        signals.append(f"净利高增({np_g:.1f}%)")
    elif np_g < 0:
        warnings.append(f"净利下滑({np_g:.1f}%)")
    
    # === 4. 现金流质量（新增）===
    # 经营现金流/净利润 近似 = 每股经营现金流 / EPS
    cash_quality = 0
    if eps > 0 and ocf_ps > 0:
        cash_quality = round(ocf_ps / eps, 2)
        if cash_quality > 1.2:
            signals.append(f"现金流优秀(经营现金流/净利={cash_quality:.1f})")
        elif cash_quality > 0.8:
            signals.append(f"现金流良好(经营现金流/净利={cash_quality:.1f})")
        elif cash_quality < 0.5:
            warnings.append(f"现金流差(经营现金流/净利={cash_quality:.1f})")
    elif eps > 0 and ocf_ps <= 0:
        warnings.append(f"经营现金流为负({ocf_ps:.2f})")
    
    # === 5. 多期趋势（新增）===
    roe_trend = _calc_trend(roe_history)
    rev_trend = _calc_trend(revenue_history)
    np_trend = _calc_trend(net_profit_history)
    
    if roe_trend == "improving":
        signals.append("ROE趋势向上")
    elif roe_trend == "declining":
        warnings.append("ROE趋势向下")
    
    if rev_trend == "improving":
        signals.append("营收趋势向上")
    elif rev_trend == "declining":
        warnings.append("营收趋势向下")
    
    if np_trend == "improving":
        signals.append("净利趋势向上")
    elif np_trend == "declining":
        warnings.append("净利趋势向下")
    
    # === 6. 周转效率（新增）===
    if inv_turnover_days > 0:
        if inv_turnover_days < 60:
            signals.append(f"存货周转快({inv_turnover_days:.0f}天)")
        elif inv_turnover_days > 180:
            warnings.append(f"存货周转慢({inv_turnover_days:.0f}天)")
    
    if recv_turnover_days > 0:
        if recv_turnover_days < 30:
            signals.append(f"回款快({recv_turnover_days:.0f}天)")
        elif recv_turnover_days > 90:
            warnings.append(f"回款慢({recv_turnover_days:.0f}天)")
    
    # === 7. 分红 ===
    if divs:
        latest_div = divs[0].get("dividend", 0)
        if latest_div > 0:
            signals.append(f"近{len(divs)}年有分红(最近每10股派{latest_div}元)")
        else:
            warnings.append("无分红记录")
    
    # === 8. 综合评分（新增）===
    score = _calc_score(
        roe=roe, gm=gm, nm=nm, debt=debt, current=current,
        rev_g=rev_g, np_g=np_g, cash_quality=cash_quality,
        roe_trend=roe_trend, rev_trend=rev_trend, np_trend=np_trend,
        inv_turnover_days=inv_turnover_days, recv_turnover_days=recv_turnover_days,
        has_dividend=len(divs) > 0 and divs[0].get("dividend", 0) > 0,
    )
    
    return {
        "profitability": {
            "roe": {"value": round(roe, 2)},
            "gross_margin": {"value": round(gm, 4)},
            "net_margin": {"value": round(nm, 4)},
        },
        "health": {
            "debt_ratio": {"value": round(debt, 4)},
            "current_ratio": {"value": round(current, 2)},
        },
        "growth": {
            "revenue_growth": {"value": round(rev_g, 6)},
            "net_profit_growth": {"value": round(np_g, 6)},
        },
        "cash_quality": {
            "ocf_per_share": {"value": round(ocf_ps, 2)},
            "ocf_to_net_profit": {"value": cash_quality},
        },
        "turnover": {
            "inventory_turnover_days": {"value": round(inv_turnover_days, 1)},
            "receivable_turnover_days": {"value": round(recv_turnover_days, 1)},
        },
        "trend": {
            "roe_history": roe_history,
            "revenue_yoy_history": data.get("revenue_yoy_history", []),
            "net_profit_yoy_history": data.get("net_profit_yoy_history", []),
            "rd_history": rd_history,
            "roe_trend": roe_trend,
            "revenue_trend": rev_trend,
            "net_profit_trend": np_trend,
        },
        "eps": round(eps, 2),
        "nav_per_share": round(nav_ps, 2),
        "ocf_per_share": round(ocf_ps, 2),
        "dividend": {"history": divs},
        "forecast": forecast,
        "fund_score": score,
        "signals": signals,
        "warnings": warnings,
    }


def _calc_trend(history: list) -> str:
    """计算趋势方向：improving / stable / declining"""
    if len(history) < 2:
        return "unknown"
    # history 是降序（最新在前），反转后看趋势
    values = [h["value"] for h in reversed(history)]
    if len(values) >= 3:
        # 简单线性回归斜率
        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        if denominator == 0:
            return "stable"
        slope = numerator / denominator
        # 斜率占均值的比例
        if y_mean == 0:
            return "stable"
        relative_slope = slope / abs(y_mean)
        if relative_slope > 0.05:
            return "improving"
        elif relative_slope < -0.05:
            return "declining"
        else:
            return "stable"
    return "unknown"


def _calc_score(roe, gm, nm, debt, current, rev_g, np_g, cash_quality,
                roe_trend, rev_trend, np_trend, inv_turnover_days, 
                recv_turnover_days, has_dividend) -> dict:
    """计算基本面综合评分（0-100）"""
    score = 0
    details = {}
    
    # ROE (0-20分)
    if roe >= 20:
        s = 20
    elif roe >= 15:
        s = 16
    elif roe >= 10:
        s = 12
    elif roe >= 5:
        s = 6
    else:
        s = 0
    score += s
    details["roe"] = s
    
    # 毛利率 (0-10分)
    if gm >= 50:
        s = 10
    elif gm >= 30:
        s = 7
    elif gm >= 20:
        s = 4
    else:
        s = 0
    score += s
    details["gross_margin"] = s
    
    # 负债率 (0-10分)
    if debt < 20:
        s = 10
    elif debt < 40:
        s = 7
    elif debt < 60:
        s = 4
    else:
        s = 0
    score += s
    details["debt_ratio"] = s
    
    # 成长能力 (0-20分)
    rev_score = min(max(rev_g, -20), 50) / 50 * 10
    np_score = min(max(np_g, -20), 50) / 50 * 10
    s = max(0, min(20, rev_score + np_score))
    score += s
    details["growth"] = round(s)
    
    # 现金流质量 (0-15分)
    if cash_quality > 1.5:
        s = 15
    elif cash_quality > 1.0:
        s = 12
    elif cash_quality > 0.7:
        s = 8
    elif cash_quality > 0:
        s = 4
    else:
        s = 0
    score += s
    details["cash_quality"] = s
    
    # 趋势 (0-15分)
    trend_score = 0
    for t in [roe_trend, rev_trend, np_trend]:
        if t == "improving":
            trend_score += 5
        elif t == "stable":
            trend_score += 2
    score += trend_score
    details["trend"] = trend_score
    
    # 周转效率 (0-10分)
    turn_score = 0
    if inv_turnover_days > 0:
        if inv_turnover_days < 60:
            turn_score += 5
        elif inv_turnover_days < 120:
            turn_score += 3
    if recv_turnover_days > 0:
        if recv_turnover_days < 30:
            turn_score += 5
        elif recv_turnover_days < 60:
            turn_score += 3
    score += turn_score
    details["turnover"] = turn_score
    
    # 分红加分 (0-5分)
    if has_dividend:
        score += 5
        details["dividend"] = 5
    
    score = min(100, score)
    
    # 评级
    if score >= 80:
        rating = "A"
    elif score >= 60:
        rating = "B"
    elif score >= 40:
        rating = "C"
    else:
        rating = "D"
    
    return {
        "total": int(score),
        "rating": rating,
        "details": [
            ("盈利能力", details.get("roe", 0), 20),
            ("毛利率", details.get("gross_margin", 0), 10),
            ("财务安全", details.get("debt_ratio", 0), 10),
            ("成长能力", details.get("growth", 0), 20),
            ("现金流质量", details.get("cash_quality", 0), 15),
            ("趋势方向", details.get("trend", 0), 15),
            ("周转效率", details.get("turnover", 0), 10),
            ("分红记录", details.get("dividend", 0), 5),
        ],
    }
