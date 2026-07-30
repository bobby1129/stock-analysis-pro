# -*- coding: utf-8 -*-
"""概念选股引擎 — 双轨评分 (板块强度 + 选股决策) + 跨概念共振

轨道A: 板块强度评分 — 回答"今天哪个板块最强/最活跃"
轨道B: 选股决策评分 — 回答"这个板块里哪几只股票现在适合买入"

跨概念共振: 同一只股票出现在多个概念的精选标的中 → 标记共振股

注意: 本模块纯计算，无网络请求。K线数据从 collectors/concept.py 的缓存获取。
"""

from typing import List, Dict
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── 轨道A: 板块强度评分 ──

def score_board_strength(concept_data: Dict, deep_analysis: Dict, trend: Dict, stocks: List[Dict] = None) -> Dict:
    """
    板块强度评分 (轨道A) — 回答"今天谁最热"
    
    评分维度 (满分100):
    - 赚钱效应 (30分): >7%占比×100 + 3~7%占比×50
    - 资金强度 (25分): 净流入(按流通市值分档) + 放量股占比
    - 板块宽度 (25分): 上涨占比、涨停数
    - 持续性 (20分): 连涨股数量 (板块级展示，连涨是正面信号)
    
    注意: 连涨在板块强度中是加分项，在选股决策中才扣分 (追高风险)
    """
    score = {'total': 0, 'details': {}, 'phase': '震荡期'}
    
    # 从 deep_analysis 提取数据
    dist = deep_analysis.get('distribution', {})
    mom = deep_analysis.get('momentum', {})
    lu = deep_analysis.get('limit_up', {})
    vol = deep_analysis.get('volume_signal', {})
    rep = deep_analysis.get('representativeness', {})
    
    # 1. 赚钱效应 (30分)
    profit = 0
    total_stocks = dist.get('total', 0)
    if total_stocks > 0:
        above_7_ratio = dist.get('above_7', 0) / total_stocks
        between_3_7_ratio = dist.get('between_3_7', 0) / total_stocks
        profit = min(30, above_7_ratio * 100 + between_3_7_ratio * 50)
    score['details']['profit'] = round(profit)
    
    # 2. 资金强度 (25分)
    strength = 0
    # 条件1: 净流入 (按流通市值≥500亿的成分股数量分档)
    net_inflow = concept_data.get('net_inflow', 0)
    if net_inflow > 0 and stocks:
        # 统计流通市值≥500亿的成分股数量
        big_cap_count = sum(1 for s in stocks if s.get('flow_market_cap', 0) >= 5e10)
        if big_cap_count <= 5:
            coeff = 3  # 小板块
        elif big_cap_count <= 15:
            coeff = 2  # 中板块
        else:
            coeff = 1  # 大板块
        net_inflow_yi = net_inflow / 1e8  # 转为亿
        strength += min(15, net_inflow_yi * coeff)
    elif net_inflow > 0:
        # 无市值数据时降级为统一系数
        strength += min(15, net_inflow / 1e8 * 3)
    # 条件2: 放量股占比
    above_avg_ratio = vol.get('ratio', 0) / 100  # 0.0 ~ 1.0
    strength += min(10, above_avg_ratio * 15)
    score['details']['strength'] = round(strength)
    
    # 3. 板块宽度 (25分)
    breadth = 0
    up_ratio = concept_data.get('up_ratio', 0) / 100  # 0.0 ~ 1.0
    breadth = min(20, up_ratio * 25)  # 80% 上涨 = 满分
    # 涨停加分
    limit_count = lu.get('count', 0)
    breadth += min(5, limit_count * 1)
    score['details']['breadth'] = round(breadth)
    
    # 4. 持续性 (20分)
    sustain = 0
    consecutive_3plus = mom.get('consecutive_3plus', 0)
    consecutive_2 = mom.get('consecutive_2', 0)
    just_started = mom.get('just_started', 0)
    # 连涨越多，板块越强
    sustain = min(20, (consecutive_3plus * 3 + consecutive_2 * 2 + just_started * 1))
    score['details']['sustain'] = round(sustain)
    
    score['total'] = score['details']['profit'] + score['details']['strength'] + \
                     score['details']['breadth'] + score['details']['sustain']
    
    # 阶段判定
    if score['total'] >= 70:
        score['phase'] = '加速期'
    elif score['total'] >= 50:
        score['phase'] = '启动期'
    elif score['total'] >= 30:
        score['phase'] = '震荡期'
    else:
        score['phase'] = '衰退期'
    
    return score


# ── 轨道B: 选股决策评分 ──

def score_pick_quality(concept_data: Dict, deep_analysis: Dict, picked_stocks: List[Dict]) -> Dict:
    """
    选股决策评分 (轨道B) — 回答"今天能买谁"
    
    评分维度 (满分100):
    - 可买标的数 (30分): picked_stocks 中 entry_type != '追高' 的数量
    - 标的质量 (25分): entry_score 平均分
    - 追高风险 (25分): 连涨3天+占比 (越高扣分越多)
    - 新鲜度 (20分): 刚启动占比
    
    注意: 这里和板块强度不同，连涨3天+在选股中是扣分项 (追高风险)
    """
    score = {'total': 0, 'details': {}, 'phase': '观望'}
    
    mom = deep_analysis.get('momentum', {})
    
    # 1. 可买标的数 (30分)
    buyable = 0
    for s in picked_stocks:
        if s.get('entry_type') != '追高':
            buyable += 1
    # 5只以上满分，按比例
    buyable_score = min(30, buyable * 6)
    score['details']['buyable_count'] = round(buyable_score)
    
    # 2. 标的质量 (25分)
    quality = 0
    if picked_stocks:
        avg_score = sum(s.get('entry_score', 0) for s in picked_stocks) / len(picked_stocks)
        quality = min(25, avg_score / 4)  # 100分 → 25分
    score['details']['quality'] = round(quality)
    
    # 3. 追高风险 (25分) — 连涨3天+占比越高扣分越多
    risk_penalty = 0
    total_stocks = mom.get('consecutive_3plus', 0) + mom.get('consecutive_2', 0) + \
                   mom.get('just_started', 0) + mom.get('falling', 0)
    if total_stocks > 0:
        consecutive_3plus_ratio = mom.get('consecutive_3plus', 0) / total_stocks
        risk_penalty = consecutive_3plus_ratio * 25  # 最高扣25分
    risk_score = 25 - risk_penalty
    score['details']['risk'] = round(max(0, risk_score))
    
    # 4. 新鲜度 (20分) — 刚启动占比
    freshness = 0
    if total_stocks > 0:
        just_started_ratio = mom.get('just_started', 0) / total_stocks
        freshness = min(20, just_started_ratio * 40)  # 50% 刚启动 = 满分
    score['details']['freshness'] = round(freshness)
    
    score['total'] = score['details']['buyable_count'] + score['details']['quality'] + \
                     score['details']['risk'] + score['details']['freshness']
    
    # 阶段判定
    if score['total'] >= 70:
        score['phase'] = '精选期'
    elif score['total'] >= 50:
        score['phase'] = '观察期'
    elif score['total'] >= 30:
        score['phase'] = '观望'
    else:
        score['phase'] = '回避'
    
    return score


# ── 个股精选 ──

def pick_stocks(stocks: List[Dict], deep_analysis: Dict, limit: int = 5) -> List[Dict]:
    """
    从成分股中精选可买标的
    
    Args:
        stocks: 成分股列表 [{symbol, name, pct, price, amount_yi, turnover, ...}, ...]
        deep_analysis: 深度分析结果 (包含K线缓存)
        limit: 精选数量
    
    Returns:
        [
            {
                'symbol': 'sh600519',
                'name': '贵州茅台',
                'pct': 3.5,
                'entry_type': '突破启动',
                'entry_score': 85,
                'reason': '放量突破平台',
                'risk': '追高风险',
                'kline_summary': '连涨1天，距月低12%',
            },
            ...
        ]
    """
    from collectors.concept import _kline_cache
    
    picked = []
    
    for s in stocks:
        symbol = s.get('symbol', '')
        klines = _kline_cache.get(symbol, [])
        
        if len(klines) < 5:
            continue
        
        # 计算入场信号
        entry = _classify_entry(s, klines)
        if entry['entry_type'] == '追高':
            # 追高的放最后，但如果分数高也可以选
            entry['entry_score'] = max(0, entry['entry_score'] - 20)
        
        picked.append(entry)
    
    # 按 entry_score 排序
    picked.sort(key=lambda x: x.get('entry_score', 0), reverse=True)
    
    return picked[:limit]


def _classify_entry(stock: Dict, klines: List[Dict]) -> Dict:
    """
    分类入场信号: 5类
    
    - 突破启动: 涨幅>5% 且 距月低<10% 且 刚启动 (连涨1天)
    - 回踩确认: 涨幅2~5% 且 距月高回撤10~20%
    - 趋势加仓: 涨幅>0 且 连涨2天
    - 底部异动: 涨幅>2% 且 距月低<5% 且 下跌趋势
    - 追高: 其他
    """
    symbol = stock.get('symbol', '')
    pct = stock.get('pct', 0)
    turnover = stock.get('turnover', 0)
    
    # 从K线计算技术指标
    recent = klines[-5:] if len(klines) >= 5 else klines
    
    # 连涨天数
    consecutive_up = 0
    for k in reversed(recent):
        if k.get('close', 0) > k.get('open', 0):
            consecutive_up += 1
        else:
            break
    
    # 月低点、月高点
    lows = [k.get('low', 0) for k in klines]
    highs = [k.get('high', 0) for k in klines]
    month_low = min(lows) if lows else 0
    month_high = max(highs) if highs else 0
    current_close = recent[-1].get('close', 0) if recent else 0
    
    # 距月低涨幅
    rise_from_low = ((current_close - month_low) / month_low * 100) if month_low > 0 else 0
    # 距月高回撤
    drawdown = ((month_high - current_close) / month_high * 100) if month_high > 0 else 0
    
    # 量比 (今日成交量 / 5日均量)
    volumes = [k.get('volume', 0) for k in recent]
    avg_vol = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else 1
    vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1
    
    # 入场分类
    entry = {
        'symbol': symbol,
        'name': stock.get('name', ''),
        'pct': pct,
        'price': stock.get('price', 0),
        'amount_yi': stock.get('amount_yi', 0),
        'turnover': turnover,
        'entry_type': '追高',
        'entry_score': 0,
        'reason': '',
        'risk': '',
        'kline_summary': f'连涨{consecutive_up}天，距月低{rise_from_low:.1f}%',
    }
    
    # 1. 突破启动
    if pct > 5 and rise_from_low < 10 and consecutive_up <= 1:
        entry['entry_type'] = '突破启动'
        entry['entry_score'] = round(80 + min(20, pct * 2), 1)
        entry['reason'] = '放量突破平台' if vol_ratio > 1.5 else '突破启动'
        entry['risk'] = '追高风险' if consecutive_up > 0 else '正常'
    
    # 2. 回踩确认
    elif 2 < pct <= 5 and 10 <= drawdown <= 20:
        entry['entry_type'] = '回踩确认'
        entry['entry_score'] = round(70 + min(20, vol_ratio * 10), 1)
        entry['reason'] = f'回撤{drawdown:.1f}%后企稳'
        entry['risk'] = '继续下跌风险'
    
    # 3. 趋势加仓
    elif pct > 0 and consecutive_up >= 2:
        entry['entry_type'] = '趋势加仓'
        entry['entry_score'] = round(60 + min(25, consecutive_up * 5), 1)
        entry['reason'] = f'连涨{consecutive_up}天，趋势延续'
        entry['risk'] = '追高风险'
    
    # 4. 底部异动
    elif pct > 2 and rise_from_low < 5:
        entry['entry_type'] = '底部异动'
        entry['entry_score'] = round(65 + min(20, vol_ratio * 10), 1)
        entry['reason'] = '底部放量异动'
        entry['risk'] = '继续下跌风险'
    
    # 5. 追高 (默认)
    else:
        entry['entry_type'] = '追高'
        entry['entry_score'] = 30
        entry['reason'] = '追高风险'
        entry['risk'] = '高位风险'
    
    return entry


# ── 跨概念共振 ──

def find_resonance(concepts_with_picks: List[Dict]) -> List[Dict]:
    """
    跨概念共振: 同一只股票出现在多个概念的精选标的中
    
    Args:
        concepts_with_picks: [
            {
                'name': '存储芯片',
                'picked_stocks': [{symbol, name, ...}, ...],
            },
            ...
        ]
    
    Returns:
        [
            {
                'symbol': 'sh688396',
                'name': '复旦微电',
                'resonance_count': 2,
                'concepts': ['存储芯片', '半导体'],
            },
            ...
        ]
    """
    from collections import defaultdict
    
    stock_concepts = defaultdict(list)
    
    for c in concepts_with_picks:
        concept_name = c.get('name', '')
        for s in c.get('picked_stocks', []):
            symbol = s.get('symbol', '')
            name = s.get('name', '')
            if symbol:
                stock_concepts[symbol].append({
                    'name': name,
                    'concept': concept_name,
                })
    
    # 找出共振股 (出现 >= 2 次)
    resonance = []
    for symbol, items in stock_concepts.items():
        if len(items) >= 2:
            concepts_list = [it['concept'] for it in items]
            resonance.append({
                'symbol': symbol,
                'name': items[0]['name'],
                'resonance_count': len(concepts_list),
                'concepts': concepts_list,
            })
    
    # 按共振次数排序
    resonance.sort(key=lambda x: x['resonance_count'], reverse=True)
    
    return resonance
