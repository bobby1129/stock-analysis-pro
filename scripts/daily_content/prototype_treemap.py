#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""概念板块资金热力图原型 v2 - 抖音竖屏1080x1920
修复: 1)小块聚合为"其他"+按块宽自适应字号(不折行断词) 2)连续色阶(sqrt归一)+色阶图例
     3)压缩留白 4)交易日日期(凌晨生成取上一交易日) 5)浅色块用深色字
"""

import sys, os, json, math
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))

for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

from datetime import datetime, timedelta

OUT_DIR = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
MAX_BLOCKS = 16          # 单独显示的最大块数, 其余聚合
MAP_X, MAP_Y, MAP_W, MAP_H = 40, 585, 1000, 1215   # treemap区域


# ---------- 交易日 ----------
def trading_date():
    now = datetime.now()
    d = now if (now.hour, now.minute) >= (15, 30) else now - timedelta(days=1)
    while d.weekday() >= 5:      # 跳过周末
        d -= timedelta(days=1)
    return d.strftime('%Y年%m月%d日')


# ---------- Squarified Treemap ----------
def worst_ratio(row, w):
    s = sum(row)
    if s == 0 or w == 0:
        return float('inf')
    rmax, rmin = max(row), min(row)
    return max(w * w * rmax / (s * s), s * s / (w * w * rmin))


def squarify(items, x, y, w, h):
    result = []
    items = list(items)
    total_area = sum(a for _, a in items)
    if total_area <= 0:
        return result
    scale = (w * h) / total_area
    items = [(d, a * scale) for d, a in items]

    while items:
        if w >= h:
            horizontal = False
            side = h
        else:
            horizontal = True
            side = w
        remaining = list(items)
        cur_row, cur_areas = [], []
        while remaining:
            d, a = remaining[0]
            trial = cur_areas + [a]
            if not cur_areas or worst_ratio(trial, side) <= worst_ratio(cur_areas, side):
                cur_row.append((d, a))
                cur_areas = trial
                remaining.pop(0)
            else:
                break
        if not cur_row:
            cur_row = [remaining.pop(0)]
            cur_areas = [cur_row[0][1]]

        strip_size = sum(cur_areas) / side
        rx, ry = x, y
        pos = ry if not horizontal else rx
        for d, a in cur_row:
            seg = a / strip_size
            if not horizontal:
                result.append((d, rx, pos, strip_size, seg))
            else:
                result.append((d, pos, ry, seg, strip_size))
            pos += seg
        if not horizontal:
            x += strip_size
            w -= strip_size
        else:
            y += strip_size
            h -= strip_size
        items = remaining
    return result


# ---------- 颜色 ----------
def lerp(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def block_style(net, max_net):
    """连续色阶: sqrt归一拉开层次。红=流入(浅玫瑰→深绯红), 绿=流出(浅绿→深绿)"""
    t = math.sqrt(min(abs(net) / max_net, 1.0)) if max_net else 0
    if net >= 0:
        bg = lerp((247, 205, 205), (139, 10, 32), t)     # 浅玫瑰 → 深绯红
        border = lerp((225, 160, 160), (100, 5, 20), t)
    else:
        bg = lerp((205, 232, 205), (16, 96, 36), t)      # 浅绿 → 深绿
        border = lerp((160, 200, 160), (10, 70, 25), t)
    dark_text = t < 0.42                                  # 浅色块用深色字
    txt = (90, 20, 20) if (net >= 0 and dark_text) else (20, 60, 25) if dark_text else (255, 255, 255)
    shadow = 'none' if dark_text else '0 1px 4px rgba(0,0,0,0.5)'
    return bg, border, txt, shadow


# ---------- 数据 ----------
def fetch_data():
    from collectors.ths_concept import fetch_ths_concept_fund_flow
    return fetch_ths_concept_fund_flow(top_n=30, verbose=False)


def prepare_blocks(concepts):
    """按|净额|排序, top N 单独显示, 其余聚合为'其他'"""
    ranked = sorted(concepts, key=lambda c: abs(c['net']), reverse=True)
    main = ranked[:MAX_BLOCKS]
    rest = ranked[MAX_BLOCKS:]
    blocks = [(c, max(abs(c['net']), 1.0)) for c in main]
    if rest:
        agg_net = sum(c['net'] for c in rest)
        agg_chg = sum(c['change_pct'] for c in rest) / len(rest)
        agg = {'name': f'其他{len(rest)}个概念', 'net': agg_net, 'change_pct': agg_chg,
               'is_agg': True, 'leader': '', 'leader_pct': 0}
        blocks.append((agg, max(abs(agg_net), sum(abs(c['net']) for c in rest) * 0.55)))
    blocks.sort(key=lambda x: x[1], reverse=True)
    return blocks


# ---------- HTML ----------
def generate_html(concepts, date_str):
    by_net = sorted(concepts, key=lambda c: c['net'], reverse=True)
    inflow_top, outflow_top = by_net[0], by_net[-1]
    if outflow_top['net'] >= 0:
        # 全流入日: 换表述, 避免"撤退"与无绿块矛盾
        tail = (f"｜ 流入最弱：<span class='gold2'>{outflow_top['name']}</span>"
                f"（仅{outflow_top['net']:.1f}亿）")
    else:
        tail = (f"｜ 主要撤退：<span class='green'>{outflow_top['name']}</span>"
                f"（{outflow_top['net']:.1f}亿）")
    verdict = f"资金主攻：<span class='red'>{inflow_top['name']}</span>（净流入{inflow_top['net']:.1f}亿）{tail}"

    blocks = prepare_blocks(concepts)
    max_net = max(abs(c['net']) for c, _ in blocks if not c.get('is_agg')) or 1
    boxes = squarify(blocks, MAP_X, MAP_Y, MAP_W, MAP_H)

    blocks_html = ''
    for c, bx, by, bw, bh in boxes:
        net = c['net']
        bg, border, txt, shadow = block_style(net, max_net)
        is_agg = c.get('is_agg', False)
        if is_agg:
            bg, border, txt, shadow = (222, 216, 203), (150, 143, 128), (70, 65, 55), 'none'

        # 字号: 按面积定基准, 再按块宽收紧保证名字不折行断词
        area_px = bw * bh
        base_fs = 44 if area_px > 70000 else 38 if area_px > 40000 else 32 if area_px > 20000 else 27 if area_px > 10000 else 23
        name = c['name']
        if is_agg:
            # 聚合块: 名字短且允许两行, 必须显示
            name_fs = min(base_fs, 30)
            name_html = f'<div class="tm-name agg" style="font-size:{name_fs}px">{name}</div>'
        else:
            name_fs = min(base_fs, int((bw - 20) / (len(name) * 1.06)))
            if name_fs < 17:      # 实在放不下 → 只显示净额不显示名字
                name_html = ''
            else:
                name_html = f'<div class="tm-name" style="font-size:{name_fs}px">{name}</div>'

        net_txt = f'{"+" if net >= 0 else ""}{net:.1f}亿'
        net_fs = min(name_fs + 2, int((bw - 20) / (len(net_txt) * 0.58)))
        net_html = f'<div class="tm-net" style="font-size:{max(net_fs, 18)}px">{net_txt}</div>' if bw > 90 else ''

        chg_html = ''
        if area_px > 15000 and not is_agg:
            chg_txt = f'涨幅 {c["change_pct"]:+.2f}%'
            chg_fs = min(int(name_fs * 0.68), int((bw - 20) / (len(chg_txt) * 0.58)))
            if chg_fs >= 17:
                chg_html = f'<div class="chg" style="font-size:{chg_fs}px">{chg_txt}</div>'

        blocks_html += f'''
    <div class="tm-block" style="left:{bx:.0f}px; top:{by:.0f}px; width:{bw-5:.0f}px; height:{bh-5:.0f}px;
         background:rgb{bg}; border-color:rgb{border}; color:rgb{txt}; text-shadow:{shadow};">{name_html}{net_html}{chg_html}</div>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    width:1080px; height:1920px; overflow:hidden;
    background:linear-gradient(160deg,#faf9f6 0%,#f5f3ee 55%,#f0ece2 100%);
    font-family:"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
    position:relative;
  }}
  .header {{ padding:50px 50px 0; }}
  .kicker {{
    display:inline-block; font-size:26px; font-weight:800; letter-spacing:3px;
    color:#b8860b; border:2px solid #d4af37; border-radius:10px;
    padding:6px 18px; background:rgba(212,175,55,0.08);
  }}
  .title {{ font-size:70px; font-weight:900; color:#1a1a1a; margin-top:20px; letter-spacing:2px; }}
  .title .gold {{ color:#b8860b; }}
  .date {{ font-size:29px; color:#888; margin-top:10px; font-weight:600; }}
  .verdict {{
    margin:26px 50px 0; background:#fff; border:2px solid #d4af37; border-left:12px solid #b8860b;
    border-radius:16px; padding:22px 28px; font-size:33px; font-weight:800; color:#1a1a1a;
    line-height:1.45; box-shadow:0 4px 14px rgba(184,134,11,0.10); word-break:keep-all;
  }}
  .verdict .red {{ color:#dc143c; }}
  .verdict .green {{ color:#228b22; }}
  .verdict .gold2 {{ color:#b8860b; }}
  .legend {{
    position:absolute; top:500px; left:50px; right:50px; display:flex; align-items:center;
    justify-content:space-between; font-size:24px; color:#666; font-weight:700;
  }}
  .legend .scale {{ display:flex; flex-direction:column; align-items:center; gap:5px; }}
  .legend .ticks {{ display:flex; justify-content:space-between; width:100%;
                    font-size:19px; color:#999; font-weight:600; }}
  .legend .agg-note {{ font-size:21px; color:#999; max-width:150px; line-height:1.3; }}
  .scale-bar {{
    width:330px; height:20px; border-radius:10px;
    background:linear-gradient(90deg, rgb(16,96,36), rgb(205,232,205) 42%, #efe9dd 50%, rgb(247,205,205) 58%, rgb(139,10,32));
    border:1px solid #ccc;
  }}
  .tm-wrap {{ position:absolute; left:0; top:0; width:1080px; height:1920px; }}
  .tm-block {{
    position:absolute; border:2px solid; border-radius:12px; overflow:hidden;
    display:flex; flex-direction:column; align-items:center; justify-content:center;
    text-align:center; padding:4px;
  }}
  .tm-name {{ font-weight:900; letter-spacing:1px; line-height:1.15; white-space:nowrap; }}
  .tm-name.agg {{ white-space:normal; }}
  .tm-net {{ font-weight:800; margin-top:3px; line-height:1.15; white-space:nowrap; }}
  .chg {{ font-weight:600; margin-top:2px; opacity:0.88; line-height:1.2; white-space:nowrap; }}
  .footer {{
    position:absolute; bottom:30px; left:0; right:0; text-align:center;
    font-size:24px; color:#999; font-weight:600; letter-spacing:1px;
  }}
  .footer .brand {{ color:#b8860b; font-weight:800; }}
</style>
</head>
<body>
  <div class="header">
    <span class="kicker">盘后情报局 · 资金热力图</span>
    <div class="title">概念板块<span class="gold">资金流向</span></div>
    <div class="date">{date_str} 收盘 ｜ 面积=资金规模 · 颜色深浅=流入/流出强度</div>
  </div>
  <div class="verdict">💡 {verdict}</div>
  <div class="legend">
    <span>◀ 流出</span>
    <span class="scale"><span class="scale-bar"></span>
      <span class="ticks"><span>-{max_net:.0f}亿</span><span>0</span><span>+{max_net:.0f}亿</span></span>
    </span>
    <span>流入 ▶</span>
    <span class="agg-note">灰块=其余概念合并</span>
  </div>
  <div class="tm-wrap">{blocks_html}
  </div>
  <div class="footer">数据来源：同花顺 ｜ <span class="brand">盘后情报局</span> 每日16:00更新</div>
</body>
</html>'''
    return html


def main():
    date_str = trading_date()
    concepts = fetch_data()
    print(f'获取 {len(concepts)} 个概念, 交易日: {date_str}')

    html = generate_html(concepts, date_str)
    html_path = os.path.join(OUT_DIR, 'prototype_treemap_v4.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    from playwright.sync_api import sync_playwright
    png_path = os.path.join(OUT_DIR, 'prototype_treemap_v4.png')
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={'width': 1080, 'height': 1920}, device_scale_factor=2)
        page = context.new_page()
        page.goto(f'file://{html_path}')
        page.wait_for_load_state('networkidle')
        page.screenshot(path=png_path, full_page=False)
        context.close()
        browser.close()
    print(f'PNG: {png_path} ({os.path.getsize(png_path)/1024:.0f}KB)')


if __name__ == '__main__':
    main()
