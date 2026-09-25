#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「板块资金全景图」动画视频 (1080x1920 mp4)

动画结构（用户定稿 2026-09-25）：
1. 标题区只有 时间 + 「板块资金全景图」，居中放大展示 → 缩回顶部
2. 四张象限卡片依次在屏幕中央放大展示（完整卡片内容）→ 飞落到四宫格位置（2×2格局不变）
   顺序：健康上涨(左上) → 涨但流出(右上) → 跌却流入(左下) → 跌且流出(右下)
3. 全部落座后，「N个活跃板块…分四象限」说明行 + 研判句 一起淡入（位于标题与四宫格之间）
4. 前端不展示「盘后情报局」字样与规则说明（kicker/页脚），规则记录在文档中

流程：akshare同花顺全量概念资金流 → compute_quadrants（与图片p0同源）→ 动画HTML → Playwright录屏 → ffmpeg_static转mp4
数据逻辑复用 generate_matrix.py，不写缓存。

输出：output/daily_content/p0_panorama_video_{date}.mp4
"""
import sys, os, shutil, subprocess, tempfile, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

from generate_matrix import fetch_data, trading_date, compute_quadrants

BASE = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG = os.path.join(SCRIPT_DIR, 'ffmpeg_static')

# ---------- 动画时间参数 ----------
TITLE_HOLD_MS = 1600     # 标题居中放大停留
TITLE_MOVE_MS = 900      # 标题缩回顶部
CARDS_START_MS = 2900    # 卡片开始飞入
STEP_MS = 1700           # 卡片间隔（每张：飞入.5s + 停留.7s + 落座）
FLY_HOLD_MS = 700        # 中央放大停留
SEAT_MS = 800            # 落座过渡
VERDICT_GAP_MS = 600     # 最后一张落座后到研判淡入
TAIL_MS = 3000           # 结尾定格

# ---------- 布局 ----------
CX = 540
STAGE_Y = 1010           # 放大卡片中心y
GRID_TOP = 560           # 四宫格顶边（标题+副标题之下）
GRID_MARGIN_X = 46
GRID_GAP = 26
CARD_W = (1080 - 2 * GRID_MARGIN_X - GRID_GAP) / 2   # ≈481
CARD_H = 430
FLY_SCALE = 1.35

# 四张卡片定义（顺序=飞入顺序，位置=落座位置）
CARDS = [
    {'key': 'q1', 'cls': 'h', 'icon': '📈', 'label': '健康上涨', 'sub': '价涨 + 资金流入',
     'col': 0, 'row': 0},
    {'key': 'q2', 'cls': 'w', 'icon': '⚠️', 'label': '涨但流出', 'sub': '价涨 + 资金撤离（背离）',
     'col': 1, 'row': 0},
    {'key': 'q3', 'cls': 'l', 'icon': '🕵️', 'label': '跌却流入', 'sub': '价跌 + 资金逆势进场',
     'col': 0, 'row': 1},
    {'key': 'q4', 'cls': 'b', 'icon': '📉', 'label': '跌且流出', 'sub': '价跌 + 资金撤离（回避）',
     'col': 1, 'row': 1},
]


def gen_html(qs, date_cn):
    """qs = compute_quadrants() 结果"""
    total = qs['total']
    mood = qs['mood']

    def card_html(c):
        n = len(qs[c['key']])
        top = qs['tops'][c['key']]
        return f'''<div class="qcard {c['cls']}" id="card_{c['key']}">
  <div class="qhead"><span class="qicon">{c['icon']}</span><span class="qnum">{n}</span></div>
  <div class="qlabel">{c['label']}</div>
  <div class="qsub">{c['sub']}</div>
  <div class="qfoot">之最：{top}</div>
</div>'''

    cards_html = "\n".join(card_html(c) for c in CARDS)
    positions_js = ",\n".join(
        f"  {{key:'{c['key']}', x:{GRID_MARGIN_X + c['col'] * (CARD_W + GRID_GAP)}, "
        f"y:{GRID_TOP + c['row'] * (CARD_H + GRID_GAP)}}}"
        for c in CARDS)

    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1080px; height:1920px; overflow:hidden;
  background:linear-gradient(160deg,#faf9f6 0%,#f5f3ee 55%,#f0ece2 100%);
  font-family:"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
  color:#1a1a1a; position:relative; }}

/* ---- 标题区：只有 时间+标题，初始居中放大，JS过渡到顶部 ---- */
.header {{ position:absolute; left:0; right:0; top:70px; text-align:center; z-index:20;
  transform-origin:center center; }}
.date {{ font-size:32px; color:#666; letter-spacing:5px; margin-bottom:10px; }}
.title {{ font-size:78px; font-weight:900; letter-spacing:4px;
  background:linear-gradient(90deg,#d4af37,#b8860b,#d4af37);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}

/* ---- 说明行+研判：标题与四宫格之间，最后一起淡入 ---- */
.intro {{ position:absolute; left:46px; right:46px; top:290px; z-index:15;
  opacity:0; transition:opacity .7s ease; }}
.sub {{ font-size:30px; color:#888; font-weight:600; text-align:center; }}

/* ---- 象限卡片 ---- */
.qcard {{ position:absolute; left:0; top:0; width:{CARD_W:.0f}px; height:{CARD_H:.0f}px;
  z-index:10; background:#fff; border:3px solid #e0d9c8; border-radius:24px;
  padding:34px 32px 28px; box-shadow:0 4px 18px rgba(0,0,0,0.05); }}
.qcard.h {{ border-color:#f0b8bc; background:linear-gradient(165deg,#fff 60%,#fdf1f2); }}
.qcard.w {{ border-color:#ecd9a0; background:linear-gradient(165deg,#fff 60%,#fdf8ea); }}
.qcard.l {{ border-color:#b8dfc2; background:linear-gradient(165deg,#fff 60%,#f0f9f2); }}
.qcard.b {{ border-color:#d8d4cc; background:linear-gradient(165deg,#fff 60%,#f6f5f2); }}
.qhead {{ display:flex; align-items:center; gap:14px; }}
.qicon {{ font-size:44px; }}
.qnum {{ font-size:88px; font-weight:900; line-height:1; letter-spacing:-2px; }}
.qcard.h .qnum {{ color:#dc143c; }} .qcard.w .qnum {{ color:#b8860b; }}
.qcard.l .qnum {{ color:#1d7a2f; }} .qcard.b .qnum {{ color:#888; }}
.qlabel {{ font-size:40px; font-weight:900; color:#1a1a1a; margin-top:14px; letter-spacing:2px; }}
.qsub {{ font-size:26px; color:#999; font-weight:600; margin-top:6px; }}
.qfoot {{ font-size:27px; font-weight:800; color:#555; margin-top:18px; padding-top:16px;
  border-top:1px dashed #e0d9c8; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}

/* ---- 研判 ---- */
.verdict {{ margin-top:16px;
  background:#fff; border:2px solid #d4af37; border-left:12px solid #b8860b;
  border-radius:16px; padding:26px 30px; font-size:38px; font-weight:800; color:#1a1a1a;
  line-height:1.5; box-shadow:0 4px 14px rgba(184,134,11,0.10); word-break:keep-all; }}
.verdict .red {{ color:#dc143c; }} .verdict .green {{ color:#228b22; }}
</style></head>
<body>
<div class="header" id="header">
  <div class="date">{date_cn}</div>
  <div class="title">板块资金全景图</div>
</div>
{cards_html}
<div class="intro" id="intro">
  <div class="sub">{total}个活跃板块（成交&gt;20亿）按 价格×资金 分四象限</div>
  <div class="verdict">💡 {mood}</div>
</div>
<script>
const CX = {CX}, STAGE_Y = {STAGE_Y};
const CARD_W = {CARD_W:.1f}, CARD_H = {CARD_H};
const FLY_SCALE = {FLY_SCALE};
const POS = [
{positions_js}
];

// ---- 阶段1：标题居中放大展示 ----
const header = document.getElementById('header');
header.style.transition = 'none';
header.style.transform = 'translateY(' + (830 - 70 - 90) + 'px) scale(1.5)';
setTimeout(() => {{
  header.style.transition = 'transform {TITLE_MOVE_MS}ms cubic-bezier(.22,1,.36,1)';
  header.style.transform = 'translateY(0) scale(1)';
}}, {TITLE_HOLD_MS});

// ---- 阶段2：卡片依次中央放大 → 落座 ----
for (let i = 0; i < POS.length; i++) {{
  const el = document.getElementById('card_' + POS[i].key);
  const seatX = POS[i].x, seatY = POS[i].y;
  const seatCX = seatX + CARD_W / 2, seatCY = seatY + CARD_H / 2;
  const dx = CX - seatCX, dy = STAGE_Y - seatCY;
  el.style.left = seatX + 'px';
  el.style.top = seatY + 'px';
  el.style.transition = 'none';
  el.style.transform = 'translate(' + dx + 'px,' + dy + 'px) scale(0.3)';
  el.style.opacity = '0';
  setTimeout(() => {{
    // 飞到中央放大
    el.style.transition = 'transform .5s cubic-bezier(.22,1,.36,1), opacity .25s';
    el.style.opacity = '1';
    el.style.transform = 'translate(' + dx + 'px,' + dy + 'px) scale(' + FLY_SCALE + ')';
    el.style.zIndex = '30';
    setTimeout(() => {{
      // 落座
      el.style.transition = 'transform .75s cubic-bezier(.22,1,.36,1)';
      el.style.transform = 'translate(0,0) scale(1)';
      setTimeout(() => {{ el.style.zIndex = '10'; }}, {SEAT_MS});
    }}, {FLY_HOLD_MS});
  }}, {CARDS_START_MS} + i * {STEP_MS});
}}

// ---- 阶段3：说明行+研判一起淡入 ----
const verdictMs = {CARDS_START_MS} + (POS.length - 1) * {STEP_MS} + {FLY_HOLD_MS} + {SEAT_MS} + {VERDICT_GAP_MS};
setTimeout(() => {{ document.getElementById('intro').style.opacity = '1'; }}, verdictMs);
</script>
</body></html>'''


def record_video(html_path, mp4_path):
    """Playwright录屏 → ffmpeg_static 转 mp4（与标尺/新进TOP50同方案）"""
    from playwright.sync_api import sync_playwright
    total = (CARDS_START_MS + (len(CARDS) - 1) * STEP_MS + FLY_HOLD_MS + SEAT_MS
             + VERDICT_GAP_MS + 700) / 1000 + TAIL_MS / 1000
    vdir = tempfile.mkdtemp(prefix='pw_p0_')
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
    ap.add_argument('--html-only', action='store_true', help='只生成HTML不录屏（调试用）')
    args = ap.parse_args()

    date_cn, date_key = trading_date()
    print(f'交易日 {date_cn} ({date_key})，采集同花顺全量概念资金流...')
    df = fetch_data()
    qs = compute_quadrants(df)
    print(f"活跃板块{qs['total']}个: 健康上涨{len(qs['q1'])} 涨但流出{len(qs['q2'])} "
          f"跌却流入{len(qs['q3'])} 跌且流出{len(qs['q4'])}")
    print(f"研判: {qs['mood']}")

    html = gen_html(qs, date_cn)
    os.makedirs(BASE, exist_ok=True)
    html_path = os.path.join(BASE, f'p0_panorama_video_{date_key}.html')
    mp4_path = os.path.join(BASE, f'p0_panorama_video_{date_key}.mp4')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'✓ HTML: {html_path}')

    if args.html_only:
        return 0

    dur = (CARDS_START_MS + (len(CARDS) - 1) * STEP_MS + FLY_HOLD_MS + SEAT_MS
           + VERDICT_GAP_MS + 700) / 1000 + TAIL_MS / 1000
    print(f'录制视频（约{dur:.0f}s）...')
    record_video(html_path, mp4_path)
    size = os.path.getsize(mp4_path) / 1e6
    print(f'✓ 视频: {mp4_path} ({size:.1f}MB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
