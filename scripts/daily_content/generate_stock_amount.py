#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成个股成交额TOP10 HTML - 新浪全市场数据"""

import sys, os
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))

for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

import requests
import json
from datetime import datetime, timedelta


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
    
    # 按成交额排序，取前50（缓存扩容，用于环比计算）
    all_stocks.sort(key=lambda x: x['amount'], reverse=True)
    return all_stocks[:50]


def fetch_yesterday_amount(codes):
    """从本地缓存文件读取昨日成交额"""
    cache_dir = os.path.expanduser('~/stock-analysis-pro/cache/daily_content')
    yesterday_amount = {}
    
    # 获取最近的交易日（简单回退，跳过周末）
    today = datetime.now()
    for delta in range(1, 5):
        d = today - timedelta(days=delta)
        date_key = d.strftime("%Y%m%d")
        cache_file = os.path.join(cache_dir, f'stock_amount_cache_{date_key}.json')
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                for item in cached:
                    if item['code'] in codes:
                        yesterday_amount[item['code']] = item['amount']
                print(f"✓ 读取昨日缓存: {date_key}, {len(yesterday_amount)} 只匹配")
                return yesterday_amount
            except Exception as e:
                print(f"读取缓存失败: {e}")
    
    print("⚠ 未找到昨日缓存文件")
    return yesterday_amount


def fetch_yesterday_top10_codes():
    """从本地缓存文件读取昨日top10的代码集合"""
    cache_dir = os.path.expanduser('~/stock-analysis-pro/cache/daily_content')
    today = datetime.now()
    for delta in range(1, 5):
        d = today - timedelta(days=delta)
        date_key = d.strftime("%Y%m%d")
        cache_file = os.path.join(cache_dir, f'stock_amount_cache_{date_key}.json')
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                # 取前10个（按成交额排序，缓存已是排序后的）
                top10_codes = set(item['code'] for item in cached[:10])
                print(f"✓ 读取昨日top10: {date_key}, {len(top10_codes)} 只")
                return top10_codes
            except Exception as e:
                print(f"读取昨日top10失败: {e}")
    print("⚠ 未找到昨日top10缓存")
    return set()


def save_amount_cache(stocks):
    """保存当日成交额到缓存文件"""
    cache_dir = os.path.expanduser('~/stock-analysis-pro/cache/daily_content')
    os.makedirs(cache_dir, exist_ok=True)
    date_key = datetime.now().strftime("%Y%m%d")
    cache_file = os.path.join(cache_dir, f'stock_amount_cache_{date_key}.json')
    
    cache_data = [{'name': s['name'], 'code': s['code'], 'amount': s['amount']} for s in stocks]
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False)
    print(f"✓ 缓存已保存: {cache_file}")


def format_amount(amount):
    """格式化成交额"""
    if amount >= 1e8:
        return f"{amount/1e8:.2f}亿"
    elif amount >= 1e4:
        return f"{amount/1e4:.2f}万"
    else:
        return f"{amount:.2f}"


def generate_html(stocks, yesterday_amount, yesterday_top10_codes):
    """生成HTML，stocks为前50只，只展示前10只。yesterday_top10_codes为昨日top10的代码集合。"""
    rows_html = ""
    display_stocks = stocks[:10]  # 只展示前10
    for i, s in enumerate(display_stocks, 1):
        change_color = "#ff4757" if s['change_pct'] > 0 else "#2ed573" if s['change_pct'] < 0 else "#ffffff"
        amount_str = format_amount(s['amount'])
        
        # 计算环比增减
        code = s['code']
        if code in yesterday_amount and yesterday_amount[code] > 0:
            ratio = (s['amount'] - yesterday_amount[code]) / yesterday_amount[code] * 100
            ratio_str = f"{ratio:+.1f}%"
            ratio_color = "#ff4757" if ratio > 0 else "#2ed573" if ratio < 0 else "#ffffff"
        else:
            ratio_str = "N/A"
            ratio_color = "#888"
        
        # 新进入top10标记
        is_new = code not in yesterday_top10_codes
        new_badge = '<span class="new-badge">NEW</span>' if is_new else ''
        
        rows_html += f'''
        <div class="stock-row">
            <div class="rank">{i}</div>
            <div class="stock-name">{s['name']}{new_badge}</div>
            <div class="stock-price">{s['price']}</div>
            <div class="stock-change" style="color:{change_color}">{s['change_pct']:+.2f}%</div>
            <div class="stock-amount">{amount_str}</div>
            <div class="stock-ratio" style="color:{ratio_color}">{ratio_str}</div>
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
    width: 160px;
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
.header-ratio {{
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
.new-badge {{
    display: inline-block;
    font-size: 18px;
    font-weight: bold;
    color: #ffd700;
    background: rgba(255,215,0,0.2);
    border-radius: 4px;
    padding: 2px 6px;
    margin-left: 8px;
    vertical-align: middle;
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
    width: 160px;
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
.stock-ratio {{
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
        <div class="header-price">现价</div>
        <div class="header-change">涨幅</div>
        <div class="header-amount">成交额</div>
        <div class="header-ratio">环比</div>
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
    print(f"获取 {len(stocks)} 只")
    
    # 获取昨日成交额用于计算环比
    codes = [s['code'] for s in stocks]
    print("获取昨日成交额数据...")
    yesterday_amount = fetch_yesterday_amount(codes)
    print(f"获取到 {len(yesterday_amount)} 只股票的昨日数据")
    
    # 获取昨日top10代码集合（用于新进标记）
    yesterday_top10_codes = fetch_yesterday_top10_codes()
    
    output_dir = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    
    print("生成成交额TOP10...")
    html = generate_html(stocks, yesterday_amount, yesterday_top10_codes)
    output_file = os.path.join(output_dir, f'stock_amount_top10_{date_str}.html')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✓ {output_file}")
    
    # 保存当日成交额缓存（前50只，供次日环比计算）
    save_amount_cache(stocks)
