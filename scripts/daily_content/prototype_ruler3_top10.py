#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原型v3：TOP10 排名标尺落座动画 (1080x1920, mp4)
v3 变更（按用户反馈）：
1. 全图下方/左右留余量，中轴底部上收（PLOT_BOTTOM 1780→1650）
2. 定格行改双行结构：名称一行 + 数据一行，撑满卡片
3. 中轴排名刻度字加大；升/降箭头加大加醒目
4. NEW 徽章固定在名称框左上角
5. 固定标题只留：日期 + 交易额TOP10（去掉kicker/Vol/副标题）
数据仍内嵌 2026-09-23 真实数据（演示用）。
"""
import os, json, shutil, subprocess, tempfile

BASE = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
FFMPEG = os.path.expanduser('~/stock-analysis-pro/scripts/daily_content/ffmpeg_static')
ANIM_HTML = os.path.join(BASE, 'prototype_ruler3_top10.html')
FINAL_PNG = os.path.join(BASE, 'prototype_ruler3_top10_final.png')
OUT_MP4 = os.path.join(BASE, 'prototype_ruler3_top10.mp4')

# ---------- 布局参数 ----------
PLOT_TOP = 380            # 整体上移80px，收紧与标题的距离；同侧行距276不变
PLOT_BOTTOM = 1622
CX = 540
LEFT_CARD_X = 30
RIGHT_CARD_X = 620
CARD_W = 430
STAGE_Y = 1000
TICK_W = 112            # 排名刻度牌宽度，连线止于其边界
FLY_SCALE = 1.6
FLY_HOLD_MS = 750
STEP_MS = 1250
START_MS = 900

# ---------- 2026-09-23 真实数据 ----------
DATA_DATE = "2026年09月23日"
ROWS = [
    (1, '中际旭创', '922.50', -0.56, 136.8, '-38.8%', 'green', ('same', '-')),
    (2, '长鑫科技', '58.62', +1.31, 121.5, '-27.2%', 'green', ('up', '↑2')),
    (3, '亨通光电', '69.94', -4.19, 111.5, '-29.6%', 'green', ('up', '↑4')),
    (4, '兆易创新', '398.72', -0.84, 105.2, '-48.9%', 'green', ('down', '↓2')),
    (5, '新易盛', '451.20', -0.83, 103.0, '-35.8%', 'green', ('up', '↑1')),
    (6, '京东方Ａ', '6.02', +0.33, 96.5, '+7.0%', 'red', ('up', '↑9')),
    (7, '东山精密', '193.00', -2.58, 94.4, '-41.4%', 'green', ('down', '↓2')),
    (8, '澜起科技', '223.37', +0.69, 79.9, '-52.9%', 'green', ('down', '↓5')),
    (9, '先导基电', '47.80', +9.28, 79.6, 'N/A', 'gray', ('new', 'NEW')),
    (10, '沪电股份', '128.10', +2.37, 79.2, '+42.0%', 'red', ('up', '↑28')),
]

rows = []
N = len(ROWS)
spacing = (PLOT_BOTTOM - PLOT_TOP) / (N - 1)
for rank, name, price, chg, amt, ratio, ratio_cls, (arw_cls, arw_txt) in ROWS:
    side = 'left' if rank % 2 == 1 else 'right'
    y_seat = PLOT_TOP + (rank - 1) * spacing
    is_new = any(b == 'NEW' for b in [arw_cls.upper()])
    rows.append({
        'rank': rank, 'name': name, 'price': price, 'chg': chg,
        'amount_yi': amt, 'ratio_str': ratio, 'ratio_cls': ratio_cls,
        'arw_cls': arw_cls, 'arw_txt': arw_txt, 'is_new': is_new,
        'side': side, 'y_seat': y_seat,
    })
ROW_H = 260             # 恢复v3.1的框高（框间净距与上一版视觉一致）

def seated_card_html(r):
    chg_color = "#dc143c" if r['chg'] > 0 else "#228b22" if r['chg'] < 0 else "#1a1a1a"
    x = LEFT_CARD_X if r['side'] == 'left' else RIGHT_CARD_X
    new_badge = '<div class="new-corner">NEW</div>' if r['is_new'] else ''
    arw_html = '' if r['is_new'] else f'<span class="arw {r["arw_cls"]}">{r["arw_txt"]}</span>'
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

cards_html = "\n".join(seated_card_html(r) for r in rows)

ticks_html = "\n".join(
    f'<div class="tick" style="top:{r["y_seat"]:.0f}px;"><span class="tick-lab">No.{r["rank"]}</span></div>'
    for r in rows
)

html = f'''<!DOCTYPE html>
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
/* ---- 定格：双行结构 ---- */
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
.arw.new {{ color:#d4af37; font-size:32px; }}
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
  <div class="date">{DATA_DATE}</div>
  <div class="title">交易额 TOP10</div>
</div>
<div class="axis"></div>
{ticks_html}
{cards_html}
<div class="footer">数据来源：新浪财经 ｜ <span class="brand">盘后情报局</span> 每日16:00 ｜ 仅供参考，不构成投资建议</div>
<script>
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

with open(ANIM_HTML, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'✓ {ANIM_HTML}')

TOTAL = (START_MS + (N - 1) * STEP_MS + FLY_HOLD_MS + 850) / 1000 + 3.0
from playwright.sync_api import sync_playwright

vdir = tempfile.mkdtemp(prefix='pw_ruler3_')
with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={'width': 1080, 'height': 1920},
                                  device_scale_factor=1,
                                  record_video_dir=vdir,
                                  record_video_size={'width': 1080, 'height': 1920})
    page = context.new_page()
    page.goto(f'file://{ANIM_HTML}')
    page.wait_for_load_state('load')
    page.wait_for_timeout(int(TOTAL * 1000))
    page.screenshot(path=FINAL_PNG)
    video = page.video
    context.close()
    browser.close()
    webm = os.path.join(BASE, 'prototype_ruler3_top10.webm')
    shutil.copy(video.path(), webm)

subprocess.run([FFMPEG, '-y', '-i', webm, '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                '-crf', '20', '-movflags', '+faststart', OUT_MP4],
               check=True, capture_output=True)
os.remove(webm)
shutil.rmtree(vdir, ignore_errors=True)
dur = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                      '-of', 'default=noprint_wrappers=1:nokey=1', OUT_MP4],
                     capture_output=True, text=True).stdout.strip()
print(f'✓ mp4: {OUT_MP4} 时长{dur}s 大小{os.path.getsize(OUT_MP4)/1e6:.1f}MB')
print(f'✓ 终态截图: {FINAL_PNG}')
