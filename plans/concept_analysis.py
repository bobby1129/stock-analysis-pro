# -*- coding: utf-8 -*-
"""Req2 概念板块分析计划 — 全景扫描 → 趋势定性 → 深度分析 → 选股"""
import sys
import os
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.concept import concept_news, clear_kline_cache
from analysis.concept import analyze_board_trend, analyze_concept_deep
from analysis.stock_picker import score_board_strength, score_pick_quality, pick_stocks, find_resonance

# ── 缓存 ──
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
CACHE_TTL = 600  # 10 分钟

def _cache_get(key: str):
    """读取缓存，过期返回 None"""
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if not os.path.exists(path):
        return None
    try:
        mtime = os.path.getmtime(path)
        if time.time() - mtime > CACHE_TTL:
            return None
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None

def _cache_set(key: str, data):
    """写入缓存"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{key}.json")
    try:
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass

FILTER_KEYWORDS = [
    # 持仓/机构类
    '两融', '融资融券', '证金', '社保', '基金重仓', '社保重仓',
    'QFII', '保险重仓', '券商重仓', '外资重仓', '信托重仓',
    # 业绩预告类
    '预盈', '预增', '业绩预升', '业绩预降', '预减', '扭亏',
    # 估值/价格类
    '破净', '高市净', '低价', '高价', '高市盈率', '低市盈率', '破发', '百元股',
    # 市值/规模/指数类
    '超大盘', '中盘', '小盘', '大盘', '央企50',
    '上证380', '深成500', '沪深300', '中证500', '中证1000',
    'MSCI中国', '央视50', '上证50', '上证180',
    # 股票特征类
    '新股', '次新', '含H', '含B', 'AB股', 'B股', 'ST', '摘帽', '创业', '科创',
    # 资本运作/交易类
    '股权激励', '整体上市', '重组', '高送转', '高送转预期',
    '员工持股', '参股新三板', '配股股', '举牌',
    '减持', '增持', '沪股通', '深股通',
    # 风格/因子/题材标签类
    '风格', '红利', '权重', '破增发', '超跌',
    '新高', '趋势', '反转', '题材',
    '昨日', '昨日连板', '昨日涨停',
    '科技风格', '大盘成长', '大盘价值', '中盘成长', '中盘价值',
    '小盘成长', '小盘价值', '质量成长', '低波动', '高股息',
    '动量因子', '价值因子',
    # 泛化标签
    '高商誉', '区域', '板块',
    # 指数/基金/宽基类
    '富时罗素', '标准普尔', 'HS300', '深证100',
    '东方财富热股', '价值股', '成长股',
    '道琼斯', '纳斯达克', '恒生', '日经',
]

REGIONS = [
    '北京', '上海', '深圳', '广东', '江苏', '浙江', '山东', '福建',
    '安徽', '四川', '湖北', '湖南', '西部', '东北', '长三角', '珠三角',
    '京津冀', '雄安', '海南', '重庆', '天津', '成渝', '特区', '海峡',
    '中部', '西北', '西南', '粤港澳', '自贸区'
]


def filter_concepts(concepts):
    """过滤宽泛/地域/风格类概念"""
    res = []
    for c in concepts:
        name = c['name']
        if any(kw in name for kw in FILTER_KEYWORDS):
            continue
        if len(name) < 2 or len(name) > 10:
            continue
        if any(r in name for r in REGIONS):
            continue
        res.append(c)
    return res


def run(target_count=10, verbose=True, use_cache=True):
    """
    执行概念板块分析 (含深度选股分析)
    
    流程:
    1. 概念排名 (映射表+腾讯行情) → Top N
    2. 新闻归因 (东财搜索API)
    3. 深度分析 (成分股K线+选股)
    4. 板块趋势定性
    
    返回: {date, concepts: [{name, ..., deep_analysis}, ...]}
    """
    date_str = datetime.now().strftime('%Y-%m-%d')
    cache_key = f"concept_deep_{date_str}_{target_count}"

    if use_cache:
        cached = _cache_get(cache_key)
        if cached:
            if verbose:
                print(f"  [缓存命中] {cache_key}")
            return cached

    if verbose:
        print(f"[{date_str}] 概念板块深度分析启动...")

    # 清空K线缓存
    clear_kline_cache()

    # === Step 1: HTTP API获取概念列表 + 逐个获取成分股 (稳定, 不触发滑块) ===
    if verbose:
        print("  Step 1: 获取概念列表 (HTTP API + Cookie)...")
    from collectors.em_concept import fetch_concept_list, fetch_concept_stocks
    from collectors.quote import batch_quotes_tencent

    concepts_raw = fetch_concept_list(top_n=60, verbose=verbose)
    if not concepts_raw:
        print("\n  ⚠️ 无法获取概念排行！可能原因：")
        print("  1. Cookie未配置或已过期")
        print("  2. 网络问题 → 检查是否能访问 push2.eastmoney.com")
        print("  💡 如有离线缓存将自动降级使用\n")
        return {"error": "无法获取概念排行", "date": date_str}

    # 过滤非行业概念
    top = filter_concepts(concepts_raw)[:target_count]

    if verbose:
        print(f"  → 过滤后{len(top)}个概念, 逐个获取成分股 (HTTP API)...")

    # 逐个概念获取成分股 (HTTP API, 1秒间隔避免限流)
    stocks_map = {}
    for i, c in enumerate(top):
        bk_code = c['bk_code']
        name = c['name']
        stocks = fetch_concept_stocks(bk_code, name=name, limit=100, verbose=verbose)
        stocks_map[bk_code] = stocks
        if i < len(top) - 1:
            time.sleep(1.0)

    # 用腾讯批量行情补充成交额 (东财HTTP拿到的amount可能为0)
    all_symbols = []
    for bk_code in stocks_map:
        for s in stocks_map[bk_code]:
            sym = s.get('symbol', '')
            if sym:
                all_symbols.append(sym)
    tencent_quotes = batch_quotes_tencent(all_symbols) if all_symbols else {}

    for c in top:
        bk_code = c['bk_code']
        stocks = stocks_map.get(bk_code, [])
        stock_details = []
        for s in stocks:
            # 剔除北交所 (代码以4/8/9开头: 43xxxx, 83xxxx, 87xxxx, 920xxx)
            code = s.get('code', '') or s.get('symbol', '')
            if code and code[0] in ('4', '8', '9'):
                continue
            try:
                pct_val = float(s.get('change_pct', 0) or 0)
            except (ValueError, TypeError):
                pct_val = 0
            # 成交额优先用东财的，为0则用腾讯行情补充
            try:
                amount_val = float(s.get('amount', 0) or 0)
            except (ValueError, TypeError):
                amount_val = 0
            sym = s.get('symbol', '')
            if amount_val == 0 and sym in tencent_quotes:
                amount_val = tencent_quotes[sym].get('amount', 0)
            try:
                turnover_val = float(s.get('turnover', 0) or 0)
            except (ValueError, TypeError):
                turnover_val = 0
            stock_details.append({
                'symbol': s['symbol'],
                'name': s.get('name', ''),
                'pct': round(pct_val, 2),
                'price': s.get('price', 0),
                'amount_yi': round(amount_val / 1e8, 2),
                'turnover': turnover_val,
            })
        stock_details.sort(key=lambda x: -x['pct'])
        c['stocks'] = stock_details
        if stock_details:
            c['total'] = len(stock_details)
            c['up_count'] = sum(1 for s in stock_details if s['pct'] > 0)
            c['down_count'] = sum(1 for s in stock_details if s['pct'] < 0)
            c['up_ratio'] = round(c['up_count'] / c['total'] * 100, 1)
            c['avg_pct'] = round(sum(s['pct'] for s in stock_details) / len(stock_details), 2)
            c['total_amount_yi'] = round(sum(s['amount_yi'] for s in stock_details), 1)
        else:
            c['total'] = 0
            c['up_count'] = 0
            c['down_count'] = 0
            c['up_ratio'] = 0
            c['avg_pct'] = 0
            c['total_amount_yi'] = 0
    top.sort(key=lambda x: -x['avg_pct'])

    results = []

    for i, c in enumerate(top):
        name = c['name']

        if verbose:
            print(f"  [{i+1}/{len(top)}] {name} 均涨{c['avg_pct']:+.2f}%")

        # 找龙头 (涨幅最高的成分股)
        leader_stock = c['stocks'][0] if c['stocks'] else {}
        entry = {
            'name': name,
            'code': c.get('bk_code', name),  # 东财板块代码
            'change_pct': c['avg_pct'],
            'amount_yi': c['total_amount_yi'],
            'net_inflow': c.get('net_inflow', 0),
            'stock_count': c['total'],
            'up_count': c['up_count'],
            'up_ratio': c['up_ratio'],
            'leader': leader_stock.get('name', ''),
            'leader_code': leader_stock.get('symbol', ''),
            'leader_pct': leader_stock.get('pct', 0),
            'source': c.get('source', 'unknown'),
        }

        # === Step 2: 新闻归因 ===
        time.sleep(0.3)
        news = concept_news(name, max_items=5)
        entry['news'] = news[:3]

        # === Step 3: 深度分析 ===
        # 将 rank_concepts 的成分股转换为 analyze_concept_deep 的格式
        deep_stocks = []
        for s in c['stocks']:
            deep_stocks.append({
                'symbol': s['symbol'],
                'name': s['name'],
                'changepercent': s['pct'],
                'turnoverratio': s.get('turnover', 0),
                'amount': s.get('amount_yi', 0) * 1e8,  # 亿 → 元
            })

        if deep_stocks:
            if verbose:
                print(f"    深度分析: {len(deep_stocks)}只成分股...")
            deep = analyze_concept_deep(deep_stocks, c['total_amount_yi'] * 1e8, verbose=verbose)
            entry['deep'] = deep

            # === Step 4: 板块级趋势定性 ===
            trend = analyze_board_trend(deep)
            entry['trend'] = trend
            
            # === Step 5: 双轨评分 (增量添加，不改原有逻辑) ===
            # 轨道A: 板块强度评分
            board_score = score_board_strength(entry, deep, trend, c['stocks'])
            entry['board_score'] = board_score
            
            # 轨道B: 选股决策评分 + 精选标的
            picked = pick_stocks(c['stocks'], deep, limit=5)
            entry['picked_stocks'] = picked
            pick_score = score_pick_quality(entry, deep, picked)
            entry['pick_score'] = pick_score
            
        else:
            entry['deep'] = {"error": "无法获取成分股"}
            entry['trend'] = {"status": "unknown", "reason": "无法获取成分股"}
            entry['board_score'] = {'total': 0, 'phase': '未知'}
            entry['pick_score'] = {'total': 0, 'phase': '未知'}
            entry['picked_stocks'] = []

        results.append(entry)

    # === Step 6: 跨概念共振 ===
    concepts_with_picks = [{'name': r['name'], 'picked_stocks': r.get('picked_stocks', [])} for r in results]
    resonance = find_resonance(concepts_with_picks)

    # === Step 7: 按资金流入倒序排序 ===
    results.sort(key=lambda x: x.get('net_inflow', 0), reverse=True)

    output = {"date": date_str, "concepts": results, "count": len(results), "resonance": resonance}

    if use_cache:
        _cache_set(cache_key, output)

    return output


def format_report(data: dict) -> str:
    """格式化输出报告 (文本版)"""
    if "error" in data:
        return f"❌ 错误: {data['error']}"

    lines = []
    lines.append(f"📊 概念板块深度分析报告 ({data['date']})")
    lines.append(f"{'='*50}")

    for i, c in enumerate(data['concepts'], 1):
        lines.append(f"\n{'─'*50}")

        lines.append(f"【{i}】{c['name']}  {c['change_pct']:+.2f}%  成交{c['amount_yi']}亿")
        lines.append(f"    龙头: {c['leader']}({c['leader_code']}) {c['leader_pct']:+.2f}%")

        # 趋势
        t = c.get('trend', {})
        if t.get('status') != 'unknown':
            status_map = {
                'breakout': '🚀 金叉启动', 'strong': '🔥 主升浪',
                'rising': '📈 上升期', 'weak_rise': '↗️ 弱上升',
                'weak': '↔️ 震荡', 'falling': '📉 下跌',
            }
            label = status_map.get(t['status'], t['status'])
            lines.append(f"    趋势: {label} — {t.get('reason', '')}")

        # 深度分析
        deep = c.get('deep', {})
        dist = deep.get('distribution', {})
        mom = deep.get('momentum', {})
        rep = deep.get('representativeness', {})

        if rep:
            top100 = rep.get('top100_amount_yi', 0)
            total = rep.get('total_amount_yi', 0)
            ratio = rep.get('ratio', 0)
            if total > 0:
                lines.append(f"    代表性: 采样{top100}亿 / 总计{total}亿 ({ratio}%)")
            else:
                lines.append(f"    代表性: 采样{top100}亿 ({rep.get('sample_count', 0)}只)")

        if dist:
            lines.append(f"    涨幅分布: >7%={dist['above_7']}只 3-7%={dist['between_3_7']}只 0-3%={dist['between_0_3']}只 <0%={dist['below_0']}只")

        if mom:
            lines.append(f"    持续性: 连涨3天+={mom['consecutive_3plus']}只 2天={mom['consecutive_2']}只 刚启动={mom['just_started']}只 下跌={mom['falling']}只")

        # 连涨股
        strong = deep.get('strong_stocks', [])
        if strong:
            lines.append(f"    🔥 连涨3天+:")
            for s in strong:
                lines.append(f"      {s['symbol']} {s['name']} 涨{s['pct']:+.2f}% 连涨{s['consecutive_days']}天 量比{s['vol_ratio']}")

        # 突破股
        breakout = deep.get('breakout_stocks', [])
        if breakout:
            lines.append(f"    🚀 新突破 (涨>5%且刚启动):")
            for s in breakout[:5]:
                rise = s.get('rise_from_low', 0)
                lines.append(f"      {s['symbol']} {s['name']} 涨{s['pct']:+.2f}% 距月低{rise:+.1f}% 量比{s['vol_ratio']}")

        # 涨停
        lu = deep.get('limit_up', {})
        if lu.get('count', 0) > 0:
            boards = lu.get('consecutive_boards', [])
            lines.append(f"    💥 涨停{lu['count']}只" + (f" 连板{len(boards)}只" if boards else ""))

        # 新闻
        news = c.get('news', [])
        if news:
            lines.append(f"    📰 新闻:")
            for n in news[:2]:
                date = n.get('date', '')[:10]
                title = n.get('title', '')[:50]
                lines.append(f"      [{date}] {title}")

        # 双轨评分
        board_score = c.get('board_score', {})
        pick_score = c.get('pick_score', {})
        board_val = board_score.get('total', 0)
        pick_val = pick_score.get('total', 0)
        board_phase = board_score.get('phase', '--')
        pick_phase = pick_score.get('phase', '--')
        
        lines.append(f"    📊 板块强度: {board_val}分 ({board_phase})")
        lines.append(f"    🎯 选股决策: {pick_val}分 ({pick_phase})")
        
        # 精选标的
        picked = c.get('picked_stocks', [])
        if picked:
            lines.append(f"    🎯 精选标的 (Top {len(picked)}):")
            for s in picked[:5]:
                entry_type = s.get('entry_type', '追高')
                entry_score = s.get('entry_score', 0)
                reason = s.get('reason', '')
                lines.append(f"      {s['name']}({s['symbol']}) {s['pct']:+.2f}% — {entry_type} {entry_score}分 {reason}")
        
        # 共振
        resonance_list = data.get('resonance', [])
        concept_resonance = [r for r in resonance_list if r['name'] in [s['name'] for s in picked]]
        if concept_resonance:
            lines.append(f"    🔗 跨概念共振:")
            for r in concept_resonance[:3]:
                concepts_str = '、'.join(r['concepts'])
                lines.append(f"      {r['name']} — 出现在 {r['resonance_count']} 个概念 ({concepts_str})")

    lines.append(f"\n{'='*50}")
    lines.append("报告生成完毕")
    return '\n'.join(lines)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='概念板块深度分析')
    parser.add_argument('--count', type=int, default=10, help='分析概念数量')
    parser.add_argument('--json', action='store_true', help='JSON输出')
    args = parser.parse_args()

    data = run(target_count=args.count, verbose=not args.json)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(format_report(data))
