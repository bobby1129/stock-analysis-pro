#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成同花顺概念 名称->885板块码 映射表
用途: 概念主力资金流(stockpage funds API, marketId=48)的入参
数据源: q.10jqka.com.cn/gn/detail/code/<页面码>/ 隐藏域 id="clid" value='885xxx'
输出: data/ths_concept_885_mapping.json  {概念名: 885码}
建议: 挂到季度 concept-mapping-check 任务刷新
"""
import os, sys, json, re, time
for k in ['HTTPS_PROXY','https_proxy','HTTP_PROXY','http_proxy']: os.environ.pop(k, None)
import akshare as ak
import requests

OUT = os.path.expanduser('~/stock-analysis-pro/data/ths_concept_885_mapping.json')
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36'}
CLID_PAT = re.compile(r"""id="clid"[^>]*value=['"]?(\d{6})""")


def fetch_clid(page_code: str):
    url = f'https://q.10jqka.com.cn/gn/detail/code/{page_code}/'
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=12)
            if r.status_code == 200:
                m = CLID_PAT.search(r.text)
                return m.group(1) if m else None
        except Exception:
            pass
        time.sleep(1 + attempt)
    return None


def main():
    concepts = ak.stock_board_concept_name_ths()   # name -> code(30xxxx页面码)
    print(f'概念总数: {len(concepts)}')
    mapping = {}
    fails = []
    t0 = time.time()
    for i, (_, row) in enumerate(concepts.iterrows()):
        name, code = row['name'], row['code']
        clid = fetch_clid(code)
        if clid:
            mapping[name] = clid
        else:
            fails.append((name, code))
        if (i + 1) % 50 == 0:
            print(f'  {i+1}/{len(concepts)} ok={len(mapping)} fail={len(fails)} {time.time()-t0:.0f}s')
        time.sleep(0.12)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump({'generated': time.strftime('%Y-%m-%d %H:%M'), 'count': len(mapping), 'concepts': mapping}, f, ensure_ascii=False, indent=1)
    print(f'\n完成: {len(mapping)} 个概念 -> {OUT}')
    if fails:
        print(f'失败 {len(fails)} 个:')
        for n, c in fails:
            print(f'  {n}({c})')


if __name__ == '__main__':
    main()
