# -*- coding: utf-8 -*-
"""宏观分析层 — 国际环境 + 国内经济 + 事件驱动(市场情绪)

三个独立分析函数 + 一个综合研判函数
"""

from typing import Dict


def analyze_global(data: Dict) -> Dict:
    """国际环境研判
    
    输入: global_macro() 返回的原始数据
    输出: 环境定性(宽松/收紧/中性) + 商品趋势 + 信号/警告
    """
    signals = []
    warnings = []
    
    # 1. 美债10Y → 全球流动性风向标
    us_10y = data.get("us_10y_yield", {})
    us_10y_val = us_10y.get("value")
    if us_10y_val is not None:
        if us_10y_val > 4.5:
            warnings.append(f"美债10Y高位({us_10y_val}%), 压制成长股估值")
        elif us_10y_val < 3.0:
            signals.append(f"美债10Y低位({us_10y_val}%), 有利于风险资产")
        else:
            signals.append(f"美债10Y适中({us_10y_val}%)")
    
    # 2. 美联储利率 → 货币政策周期
    fed = data.get("fed_rate", {})
    fed_val = fed.get("value")
    if fed_val is not None:
        if fed_val >= 5.0:
            warnings.append(f"联邦基金利率{fed_val}%, 紧缩周期")
        elif fed_val <= 2.0:
            signals.append(f"联邦基金利率{fed_val}%, 宽松周期")
        else:
            signals.append(f"联邦基金利率{fed_val}%, 政策中性")
    
    # 3. 大宗商品趋势
    commodities = []
    for key, name in [("gold", "黄金"), ("silver", "白银"), ("crude_oil", "原油")]:
        item = data.get(key, {})
        if item and item.get("price"):
            pct = item.get("change_pct")
            trend = "涨" if pct and pct > 0 else ("跌" if pct and pct < 0 else "平")
            commodities.append({
                "name": name,
                "price": item["price"],
                "change_pct": pct,
                "trend": trend,
            })
            if key == "gold" and pct and pct > 1.5:
                signals.append(f"黄金强势({pct:+.1f}%), 避险情绪升温")
            if key == "crude_oil" and pct and pct < -2:
                warnings.append(f"原油大跌({pct:+.1f}%), 关注需求端信号")
    
    # 4. 综合环境定性
    signal_count = len(signals)
    warning_count = len(warnings)
    
    if signal_count > warning_count + 1:
        environment = "宽松利好"
    elif warning_count > signal_count + 1:
        environment = "紧缩承压"
    else:
        environment = "中性"
    
    return {
        "environment": environment,
        "us_10y_yield": us_10y,
        "fed_rate": fed,
        "commodities": commodities,
        "signals": signals,
        "warnings": warnings,
    }


def analyze_domestic(data: Dict) -> Dict:
    """国内经济研判
    
    输入: domestic_macro() 返回的原始数据
    输出: 经济周期(复苏/过热/滞胀/衰退) + 流动性 + 信号/警告
    """
    signals = []
    warnings = []
    
    # 1. CPI → 通胀压力
    cpi = data.get("cpi", {})
    cpi_val = cpi.get("value")
    if cpi_val is not None:
        if cpi_val > 3.0:
            warnings.append(f"CPI偏高({cpi_val}%), 通胀压力")
        elif cpi_val < 0:
            warnings.append(f"CPI为负({cpi_val}%), 通缩风险")
        elif cpi_val < 1.0:
            signals.append(f"CPI温和({cpi_val}%), 物价稳定")
    
    # 2. PMI → 经济景气度
    pmi = data.get("pmi_manufacturing", {})
    pmi_val = pmi.get("value")
    if pmi_val is not None:
        if pmi_val > 52:
            signals.append(f"PMI扩张({pmi_val}), 制造业景气")
        elif pmi_val < 49:
            warnings.append(f"PMI收缩({pmi_val}), 制造业低迷")
        else:
            signals.append(f"PMI平稳({pmi_val})")
    
    # 非制造业PMI
    pmi_nm = data.get("pmi_non_manufacturing", {})
    pmi_nm_val = pmi_nm.get("value")
    if pmi_nm_val is not None:
        if pmi_nm_val > 55:
            signals.append(f"服务业PMI高景气({pmi_nm_val})")
        elif pmi_nm_val < 50:
            warnings.append(f"服务业PMI收缩({pmi_nm_val})")
    
    # 3. M2 → 流动性
    m2 = data.get("m2_yoy", {})
    m2_val = m2.get("value")
    if m2_val is not None:
        if m2_val > 12:
            signals.append(f"M2高增({m2_val}%), 流动性充裕")
        elif m2_val < 8:
            warnings.append(f"M2低增({m2_val}%), 流动性偏紧")
    
    # 4. LPR → 货币政策信号
    lpr = data.get("lpr", {})
    lpr_1y = lpr.get("1y")
    lpr_5y = lpr.get("5y")
    if lpr_1y:
        signals.append(f"LPR: 1Y={lpr_1y}%, 5Y={lpr_5y}%")
    
    # 5. 经济周期定性 (简化版美林时钟)
    #    PMI + CPI 组合判断
    cycle = "未知"
    if pmi_val is not None and cpi_val is not None:
        if pmi_val > 50 and cpi_val < 2:
            cycle = "复苏"
        elif pmi_val > 50 and cpi_val >= 2:
            cycle = "过热"
        elif pmi_val <= 50 and cpi_val >= 2:
            cycle = "滞胀"
        elif pmi_val <= 50 and cpi_val < 2:
            cycle = "衰退"
    
    # 流动性定性
    liquidity = "中性"
    if m2_val is not None:
        if m2_val > 12:
            liquidity = "充裕"
        elif m2_val < 8:
            liquidity = "偏紧"
    
    return {
        "cycle": cycle,
        "liquidity": liquidity,
        "cpi": cpi,
        "pmi_manufacturing": pmi,
        "pmi_non_manufacturing": pmi_nm,
        "m2_yoy": m2,
        "lpr": lpr,
        "signals": signals,
        "warnings": warnings,
    }


def analyze_event(data: Dict) -> Dict:
    """事件驱动分析: 涨停复盘 → 市场情绪
    
    输入: zt_pool() 返回的原始数据
    输出: 情绪定性(冰点/低迷/温和/活跃/过热) + 连板高度 + 热门方向 + 持续性
    """
    signals = []
    warnings = []
    
    stats = data.get("zt_stats", {})
    zt_count = stats.get("count", 0)
    max_height = stats.get("max_height", 0)
    max_stocks = stats.get("max_height_stocks", [])
    hot_sectors = stats.get("hot_sectors", {})
    height_dist = stats.get("height_distribution", {})
    
    # 1. 市场情绪定性 (基于涨停数量)
    if zt_count == 0:
        sentiment = "冰点"
        warnings.append("无涨停, 市场极度低迷")
    elif zt_count < 20:
        sentiment = "低迷"
        warnings.append(f"涨停仅{zt_count}只, 赚钱效应差")
    elif zt_count < 50:
        sentiment = "温和"
        signals.append(f"涨停{zt_count}只, 结构性行情")
    elif zt_count < 100:
        sentiment = "活跃"
        signals.append(f"涨停{zt_count}只, 赚钱效应好")
    else:
        sentiment = "过热"
        warnings.append(f"涨停{zt_count}只, 注意追高风险")
    
    # 2. 连板高度 → 短线情绪
    if max_height >= 7:
        signals.append(f"最高{max_height}连板({', '.join(max_stocks)}), 妖股效应强")
    elif max_height >= 4:
        signals.append(f"最高{max_height}连板({', '.join(max_stocks)}), 接力意愿尚可")
    elif max_height >= 2:
        signals.append(f"最高{max_height}连板, 接力情绪一般")
    elif max_height == 1 and zt_count > 0:
        warnings.append("全部首板无连板, 接力情绪冰点")
    
    # 连板股数量 (2板以上)
    multi_board = sum(cnt for h, cnt in height_dist.items() if h >= 2)
    if multi_board > 0:
        signals.append(f"连板股{multi_board}只")
    
    # 3. 热门方向
    if hot_sectors:
        top_sectors = list(hot_sectors.items())[:3]
        sector_str = ", ".join(f"{s}({c}只)" for s, c in top_sectors)
        signals.append(f"涨停集中: {sector_str}")
    
    # 4. 昨日涨停今日表现 → 持续性
    prev_zt = data.get("prev_zt_perf", [])
    if prev_zt:
        avg_pct = sum(s.get("pct", 0) for s in prev_zt) / len(prev_zt)
        up_count = sum(1 for s in prev_zt if s.get("pct", 0) > 0)
        up_ratio = up_count / len(prev_zt) * 100
        
        if avg_pct > 2:
            signals.append(f"昨日涨停今日均涨{avg_pct:.1f}%, 持续性强")
        elif avg_pct < -1:
            warnings.append(f"昨日涨停今日均跌{avg_pct:.1f}%, 追高被套")
        else:
            signals.append(f"昨日涨停今日均涨{avg_pct:.1f}%, 表现平稳")
        
        continuation = {
            "avg_pct": round(avg_pct, 2),
            "up_ratio": round(up_ratio, 1),
            "count": len(prev_zt),
        }
    else:
        continuation = {}
    
    # 5. 强势涨停
    strong_list = data.get("strong_list", [])
    if strong_list:
        signals.append(f"强势涨停{len(strong_list)}只(创新高/突破)")
    
    return {
        "sentiment": sentiment,
        "zt_count": zt_count,
        "max_height": max_height,
        "max_height_stocks": max_stocks,
        "height_distribution": height_dist,
        "hot_sectors": hot_sectors,
        "continuation": continuation,
        "strong_count": len(strong_list),
        "signals": signals,
        "warnings": warnings,
    }


def synthesize(global_data: Dict, domestic_data: Dict, event_data: Dict) -> Dict:
    """综合研判: 国际+国内+事件 → 操作建议
    
    输出: 综合评级 + 操作建议 + 关键变量
    """
    signals = []
    warnings = []
    
    g_env = global_data.get("environment", "中性")
    d_cycle = domestic_data.get("cycle", "未知")
    d_liq = domestic_data.get("liquidity", "中性")
    e_sent = event_data.get("sentiment", "未知")
    
    # 汇总信号/警告
    signals.extend(global_data.get("signals", []))
    signals.extend(domestic_data.get("signals", []))
    signals.extend(event_data.get("signals", []))
    warnings.extend(global_data.get("warnings", []))
    warnings.extend(domestic_data.get("warnings", []))
    warnings.extend(event_data.get("warnings", []))
    
    # 综合评级
    positive = 0
    negative = 0
    
    # 国际环境
    if g_env == "宽松利好":
        positive += 2
    elif g_env == "紧缩承压":
        negative += 2
    
    # 经济周期
    if d_cycle == "复苏":
        positive += 2
    elif d_cycle == "过热":
        positive += 1
        warnings.append("经济过热, 警惕政策收紧")
    elif d_cycle == "滞胀":
        negative += 2
    elif d_cycle == "衰退":
        negative += 1
        signals.append("衰退期关注防御板块(公用事业/必选消费)")
    
    # 流动性
    if d_liq == "充裕":
        positive += 1
    elif d_liq == "偏紧":
        negative += 1
    
    # 市场情绪
    if e_sent == "活跃":
        positive += 1
    elif e_sent == "过热":
        warnings.append("市场过热, 注意控制仓位")
    elif e_sent == "低迷":
        negative += 1
    elif e_sent == "冰点":
        negative += 2
        signals.append("情绪冰点, 关注超跌反弹机会")
    
    score = positive - negative
    
    if score >= 4:
        outlook = "积极看多"
        action = "加仓为主, 进攻型配置"
    elif score >= 2:
        outlook = "偏多"
        action = "适度参与, 关注结构性机会"
    elif score >= 0:
        outlook = "中性"
        action = "控制仓位, 精选个股"
    elif score >= -2:
        outlook = "偏空"
        action = "防守为主, 轻仓观望"
    else:
        outlook = "谨慎"
        action = "空仓等待, 关注政策底/市场底信号"
    
    return {
        "outlook": outlook,
        "action": action,
        "score": score,
        "positive_factors": positive,
        "negative_factors": negative,
        "signals": signals[:12],
        "warnings": warnings[:12],
    }
