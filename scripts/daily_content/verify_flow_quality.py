#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""资金流质量分析验证 - 用9/23数据测试四个价值维度
1.资金留存率 = 净额/(流入+流出) -> 识别巨量对倒型流入(隐患)
2.量价四象限 -> 缩量上涨(拉高出货嫌疑)/低位吸筹(埋伏机会)
3.人均吸金强度 = 净额/公司家数 -> 板块普吸vs个别股票吸
4.龙头依赖度 = 板块涨幅/领涨股涨幅 -> 一股独秀vs板块效应
"""
import os, sys
for k in ['HTTPS_PROXY','https_proxy','HTTP_PROXY','http_proxy']: os.environ.pop(k, None)
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro/scripts/daily_content'))
import akshare as ak
import pandas as pd
pd.set_option('display.width', 200)

from generate_concept_html import is_bucket_concept

df = ak.stock_fund_flow_concept(symbol="即时")
for c in ['流入资金','流出资金','净额','行业-涨跌幅','公司家数','领涨股-涨跌幅']:
    df[c] = pd.to_numeric(df[c], errors='coerce')
df = df[~df['行业'].apply(is_bucket_concept)].copy()

df['总额'] = df['流入资金'] + df['流出资金']
df['留存率'] = df['净额'] / df['总额'] * 100          # %
df['人均吸金'] = df['净额'] / df['公司家数']            # 亿/家
df['龙头依赖'] = df['行业-涨跌幅'] / df['领涨股-涨跌幅'].replace(0, float('nan'))

print('='*70)
print('维度1: 资金留存率 — 净流入TOP10里的"对倒嫌疑"')
print('='*70)
top10 = df.sort_values('净额', ascending=False).head(10)
for _, r in top10.iterrows():
    flag = '⚠️对倒嫌疑' if r['留存率'] < 1.5 else ('✓坚决' if r['留存率'] > 5 else '中性')
    print(f"  {r['行业']:12s} 净额{r['净额']:+6.1f}亿 总成交{r['总额']:7.1f}亿 留存率{r['留存率']:5.2f}% {flag}")

print()
print('='*70)
print('维度2: 量价背离 — 涨幅>1%但净额<0 (拉高出货嫌疑)')
print('='*70)
diverge = df[(df['行业-涨跌幅'] > 1.0) & (df['净额'] < 0)].sort_values('净额')
for _, r in diverge.head(8).iterrows():
    print(f"  {r['行业']:12s} 涨幅{r['行业-涨跌幅']:+.2f}% 净额{r['净额']:+7.2f}亿 领涨{r['领涨股']}({r['领涨股-涨跌幅']:+.1f}%)")

print()
print('='*70)
print('维度3: 低位吸筹 — 净额>5亿但涨幅<0.5% (资金进场价格未动)')
print('='*70)
absorb = df[(df['净额'] > 5) & (df['行业-涨跌幅'] < 0.5)].sort_values('净额', ascending=False)
for _, r in absorb.head(8).iterrows():
    print(f"  {r['行业']:12s} 净额{r['净额']:+6.1f}亿 涨幅{r['行业-涨跌幅']:+.2f}% 家数{int(r['公司家数'])}")

print()
print('='*70)
print('维度4: 龙头依赖度 — 净流入TOP10里板块是普涨还是一股独秀')
print('='*70)
for _, r in top10.iterrows():
    dep = r['龙头依赖']
    tag = '⚠️一股独秀' if dep < 0.5 else ('✓板块效应' if dep > 0.8 else '中性')
    print(f"  {r['行业']:12s} 板块{r['行业-涨跌幅']:+.2f}% vs 龙头{r['领涨股']}({r['领涨股-涨跌幅']:+.1f}%) 依赖度{dep:.2f} {tag}")
