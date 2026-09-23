#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""概念板块 量价资金 2D矩阵分析 - 9/23全量373概念
核心: 涨幅(价格维度) × 资金(留存率/净额) 交叉, 识别主力意图而非搬运结果
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
df['留存率'] = df['净额'] / df['总额'] * 100   # 资金 conviction, 归一化可跨板块比

# 只看有一定成交量的板块(过滤僵尸概念), 总额>20亿
df = df[df['总额'] > 20].copy()
print(f'活跃概念(总成交>20亿): {len(df)} 个\n')

chg = df['行业-涨跌幅']; net = df['净额']; ret = df['留存率']

print('='*72)
print('【象限分布】涨幅 × 净额')
print('='*72)
q1 = df[(chg>0.3)&(net>0)]    # 涨+流入
q2 = df[(chg>0.3)&(net<0)]    # 涨+流出 = 背离
q3 = df[(chg<-0.3)&(net>0)]   # 跌+流入 = 低吸
q4 = df[(chg<-0.3)&(net<0)]   # 跌+流出 = 回避
q0 = df[(chg.abs()<=0.3)]     # 横盘
print(f'  Q1 涨+流入(健康): {len(q1)}   Q2 涨+流出(背离): {len(q2)}')
print(f'  Q3 跌+流入(低吸): {len(q3)}   Q4 跌+流出(回避): {len(q4)}   横盘: {len(q0)}')

def show(title, sub, n=8, sortcol='净额', asc=False):
    print(f'\n{"="*72}\n{title}\n{"="*72}')
    s = sub.sort_values(sortcol, ascending=asc).head(n)
    for _,r in s.iterrows():
        print(f"  {r['行业']:14s} 涨幅{r['行业-涨跌幅']:+6.2f}% 净额{r['净额']:+7.2f}亿 留存率{r['留存率']:+5.2f}% 龙头{r['领涨股']}({r['领涨股-涨跌幅']:+.1f}%)")

# A. 真主线: 涨幅>1% + 留存率高 (量价资金三共振)
show('【A 真主线】涨幅>1% 且 留存率>3% (价涨+钱留,主力坚决)',
     df[(df['行业-涨跌幅']>1.0)&(df['留存率']>3)], sortcol='留存率')

# B. 背离派发: 涨幅>0.5% 但净流出 (涨是假的,钱在跑)
show('【B 背离警示】涨幅>0.5% 但净额<0 (拉高出货嫌疑)',
     df[(df['行业-涨跌幅']>0.5)&(df['净额']<0)], sortcol='净额', asc=True)

# C. 潜伏吸筹: 涨幅小(<0.5%) 但留存率高/净额大 (钱进价未动)
show('【C 潜伏吸筹】涨幅<0.5% 且 留存率>4% (资金埋伏,价格未启动)',
     df[(df['行业-涨跌幅']<0.5)&(df['留存率']>4)], sortcol='留存率')

# D. 对倒嫌疑: 涨幅>1% 净额>0 但留存率<1.5% (天量换手,净额是假象)
show('【D 对倒嫌疑】涨幅>1% 净额>0 但留存率<1.5% (巨量换手,小心出货)',
     df[(df['行业-涨跌幅']>1.0)&(df['净额']>0)&(df['留存率']<1.5)], sortcol='总额', )

# E. 低吸: 跌幅明显但净流入 (恐慌中吸筹)
show('【E 恐慌低吸】涨幅<-0.5% 但净额>0 (逆势吸筹)',
     df[(df['行业-涨跌幅']<-0.5)&(df['净额']>0)], sortcol='净额')
