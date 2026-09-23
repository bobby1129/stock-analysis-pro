#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证: 绝对额排序 vs 归一化(留存率)排序 的差异"""
import os, sys
for k in ['HTTPS_PROXY','https_proxy','HTTP_PROXY','http_proxy']: os.environ.pop(k, None)
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro/scripts/daily_content'))
import akshare as ak
import pandas as pd
pd.set_option('display.width', 200)
from generate_concept_html import is_bucket_concept

df = ak.stock_fund_flow_concept(symbol="即时")
for c in ['流入资金','流出资金','净额','行业-涨跌幅','公司家数']:
    df[c] = pd.to_numeric(df[c], errors='coerce')
df = df[~df['行业'].apply(is_bucket_concept)].copy()
df['总额'] = df['流入资金'] + df['流出资金']
df['留存率'] = df['净额'] / df['总额'] * 100
active = df[df['总额'] > 20].copy()

print('='*78)
print('【流出侧】绝对额TOP10 vs 留存率TOP10 (板块跌但资金抽走)')
print('='*78)
out_abs = active[active['净额'] < 0].sort_values('净额').head(10)
out_rate = active[(active['净额'] < 0)].sort_values('留存率').head(10)

print('\n--- 按绝对额排 (现在的做法) ---')
for _,r in out_abs.iterrows():
    print(f"  {r['行业']:14s} 净额{r['净额']:+8.1f}亿  成交{r['总额']:7.0f}亿  抽血{r['留存率']:+6.2f}%  涨{r['行业-涨跌幅']:+.2f}%")
print('\n--- 按留存率排 (归一化) ---')
for _,r in out_rate.iterrows():
    print(f"  {r['行业']:14s} 抽血{r['留存率']:+6.2f}%  净额{r['净额']:+7.1f}亿  成交{r['总额']:6.0f}亿  涨{r['行业-涨跌幅']:+.2f}%")

only_rate = set(out_rate['行业']) - set(out_abs['行业'])
print(f'\n>>> 只进留存率榜、不进绝对额榜的"隐形失血者": {only_rate if only_rate else "无"}')

print()
print('='*78)
print('【流入侧】绝对额TOP10 vs 留存率TOP10')
print('='*78)
in_abs = active[active['净额'] > 0].sort_values('净额', ascending=False).head(10)
in_rate = active[active['净额'] > 0].sort_values('留存率', ascending=False).head(10)
print('\n--- 按绝对额排 ---')
for _,r in in_abs.iterrows():
    print(f"  {r['行业']:14s} 净额{r['净额']:+7.1f}亿  成交{r['总额']:7.0f}亿  留存{r['留存率']:+5.2f}%")
print('\n--- 按留存率排 ---')
for _,r in in_rate.iterrows():
    print(f"  {r['行业']:14s} 留存{r['留存率']:+6.2f}%  净额{r['净额']:+6.1f}亿  成交{r['总额']:6.0f}亿")
only_r = set(in_rate['行业']) - set(in_abs['行业'])
print(f'\n>>> 只进留存率榜的"小而坚决": {only_r if only_r else "无"}')

# 规模分层检查: 大中小板块的留存率分布是否有系统性偏差
print()
print('='*78)
print('【规模偏差检查】留存率是否天然偏向小板块?')
print('='*78)
active['size_tier'] = pd.cut(active['总额'], [20,100,400,100000], labels=['小(<100亿)','中(100-400亿)','大(>400亿)'])
print(active.groupby('size_tier', observed=True)['留存率'].describe()[['count','mean','std','min','max']].round(2).to_string())
