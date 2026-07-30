# -*- coding: utf-8 -*-
"""分析维度层 — 概念板块趋势定性 + 深度分析 + 机会挖掘"""

from collectors.concept import concept_leader_kline, concept_stocks, batch_klines


def analyze_board_trend(deep_result: dict) -> dict:
    """
    板块级趋势定性 — 基于100只成分股的综合数据

    用涨幅分布 + 持续性分布 + 放量信号 综合判断板块整体状态

    返回: {
        status: breakout / strong / rising / weak_rise / weak / falling,
        reason: str,
        detail: {up_ratio, strong_ratio, just_started_ratio, ...}
    }
    """
    dist = deep_result.get('distribution', {})
    mom = deep_result.get('momentum', {})
    vol = deep_result.get('volume_signal', {})
    lu = deep_result.get('limit_up', {})

    total = dist.get('total', 0)
    if total == 0:
        return {"status": "unknown", "reason": "无数据"}

    # 核心比例
    up_count = dist.get('above_7', 0) + dist.get('between_3_7', 0) + dist.get('between_0_3', 0)
    up_ratio = up_count / total
    strong_ratio = dist['above_7'] / total
    dn_ratio = dist.get('below_0', 0) / total
    just_started_ratio = mom.get('just_started', 0) / total
    consecutive_3plus_ratio = mom.get('consecutive_3plus', 0) / total
    consecutive_2_ratio = mom.get('consecutive_2', 0) / total
    vol_ratio = vol.get('ratio', 0) / 100
    limit_up_count = lu.get('count', 0)

    detail = {
        "up_ratio": round(up_ratio * 100, 1),
        "strong_ratio": round(strong_ratio * 100, 1),
        "dn_ratio": round(dn_ratio * 100, 1),
        "just_started_ratio": round(just_started_ratio * 100, 1),
        "consecutive_3plus_ratio": round(consecutive_3plus_ratio * 100, 1),
        "limit_up": limit_up_count,
        "vol_active_ratio": vol.get('ratio', 0),
    }

    # ── 趋势判定 ──

    # 1. 金叉启动: 刚启动占比高 + 赚钱效应好
    if just_started_ratio > 0.25 and up_ratio > 0.6:
        return {
            "status": "breakout",
            "reason": f"板块刚启动，{detail['just_started_ratio']}%个股首日上涨，上涨面{detail['up_ratio']}%",
            "detail": detail,
        }

    # 2. 主升浪: 连涨多 + 赚钱效应强 + 有涨停
    if consecutive_3plus_ratio > 0.35 and up_ratio > 0.65 and limit_up_count >= 2:
        return {
            "status": "strong",
            "reason": f"主升浪，{detail['consecutive_3plus_ratio']}%个股连涨3天+，涨停{limit_up_count}只",
            "detail": detail,
        }

    # 3. 上升期: 连涨适中 + 上涨面较广
    if (consecutive_3plus_ratio > 0.15 or consecutive_2_ratio > 0.1) and up_ratio > 0.55:
        return {
            "status": "rising",
            "reason": f"上升趋势，{detail['up_ratio']}%个股上涨，{detail['consecutive_3plus_ratio']}%连涨3天+",
            "detail": detail,
        }

    # 4. 弱上升: 有上涨但动能分散
    if up_ratio > 0.5 and strong_ratio < 0.1:
        return {
            "status": "weak_rise",
            "reason": f"弱上升，{detail['up_ratio']}%上涨但强势股仅{detail['strong_ratio']}%",
            "detail": detail,
        }

    # 5. 下跌: 下跌面大
    if dn_ratio > 0.5:
        return {
            "status": "falling",
            "reason": f"板块走弱，{detail['dn_ratio']}%个股下跌",
            "detail": detail,
        }

    # 6. 震荡
    return {
        "status": "weak",
        "reason": f"方向不明，涨{detail['up_ratio']}% 跌{detail['dn_ratio']}%",
        "detail": detail,
    }


def _count_consecutive_up(klines: list) -> int:
    """从最新一天往回数，连续上涨天数 (close > prev_close)"""
    if not klines or len(klines) < 2:
        return 0
    count = 0
    for i in range(len(klines) - 1, 0, -1):
        if klines[i]['close'] > klines[i - 1]['close']:
            count += 1
        else:
            break
    return count


def _volume_ratio(klines: list, period: int = 20) -> float:
    """当日成交量 / 近N日均量"""
    if not klines or len(klines) < period + 1:
        return 0.0
    current_vol = klines[-1]['volume']
    avg_vol = sum(k['volume'] for k in klines[-(period + 1):-1]) / period
    if avg_vol <= 0:
        return 0.0
    return round(current_vol / avg_vol, 2)


def _is_limit_up(pct: float) -> bool:
    """判断是否涨停 (A股主板10%, 创业板/科创板20%, ST5%)"""
    # 简化判断: >=9.8% 视为涨停
    return pct >= 9.8


def _get_limit_up_pct(symbol: str) -> float:
    """根据股票代码判断涨停幅度 (%)"""
    # 去掉 sh/sz 前缀
    code = symbol[2:] if symbol[:2] in ('sh', 'sz', 'bj') else symbol
    if code.startswith(('300', '688')):
        return 20.0  # 创业板/科创板
    elif code.startswith('8'):
        return 30.0  # 北交所
    else:
        return 10.0  # 主板


def _is_just_started(klines: list, symbol: str) -> tuple:
    """
    判断是否"刚启动": 首日上涨 + 相对近一月低点涨幅 < 涨停*1.2

    Returns: (is_just_started: bool, rise_from_low: float)
    """
    if not klines or len(klines) < 2:
        return False, 0.0

    # 条件1: 首日上涨
    if klines[-1]['close'] <= klines[-2]['close']:
        return False, 0.0

    # 条件2: 对比近一月(20日)低点
    lookback = min(len(klines), 20)
    recent = klines[-lookback:]
    low = min(k['low'] for k in recent)
    current = klines[-1]['close']

    if low <= 0:
        return False, 0.0

    rise_from_low = (current - low) / low * 100
    threshold = _get_limit_up_pct(symbol) * 1.2

    return rise_from_low <= threshold, round(rise_from_low, 2)


def analyze_concept_deep(stocks: list, total_amount: float, verbose=False) -> dict:
    """
    概念深度分析 — 选股决策链

    Args:
        stocks: 成分股列表 (100只, 按涨跌幅排序)
                每只: {symbol, name, changepercent, turnoverratio, amount}
        total_amount: 概念总成交额 (新浪接口给的)
        verbose: 是否打印进度

    Returns:
        深度分析结果 dict
    """
    if not stocks:
        return {"error": "无成分股数据"}

    # ── 1. 采样覆盖: 前100成交额 ──
    top100_amount = sum(float(s.get('amount', 0)) for s in stocks)
    representativeness = {
        "top100_amount_yi": round(top100_amount / 1e8, 1),
        "sample_count": len(stocks),
    }

    # ── 2. 涨幅分布 ──
    above_7 = between_3_7 = between_0_3 = below_0 = 0
    for s in stocks:
        pct = float(s.get('changepercent', 0))
        if pct >= 7:
            above_7 += 1
        elif pct >= 3:
            between_3_7 += 1
        elif pct > 0:
            between_0_3 += 1
        else:
            below_0 += 1

    distribution = {
        "above_7": above_7,
        "between_3_7": between_3_7,
        "between_0_3": between_0_3,
        "below_0": below_0,
        "total": len(stocks),
    }

    # ── 拉K线数据 (用于连续天数 + 量比) ──
    symbols = [s['symbol'] for s in stocks if s.get('symbol')]
    if verbose:
        print(f"    拉取 {len(symbols)} 只股票K线...")
    klines_map = batch_klines(symbols, datalen=30, delay=0.12, verbose=verbose)

    # ── 3. 持续性分布 (连续上涨天数) ──
    consecutive_3plus = consecutive_2 = just_started = falling = flat_or_other = 0
    # 同时记录每只股票的K线分析结果
    stock_momentum = []  # [{symbol, name, pct, consecutive_days, vol_ratio}]
    for s in stocks:
        sym = s.get('symbol', '')
        pct = float(s.get('changepercent', 0))
        klines = klines_map.get(sym, [])
        days = _count_consecutive_up(klines)
        vr = _volume_ratio(klines)

        is_js, rise_low = _is_just_started(klines, sym)

        stock_momentum.append({
            "symbol": sym,
            "name": s.get('name', ''),
            "pct": round(pct, 2),
            "consecutive_days": days,
            "vol_ratio": vr,
            "turnover": float(s.get('turnoverratio', 0)),
            "amount_yi": round(float(s.get('amount', 0)) / 1e8, 2),
            "rise_from_low": rise_low,
        })

        if days >= 3:
            consecutive_3plus += 1
        elif days == 2:
            consecutive_2 += 1
        elif is_js:
            just_started += 1
        elif pct < 0:
            falling += 1
        else:
            flat_or_other += 1

    momentum = {
        "consecutive_3plus": consecutive_3plus,
        "consecutive_2": consecutive_2,
        "just_started": just_started,
        "falling": falling,
        "flat_or_other": flat_or_other,
    }

    # ── 4. 连涨3天+股票 (最多5只, 按连涨天数降序) ──
    strong_stocks = sorted(
        [sm for sm in stock_momentum if sm['consecutive_days'] >= 3],
        key=lambda x: (-x['consecutive_days'], -x['pct'])
    )[:5]

    # ── 5. 涨幅>5%且刚启动 的股票（排除已连涨2天+的） ──
    breakout_stocks = sorted(
        [sm for sm in stock_momentum
         if sm['pct'] > 5
         and sm['consecutive_days'] <= 1
         and sm.get('rise_from_low', 999) <= _get_limit_up_pct(sm['symbol']) * 1.2],
        key=lambda x: -x['pct']
    )[:10]

    # ── 6. 涨停统计 ──
    limit_up_stocks = [sm for sm in stock_momentum if _is_limit_up(sm['pct'])]
    limit_up_count = len(limit_up_stocks)
    # 连板: 涨停且连涨>=2天
    consecutive_boards = [sm for sm in limit_up_stocks if sm['consecutive_days'] >= 2]

    # ── 7. 放量信号: 量比 > 1.5 的股票数 ──
    above_avg_stocks = [sm for sm in stock_momentum if sm['vol_ratio'] >= 1.5]
    volume_signal = {
        "above_avg_count": len(above_avg_stocks),
        "ratio": round(len(above_avg_stocks) / len(stock_momentum) * 100, 1) if stock_momentum else 0,
    }

    return {
        "representativeness": representativeness,
        "distribution": distribution,
        "momentum": momentum,
        "strong_stocks": strong_stocks,
        "breakout_stocks": breakout_stocks,
        "limit_up": {
            "count": limit_up_count,
            "stocks": limit_up_stocks[:5],
            "consecutive_boards": consecutive_boards,
        },
        "volume_signal": volume_signal,
    }


def analyze_opportunity(node_code: str, top_n: int = 5) -> dict:
    """
    成分股统计 + 领涨龙头筛选
    返回: {
        total, up_count, down_count, flat_count,
        avg_pct, top_stocks: [{code, name, pct, turnover, amount}]
    }
    """
    stocks = concept_stocks(node_code, num=100)
    if not stocks:
        return {"total": 0, "reason": "无法获取成分股"}

    total = len(stocks)
    up, down, flat = 0, 0, 0
    pct_sum = 0.0

    for s in stocks:
        pct = float(s.get('changepercent', 0))
        pct_sum += pct
        if pct > 0.5:
            up += 1
        elif pct < -0.5:
            down += 1
        else:
            flat += 1

    avg_pct = pct_sum / total if total else 0

    # 按涨跌幅排序取 top_n (已在请求中排序)
    top_stocks = []
    for s in stocks[:top_n]:
        top_stocks.append({
            "code": s.get("symbol", ""),
            "name": s.get("name", ""),
            "pct": float(s.get("changepercent", 0)),
            "turnover": float(s.get("turnoverratio", 0)),
            "amount": round(float(s.get("amount", 0)) / 1e8, 2),  # 亿
        })

    return {
        "total": total,
        "up_count": up, "down_count": down, "flat_count": flat,
        "avg_pct": round(avg_pct, 2),
        "top_stocks": top_stocks,
    }
