#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""个股F10主营业务采集 + 持久缓存 (点火雷达v6标签净化数据源)

数据源: basic.10jqka.com.cn/{code}/company.html "主营业务"字段
  (industry_screener.fetch_main_business 同链路, 不受q10jqka成分股页风控影响)

缓存: data/stock_business_map.json (数据文件, git不提交)
  {code: {"business": 主营文本, "updated": "YYYYMMDD"}}
  TTL 180天(用户要求, 2026-10-13): 超期自动重抓核对,
  防公司近期新增业务(转型/并购)后按旧主营误剔新标签。

用法:
    from collectors.ths_stock_business import get_or_fetch_business
    biz = get_or_fetch_business(['300827', ...])   # {code: 主营文本}
"""
import os, json, time
from datetime import datetime
for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

_ROOT = os.path.expanduser('~/stock-analysis-pro')
CACHE_FILE = os.path.join(_ROOT, 'data', 'stock_business_map.json')
BIZ_TTL_DAYS = 180


def _load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    tmp = CACHE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, CACHE_FILE)


def _days_since(updated):
    """YYYYMMDD → 距今天数; 解析失败视为过期"""
    try:
        return (datetime.now() - datetime.strptime(str(updated), '%Y%m%d')).days
    except ValueError:
        return 10 ** 6


def get_or_fetch_business(codes, verbose=True):
    """缓存命中直接用, 未命中/超180天重抓F10
    返回 {code: 主营文本} (拉取失败/为空的code不在返回中)"""
    cache = _load_cache()
    out, need = {}, []
    for code in codes:
        ent = cache.get(code)
        if ent and ent.get('business') and _days_since(ent.get('updated', '')) <= BIZ_TTL_DAYS:
            out[code] = ent['business']
        else:
            need.append(code)
    if need:
        if verbose:
            print(f'  主营业务: 缓存命中{len(out)} 待抓{len(need)} (TTL {BIZ_TTL_DAYS}天)')
        from plans.industry_screener import fetch_main_business
        for i, code in enumerate(need):
            try:
                biz = fetch_main_business(code)
            except Exception:
                biz = ''
            if biz:
                cache[code] = {'business': biz, 'updated': time.strftime('%Y%m%d')}
            if (i + 1) % 20 == 0:
                _save_cache(cache)   # 中途落盘防中断
                if verbose:
                    print(f'    主营 {i+1}/{len(need)}')
            time.sleep(0.1)
        _save_cache(cache)
        for code in need:
            ent = cache.get(code)
            if ent and ent.get('business'):
                out[code] = ent['business']
    return out
