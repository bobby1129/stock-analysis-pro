#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成新进成交额TOP50 HTML - 首次进入TOP50的股票"""

import sys, os
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))

for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

import requests
import json
from datetime import datetime, timedelta
from stock_short_names import get_short_name


def fetch_stock_amount():
    """新浪行情接口 - 全市场按成交额排序，取前50"""
    url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://finance.sina.com.cn"
    }
    
    all_stocks = []
    
    for market_node in ["sh_a", "sz_a"]:
        for page in range(1, 10):
            params = {
                "page": page,
                "num": 100,
                "sort": "amount",
                "asc": 0,
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
                            'amount': float(item.get('amount', 0)),
                        })
                else:
                    break
            except Exception as e:
                print(f"获取失败: {e}")
                break
    
    all_stocks.sort(key=lambda x: x['amount'], reverse=True)
    return all_stocks[:50]


def fetch_yesterday_top50_codes():
    """从本地缓存文件读取昨日top50的代码集合"""
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
                top50_codes = set(item['code'] for item in cached[:50])
                print(f"✓ 读取昨日top50缓存: {date_key}, {len(top50_codes)} 只")
                return top50_codes
            except Exception as e:
                print(f"读取缓存失败: {e}")
    print("⚠ 未找到昨日top50缓存")
    return set()


def format_amount(amount):
    """格式化成交额"""
    if amount >= 1e8:
        return f"{amount/1e8:.2f}亿"
    elif amount >= 1e4:
        return f"{amount/1e4:.2f}万"
    else:
        return f"{amount:.2f}"


def generate_html(new_stocks, page=1, total_pages=1):
    """生成HTML，展示新进TOP50的股票，支持分页"""
    # 分页逻辑
    items_per_page = 10 if total_pages > 1 else len(new_stocks)
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    page_stocks = new_stocks[start_idx:end_idx]
    
    if not page_stocks:
        rows_html = '''
        <div class="empty-row">
            <div class="empty-text">今日无新进TOP50股票</div>
        </div>
        '''
    else:
        rows_html = ""
        for i, s in enumerate(page_stocks, start_idx + 1):
            change_color = "#dc143c" if s['change_pct'] > 0 else "#228b22" if s['change_pct'] < 0 else "#1a1a1a"
            amount_str = format_amount(s['amount'])
            
            rows_html += f'''
            <div class="stock-row">
                <div class="rank">{i}</div>
                <div class="stock-name">{get_short_name(s['name'])}</div>
                <div class="stock-price">{s['price']}</div>
                <div class="stock-change" style="color:{change_color}">{s['change_pct']:+.2f}%</div>
                <div class="stock-amount">{amount_str}</div>
            </div>
            '''
    
    date_str = datetime.now().strftime("%Y年%m月%d日")
    count = len(new_stocks)
    page_info = f"第{page}/{total_pages}页" if total_pages > 1 else ""
    
    html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: 1080px;
    height: 1920px;
    background: linear-gradient(180deg, #faf9f6 0%, #f5f3ee 100%);
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    color: #1a1a1a;
    padding: 100px 45px 80px;
    overflow: hidden;
}}
.header {{
    text-align: center;
    margin-bottom: 30px;
}}
.date {{
    font-size: 32px;
    color: #666;
    margin-bottom: 8px;
    letter-spacing: 4px;
}}
.title {{
    font-size: 60px;
    font-weight: 800;
    background: linear-gradient(90deg, #d4af37, #b8860b, #d4af37);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: 6px;
}}
.subtitle {{
    font-size: 28px;
    color: #888;
    margin-top: 8px;
}}
.table-header {{
    display: flex;
    align-items: center;
    padding: 16px 28px;
    background: rgba(212,175,55,0.08);
    border-radius: 14px;
    margin-bottom: 12px;
    border: 2px solid #d4af37;
}}
.header-rank {{
    font-size: 28px;
    color: #b8860b;
    font-weight: 700;
    width: 55px;
    flex-shrink: 0;
}}
.header-name {{
    font-size: 28px;
    color: #b8860b;
    font-weight: 700;
    width: 260px;
    flex-shrink: 0;
}}
.header-price {{
    font-size: 28px;
    color: #b8860b;
    font-weight: 700;
    flex: 1;
    text-align: right;
}}
.header-change {{
    font-size: 28px;
    color: #b8860b;
    font-weight: 700;
    flex: 1;
    text-align: right;
}}
.header-amount {{
    font-size: 28px;
    color: #b8860b;
    font-weight: 700;
    flex: 1;
    text-align: right;
}}
.stock-row {{
    display: flex;
    align-items: center;
    padding: 16px 28px;
    background: #fff;
    border-radius: 14px;
    margin-bottom: 10px;
    border: 1px solid #e8e4d9;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}}
.rank {{
    font-size: 36px;
    font-weight: 800;
    color: #b8860b;
    width: 55px;
    flex-shrink: 0;
}}
.stock-name {{
    font-size: 32px;
    font-weight: 700;
    color: #1a1a1a;
    width: 260px;
    flex-shrink: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.stock-price {{
    font-size: 30px;
    flex: 1;
    text-align: right;
    font-weight: 500;
}}
.stock-change {{
    font-size: 32px;
    font-weight: 800;
    flex: 1;
    text-align: right;
}}
.stock-amount {{
    font-size: 30px;
    font-weight: 600;
    flex: 1;
    text-align: right;
}}
.empty-row {{
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 80px 28px;
    background: #fff;
    border-radius: 14px;
    border: 1px solid #e8e4d9;
}}
.empty-text {{
    font-size: 36px;
    color: #999;
}}
.footer {{
    text-align: center;
    margin-top: 30px;
    font-size: 26px;
    color: #999;
}}
</style>
</head>
<body>
    <div class="header">
        <div class="date">{date_str}</div>
        <div class="title">新进成交额TOP50</div>
        <div class="subtitle">首次进入成交额前50 · 共{count}只 {page_info}</div>
    </div>
    
    <div class="table-header">
        <div class="header-rank">#</div>
        <div class="header-name">股票</div>
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
    print(f"获取 {len(stocks)} 只")
    
    print("获取昨日TOP50数据...")
    yesterday_top50_codes = fetch_yesterday_top50_codes()
    
    # 找出新进TOP50的股票（今日在top50但昨日不在）
    new_stocks = []
    for s in stocks:
        if s['code'] not in yesterday_top50_codes:
            new_stocks.append(s)
    
    print(f"新进TOP50: {len(new_stocks)} 只")
    for s in new_stocks:
        print(f"  {s['name']} ({s['code']}) 成交额: {format_amount(s['amount'])}")
    
    output_dir = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    
    # 分页规则：≤15只→1页展示完；>15只→每页10只
    total = len(new_stocks)
    if total <= 15:
        pages = [1]
        total_pages = 1
    else:
        total_pages = (total + 9) // 10  # 每页10只
        pages = list(range(1, total_pages + 1))
    
    print(f"分页：共{total_pages}页")
    for page in pages:
        print(f"生成新进TOP50 HTML (第{page}/{total_pages}页)...")
        html = generate_html(new_stocks, page=page, total_pages=total_pages)
        if total_pages == 1:
            output_file = os.path.join(output_dir, f'new_top50_{date_str}.html')
        else:
            output_file = os.path.join(output_dir, f'new_top50_p{page}_{date_str}.html')
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"✓ {output_file}")
