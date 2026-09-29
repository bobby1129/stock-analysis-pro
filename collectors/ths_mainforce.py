# -*- coding: utf-8 -*-
"""同花顺概念板块主力资金流采集

数据源(同花顺官方, 与APP"主力资金"同口径, 2026-09-30用户对照APP验证一致):
    https://stockpage.10jqka.com.cn/stock_page/api/v1/stockpage/funds/?code=<885码>&marketId=48
    返回 largeOrderFlow: big(超大单)/mass(大单)/medium(中单)/small(小单) 流入/流出/净额, 单位: 元

口径说明:
    - 主力净额 = 超大单净额 + 大单净额
    - 该接口按委托单大小分档记账, 四单净额之和恒为0 (买卖两侧分别按各自委托单档位记账)
    - 与 gnzjl 全口径净额(主动买-主动卖)是两个正交切面, 不可相加;
      两者背离(主力流出+主动净流入)是派发嫌疑信号
    - 885板块码映射表: data/ths_concept_885_mapping.json (scripts/build_ths_885_mapping.py 生成, 季度刷新)

用法:
    from collectors.ths_mainforce import fetch_concept_main_force
    mf = fetch_concept_main_force()   # {概念名: {...}}, 当日缓存于 cache/ths_mainforce_YYYYMMDD.json
"""

import os
import json
import time
from datetime import datetime

import requests

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPING_FILE = os.path.join(_BASE, 'data', 'ths_concept_885_mapping.json')
CACHE_DIR = os.path.join(_BASE, 'cache')

_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0',
            'Referer': 'https://stockpage.10jqka.com.cn/'}

# 拉取参数
GAP = 0.1        # 请求间隔(秒), 实测0.1s无风控
RETRIES = 2


def load_885_mapping():
    """{概念名: 885板块码}"""
    with open(MAPPING_FILE, encoding='utf-8') as f:
        return json.load(f)['concepts']


def fetch_one(code885, session=None):
    """单概念四单资金, 返回dict(单位:亿) 或 None"""
    s = session or requests
    url = (f'https://stockpage.10jqka.com.cn/stock_page/api/v1/stockpage/funds/'
           f'?code={code885}&marketId=48')
    for i in range(RETRIES + 1):
        try:
            d = s.get(url, headers=_HEADERS, timeout=8).json()
            f = d.get('data', {}).get('fundsData', {}).get('largeOrderFlow') or {}
            if f.get('big_capital_net_inflow') is None:
                raise ValueError('null fields')
            return {
                'super_net': f['big_capital_net_inflow'] / 1e8,       # 超大单净额(亿)
                'big_net': f['mass_capital_net_inflow'] / 1e8,        # 大单净额(亿)
                'medium_net': f['medium_capital_net_inflow'] / 1e8,   # 中单净额(亿)
                'small_net': f['small_capital_net_inflow'] / 1e8,     # 小单净额(亿)
                'main_net': (f['big_capital_net_inflow'] + f['mass_capital_net_inflow']) / 1e8,  # 主力净额(亿)
                'main_in': (f['big_capital_inflow'] + f['mass_capital_inflow']) / 1e8,           # 主力流入(亿)
                'main_out': (f['big_capital_outflow'] + f['mass_capital_outflow']) / 1e8,        # 主力流出(亿)
            }
        except Exception:
            if i < RETRIES:
                time.sleep(1 + i)
    return None


def _cache_is_post_close(path):
    """缓存有效性守卫: 文件须生成于当日15:05之后(收盘定格数据)。
    防止盘前/凌晨抓到的旧交易日数据被当日任务误用"""
    mt = datetime.fromtimestamp(os.path.getmtime(path))
    now = datetime.now()
    return mt.date() == now.date() and mt.hour * 60 + mt.minute >= 15 * 60 + 5


def fetch_concept_main_force(names=None, verbose=True, use_cache=True):
    """批量抓取概念主力资金

    Args:
        names: 概念名列表; None=映射表全量
        use_cache: 当日缓存命中则直接返回(盘后数据不变, 复盘/内容任务共享)
    Returns:
        {概念名: {super_net, big_net, medium_net, small_net, main_net, main_in, main_out}}
        抓取失败的概念不在结果中(调用方自行判断覆盖率)
    """
    for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
        os.environ.pop(k, None)

    date_key = datetime.now().strftime('%Y%m%d')
    cache_file = os.path.join(CACHE_DIR, f'ths_mainforce_{date_key}.json')
    if use_cache and os.path.exists(cache_file) and _cache_is_post_close(cache_file):
        try:
            with open(cache_file, encoding='utf-8') as f:
                cached = json.load(f)
            if names is None or set(names) <= set(cached):
                if verbose:
                    print(f'[mainforce] 命中当日缓存: {cache_file} ({len(cached)}概念)')
                return cached
        except Exception:
            pass

    mapping = load_885_mapping()
    targets = names if names else list(mapping.keys())
    missing = [n for n in targets if n not in mapping]
    if missing and verbose:
        print(f'[mainforce] ⚠ 映射缺失{len(missing)}个: {missing[:5]}')

    session = requests.Session()
    result = {}
    t0 = time.time()
    for i, name in enumerate(targets):
        code = mapping.get(name)
        if not code:
            continue
        d = fetch_one(code, session)
        if d:
            result[name] = d
        if (i + 1) % 100 == 0 and verbose:
            print(f'[mainforce] {i+1}/{len(targets)} ok={len(result)} {time.time()-t0:.0f}s')
        time.sleep(GAP)

    if verbose:
        print(f'[mainforce] 完成: {len(result)}/{len(targets)} 概念, 耗时{time.time()-t0:.0f}s')

    if names is None and result:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False)
        if verbose:
            print(f'[mainforce] 已缓存: {cache_file}')
    return result


def fetch_concept_flow_combined(top_n=None, verbose=True):
    """复盘报告用: 概念资金流(主力口径+全口径主动净额合并)

    Returns:
        [{name, change_pct, net(主力净额亿), active_net(全口径主动净额亿),
          leader, leader_pct, diverge('distribution'派发/'absorb'吸筹/'')}, ...]
        按主力净额降序; top_n=None返回全量; 已过滤宽基属性桶(融资融券/股通等)
    """
    import akshare as ak
    import pandas as pd

    # 宽基属性桶过滤规则与 daily_content 保持一致(国家大基金持股是真题材不可误杀)
    BUCKET_KEYWORDS = [
        '融资融券', '转融券', '股通', '国企改革', '中报', '年报', '季报',
        '预增', '预减', '预盈', '预亏', '扭亏', '举牌', '股权激励',
        'QFII', 'MSCI', '标普', '富时', 'AH股', 'B股', '转债',
        '昨日涨停', '昨日连板', '昨日触板', 'ST板块', '次新', '新股与',
    ]

    df = ak.stock_fund_flow_concept(symbol="即时")
    for c in ['净额', '行业-涨跌幅', '领涨股-涨跌幅']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    mf = fetch_concept_main_force(verbose=verbose)

    results = []
    for _, r in df.iterrows():
        name = str(r['行业']).strip()
        if any(kw in name for kw in BUCKET_KEYWORDS):
            continue
        m = mf.get(name)
        if not m:
            continue
        main_net = m['main_net']
        active_net = float(r['净额'])
        diverge = ''
        # 背离判定: 主力流出≥0.5亿+主动流入≥2亿=派发嫌疑(散户追主力撤); 反向=吸筹嫌疑
        if main_net <= -0.5 and active_net >= 2:
            diverge = 'distribution'
        elif main_net >= 0.5 and active_net <= -2:
            diverge = 'absorb'
        results.append({
            'name': name,
            'change_pct': float(r['行业-涨跌幅']),
            'net': round(main_net, 2),
            'active_net': round(active_net, 2),
            'leader': str(r['领涨股']).strip(),
            'leader_pct': float(r['领涨股-涨跌幅']),
            'diverge': diverge,
        })
    results.sort(key=lambda x: x['net'], reverse=True)
    return results[:top_n] if top_n else results


if __name__ == '__main__':
    mf = fetch_concept_main_force(use_cache=False)
    for n in ['粮食概念', '乳业', '白酒概念']:
        if n in mf:
            print(n, mf[n])
    # 分布统计: 主力总额量级(为矩阵门槛调参)
    import statistics
    totals = sorted(v['main_in'] + v['main_out'] for v in mf.values())
    print(f'\n主力总额分布(亿): n={len(totals)}')
    for p in [10, 25, 50, 75, 90]:
        print(f'  P{p}: {totals[int(len(totals)*p/100)]:.1f}')
    nets = sorted(abs(v['main_net']) for v in mf.values())
    print('主力|净额|分布(亿):')
    for p in [25, 50, 75, 90]:
        print(f'  P{p}: {nets[int(len(nets)*p/100)]:.2f}')
