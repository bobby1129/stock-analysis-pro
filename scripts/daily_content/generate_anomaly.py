#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成异常信号捕捉日报HTML - 腾讯源（含量比）+ 连板梯队
拆分为4张独立图片：放量滞涨/缩量新高/放量急拉/连板梯队
"""

import sys, os, json, time
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))

for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

import requests
from datetime import datetime


def fetch_all_stocks_tencent():
    """腾讯批量获取全A股行情（含量比）"""
    url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://finance.sina.com.cn"
    }
    
    all_codes = []
    for market_node in ["sh_a", "sz_a"]:
        for page in range(1, 60):
            params = {
                "page": page, "num": 100, "sort": "symbol", "asc": 1,
                "node": market_node, "symbol": "", "_s_r_a": "page",
            }
            try:
                r = requests.get(url, params=params, headers=headers, timeout=15)
                if r.text.startswith('['):
                    data = json.loads(r.text)
                    if not data:
                        break
                    for item in data:
                        symbol = item.get('symbol', '')
                        if symbol:
                            all_codes.append(symbol)
                else:
                    break
            except Exception as e:
                break
            time.sleep(0.15)
    
    print(f"获取到 {len(all_codes)} 只股票代码")
    
    all_stocks = []
    batch_size = 50
    for i in range(0, len(all_codes), batch_size):
        batch = all_codes[i:i+batch_size]
        query = ','.join(batch)
        
        try:
            tq_url = f"https://qt.gtimg.cn/q={query}"
            resp = requests.get(tq_url, timeout=10)
            resp.encoding = 'gbk'
            
            for line in resp.text.strip().split(';'):
                line = line.strip()
                if not line or 'unknown' in line:
                    continue
                if '=' not in line:
                    continue
                var_part, data_part = line.split("=", 1)
                sym_key = var_part.replace("v_", "").strip()
                data = data_part.strip('"')
                parts = data.split("~")
                
                if len(parts) < 50:
                    continue
                
                try:
                    stock = {
                        'symbol': sym_key,
                        'name': parts[1],
                        'code': parts[2],
                        'price': float(parts[3]) if parts[3] else 0,
                        'change_pct': float(parts[32]) if parts[32] else 0,
                        'volume_ratio': float(parts[49]) if len(parts) > 49 and parts[49] else 0,
                        'amount': float(parts[37]) if parts[37] else 0,
                        'turnover': float(parts[38]) if parts[38] else 0,
                    }
                    all_stocks.append(stock)
                except (ValueError, IndexError):
                    continue
        except Exception as e:
            pass
        
        if (i // batch_size) % 10 == 0:
            print(f"  已获取 {len(all_stocks)}/{len(all_codes)}")
        time.sleep(0.1)
    
    return all_stocks


def detect_signals(stocks):
    """检测异常信号"""
    valid = []
    for s in stocks:
        name = s.get('name', '')
        cp = s.get('change_pct')
        if not isinstance(cp, (int, float)):
            continue
        if name.startswith('ST') or name.startswith('*'):
            continue
        valid.append(s)
    
    print(f"有效股票: {len(valid)}")
    
    vol_high_stagnant = []
    for s in valid:
        vr = s.get('volume_ratio', 0) or 0
        cp = s.get('change_pct', 0) or 0
        if vr > 3 and -1 < cp < 1:
            vol_high_stagnant.append(s)
    vol_high_stagnant.sort(key=lambda x: x.get('volume_ratio', 0), reverse=True)
    
    vol_low_surge = []
    for s in valid:
        vr = s.get('volume_ratio', 0) or 0
        cp = s.get('change_pct', 0) or 0
        if 0 < vr < 0.8 and cp > 5:
            vol_low_surge.append(s)
    vol_low_surge.sort(key=lambda x: x.get('change_pct', 0), reverse=True)
    
    vol_surge = []
    for s in valid:
        vr = s.get('volume_ratio', 0) or 0
        cp = s.get('change_pct', 0) or 0
        if vr > 2 and cp > 5:
            vol_surge.append(s)
    vol_surge.sort(key=lambda x: x.get('change_pct', 0), reverse=True)
    
    return {
        'vol_high_stagnant': vol_high_stagnant[:10],
        'vol_low_surge': vol_low_surge[:10],
        'vol_surge': vol_surge[:10],
    }


def fetch_lianban_data():
    """获取连板梯队数据"""
    from collectors.breadth import fetch_limit_stats
    limit_stats = fetch_limit_stats()
    
    lb_dist = {}
    lb_names = {}
    for s in limit_stats.get('zt_stocks', []):
        lb = s['lianban']
        lb_dist[lb] = lb_dist.get(lb, 0) + 1
        if lb not in lb_names:
            lb_names[lb] = []
        lb_names[lb].append(s['name'])
    
    return lb_dist, lb_names, limit_stats


def build_css():
    """浅色大字体样式（抖音优化）"""
    return """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    width: 1080px; height: 1920px;
    background: linear-gradient(180deg, #faf9f6 0%, #f5f3ee 100%);
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    color: #1a1a1a;
    padding: 100px 45px 80px;
    overflow: hidden;
}
.header { text-align: center; margin-bottom: 50px; }
.date { font-size: 40px; color: #666; margin-bottom: 16px; letter-spacing: 4px; }
.title {
    font-size: 80px; font-weight: 800;
    background: linear-gradient(90deg, #d4af37, #b8860b, #d4af37);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    letter-spacing: 6px;
}
.section {
    background: #fff; border-radius: 24px;
    padding: 40px 40px; margin-bottom: 30px;
    border: 2px solid #d4af37;
    box-shadow: 0 4px 24px rgba(212,175,55,0.15);
}
.section-title {
    font-size: 48px; color: #b8860b;
    margin-bottom: 28px; padding-bottom: 18px;
    border-bottom: 2px solid #d4af37; font-weight: 700;
}
.signal-row {
    display: flex; align-items: center;
    padding: 22px 26px; background: #faf9f6;
    border-radius: 12px; margin-bottom: 16px;
    border: 1px solid #e8e4d9;
}
.signal-rank { font-size: 42px; font-weight: 800; color: #b8860b; width: 60px; }
.signal-name { font-size: 42px; font-weight: 700; color: #1a1a1a; width: 200px; }
.signal-code { font-size: 34px; color: #888; flex: 1; text-align: center; }
.signal-change { font-size: 42px; font-weight: 800; flex: 1; text-align: center; }
.signal-vol { font-size: 36px; color: #d4af37; font-weight: 600; flex: 1; text-align: right; }
.lb-item {
    display: flex; align-items: center;
    padding: 26px 26px; background: #faf9f6;
    border-radius: 12px; margin-bottom: 16px;
    border: 1px solid #e8e4d9;
}
.lb-level { font-size: 48px; font-weight: 800; color: #b8860b; width: 120px; }
.lb-count { font-size: 42px; color: #dc143c; font-weight: 700; width: 100px; text-align: center; }
.lb-names { font-size: 36px; color: #333; flex: 1; }
.footer { text-align: center; margin-top: 30px; font-size: 28px; color: #999; }
"""


def generate_signal_page(title, items, show_vol=True):
    """生成单个信号页面的HTML"""
    css = build_css()
    date_str = datetime.now().strftime("%Y年%m月%d日")
    
    rows_html = ""
    for i, s in enumerate(items, 1):
        cp = s.get('change_pct', 0) or 0
        vr = s.get('volume_ratio', 0) or 0
        color = '#dc143c' if cp > 0 else '#228b22'
        right_col = f'<div class="signal-vol">量比{vr:.1f}</div>' if show_vol else ''
        rows_html += f'''
        <div class="signal-row">
            <div class="signal-rank">{i}</div>
            <div class="signal-name">{s.get('name', '')}</div>
            <div class="signal-code">{s.get('code', '')}</div>
            <div class="signal-change" style="color:{color}">{cp:+.2f}%</div>
            {right_col}
        </div>
        '''
    
    if not rows_html:
        rows_html = '<div style="color:#888;text-align:center;padding:20px;font-size:32px;">暂无符合条件个股</div>'
    
    html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>{css}</style>
</head>
<body>
    <div class="header">
        <div class="date">{date_str}</div>
        <div class="title">异常信号捕捉</div>
    </div>
    <div class="section">
        <div class="section-title">{title}</div>
        {rows_html}
    </div>
    <div class="footer">数据来源：沪深A股 | 仅供参考，不构成投资建议</div>
</body>
</html>'''
    
    return html


def generate_lianban_page(lb_dist, lb_names):
    """生成连板梯队页面的HTML"""
    css = build_css()
    date_str = datetime.now().strftime("%Y年%m月%d日")
    
    lb_html = ""
    for lb in sorted(lb_dist.keys(), reverse=True):
        count = lb_dist[lb]
        names = lb_names.get(lb, [])
        if count <= 5:
            names_str = '、'.join(names)
        else:
            names_str = '、'.join(names[:5]) + f'等{count}家'
        lb_html += f'''
        <div class="lb-item">
            <div class="lb-level">{lb}板</div>
            <div class="lb-count">{count}家</div>
            <div class="lb-names">{names_str}</div>
        </div>
        '''
    
    if not lb_html:
        lb_html = '<div style="color:#888;text-align:center;padding:20px;font-size:32px;">暂无连板数据</div>'
    
    html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>{css}</style>
</head>
<body>
    <div class="header">
        <div class="date">{date_str}</div>
        <div class="title">异常信号捕捉</div>
    </div>
    <div class="section">
        <div class="section-title">🔥 连板梯队</div>
        {lb_html}
    </div>
    <div class="footer">数据来源：沪深A股 | 仅供参考，不构成投资建议</div>
</body>
</html>'''
    
    return html


if __name__ == '__main__':
    print("获取全市场数据（腾讯源）...")
    stocks = fetch_all_stocks_tencent()
    print(f"总计: {len(stocks)} 只")
    
    print("\n检测异常信号...")
    signals = detect_signals(stocks)
    
    print(f"放量滞涨: {len(signals['vol_high_stagnant'])}")
    print(f"缩量新高: {len(signals['vol_low_surge'])}")
    print(f"放量急拉: {len(signals['vol_surge'])}")
    
    print("\n获取连板梯队数据...")
    lb_dist, lb_names, limit_stats = fetch_lianban_data()
    print(f"涨停: {limit_stats['zt_count']} 跌停: {limit_stats['dt_count']}")
    print(f"连板分布: {lb_dist}")
    
    output_dir = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
    os.makedirs(output_dir, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    
    # 写数据缓存（供 generate_anomaly_video.py 只读复用，避免视频重新抓全市场）
    cache_dir = os.path.expanduser('~/stock-analysis-pro/cache/daily_content')
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f'anomaly_cache_{date_str}.json')
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump({
            'date': date_str,
            'date_cn': datetime.now().strftime("%Y年%m月%d日"),
            'signals': signals,
            'lb_dist': {str(k): v for k, v in lb_dist.items()},
            'lb_names': {str(k): v for k, v in lb_names.items()},
        }, f, ensure_ascii=False)
    print(f"✓ 数据缓存: {cache_file}")
    
    # 生成4张独立HTML
    print("\n生成HTML（4张）...")
    
    # P1: 放量滞涨
    html = generate_signal_page("⚠️ 放量滞涨（量比&gt;3 涨幅&lt;1%）", signals['vol_high_stagnant'])
    output_file = os.path.join(output_dir, f'anomaly_p1_{date_str}.html')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✓ {output_file}")
    
    # P2: 缩量新高
    html = generate_signal_page("🚀 缩量新高（量比&lt;0.8 涨幅&gt;5%）", signals['vol_low_surge'])
    output_file = os.path.join(output_dir, f'anomaly_p2_{date_str}.html')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✓ {output_file}")
    
    # P3: 放量急拉
    html = generate_signal_page("⚡ 放量急拉（量比&gt;2 涨幅&gt;5%）", signals['vol_surge'])
    output_file = os.path.join(output_dir, f'anomaly_p3_{date_str}.html')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✓ {output_file}")
    
    # P4: 连板梯队
    html = generate_lianban_page(lb_dist, lb_names)
    output_file = os.path.join(output_dir, f'anomaly_p4_{date_str}.html')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✓ {output_file}")
