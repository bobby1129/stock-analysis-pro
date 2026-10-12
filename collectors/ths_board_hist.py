#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同花顺概念板块日K历史采集器 (直连 d.10jqka.com.cn, 绕过 q.10jqka 详情页风控)

数据源: https://d.10jqka.com.cn/v4/line/bk_<885码>/01/<year>.js
  - 885码来自 data/ths_concept_885_mapping.json (季度刷新)
  - 需 hexin-v cookie (py_mini_racer + akshare自带 ths.js 生成, 与 akshare 同法)
  - 返回整年日K: 日期,开,高,低,收,成交量,成交额,... (分号分隔, 逗号字段)
  - 成交额单位: 元 (实测与akshare stock_board_concept_index_ths一致)

风控备忘(AGENTS.md): q.10jqka.com.cn/gn/detail 全量爬会403封IP;
  本模块**不访问** q.10jqka 详情页, 直接用885码请求 d.10jqka 年线文件。

缓存: cache/concept_amount_history.json
  {概念名: {"885": "885xxx", "amt": {"YYYYMMDD": 成交额(亿)}}}
  只保留最近 KEEP_DAYS 个交易日, 每日增量合并。

用法:
    python3 collectors/ths_board_hist.py           # 刷新缓存(增量)
    from collectors.ths_board_hist import load_board_volume_ratio
    ratios = load_board_volume_ratio()             # {概念名: (今日额亿, 20日均额亿, 量比)}
"""
import os, sys, json, time, re
for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)
import requests

_ROOT = os.path.expanduser('~/stock-analysis-pro')
MAPPING_FILE = os.path.join(_ROOT, 'data', 'ths_concept_885_mapping.json')
INDUSTRY_MAPPING_FILE = os.path.join(_ROOT, 'data', 'ths_industry_881_mapping.json')
CACHE_FILE = os.path.join(_ROOT, 'cache', 'concept_amount_history.json')
INDUSTRY_CACHE_FILE = os.path.join(_ROOT, 'cache', 'industry_amount_history.json')
KEEP_DAYS = 70          # 保留最近N个交易日(20日均量+余量)
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')


def _gen_v_cookie():
    """hexin-v cookie, 与 akshare 同法 (py_mini_racer + akshare内置 ths.js)"""
    import py_mini_racer
    from akshare.utils import cons  # noqa: F401  (确保akshare可导入)
    import akshare
    pkg = os.path.dirname(akshare.__file__)
    js_path = None
    for cand in [os.path.join(pkg, 'file', 'ths.js'),
                 os.path.join(pkg, 'utils', 'ths.js')]:
        if os.path.exists(cand):
            js_path = cand
            break
    if js_path is None:  # 兜底: 包内搜索
        for dirpath, _, files in os.walk(pkg):
            if 'ths.js' in files:
                js_path = os.path.join(dirpath, 'ths.js')
                break
    if js_path is None:
        raise RuntimeError('找不到 akshare ths.js')
    ctx = py_mini_racer.MiniRacer()
    with open(js_path, encoding='utf-8') as f:
        ctx.eval(f.read())
    return ctx.call('v')


def fetch_board_year(name, code_885, year, v_cookie, session=None):
    """拉单个板块单年日K → [{date: YYYYMMDD, amount: 亿}, ...]"""
    url = f'https://d.10jqka.com.cn/v4/line/bk_{code_885}/01/{year}.js'
    headers = {'User-Agent': UA, 'Referer': 'http://q.10jqka.com.cn',
               'Host': 'd.10jqka.com.cn', 'Cookie': f'v={v_cookie}'}
    s = session or requests
    r = s.get(url, headers=headers, timeout=15)
    text = r.text
    i = text.find('"data":"')
    if i < 0:
        return []
    seg = text[i + 8:]
    seg = seg[:seg.find('"')]
    out = []
    for row in seg.split(';'):
        f = row.split(',')
        if len(f) >= 7 and re.match(r'^\d{8}$', f[0]):
            try:
                amt = float(f[6])
            except ValueError:
                continue
            if amt > 0:
                out.append({'date': f[0], 'amount': amt / 1e8})  # 元→亿
    return out


def _refresh_mapping_history(mapping_file, cache_file, key, verbose=True, max_concepts=None):
    """通用: 拉 mapping_file 中全部板块的当年+去年日K, 增量合并进 cache_file"""
    with open(mapping_file, encoding='utf-8') as f:
        concepts = json.load(f)[key]
    if max_concepts:
        concepts = dict(list(concepts.items())[:max_concepts])

    cache = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, encoding='utf-8') as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    v_cookie = _gen_v_cookie()
    now_year = time.localtime().tm_year
    sess = requests.Session()
    ok = fail = 0
    fails = []
    t0 = time.time()
    for i, (name, code) in enumerate(concepts.items()):
        rows = []
        for year in (now_year - 1, now_year):
            try:
                rows += fetch_board_year(name, code, year, v_cookie, sess)
            except Exception as e:
                if verbose:
                    print(f'  ⚠ {name} {year}: {e}')
        if rows:
            amt = {r['date']: round(r['amount'], 2) for r in rows}
            ent = cache.get(name, {'code': code, 'amt': {}})
            ent['code'] = code
            ent['amt'].update(amt)
            keys = sorted(ent['amt'].keys())
            if len(keys) > KEEP_DAYS:
                for k in keys[:-KEEP_DAYS]:
                    ent['amt'].pop(k)
            cache[name] = ent
            ok += 1
        else:
            fail += 1
            fails.append(name)
        if verbose and (i + 1) % 50 == 0:
            print(f'  {i+1}/{len(concepts)} ok={ok} fail={fail} {time.time()-t0:.0f}s')
        time.sleep(0.12)

    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, separators=(',', ':'))
    if verbose:
        print(f'✓ 板块历史缓存: ok={ok} fail={fail} → {cache_file}')
        if fails:
            print(f'  失败名单(前10): {fails[:10]}')
    return ok, fail, fails


def refresh_history(verbose=True, max_concepts=None):
    """概念板块(885)全量刷新"""
    return _refresh_mapping_history(MAPPING_FILE, CACHE_FILE, 'concepts',
                                    verbose, max_concepts)


def refresh_industry_history(verbose=True, max_concepts=None):
    """一级行业板块(881, 约90个)全量刷新"""
    return _refresh_mapping_history(INDUSTRY_MAPPING_FILE, INDUSTRY_CACHE_FILE,
                                    'industries', verbose, max_concepts)


def _load_ratio_from_cache(cache_file, min_days=10):
    if not os.path.exists(cache_file):
        return {}
    with open(cache_file, encoding='utf-8') as f:
        cache = json.load(f)
    out = {}
    for name, ent in cache.items():
        amt = ent.get('amt', {})
        if len(amt) < min_days:
            continue
        keys = sorted(amt.keys())
        last = keys[-1]
        hist = [amt[k] for k in keys[:-1]][-20:]
        if len(hist) < min_days:
            continue
        avg20 = sum(hist) / len(hist)
        if avg20 <= 0:
            continue
        out[name] = {'today_amt': amt[last], 'avg20': round(avg20, 2),
                     'ratio': round(amt[last] / avg20, 2), 'days': len(hist),
                     'date': last}
    return out


def load_board_volume_ratio(min_days=10):
    """概念板块(885)量比 → {概念名: {'today_amt','avg20','ratio','days','date'}}"""
    return _load_ratio_from_cache(CACHE_FILE, min_days)


def load_industry_volume_ratio(min_days=10):
    """一级行业板块(881)量比 → {行业名: {...}} (点火雷达LLM标签匹配用)"""
    return _load_ratio_from_cache(INDUSTRY_CACHE_FILE, min_days)


def _cache_latest_date(cache_file):
    latest = None
    if os.path.exists(cache_file):
        try:
            with open(cache_file, encoding='utf-8') as f:
                cache = json.load(f)
            for ent in cache.values():
                ks = ent.get('amt', {})
                if ks:
                    d = max(ks.keys())
                    latest = d if latest is None or d > latest else latest
        except Exception:
            latest = None
    return latest


def ensure_history_fresh(trade_date=None):
    """generate_matrix 前置调用: 概念缓存最新日期 < 目标交易日才刷新(幂等, 重跑不重复拉)"""
    latest = _cache_latest_date(CACHE_FILE)
    if trade_date and latest and latest >= trade_date:
        print(f'✓ 板块历史缓存已是最新({latest}), 跳过刷新')
        return False
    print(f'板块历史缓存过期(最新{latest}, 目标{trade_date}), 开始刷新...')
    refresh_history()
    return True


def ensure_industry_history_fresh(trade_date=None):
    """generate_ignition 前置调用: 行业缓存幂等刷新(90个板块约20秒)"""
    latest = _cache_latest_date(INDUSTRY_CACHE_FILE)
    if trade_date and latest and latest >= trade_date:
        print(f'✓ 行业历史缓存已是最新({latest}), 跳过刷新')
        return False
    print(f'行业历史缓存过期(最新{latest}, 目标{trade_date}), 开始刷新...')
    refresh_industry_history()
    return True


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg == 'industry':
        refresh_industry_history()
    else:
        n = int(arg) if arg else None
        refresh_history(max_concepts=n)
