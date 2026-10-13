#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""个股→同花顺概念 F10采集 + 持久缓存 (点火雷达v5概念聚合数据源)

数据源: basic.10jqka.com.cn/{code}/concept.html "概念题材"页 (kamis JS动态渲染,
  静态curl拿不到, 需Playwright渲染后提取 #concept 表格第2列概念名)。
风控实测(2026-10-12): basic.10jqka 不受 q10jqka成分股页风控影响(同AGENTS.md备忘),
  概念名与 data/ths_concept_885_mapping.json 完全同体系。

缓存: data/stock_concept_map.json (静态映射数据, git跟踪, 同885映射表规则)
  {code: {"names": [概念名...], "codes": [885码...(未命中的季度性新概念不含)],
          "updated": "YYYYMMDD", "source": "f10"|"llm"}}
  - f10: 权威挂靠关系, 90天过期自动刷新
  - llm: 兜底归类(F10拉取失败/冷启动), 30天过期, f10成功后覆盖
  注意: 本缓存只用于事件构建(触发样本线), 严禁参与板块量比计算
  (量比只认885指数K线全量口径 — IGNITION_RADAR_DESIGN.md §11.1红线)。

用法:
    from collectors.ths_stock_concept import get_stock_concepts, refresh_many
    get_stock_concepts('300827')        # 读缓存(过期视为未命中)
    refresh_many(['300827', ...])       # 批量拉F10并写缓存, 返回{code: names}
"""
import os, json, time
from datetime import datetime
for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

_ROOT = os.path.expanduser('~/stock-analysis-pro')
CACHE_FILE = os.path.join(_ROOT, 'data', 'stock_concept_map.json')
MAPPING_FILE = os.path.join(_ROOT, 'data', 'ths_concept_885_mapping.json')
F10_TTL_DAYS = 90
LLM_TTL_DAYS = 30
_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')


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


def _load_885_mapping():
    with open(MAPPING_FILE, encoding='utf-8') as f:
        return json.load(f)['concepts']


def _days_since(updated):
    """YYYYMMDD字符串 → 距今天数; 解析失败返回10**6(视为过期)"""
    try:
        return (datetime.now() - datetime.strptime(str(updated), '%Y%m%d')).days
    except ValueError:
        return 10 ** 6


def get_stock_concepts(code):
    """读缓存 → {'names': [...], 'codes': [...], 'source': ...} 或 None(未命中/过期)"""
    ent = _load_cache().get(code)
    if not ent:
        return None
    ttl = F10_TTL_DAYS if ent.get('source') == 'f10' else LLM_TTL_DAYS
    if _days_since(ent.get('updated', '')) > ttl:
        return None
    return {'names': ent.get('names', []), 'codes': ent.get('codes', []),
            'source': ent.get('source', 'f10')}


def save_llm_fallback(code, names, source='llm'):
    """LLM兜底归类写入缓存(短TTL, f10成功后覆盖)"""
    cache = _load_cache()
    m885 = _load_885_mapping()
    cache[code] = {'names': names,
                   'codes': [m885[n] for n in names if n in m885],
                   'updated': time.strftime('%Y%m%d'), 'source': source}
    _save_cache(cache)


def _extract_concepts(page, code, timeout_ms=25000):
    """Playwright渲染F10概念页, 提取常规概念表第2列概念名"""
    page.goto(f'http://basic.10jqka.com.cn/{code}/concept.html', timeout=timeout_ms)
    page.wait_for_timeout(2500)
    try:
        rows = page.eval_on_selector_all('#concept table tr', '''els => els.map(e => {
            const td = e.querySelectorAll('td');
            return td.length >= 2 ? td[1].innerText.trim() : null;
        }).filter(x => x)''')
    except Exception:
        rows = []
    # 去重保序 + 过滤明显非概念行(表头/序号)
    seen, out = set(), []
    for r in rows:
        r = r.strip()
        if not r or r == '概念名称' or r in seen or len(r) > 20:
            continue
        seen.add(r)
        out.append(r)
    return out


def refresh_many(codes, verbose=True, per_page=8):
    """批量拉F10概念写缓存(Playwright, 每per_page只股复用一个page)
    返回 {code: {'names': [...], 'codes': [...], 'ok': bool}}"""
    from playwright.sync_api import sync_playwright
    m885 = _load_885_mapping()
    cache = _load_cache()
    result = {}
    if not codes:
        return result
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(user_agent=_UA)
        page = ctx.new_page()
        for i, code in enumerate(codes):
            ok = False
            for attempt in range(2):
                try:
                    names = _extract_concepts(page, code)
                    if names:
                        cache[code] = {'names': names,
                                       'codes': [m885[n] for n in names if n in m885],
                                       'updated': time.strftime('%Y%m%d'), 'source': 'f10'}
                        result[code] = {'names': names, 'codes': cache[code]['codes'], 'ok': True}
                        ok = True
                        break
                except Exception as e:
                    if verbose:
                        print(f'  ⚠ F10 {code} 第{attempt+1}次失败: {str(e)[:80]}')
                    try:
                        page.close()
                        page = ctx.new_page()
                    except Exception:
                        pass
            if not ok:
                result[code] = {'names': [], 'codes': [], 'ok': False}
            if (i + 1) % per_page == 0:
                try:
                    page.close()
                    page = ctx.new_page()
                except Exception:
                    pass
            if verbose and (i + 1) % 20 == 0:
                _save_cache(cache)   # 中途落盘防中断丢进度
                print(f'  F10概念 {i+1}/{len(codes)} {time.time()-t0:.0f}s')
            time.sleep(0.3)
        browser.close()
    _save_cache(cache)
    n_ok = sum(1 for v in result.values() if v['ok'])
    if verbose:
        print(f'✓ F10概念缓存: ok={n_ok}/{len(codes)} → {CACHE_FILE}')
    return result


def get_or_fetch(codes, verbose=True):
    """入口: 缓存命中直接用, 未命中/过期批量拉F10
    返回 {code: {'names', 'codes', 'source'}} (拉取失败的code不在返回中)"""
    cache = _load_cache()
    out, need = {}, []
    for code in codes:
        ent = cache.get(code)
        if ent:
            ttl = F10_TTL_DAYS if ent.get('source') == 'f10' else LLM_TTL_DAYS
            if _days_since(ent.get('updated', '')) <= ttl:
                out[code] = {'names': ent.get('names', []), 'codes': ent.get('codes', []),
                             'source': ent.get('source', 'f10')}
                continue
        need.append(code)
    if need:
        if verbose:
            print(f'  F10概念缓存未命中 {len(need)}只, 增量拉取...')
        res = refresh_many(need, verbose=verbose)
        for code, v in res.items():
            if v['ok']:
                out[code] = {'names': v['names'], 'codes': v['codes'], 'source': 'f10'}
    return out
