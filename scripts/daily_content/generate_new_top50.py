#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成新进成交额TOP50 HTML - 首次进入TOP50的股票
含: IP角标(盘后情报局 Vol.N) + 自动研判句 + 量比/换手列(腾讯源) + 巨量绿柱⚠信号标注
"""

import sys, os
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

import requests
import json
from datetime import datetime, timedelta
from stock_short_names import get_short_name
from generate_stock_amount import get_episode_vol


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


def fetch_yesterday_top50_codes(prev_date=None):
    """从本地缓存文件读取昨日top50的代码集合。prev_date可指定YYYYMMDD(测试用)"""
    cache_dir = os.path.expanduser('~/stock-analysis-pro/cache/daily_content')
    if prev_date:
        deltas = [None]
        dates = [prev_date]
    else:
        today = datetime.now()
        dates = [(today - timedelta(days=d)).strftime("%Y%m%d") for d in range(1, 5)]
    for date_key in dates:
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


def fetch_tencent_extras(codes):
    """腾讯批量接口补充量比/换手率。返回 {code: {'volume_ratio':float,'turnover':float}}
    字段映射已验证(2026-09-25): parts[1]名称 parts[38]换手 parts[49]量比"""
    extras = {}
    if not codes:
        return extras
    syms = []
    for c in codes:
        prefix = 'sh' if c.startswith(('6', '9', '5')) else 'sz'
        syms.append(prefix + c)
    try:
        r = requests.get('https://qt.gtimg.cn/q=' + ','.join(syms), timeout=10)
        r.encoding = 'gbk'
        for line in r.text.strip().split(';'):
            line = line.strip()
            if not line or '=' not in line:
                continue
            parts = line.split('=', 1)[1].strip('"').split('~')
            if len(parts) < 50:
                continue
            try:
                extras[parts[2]] = {
                    'volume_ratio': float(parts[49]) if parts[49] else 0,
                    'turnover': float(parts[38]) if parts[38] else 0,
                }
            except (ValueError, IndexError):
                continue
        print(f"✓ 腾讯量比/换手补充: {len(extras)}/{len(codes)} 只")
    except Exception as e:
        print(f"⚠ 腾讯接口失败(量比/换手显示为—): {e}")
    return extras


def classify_signal(s, extras):
    """信号分类: danger=巨量绿柱(量比>2且下跌) / inflow=温和放量上涨(量比>1.2且上涨) / None"""
    ex = extras.get(s['code'], {})
    vr = ex.get('volume_ratio', 0) or 0
    cp = s['change_pct']
    if vr > 2 and cp < 0:
        return 'danger'
    if vr > 1.2 and cp > 0:
        return 'inflow'
    return None


def build_verdict(new_stocks, extras):
    """从当日数据自动生成一句研判（每天内容必不同，打破模板指纹）"""
    total = len(new_stocks)
    if total == 0:
        return "今日榜单零换血——资金锁仓主线，无新面孔进场"
    up = sum(1 for s in new_stocks if s['change_pct'] > 0)
    down = sum(1 for s in new_stocks if s['change_pct'] < 0)
    dangers = [s for s in new_stocks if classify_signal(s, extras) == 'danger']
    inflows = [s for s in new_stocks if classify_signal(s, extras) == 'inflow']
    red_green = f"{up}红{down}绿" if down > 0 and up > 0 else (f"{up}红" if down == 0 else f"{down}绿")
    parts = [f"今日<span class='red'>{total}</span>只新进榜（{red_green}）"]
    if dangers:
        names = "、".join(get_short_name(s['name']) for s in dangers[:3])
        parts.append(f"<span class='green'>{len(dangers)}只巨量绿柱⚠</span>：{names}等，警惕次日低开")
    elif inflows:
        names = "、".join(get_short_name(s['name']) for s in inflows[:3])
        parts.append(f"<span class='red'>{len(inflows)}只放量上涨</span>：{names}等，资金真实进场")
    else:
        parts.append("无巨量异动，多为温和换手进榜")
    return "｜".join(parts)


def format_amount(amount):
    """格式化成交额"""
    if amount >= 1e8:
        return f"{amount/1e8:.2f}亿"
    elif amount >= 1e4:
        return f"{amount/1e4:.2f}万"
    else:
        return f"{amount:.2f}"


def generate_html(new_stocks, extras, verdict, vol, page=1, total_pages=1):
    """生成HTML，展示新进TOP50的股票，支持分页"""
    # 分页逻辑
    total = len(new_stocks)
    if total <= 10:
        # ≤10只：单页大字体
        items_per_page = total
        font_size = 'large'
    elif total <= 15:
        # 11-15只：单页小字体
        items_per_page = total
        font_size = 'small'
    else:
        # >15只：分页，每页10只，大字体
        items_per_page = 10
        font_size = 'large'
    
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
            ex = extras.get(s['code'], {})
            vr = ex.get('volume_ratio', 0) or 0
            to = ex.get('turnover', 0) or 0
            vr_str = f"{vr:.2f}" if vr else "—"
            to_str = f"{to:.1f}%" if to else "—"
            # 量比>2标红加重
            vr_color = "#dc143c" if vr > 2 else "#1a1a1a"
            vr_weight = "800" if vr > 2 else "500"
            # 信号角标
            sig = classify_signal(s, extras)
            if sig == 'danger':
                badge = '<span class="sig-badge danger" title="巨量绿柱">⚠巨量绿柱</span>'
            elif sig == 'inflow':
                badge = '<span class="sig-badge inflow">🟢资金进场</span>'
            else:
                badge = ''
            
            rows_html += f'''
            <div class="stock-row{' row-danger' if sig == 'danger' else ''}">
                <div class="rank">{i}</div>
                <div class="stock-name">{get_short_name(s['name'])}{badge}</div>
                <div class="stock-price">{s['price']}</div>
                <div class="stock-change" style="color:{change_color}">{s['change_pct']:+.2f}%</div>
                <div class="stock-vr" style="color:{vr_color};font-weight:{vr_weight}">{vr_str}</div>
                <div class="stock-to">{to_str}</div>
                <div class="stock-amount">{amount_str}</div>
            </div>
            '''
    
    date_str = datetime.now().strftime("%Y年%m月%d日")
    count = len(new_stocks)
    page_info = f"第{page}/{total_pages}页" if total_pages > 1 else ""
    
    if font_size == 'large':
        row_padding = '24px 24px'
        row_margin = '16px'
        rank_size = '38px'
        name_size = '33px'
        price_size = '30px'
        change_size = '32px'
        vr_size = '30px'
        to_size = '28px'
        amount_size = '30px'
        header_size = '26px'
        header_padding = '20px 24px'
        header_margin = '18px'
        badge_size = '20px'
    else:
        row_padding = '11px 24px'
        row_margin = '7px'
        rank_size = '32px'
        name_size = '28px'
        price_size = '26px'
        change_size = '28px'
        vr_size = '26px'
        to_size = '24px'
        amount_size = '26px'
        header_size = '23px'
        header_padding = '14px 24px'
        header_margin = '11px'
        badge_size = '17px'
    
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
    padding: 90px 40px 90px;
    overflow: hidden;
}}
.header {{
    text-align: center;
    margin-bottom: 18px;
}}
.kicker {{
    display: inline-block;
    font-size: 28px;
    font-weight: 800;
    letter-spacing: 3px;
    color: #b8860b;
    border: 2px solid #d4af37;
    border-radius: 10px;
    padding: 6px 16px;
    background: rgba(212,175,55,0.08);
    margin-bottom: 16px;
}}
.date {{
    font-size: 30px;
    color: #666;
    margin-bottom: 8px;
    letter-spacing: 4px;
}}
.title {{
    font-size: 62px;
    font-weight: 800;
    background: linear-gradient(90deg, #d4af37, #b8860b, #d4af37);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: 6px;
}}
.subtitle {{
    font-size: 27px;
    color: #888;
    margin-top: 8px;
}}
.verdict {{
    background: #fff;
    border: 2px solid #d4af37;
    border-left: 12px solid #b8860b;
    border-radius: 16px;
    padding: 16px 22px;
    font-size: 29px;
    font-weight: 800;
    color: #1a1a1a;
    line-height: 1.45;
    box-shadow: 0 4px 14px rgba(184,134,11,0.10);
    margin-bottom: 16px;
}}
.verdict .red {{ color: #dc143c; }}
.verdict .green {{ color: #228b22; }}
.table-header {{
    display: flex;
    align-items: center;
    padding: {header_padding};
    background: rgba(212,175,55,0.08);
    border-radius: 14px;
    margin-bottom: {header_margin};
    border: 2px solid #d4af37;
}}
.header-rank {{
    font-size: {header_size};
    color: #b8860b;
    font-weight: 700;
    width: 50px;
    flex-shrink: 0;
}}
.header-name {{
    font-size: {header_size};
    color: #b8860b;
    font-weight: 700;
    width: 290px;
    flex-shrink: 0;
}}
.header-price {{
    font-size: {header_size};
    color: #b8860b;
    font-weight: 700;
    flex: 1;
    text-align: right;
}}
.header-change {{
    font-size: {header_size};
    color: #b8860b;
    font-weight: 700;
    flex: 1;
    text-align: right;
}}
.header-vr {{
    font-size: {header_size};
    color: #b8860b;
    font-weight: 700;
    flex: 1;
    text-align: right;
}}
.header-to {{
    font-size: {header_size};
    color: #b8860b;
    font-weight: 700;
    flex: 1;
    text-align: right;
}}
.header-amount {{
    font-size: {header_size};
    color: #b8860b;
    font-weight: 700;
    flex: 1;
    text-align: right;
}}
.stock-row {{
    display: flex;
    align-items: center;
    padding: {row_padding};
    background: #fff;
    border-radius: 14px;
    margin-bottom: {row_margin};
    border: 1px solid #e8e4d9;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}}
.stock-row.row-danger {{
    border: 2px solid rgba(34,139,34,0.55);
    background: #f6fbf6;
}}
.rank {{
    font-size: {rank_size};
    font-weight: 800;
    color: #b8860b;
    width: 50px;
    flex-shrink: 0;
}}
.stock-name {{
    font-size: {name_size};
    font-weight: 700;
    color: #1a1a1a;
    width: 290px;
    flex-shrink: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.sig-badge {{
    display: inline-block;
    font-size: {badge_size};
    font-weight: 800;
    border-radius: 8px;
    padding: 2px 8px;
    margin-left: 8px;
    vertical-align: middle;
    white-space: nowrap;
}}
.sig-badge.danger {{
    color: #fff;
    background: #228b22;
}}
.sig-badge.inflow {{
    color: #fff;
    background: #dc143c;
}}
.stock-price {{
    font-size: {price_size};
    flex: 1;
    text-align: right;
    font-weight: 500;
}}
.stock-change {{
    font-size: {change_size};
    font-weight: 800;
    flex: 1;
    text-align: right;
}}
.stock-vr {{
    font-size: {vr_size};
    flex: 1;
    text-align: right;
}}
.stock-to {{
    font-size: {to_size};
    flex: 1;
    text-align: right;
    color: #555;
}}
.stock-amount {{
    font-size: {amount_size};
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
    margin-top: 20px;
    font-size: 24px;
    color: #999;
}}
.footer .brand {{ color: #b8860b; font-weight: 800; }}
</style>
</head>
<body>
    <div class="header">
        <div class="kicker">盘后情报局 · Vol.{vol}</div>
        <div class="date">{date_str}</div>
        <div class="title">新进成交额TOP50</div>
        <div class="subtitle">首次进入成交额前50 · 共{count}只 {page_info}</div>
    </div>
    
    <div class="verdict">💡 {verdict}</div>
    
    <div class="table-header">
        <div class="header-rank">#</div>
        <div class="header-name">股票</div>
        <div class="header-price">现价</div>
        <div class="header-change">涨幅</div>
        <div class="header-vr">量比</div>
        <div class="header-to">换手</div>
        <div class="header-amount">成交额</div>
    </div>
    
    {rows_html}
    
    <div class="footer">
        <span class="brand">盘后情报局</span> · 数据来源：新浪财经/腾讯行情 | 仅供参考，不构成投资建议
    </div>
</body>
</html>'''
    
    return html


if __name__ == '__main__':
    prev_date = None
    if '--prev-date' in sys.argv:
        prev_date = sys.argv[sys.argv.index('--prev-date') + 1]
        print(f"[测试模式] 对比缓存日期: {prev_date}")

    print("采集个股成交额数据（新浪全市场）...")
    stocks = fetch_stock_amount()
    print(f"获取 {len(stocks)} 只")
    
    print("获取昨日TOP50数据...")
    yesterday_top50_codes = fetch_yesterday_top50_codes(prev_date)
    
    # 找出新进TOP50的股票（今日在top50但昨日不在）
    new_stocks = []
    for s in stocks:
        if s['code'] not in yesterday_top50_codes:
            new_stocks.append(s)
    
    print(f"新进TOP50: {len(new_stocks)} 只")

    # 腾讯补充量比/换手
    extras = fetch_tencent_extras([s['code'] for s in new_stocks])

    for s in new_stocks:
        ex = extras.get(s['code'], {})
        sig = classify_signal(s, extras)
        sig_txt = {'danger': ' ⚠巨量绿柱', 'inflow': ' 🟢资金进场'}.get(sig, '')
        print(f"  {s['name']} ({s['code']}) 成交额: {format_amount(s['amount'])} "
              f"量比{ex.get('volume_ratio', 0):.2f} 换手{ex.get('turnover', 0):.1f}%{sig_txt}")

    verdict = build_verdict(new_stocks, extras)
    vol = get_episode_vol()
    print(f"研判: {verdict}")

    output_dir = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    
    # 分页规则：≤10只→1页大字体；11-15只→1页小字体；>15只→每页10只大字体
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
        html = generate_html(new_stocks, extras, verdict, vol, page=page, total_pages=total_pages)
        if total_pages == 1:
            output_file = os.path.join(output_dir, f'new_top50_{date_str}.html')
        else:
            output_file = os.path.join(output_dir, f'new_top50_p{page}_{date_str}.html')
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"✓ {output_file}")
