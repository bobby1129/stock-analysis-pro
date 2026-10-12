#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成同花顺一级行业板块 名称->881码 映射表 (约90个)
用途: 行业板块日K(d.10jqka bk_881xxx)入参; 点火雷达LLM标签是行业级, 匹配行业板块量比
数据源: akshare stock_board_industry_name_ths() 直接返回881码, 无需爬详情页
输出: data/ths_industry_881_mapping.json
建议: 季度随 concept-mapping-check 一起刷新
"""
import os, json
for k in ['HTTPS_PROXY','https_proxy','HTTP_PROXY','http_proxy']: os.environ.pop(k, None)
import akshare as ak

OUT = os.path.expanduser('~/stock-analysis-pro/data/ths_industry_881_mapping.json')


def main():
    df = ak.stock_board_industry_name_ths()
    mapping = {str(r['name']): str(r['code']) for _, r in df.iterrows()}
    assert all(v.startswith('881') for v in mapping.values()), '出现非881码, 需检查接口'
    with open(OUT, 'w', encoding='utf-8') as f:
        import time
        json.dump({'generated': time.strftime('%Y-%m-%d %H:%M'), 'count': len(mapping),
                   'industries': mapping}, f, ensure_ascii=False, indent=1)
    print(f'完成: {len(mapping)} 个行业 -> {OUT}')


if __name__ == '__main__':
    main()
