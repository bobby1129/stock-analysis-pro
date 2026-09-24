#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「交易额TOP10 · 龙虎标尺」动画视频 (1080x1920 mp4)

流程：实时采集(新浪) → 与昨日缓存对比(环比/箭头/NEW) → 生成动画HTML → Playwright录屏 → ffmpeg转mp4
数据逻辑复用 generate_stock_amount.py（同一数据源、同一缓存体系）。
不保存缓存（由 generate_stock_amount.py 负责），可安全在其后运行。

输出：output/daily_content/ruler_top10_{date}.mp4
测试：--cache-date 20260923 可指定对比的缓存日期（演示/回测用）
"""
import sys, os, json, shutil, subprocess, tempfile, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

from datetime import datetime, timedelta
from generate_stock_amount import (
    fetch_stock_amount, get_episode_vol, format_amount,
)

BASE = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
CACHE_DIR = os.path.expanduser('~/stock-analysis-pro/cache/daily_content')
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG = os.path.join(SCRIPT_DIR, 'ffmpeg_static')

# ---------- 布局参数（v3.2定稿，勿轻动） ----------
PLOT_TOP = 380
PLOT_BOTTOM = 1622
CX = 540
LEFT_CARD_X = 30
RIGHT_CARD_X = 620
CARD_W = 430
STAGE_Y = 1000
TICK_W = 112
FLY_SCALE = 1.6
FLY_HOLD_MS = 750
STEP_MS = 1250
START_MS = 900
ROW_H = 260


def load_yesterday_cache(cache_date=None):
    """读取昨日缓存（top50列表）。cache_date可强制指定（测试用）。"""
    if cache_date:
        f = os.path.join(CACHE_DIR, f'stock_amount_cache_{cache_date}.json')
        if os.path.exists(f):
            with open(f, 'r', encoding='utf-8') as fh:
                return json.load(fh), cache_date
        print(f'⚠ 指定缓存不存在: {f}')
        return None, None
    today = datetime.now()
    for delta in range(1, 5):
        d = today - timedelta(days=delta)
        key = d.strftime('%Y%m%d')
        f = os.path.join(CACHE_DIR, f'stock_amount_cache_{key}.json')
        if os.path.exists(f):
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    return json.load(fh), key
            except Exception as e:
                print(f'⚠ 缓存读取失败 {key}: {e}')
    return None, None


def build_rows(stocks, cached, cache_key):
    """构建10行数据：环比、排名箭头、NEW判定"""
    y_amount = {x['code']: x['amount'] for x in cached} if cached else {}
    y_ranks = {x['code']: i + 1 for i, x in enumerate(cached)} if cached else {}
    y_top10 = set(x['code'] for x in cached[:10]) if cached else set()

    rows = []
    for i, s in enumerate(stocks[:10], 1):
        code = s['code']
        # 环比
        if code in y_amount and y_amount[code] > 0:
            ratio = (s['amount'] - y_amount[code]) / y_amount[code] * 100
            ratio_str = f'{ratio:+.1f}%'
            ratio_cls = 'red' if ratio > 0 else 'green' if ratio < 0 else 'gray'
        else:
            ratio_str = 'N/A'
            ratio_cls = 'gray'
        # NEW角标：不在昨日top10
        is_new = bool(y_top10) and code not in y_top10
        # 排名箭头：昨日在缓存中才有↑↓，NEW时行内不再重复显示
        if is_new or code not in y_ranks:
            arw_cls, arw_txt = '', ''
        else:
            diff = y_ranks[code] - i
            if diff > 0:
                arw_cls, arw_txt = 'up', f'↑{diff}'
            elif diff < 0:
                arw_cls, arw_txt = 'down', f'↓{abs(diff)}'
            else:
                arw_cls, arw_txt = 'same', '-'
        side = 'left' if i % 2 == 1 else 'right'
        rows.append({
            'rank': i, 'name': s['name'], 'price': s['price'],
            'chg': s['change_pct'], 'amount_yi': s['amount'] / 1e8,
            'ratio_str': ratio_str, 'ratio_cls': ratio_cls,
            'arw_cls': arw_cls, 'arw_txt': arw_txt, 'is_new': is_new,
            'side': side,
        })
    # 排名等距 y 坐标
    n = len(rows)
    spacing = (PLOT_BOTTOM - PLOT_TOP) / (n - 1)
    for r in rows:
        r['y_seat'] = PLOT_TOP + (r['rank'] - 1) * spacing
    return rows


def gen_html(rows, date_str, vol):
    def card(r):
        chg_color = "#dc143c" if r['chg'] > 0 else "#228b22" if r['chg'] < 0 else "#1a1a1a"
        x = LEFT_CARD_X if r['side'] == 'left' else RIGHT_CARD_X
        new_badge = '<div class="new-corner">NEW</div>' if r['is_new'] else ''
        arw_html = f'<span class="arw {r["arw_cls"]}">{r["arw_txt"]}</span>' if r['arw_txt'] else ''
        return f'''<div class="card {r['side']}" id="card{r['rank']}" style="left:{x}px; top:{r['y_seat'] - ROW_H/2:.0f}px; height:{ROW_H}px;">
  <div class="fly">
    <div class="f-rank">No.{r['rank']}</div>
    <div class="f-name">{r['name']}</div>
    <div class="f-grid">
      <div class="f-item"><div class="f-lab">现价</div><div class="f-val">{r['price']}</div></div>
      <div class="f-item"><div class="f-lab">涨幅</div><div class="f-val" style="color:{chg_color}">{r['chg']:+.2f}%</div></div>
      <div class="f-item"><div class="f-lab">成交额</div><div class="f-val big">{r['amount_yi']:.1f}<span class="unit">亿</span></div></div>
      <div class="f-item"><div class="f-lab">环比</div><div class="f-val {r['ratio_cls']}">{r['ratio_str']}</div></div>
    </div>
  </div>
  <div class="seat">
    {new_badge}
    <div class="s-line1"><span class="s-name">{r['name']}</span>{arw_html}</div>
    <div class="s-data">
      <span class="s-amt">{r['amount_yi']:.1f}<span class="s-unit">亿</span></span>
      <span class="s-ratio {r['ratio_cls']}">{r['ratio_str']}</span>
    </div>
  </div>
  <div class="conn"></div>
</div>'''

    cards_html = "\n".join(card(r) for r in rows)
    ticks_html = "\n".join(
        f'<div class="tick" style="top:{r["y_seat"]:.0f}px;"><span class="tick-lab">No.{r["rank"]}</span></div>'
        for r in rows
    )

    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1080px; height:1920px; overflow:hidden;
  background:linear-gradient(180deg,#faf9f6 0%,#f5f3ee 100%);
  font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  color:#1a1a1a; position:relative; }}
.header {{ text-align:center; padding-top:56px; animation:fadeDown .5s ease-out both; }}
.date {{ font-size:32px; color:#666; letter-spacing:5px; margin-bottom:10px; }}
.title {{ font-size:72px; font-weight:900; letter-spacing:6px;
  background:linear-gradient(90deg,#d4af37,#b8860b,#d4af37);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
.axis {{ position:absolute; left:{CX-3}px; top:{PLOT_TOP-26}px; width:6px; height:{PLOT_BOTTOM-PLOT_TOP+52}px;
  background:linear-gradient(180deg,#d4af37,#b8860b); border-radius:3px; animation:fadeIn .6s .3s both; }}
.tick {{ position:absolute; left:{CX-56}px; width:112px; text-align:center; transform:translateY(-50%);
  pointer-events:none; z-index:3; animation:fadeIn .5s .5s both; }}
.tick-lab {{ display:inline-block; font-size:34px; font-weight:900; color:#8a6d1a; background:#f3ecd6;
  border:2px solid #d9c481; border-radius:10px; padding:2px 12px; letter-spacing:1px; }}
.card {{ position:absolute; width:{CARD_W}px; z-index:5; }}
.fly, .seat {{ position:absolute; left:50%; top:50%; width:{CARD_W-8}px; }}
.fly {{ transform:translate(-50%,-50%); background:#fff; border:3px solid #d4af37; border-radius:20px;
  padding:26px 22px; box-shadow:0 10px 40px rgba(184,134,11,.25); text-align:center;
  transition:opacity .35s ease-in .45s; }}
.f-rank {{ font-size:26px; font-weight:800; color:#b8860b; letter-spacing:2px; }}
.f-name {{ font-size:54px; font-weight:900; margin:4px 0 14px; }}
.f-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px 14px; }}
.f-lab {{ font-size:22px; color:#999; font-weight:700; }}
.f-val {{ font-size:38px; font-weight:800; }}
.f-val.big {{ font-size:52px; color:#b8860b; }}
.f-val.big .unit {{ font-size:26px; }}
.f-val.red {{ color:#dc143c; }} .f-val.green {{ color:#228b22; }} .f-val.gray {{ color:#888; }}
.seat {{ transform:translate(-50%,-50%); opacity:0; transition:opacity .3s ease-in .55s;
  background:#fff; border:3px solid #e8e4d9; border-radius:18px;
  padding:16px 24px 14px; box-shadow:0 3px 12px rgba(0,0,0,.07); position:relative;
  display:flex; flex-direction:column; justify-content:center; }}
.new-corner {{ position:absolute; top:-16px; left:-12px; z-index:6;
  font-size:24px; font-weight:900; color:#fff; letter-spacing:2px;
  background:linear-gradient(90deg,#d4af37,#b8860b); border-radius:8px; padding:4px 12px;
  box-shadow:0 2px 8px rgba(184,134,11,.4); }}
.s-line1 {{ display:flex; align-items:baseline; gap:12px; white-space:nowrap; }}
.s-name {{ font-size:58px; font-weight:900; white-space:nowrap; line-height:1.15; }}
.s-data {{ display:flex; align-items:baseline; margin-top:4px; }}
.s-amt {{ font-size:58px; font-weight:900; color:#b8860b; white-space:nowrap; }}
.s-unit {{ font-size:30px; font-weight:700; }}
.s-ratio {{ font-size:40px; font-weight:800; white-space:nowrap; margin-left:auto; }}
.s-ratio.red {{ color:#dc143c; }} .s-ratio.green {{ color:#228b22; }} .s-ratio.gray {{ color:#888; }}
.arw {{ font-size:44px; font-weight:900; white-space:nowrap; }}
.arw.up {{ color:#dc143c; }} .arw.down {{ color:#228b22; }} .arw.same {{ color:#aaa; }}
.conn {{ position:absolute; top:50%; height:4px; background:#cbb96f; opacity:0; transition:opacity .3s ease-in .7s; }}
.card.left .conn {{ left:{CARD_W}px; width:{CX - TICK_W//2 - LEFT_CARD_X - CARD_W}px; }}
.card.right .conn {{ right:{CARD_W}px; width:{RIGHT_CARD_X - CX - TICK_W//2}px; }}
.card.seated .seat {{ opacity:1; }}
.card.seated .fly {{ opacity:0; pointer-events:none; }}
.card.seated .conn {{ opacity:1; }}
.footer {{ position:absolute; bottom:36px; left:0; right:0; text-align:center; font-size:25px;
  color:#999; font-weight:600; letter-spacing:1px; animation:fadeIn .5s 15.5s both; }}
.footer .brand {{ color:#b8860b; font-weight:800; }}
@keyframes fadeDown {{ from {{ opacity:0; transform:translateY(-16px); }} to {{ opacity:1; transform:none; }} }}
@keyframes fadeIn {{ from {{ opacity:0; }} to {{ opacity:1; }} }}
</style></head>
<body>
<div class="header">
  <div class="date">{date_str}</div>
  <div class="title">交易额 TOP10</div>
</div>
<div class="axis"></div>
{ticks_html}
{cards_html}
<div class="footer">数据来源：新浪财经 ｜ <span class="brand">盘后情报局 Vol.{vol}</span> 每日16:00 ｜ 仅供参考，不构成投资建议</div>
<script>
// 名称/数据超宽保护：逐档缩小字号直到放得下（正式数据可能出现长名称）
document.querySelectorAll('.seat').forEach(seat => {{
  const avail = seat.clientWidth - 48;
  const l1 = seat.querySelector('.s-line1');
  const data = seat.querySelector('.s-data');
  const name = seat.querySelector('.s-name');
  let fs = 58;
  while ((l1.scrollWidth > avail || data.scrollWidth > avail) && fs > 34) {{
    fs -= 2;
    name.style.fontSize = fs + 'px';
    seat.querySelector('.s-amt').style.fontSize = fs + 'px';
    const rt = seat.querySelector('.s-ratio');
    rt.style.fontSize = Math.max(28, fs - 18) + 'px';
    const aw = seat.querySelector('.arw');
    if (aw) aw.style.fontSize = Math.max(28, fs - 14) + 'px';
  }}
}});
const cards = {json.dumps([r['rank'] for r in rows])};
const sides = {{ {", ".join(f"{r['rank']}:'{r['side']}'" for r in rows)} }};
const seatTops = {{ {", ".join(f"{r['rank']}:{r['y_seat'] - ROW_H/2:.1f}" for r in rows)} }};
const cardH = {ROW_H};
cards.forEach((rank, idx) => {{
  const el = document.getElementById('card' + rank);
  const side = sides[rank];
  const cardX = side === 'left' ? {LEFT_CARD_X} : {RIGHT_CARD_X};
  const seatTop = seatTops[rank];
  const dx = {CX} - (cardX + {CARD_W}/2);
  const dy = {STAGE_Y} - (seatTop + cardH/2);
  el.style.transition = 'none';
  el.style.transform = `translate(${{dx}}px, ${{dy}}px) scale(0.35)`;
  el.style.opacity = '0';
  setTimeout(() => {{
    el.style.transition = 'transform .55s cubic-bezier(.22,1,.36,1), opacity .3s';
    el.style.opacity = '1';
    el.style.transform = `translate(${{dx}}px, ${{dy}}px) scale({FLY_SCALE})`;
    setTimeout(() => {{
      el.style.transition = 'transform .85s cubic-bezier(.22,1,.36,1)';
      el.style.transform = 'translate(0,0) scale(1)';
      setTimeout(() => el.classList.add('seated'), 850);
    }}, {FLY_HOLD_MS});
  }}, {START_MS} + idx * {STEP_MS});
}});
</script>
</body></html>'''


def record_video(html_path, mp4_path, n_cards=10):
    """Playwright录屏 → ffmpeg_static 转 mp4"""
    from playwright.sync_api import sync_playwright
    total = (START_MS + (n_cards - 1) * STEP_MS + FLY_HOLD_MS + 850) / 1000 + 3.0
    vdir = tempfile.mkdtemp(prefix='pw_ruler_')
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
    ap.add_argument('--cache-date', help='强制指定昨日缓存日期(YYYYMMDD)，测试用')
    args = ap.parse_args()

    print('采集个股成交额数据（新浪全市场）...')
    stocks = fetch_stock_amount()
    if len(stocks) < 10:
        print(f'✗ 数据不足: {len(stocks)} 只')
        return 1
    cached, cache_key = load_yesterday_cache(args.cache_date)
    if cached:
        print(f'✓ 昨日缓存: {cache_key}')
    else:
        print('⚠ 无昨日缓存，环比/箭头/NEW将留空')

    rows = build_rows(stocks, cached, cache_key)
    date_str = datetime.now().strftime('%Y年%m月%d日')
    vol = get_episode_vol()

    html = gen_html(rows, date_str, vol)
    os.makedirs(BASE, exist_ok=True)
    dstr = datetime.now().strftime('%Y%m%d')
    html_path = os.path.join(BASE, f'ruler_top10_{dstr}.html')
    mp4_path = os.path.join(BASE, f'ruler_top10_{dstr}.mp4')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'✓ HTML: {html_path}')

    print('录制视频（约20s）...')
    record_video(html_path, mp4_path, len(rows))
    size = os.path.getsize(mp4_path) / 1e6
    print(f'✓ 视频: {mp4_path} ({size:.1f}MB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
