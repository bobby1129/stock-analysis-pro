#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「新进入TOP50」动画视频 (1080x1920 mp4)

动画结构（用户定稿）：
1. 标题区只有 时间 + 新进入TOP50 两部分，先在屏幕中间放大展示，再缩回顶部
2. 列表条目依次飞入：中间放大时只显示 股票名称/涨幅/成交额
3. 落位后展示完整信息（排名/名称+信号徽章/现价/涨幅/量比/换手/成交额）

流程：实时采集(新浪+腾讯量比) → 与昨日缓存对比 → 生成动画HTML → Playwright录屏 → ffmpeg_static转mp4
数据逻辑复用 generate_new_top50.py（同一数据源、同一缓存体系），不写缓存。

输出：output/daily_content/new_top50_video_{date}.mp4
测试：--prev-date 20260923 指定对比缓存日期
"""
import sys, os, json, shutil, subprocess, tempfile, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

from datetime import datetime
from generate_stock_amount import get_episode_vol, format_amount
from generate_new_top50 import (
    fetch_stock_amount, fetch_yesterday_top50_codes,
    fetch_tencent_extras, classify_signal,
)
from stock_short_names import get_short_name

BASE = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG = os.path.join(SCRIPT_DIR, 'ffmpeg_static')

# ---------- 动画时间参数 ----------
TITLE_HOLD_MS = 1600     # 标题居中放大停留
TITLE_MOVE_MS = 900      # 标题缩回顶部
ROWS_START_MS = 2900     # 条目开始飞入（标题动画结束后）
STEP_MS = 1150           # 条目间隔
FLY_HOLD_MS = 700        # 中间放大停留
SEAT_MS = 800            # 落位过渡
TAIL_MS = 3000           # 结尾定格

# ---------- 布局 ----------
HEADER_H = 300           # 标题区最终高度
PLOT_TOP = 340
PLOT_BOTTOM = 1810
CX = 540
STAGE_Y = 1000           # 放大卡片中心y
FLY_SCALE = 1.0


def build_layout(n):
    """根据条目数计算行高与字号（n可变：1~20+）"""
    avail = PLOT_BOTTOM - PLOT_TOP
    row_h = min(150, max(78, avail // max(n, 1)))
    # 字号随行高缩放
    if row_h >= 120:
        fs = {'rank': 40, 'name': 40, 'num': 34, 'amt': 36, 'badge': 22, 'gap': 8}
    elif row_h >= 95:
        fs = {'rank': 32, 'name': 32, 'num': 27, 'amt': 29, 'badge': 18, 'gap': 6}
    else:
        fs = {'rank': 26, 'name': 26, 'num': 22, 'amt': 24, 'badge': 15, 'gap': 4}
    return row_h, fs


def gen_html(rows, date_str, vol, row_h, fs):
    n = len(rows)

    def seat_row(r):
        chg_color = "#dc143c" if r['chg'] > 0 else "#228b22" if r['chg'] < 0 else "#1a1a1a"
        vr_color = "#dc143c" if r['vr'] > 2 else "#1a1a1a"
        vr_weight = "800" if r['vr'] > 2 else "500"
        if r['sig'] == 'danger':
            badge = '<span class="sig-badge danger">⚠巨量绿柱</span>'
        elif r['sig'] == 'inflow':
            badge = '<span class="sig-badge inflow">🟢资金进场</span>'
        else:
            badge = ''
        danger_cls = ' row-danger' if r['sig'] == 'danger' else ''
        return f'''<div class="card{' danger' if r['sig']=='danger' else ''}" id="card{r['rank']}">
  <div class="fly">
    <div class="f-rank">新进榜 · No.{r['rank']}</div>
    <div class="f-name">{r['name']}</div>
    <div class="f-row">
      <span class="f-chg" style="color:{chg_color}">{r['chg']:+.2f}%</span>
      <span class="f-amt">{r['amt_str']}</span>
    </div>
  </div>
  <div class="seat{danger_cls}">
    <span class="s-rank">{r['rank']}</span>
    <span class="s-name">{r['name']}{badge}</span>
    <span class="s-price">{r['price']}</span>
    <span class="s-chg" style="color:{chg_color}">{r['chg']:+.2f}%</span>
    <span class="s-vr" style="color:{vr_color};font-weight:{vr_weight}">{r['vr_str']}</span>
    <span class="s-to">{r['to_str']}</span>
    <span class="s-amt">{r['amt_str']}</span>
  </div>
</div>'''

    cards_html = "\n".join(seat_row(r) for r in rows)

    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1080px; height:1920px; overflow:hidden;
  background:linear-gradient(180deg,#faf9f6 0%,#f5f3ee 100%);
  font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  color:#1a1a1a; position:relative; }}

/* ---- 标题：初始居中放大，JS过渡到顶部 ---- */
.header {{ position:absolute; left:0; right:0; top:90px; text-align:center; z-index:20;
  transform-origin:center center; }}
.date {{ font-size:32px; color:#666; letter-spacing:5px; margin-bottom:10px; }}
.title {{ font-size:66px; font-weight:900; letter-spacing:6px; line-height:1.18;
  width:400px; margin:0 auto; text-align:center;
  transition:width {TITLE_MOVE_MS}ms cubic-bezier(.22,1,.36,1);
  background:linear-gradient(90deg,#d4af37,#b8860b,#d4af37);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}

/* ---- 列表行 ---- */
.card {{ position:absolute; left:36px; width:1008px; z-index:5; }}
.fly, .seat {{ position:absolute; left:50%; top:50%; }}
.fly {{ width:760px; transform:translate(-50%,-50%);
  background:#fff; border:3px solid #d4af37; border-radius:22px;
  padding:34px 30px; box-shadow:0 12px 44px rgba(184,134,11,.28); text-align:center;
  transition:opacity .3s ease-in .5s; }}
.f-rank {{ font-size:28px; font-weight:800; color:#b8860b; letter-spacing:3px; }}
.f-name {{ font-size:72px; font-weight:900; margin:10px 0 18px; white-space:nowrap; }}
.f-row {{ display:flex; justify-content:center; gap:60px; align-items:baseline; }}
.f-chg {{ font-size:56px; font-weight:900; }}
.f-amt {{ font-size:56px; font-weight:900; color:#b8860b; }}

.seat {{ width:1008px; transform:translate(-50%,-50%); opacity:0;
  transition:opacity .3s ease-in .5s;
  background:#fff; border:2px solid #e8e4d9; border-radius:14px;
  box-shadow:0 2px 8px rgba(0,0,0,.05);
  display:flex; align-items:center; padding:0 22px; height:{row_h - fs['gap']}px; }}
.seat.row-danger {{ border:2px solid rgba(34,139,34,.55); background:#f6fbf6; }}
.s-rank {{ font-size:{fs['rank']}px; font-weight:800; color:#b8860b; width:52px; flex-shrink:0; }}
.s-name {{ font-size:{fs['name']}px; font-weight:700; flex:2.4; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }}
.s-price {{ font-size:{fs['num']}px; flex:1; text-align:right; font-weight:500; }}
.s-chg {{ font-size:{fs['num'] + 2}px; flex:1.15; text-align:right; font-weight:800; }}
.s-vr {{ font-size:{fs['num']}px; flex:.85; text-align:right; }}
.s-to {{ font-size:{fs['num'] - 2}px; flex:.95; text-align:right; color:#555; }}
.s-amt {{ font-size:{fs['amt']}px; flex:1.25; text-align:right; font-weight:700; }}
.sig-badge {{ display:inline-block; font-size:{fs['badge']}px; font-weight:800; color:#fff;
  border-radius:8px; padding:2px 8px; margin-left:8px; vertical-align:middle; white-space:nowrap; }}
.sig-badge.danger {{ background:#228b22; }}
.sig-badge.inflow {{ background:#dc143c; }}

.card.seated .seat {{ opacity:1; }}
.card.seated .fly {{ opacity:0; pointer-events:none; }}

.footer {{ position:absolute; bottom:34px; left:0; right:0; text-align:center;
  font-size:24px; color:#999; font-weight:600; opacity:0; transition:opacity .6s; }}
.footer .brand {{ color:#b8860b; font-weight:800; }}
</style></head>
<body>
<div class="header" id="header">
  <div class="date">{date_str}</div>
  <div class="title">交易额新进TOP50</div>
</div>
{cards_html}
<div class="footer" id="footer">数据来源：新浪财经/腾讯行情 ｜ <span class="brand">盘后情报局 Vol.{vol}</span> ｜ 仅供参考，不构成投资建议</div>
<script>
const N = {n};
const ROW_H = {row_h};
const PLOT_TOP = {PLOT_TOP};
const CX = {CX}, STAGE_Y = {STAGE_Y};

// ---- 阶段1：标题居中放大展示 ----
const header = document.getElementById('header');
// 初始：移到屏幕中央并放大
header.style.transition = 'none';
header.style.transform = 'translateY(' + (960 - 90 - 110) + 'px) scale(1.55)';
setTimeout(() => {{
  // 缩回顶部，同时标题从两行恢复成一行
  header.style.transition = 'transform {TITLE_MOVE_MS}ms cubic-bezier(.22,1,.36,1)';
  header.style.transform = 'translateY(0) scale(1)';
  document.querySelector('.title').style.width = '800px';
}}, {TITLE_HOLD_MS});

// ---- 阶段2：条目依次飞入 ----
for (let idx = 0; idx < N; idx++) {{
  const el = document.getElementById('card' + (idx + 1));
  const seatTop = PLOT_TOP + idx * ROW_H + ROW_H / 2;
  el.style.top = (seatTop - ROW_H / 2) + 'px';
  el.style.height = ROW_H + 'px';
  const dy = STAGE_Y - seatTop;
  el.style.transition = 'none';
  el.style.transform = 'translateY(' + dy + 'px) scale(0.3)';
  el.style.opacity = '0';
  setTimeout(() => {{
    // 飞入到中间放大
    el.style.transition = 'transform .5s cubic-bezier(.22,1,.36,1), opacity .25s';
    el.style.opacity = '1';
    el.style.transform = 'translateY(' + dy + 'px) scale({FLY_SCALE})';
    setTimeout(() => {{
      // 落位
      el.style.transition = 'transform .75s cubic-bezier(.22,1,.36,1)';
      el.style.transform = 'translateY(0) scale(1)';
      setTimeout(() => el.classList.add('seated'), {SEAT_MS});
    }}, {FLY_HOLD_MS});
  }}, {ROWS_START_MS} + idx * {STEP_MS});
}}

// ---- 结尾：footer淡入 ----
const totalMs = {ROWS_START_MS} + (N - 1) * {STEP_MS} + {FLY_HOLD_MS} + {SEAT_MS} + 600;
setTimeout(() => {{ document.getElementById('footer').style.opacity = '1'; }}, totalMs);
</script>
</body></html>'''


def record_video(html_path, mp4_path, n):
    """Playwright录屏 → ffmpeg_static 转 mp4（与龙虎标尺同方案）"""
    from playwright.sync_api import sync_playwright
    total = (ROWS_START_MS + (n - 1) * STEP_MS + FLY_HOLD_MS + SEAT_MS) / 1000 + TAIL_MS / 1000
    vdir = tempfile.mkdtemp(prefix='pw_top50_')
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport={'width': 1080, 'height': 1920},
                                          device_scale_factor=1,
                                          record_video_dir=vdir,
                                          record_video_size={'width': 1080, 'height': 1920})
            page = context.new_page()
            page.goto(f'file://{html_path}')
            page.wait_for_load_state('load')
            page.wait_for_timeout(int(total * 1000))
            video = page.video
            context.close()
            browser.close()
            webm = mp4_path.replace('.mp4', '.webm')
            shutil.copy(video.path(), webm)
        subprocess.run([FFMPEG, '-y', '-i', webm, '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        '-crf', '20', '-movflags', '+faststart', mp4_path],
                       check=True, capture_output=True)
        os.remove(webm)
    finally:
        shutil.rmtree(vdir, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prev-date', help='强制指定昨日缓存日期(YYYYMMDD)，测试用')
    args = ap.parse_args()

    print('采集个股成交额数据（新浪全市场）...')
    stocks = fetch_stock_amount()
    print(f'获取 {len(stocks)} 只')

    yesterday_codes = fetch_yesterday_top50_codes(args.prev_date)
    new_stocks = [s for s in stocks if s['code'] not in yesterday_codes]
    print(f'新进TOP50: {len(new_stocks)} 只')

    if not new_stocks:
        print('今日无新进榜，跳过视频生成')
        return 0

    extras = fetch_tencent_extras([s['code'] for s in new_stocks])

    rows = []
    for i, s in enumerate(new_stocks, 1):
        ex = extras.get(s['code'], {})
        vr = ex.get('volume_ratio', 0) or 0
        to = ex.get('turnover', 0) or 0
        rows.append({
            'rank': i,
            'name': get_short_name(s['name']),
            'price': s['price'],
            'chg': s['change_pct'],
            'amt_str': format_amount(s['amount']),
            'vr': vr,
            'vr_str': f'{vr:.2f}' if vr else '—',
            'to_str': f'{to:.1f}%' if to else '—',
            'sig': classify_signal(s, extras),
        })

    row_h, fs = build_layout(len(rows))
    print(f'布局: {len(rows)}行 × {row_h}px')

    date_str = datetime.now().strftime('%Y年%m月%d日')
    vol = get_episode_vol()

    html = gen_html(rows, date_str, vol, row_h, fs)
    os.makedirs(BASE, exist_ok=True)
    dstr = datetime.now().strftime('%Y%m%d')
    html_path = os.path.join(BASE, f'new_top50_video_{dstr}.html')
    mp4_path = os.path.join(BASE, f'new_top50_video_{dstr}.mp4')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'✓ HTML: {html_path}')

    dur = (ROWS_START_MS + (len(rows) - 1) * STEP_MS + FLY_HOLD_MS + SEAT_MS) / 1000 + TAIL_MS / 1000
    print(f'录制视频（约{dur:.0f}s）...')
    record_video(html_path, mp4_path, len(rows))
    size = os.path.getsize(mp4_path) / 1e6
    print(f'✓ 视频: {mp4_path} ({size:.1f}MB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
