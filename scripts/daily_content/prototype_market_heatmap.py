#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全市场个股热力图原型 (Finviz式) - 抖音竖屏1080x1920
面积=流通市值, 颜色=涨跌幅(红涨绿跌,深浅=强度)
数据源: 新浪全市场排行API (sort=mktcap), 无采样偏差
"""

import sys, os, json, math, time
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))
for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

import requests
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.expanduser('~/stock-analysis-pro'), 'scripts/daily_content'))
from stock_short_names import get_short_name

OUT_DIR = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
MAP_X, MAP_Y, MAP_W, MAP_H = 30, 600, 1020, 1220
MAX_BLOCKS = 90        # 单独显示的股票数(按市值), 其余聚合
SIN_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn"}


def trading_date():
    now = datetime.now()
    d = now if (now.hour, now.minute) >= (15, 30) else now - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime('%Y年%m月%d日')


def fetch_market(n_pages=5):
    """按总市值排序取前 n_pages*100 只"""
    out = []
    for page in range(1, n_pages + 1):
        params = {"page": page, "num": 100, "sort": "mktcap", "asc": 0,
                  "node": "hs_a", "symbol": "", "_s_r_a": "page"}
        r = requests.get(SIN_URL, params=params, headers=HDRS, timeout=15)
        rows = json.loads(r.text)
        if not rows:
            break
        out.extend(rows)
        time.sleep(0.3)
    return out


def is_bse(code):
    return code[0] in ('4', '8', '9')


# ---------- Squarified Treemap ----------
def worst_ratio(row, w):
    s = sum(row)
    if s == 0 or w == 0:
        return float('inf')
    return max(w * w * max(row) / (s * s), s * s / (w * w * min(row)))


def squarify(items, x, y, w, h):
    result = []
    total = sum(a for _, a in items)
    if total <= 0:
        return result
    scale = (w * h) / total
    items = [(d, a * scale) for d, a in items]
    while items:
        horizontal = w < h
        side = h if not horizontal else w
        cur_row, cur_areas, remaining = [], [], list(items)
        while remaining:
            d, a = remaining[0]
            trial = cur_areas + [a]
            if not cur_areas or worst_ratio(trial, side) <= worst_ratio(cur_areas, side):
                cur_row.append((d, a)); cur_areas = trial; remaining.pop(0)
            else:
                break
        if not cur_row:
            cur_row = [remaining.pop(0)]; cur_areas = [cur_row[0][1]]
        strip = sum(cur_areas) / side
        pos = y if not horizontal else x
        for d, a in cur_row:
            seg = a / strip
            result.append((d, x, pos, strip, seg) if not horizontal else (d, pos, y, seg, strip))
            pos += seg
        if not horizontal:
            x += strip; w -= strip
        else:
            y += strip; h -= strip
        items = remaining
    return result


def lerp(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def chg_color(chg):
    """红涨绿跌, ±7%封顶, sqrt拉开层次"""
    t = math.sqrt(min(abs(chg) / 7.0, 1.0))
    if chg >= 0:
        bg = lerp((240, 205, 205), (150, 8, 25), t)       # 浅玫瑰→深红
        if chg >= 9.8:
            bg = (178, 0, 20)                              # 涨停特殊深红
    else:
        bg = lerp((200, 228, 200), (10, 100, 35), t)      # 浅绿→深绿
    dark = t < 0.42 and abs(chg) < 9.8
    txt = (100, 25, 25) if (chg >= 0 and dark) else (20, 70, 30) if dark else (255, 255, 255)
    return bg, txt


def main():
    date_str = trading_date()
    raw = fetch_market(n_pages=5)
    print(f'获取 {len(raw)} 只(按市值)')

    stocks = []
    for s in raw:
        if is_bse(s['code']):
            continue
        try:
            nmc = float(s['nmc']) * 10000  # 万元→元? nmc单位: 万元. mktcap/nmc 单位为万元
        except (ValueError, TypeError):
            continue
        chg = float(s['changepercent'])
        name = get_short_name(s['name'])
        stocks.append({'name': name, 'code': s['code'], 'chg': chg,
                       'nmc': float(s['nmc']), 'amount': float(s['amount'])})
    print(f'有效 {len(stocks)} 只 (剔除北交所)')

    # 统计(基于全部样本)
    up = sum(1 for s in stocks if s['chg'] > 0)
    down = sum(1 for s in stocks if s['chg'] < 0)
    flat = len(stocks) - up - down
    zt = sum(1 for s in stocks if s['chg'] >= 9.8)
    dt = sum(1 for s in stocks if s['chg'] <= -9.8)

    main_stocks = stocks
    blocks = [(s, s['nmc']) for s in main_stocks]
    blocks.sort(key=lambda x: x[1], reverse=True)

    boxes = squarify(blocks, MAP_X, MAP_Y, MAP_W, MAP_H)

    blocks_html = ''
    for s, bx, by, bw, bh in boxes:
        is_agg = s.get('is_agg', False)
        if is_agg:
            bg, txt = (222, 216, 203), (70, 65, 55)
        else:
            bg, txt = chg_color(s['chg'])
        area = bw * bh
        base = 40 if area > 50000 else 34 if area > 25000 else 28 if area > 12000 else 24 if area > 6000 else 20
        name = s['name']
        name_fs = min(base, int((bw - 12) / (max(len(line) for line in name.split('\n')) * 1.05)))
        shadow = 'none' if (is_agg or txt[0] < 150) else '0 1px 3px rgba(0,0,0,0.45)'
        chg_html = ''
        if not is_agg and area > 7000:
            chg_txt = f'{s["chg"]:+.1f}%'
            chg_fs = min(int(name_fs * 0.72), int((bw - 12) / (len(chg_txt) * 0.6)))
            if chg_fs >= 16:
                chg_html = f'<div class="chg" style="font-size:{chg_fs}px">{chg_txt}</div>'
        name_html = ''
        if name_fs >= 15 or is_agg:
            name_html = f'<div class="nm{" agg" if is_agg else ""}" style="font-size:{max(name_fs,15)}px">{name}</div>'
        blocks_html += f'''
    <div class="blk" style="left:{bx:.0f}px;top:{by:.0f}px;width:{bw-4:.0f}px;height:{bh-4:.0f}px;background:rgb{bg};color:rgb{txt};text-shadow:{shadow};">{name_html}{chg_html}</div>'''

    verdict = f"红 <span class='red'>{up}</span> ｜ 绿 <span class='green'>{down}</span> ｜ 平 {flat} ｜ 涨停 <span class='red'>{zt}</span> ｜ 跌停 <span class='green'>{dt}</span>"

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8">
<style>
  * {{ margin:0;padding:0;box-sizing:border-box; }}
  body {{ width:1080px;height:1920px;overflow:hidden;
    background:linear-gradient(160deg,#faf9f6 0%,#f5f3ee 55%,#f0ece2 100%);
    font-family:"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;position:relative; }}
  .header {{ padding:50px 46px 0; }}
  .kicker {{ display:inline-block;font-size:26px;font-weight:800;letter-spacing:3px;color:#b8860b;
    border:2px solid #d4af37;border-radius:10px;padding:6px 18px;background:rgba(212,175,55,0.08); }}
  .title {{ font-size:70px;font-weight:900;color:#1a1a1a;margin-top:18px;letter-spacing:2px; }}
  .title .gold {{ color:#b8860b; }}
  .date {{ font-size:28px;color:#888;margin-top:8px;font-weight:600; }}
  .verdict {{ margin:24px 46px 0;background:#fff;border:2px solid #d4af37;border-left:12px solid #b8860b;
    border-radius:16px;padding:20px 28px;font-size:34px;font-weight:800;color:#1a1a1a;
    box-shadow:0 4px 14px rgba(184,134,11,0.10);letter-spacing:1px; }}
  .verdict .red {{ color:#dc143c; }} .verdict .green {{ color:#228b22; }}
  .legend {{ position:absolute;top:528px;left:46px;right:46px;display:flex;align-items:center;
    justify-content:space-between;font-size:24px;color:#666;font-weight:700; }}
  .legend .scale {{ display:flex;flex-direction:column;align-items:center;gap:4px; }}
  .scale-bar {{ width:360px;height:20px;border-radius:10px;border:1px solid #ccc;
    background:linear-gradient(90deg, rgb(10,100,35), rgb(200,228,200) 40%, #efe9dd 50%, rgb(240,205,205) 60%, rgb(150,8,25)); }}
  .legend .ticks {{ display:flex;justify-content:space-between;width:100%;font-size:19px;color:#999;font-weight:600; }}
  .note {{ font-size:22px;color:#999; }}
  .wrap {{ position:absolute;left:0;top:0;width:1080px;height:1920px; }}
  .blk {{ position:absolute;border:2px solid rgba(255,255,255,0.85);border-radius:8px;overflow:hidden;
    display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:3px; }}
  .nm {{ font-weight:900;line-height:1.12;white-space:nowrap; }}
  .nm.agg {{ white-space:pre-line;font-size:26px; }}
  .chg {{ font-weight:700;margin-top:2px;line-height:1.15;white-space:nowrap;opacity:0.92; }}
  .footer {{ position:absolute;bottom:26px;left:0;right:0;text-align:center;font-size:24px;color:#999;font-weight:600; }}
  .footer .brand {{ color:#b8860b;font-weight:800; }}
</style></head>
<body>
  <div class="header">
    <span class="kicker">盘后情报局 · 市场全景</span>
    <div class="title">A股<span class="gold">热力图</span></div>
    <div class="date">{date_str} 收盘 ｜ 面积=流通市值 · 红涨绿跌 · 颜色越深涨跌越猛</div>
  </div>
  <div class="verdict">📊 {verdict}</div>
  <div class="legend">
    <span>-7% ◀</span>
    <span class="scale"><span class="scale-bar"></span>
      <span class="ticks"><span>跌停</span><span>0</span><span>涨停</span></span></span>
    <span>▶ +7%</span>
    <span class="note">市值前{len(stocks)}只 · 小块仅色</span>
  </div>
  <div class="wrap">{blocks_html}
  </div>
  <div class="footer">数据来源：新浪财经 ｜ <span class="brand">盘后情报局</span> 每日16:00更新</div>
</body></html>'''

    html_path = os.path.join(OUT_DIR, 'prototype_market_heatmap.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    from playwright.sync_api import sync_playwright
    png_path = os.path.join(OUT_DIR, 'prototype_market_heatmap.png')
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={'width': 1080, 'height': 1920}, device_scale_factor=2)
        page = context.new_page()
        page.goto(f'file://{html_path}')
        page.wait_for_load_state('networkidle')
        page.screenshot(path=png_path, full_page=False)
        context.close(); browser.close()
    print(f'PNG: {png_path} ({os.path.getsize(png_path)/1024:.0f}KB)')


if __name__ == '__main__':
    main()
