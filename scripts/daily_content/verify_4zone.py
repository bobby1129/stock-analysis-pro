import os, sys
for k in ['HTTPS_PROXY','https_proxy','HTTP_PROXY','http_proxy']: os.environ.pop(k, None)
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro/scripts/daily_content'))
import akshare as ak
import pandas as pd
from generate_concept_html import is_bucket_concept

df = ak.stock_fund_flow_concept(symbol="即时")
for c in ['流入资金','流出资金','净额','行业-涨跌幅','公司家数','领涨股-涨跌幅']:
    df[c] = pd.to_numeric(df[c], errors='coerce')
df = df[~df['行业'].apply(is_bucket_concept)].copy()
df['总额'] = df['流入资金'] + df['流出资金']
df['留存率'] = df['净额']/df['总额']*100
df['能量'] = df['总额']/df['公司家数']   # 亿/只
active = df[df['总额']>20].copy()
med = active['能量'].median()
print(f'活跃板块{len(active)}个, 能量中位数={med:.2f}亿/只\n')

zones = {
 '主攻方向': active[(active['行业-涨跌幅']>=0.5)&(active['净额']>=3)&(active['留存率']>=3)&(active['能量']>=med)].sort_values('留存率',ascending=False),
 '潜伏吸筹': active[(active['行业-涨跌幅']<0.5)&(active['净额']>=3)&(active['留存率']>=4)].sort_values('留存率',ascending=False),
 '失血强度': active[(active['净额']<=-3)&(active['总额']>=50)].sort_values('留存率'),
 '对倒嫌疑': active[(active['行业-涨跌幅']>0.8)&(active['净额']>0)&(active['留存率']<1.5)&(active['总额']>=100)].sort_values('总额',ascending=False),
}
for z, sub in zones.items():
    print(f'【{z}】候选 {len(sub)} 个 (取前5):')
    for _,r in sub.head(5).iterrows():
        print(f'   {r["行业"]:12s} 涨{r["行业-涨跌幅"]:+6.2f}% 净{r["净额"]:+7.1f}亿 留存{r["留存率"]:+6.2f}% 能量{r["能量"]:5.2f}亿/只')
    print()

overlap1 = set(zones['主攻方向'].head(5)['行业']) & set(zones['对倒嫌疑'].head(5)['行业'])
overlap2 = set(zones['主攻方向'].head(5)['行业']) & set(zones['潜伏吸筹'].head(5)['行业'])
overlap3 = set(zones['失血强度'].head(5)['行业']) & set(zones['对倒嫌疑'].head(5)['行业'])
print('主攻∩对倒:', overlap1 or '无', '| 主攻∩潜伏:', overlap2 or '无', '| 失血∩对倒:', overlap3 or '无')
