#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成个股成交额TOP10 HTML - 新浪全市场数据"""

import sys, os
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))

for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

import requests
import json
from datetime import datetime


def fetch_stock_amount():
    """新浪行情接口 - 全市场按成交额排序"""
    url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://finance.sina.com.cn"
    }
    
    all_stocks = []
    
    # 获取沪深A股，按成交额排序
    for market_node in ["sh_a", "sz_a"]:
        for page in range(1, 10):  # 取前10页足够覆盖TOP10
            params = {
                "page": page,
                "num": 100,
                "sort": "amount",  # 按成交额排序
                "asc": 0,  # 降序
                "node": market_node,
                "symbol": "",
                "_s_r_a": "page",
            }
            try:
                r = requests.get(url, params=params, headers=headers, timeout=15)
                if r.text.startswith('['):
                    data = json.loads(r.text)
                    if not data:
                        break
                    for item in data:
                        all_stocks.append({
                            'name': item.get('name', ''),
                            'code': item.get('code', ''),
                            'price': item.get('trade', ''),
                            'change_pct': float(item.get('changepercent', 0)),
                            'amount': float(item.get('amount', 0)),  # 成交额（元）
                        })
                else:
                    break
            except Exception as e:
                print(f"获取失败: {e}")
                break
    
    # 按成交额排序，取前10
    all_stocks.sort(key=lambda x: x['amount'], reverse=True)
    return all_stocks[:10]


def format_amount(amount):
    """格式化成交额"""
    if amount >= 1e8:
        return f"{amount/1e8:.2f}亿"
    elif amount >= 1e4:
        return f"{amount/1e4:.2f}万"
    else:
        return f"{amount:.2f}"


def generate_html(stocks):
    rows_html = ""
    for i, s in enumerate(stocks, 1):
        change_color = "#ff4757" if s['change_pct'] > 0 else "#2ed573" if s['change_pct'] < 0 else "#ffffff"
        amount_str = format_amount(s['amount'])
        
        rows_html += f'''
        <div class="stock-row">
            <div class="rank">{i}</div>
            <div class="stock-name">{s['name']}</div>
            <div class="stock-code">{s['code']}</div>
            <div class="stock-price">{s['price']}</div>
            <div class="stock-change" style="color:{change_color}">{s['change_pct']:+.2f}%</div>
            <div class="stock-amount">{amount_str}</div>
        </div>
        '''
    
    date_str = datetime.now().strftime("%Y年%m月%d日")
    
    html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: 1080px;
    height: 1920px;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    color: #fff;
    padding: 120px 60px 120px;
    overflow: hidden;
}}
.header {{
    text-align: center;
    margin-bottom: 50px;
}}
.date {{
    font-size: 32px;
    color: #888;
    margin-bottom: 15px;
}}
.title {{
    font-size: 64px;
    font-weight: bold;
    background: linear-gradient(90deg, #ffd700, #ffb700);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}}
.table-header {{
    display: flex;
    align-items: center;
    padding: 20px 30px;
    background: rgba(255,255,255,0.05);
    border-radius: 15px;
    margin-bottom: 25px;
    border: 1px solid rgba(255,215,0,0.2);
}}
.header-rank {{
    font-size: 28px;
    color: #ffd700;
    width: 50px;
    flex-shrink: 0;
}}
.header-name {{
    font-size: 28px;
    color: #ffd700;
    width: 140px;
    flex-shrink: 0;
}}
.header-code {{
    font-size: 28px;
    color: #ffd700;
    width: 100px;
    flex-shrink: 0;
}}
.header-price {{
    font-size: 28px;
    color: #ffd700;
    flex: 1;
    text-align: right;
}}
.header-change {{
    font-size: 28px;
    color: #ffd700;
    flex: 1;
    text-align: right;
}}
.header-amount {{
    font-size: 28px;
    color: #ffd700;
    flex: 1;
    text-align: right;
}}
.stock-row {{
    display: flex;
    align-items: center;
    padding: 28px 30px;
    background: rgba(255,255,255,0.05);
    border-radius: 15px;
    margin-bottom: 25px;
    border: 1px solid rgba(255,215,0,0.1);
}}
.rank {{
    font-size: 36px;
    font-weight: bold;
    color: #ffd700;
    width: 50px;
    flex-shrink: 0;
}}
.stock-name {{
    font-size: 32px;
    font-weight: bold;
    width: 140px;
    flex-shrink: 0;
}}
.stock-code {{
    font-size: 28px;
    color: #888;
    width: 100px;
    flex-shrink: 0;
}}
.stock-price {{
    font-size: 32px;
    flex: 1;
    text-align: right;
}}
.stock-change {{
    font-size: 32px;
    flex: 1;
    text-align: right;
}}
.stock-amount {{
    font-size: 32px;
    flex: 1;
    text-align: right;
}}
.footer {{
    text-align: center;
    margin-top: 50px;
    font-size: 24px;
    color: #666;
}}
</style>
</head>
<body>
    <div class="header">
        <div class="date">{date_str}</div>
        <div class="title">个股成交额 TOP10</div>
    </div>
    
    <div class="table-header">
        <div class="header-rank">排名</div>
        <div class="header-name">股票</div>
        <div class="header-code">代码</div>
        <div class="header-price">现价</div>
        <div class="header-change">涨幅</div>
        <div class="header-amount">成交额</div>
    </div>
    
    {rows_html}
    
    <div class="footer">
        数据来源：新浪财经 | 仅供参考，不构成投资建议
    </div>
</body>
</html>'''
    
    return html


if __name__ == '__main__':
    print("采集个股成交额数据（新浪全市场）...")
    stocks = fetch_stock_amount()
    print(f"获取 {len(stocks)} 只股票")
    
    output_dir = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    
    print("生成成交额TOP10...")
    html = generate_html(stocks)
    output_file = os.path.join(output_dir, f'stock_amount_top10_{date_str}.html')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✓ {output_file}")
