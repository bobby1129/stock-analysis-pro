#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「资金意图矩阵四榜」动画视频 (1080x1920 mp4 x4)

p1资金失血榜 / p2对倒嫌疑榜 / p3主攻方向榜 / p4潜伏吸筹榜，四个视频同一动画逻辑：
1. 标题区只有 日期 + 榜名（保留红/绿/金配色），居中放大展示 → 落座顶部
2. 落座后其余内容依次轻微先后淡入：副标题说明行 → 💡研判 → 榜单section（各间隔300ms）
3. 前端不展示「盘后情报局」kicker角标与门槛规则页脚（用户决定 2026-09-26），
   规则存档 DAILY_CONTENT.md 2c节；图片版p1-p4不受影响仍保留
4. 数据同源 generate_matrix.py（fetch_data/select_zones/load_yesterday_zones/zone_content），
   只读不写缓存

流程：akshare同花顺全量概念资金流 → zone_content（与图片p1-p4同源）→ 动画HTML
     → Playwright录屏 → ffmpeg_static转mp4
输出：output/daily_content/matrix_p{1..4}_video_{date}.mp4
"""
import sys, os, shutil, subprocess, tempfile, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

from generate_matrix import (CSS_BASE, fetch_data, trading_date, select_zones,
                             load_yesterday_zones, zone_content)

BASE = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG = os.path.join(SCRIPT_DIR, 'ffmpeg_static')

# ---------- 动画时间参数（四榜统一） ----------
TITLE_HOLD_MS = 1600     # 标题居中放大停留
TITLE_MOVE_MS = 900      # 标题落座顶部
CONTENT_START_MS = 2800  # 落座后内容开始淡入（副标题）
FADE_STEP_MS = 300       # 副标题→研判→榜单 依次间隔
FADE_MS = 600            # 每块淡入时长
TAIL_MS = 3000           # 结尾定格

# 榜单顺序: (zone_key, 输出p编号)
ZONES = [('bleed', 1), ('fake', 2), ('firm', 3), ('lurk', 4)]


def gen_html(zc, date_cn):
    """zc = zone_content() 结果: title_html/sub/verdict/section"""
    # 视频版副标题去掉日期前缀（日期已在标题区展示）
    sub = zc['sub']
    for sep in ['收盘 ｜ ', '收盘｜']:
        if sep in sub:
            sub = sub.split(sep, 1)[1]
            break

    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<style>{CSS_BASE}
/* ---- 视频版覆盖：header绝对定位（JS做居中放大→落座），内容块依次淡入 ---- */
.header {{ position:absolute; left:46px; right:46px; top:62px; padding:0;
  z-index:20; transform-origin:center center; text-align:center; }}
.vdate {{ font-size:32px; color:#666; letter-spacing:5px; margin-bottom:10px; font-weight:600; }}
.content {{ position:absolute; left:46px; right:46px; top:310px; z-index:10; }}
.content .sub {{ opacity:0; transition:opacity {FADE_MS}ms ease; text-align:left; }}
.content .verdict {{ margin:26px 0 0; opacity:0; transition:opacity {FADE_MS}ms ease; }}
.content .section {{ margin:28px 0 0; }}
.content #fade2 {{ opacity:0; transition:opacity {FADE_MS}ms ease; }}
</style></head>
<body>
  <div class="header" id="header">
    <div class="vdate">{date_cn}</div>
    <div class="title">{zc['title_html']}</div>
  </div>
  <div class="content">
    <div class="sub" id="fade0">{sub}</div>
    <div class="verdict" id="fade1">💡 {zc['verdict']}</div>
    <div id="fade2">{zc['section']}</div>
  </div>
<script>
// ---- 阶段1：标题居中放大展示 → 落座顶部 ----
const header = document.getElementById('header');
header.style.transition = 'none';
header.style.transform = 'translateY(' + (830 - 62 - 90) + 'px) scale(1.5)';
setTimeout(() => {{
  header.style.transition = 'transform {TITLE_MOVE_MS}ms cubic-bezier(.22,1,.36,1)';
  header.style.transform = 'translateY(0) scale(1)';
}}, {TITLE_HOLD_MS});

// ---- 阶段2：副标题→研判→榜单 轻微先后淡入 ----
for (let i = 0; i < 3; i++) {{
  setTimeout(() => {{
    document.getElementById('fade' + i).style.opacity = '1';
  }}, {CONTENT_START_MS} + i * {FADE_STEP_MS});
}}
</script>
</body></html>'''


def record_video(html_path, mp4_path):
    """Playwright录屏 → ffmpeg_static 转 mp4（与标尺/新进TOP50/全景图同方案）"""
    from playwright.sync_api import sync_playwright
    total = (CONTENT_START_MS + 2 * FADE_STEP_MS + FADE_MS) / 1000 + TAIL_MS / 1000
    vdir = tempfile.mkdtemp(prefix='pw_zone_')
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


def check_overflow(html_paths):
    """程序化溢出检查：内容底边不得越过1920-90安全区，section不得超宽"""
    from playwright.sync_api import sync_playwright
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1080, 'height': 1920})
        for hp in html_paths:
            page.goto(f'file://{hp}')
            page.wait_for_load_state('load')
            r = page.evaluate("""() => {
                let maxBottom = 0, overW = 0;
                for (const el of document.querySelectorAll('.content, .content *')) {
                    const b = el.getBoundingClientRect();
                    if (b.bottom > maxBottom) maxBottom = b.bottom;
                    if (el.scrollWidth > el.clientWidth + 1) overW++;
                }
                return {maxBottom: Math.round(maxBottom), overW};
            }""")
            results.append((os.path.basename(hp), r['maxBottom'], r['overW']))
        browser.close()
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--html-only', action='store_true', help='只生成HTML不录屏（调试用）')
    args = ap.parse_args()

    date_cn, date_key = trading_date()
    print(f'交易日 {date_cn} ({date_key})，采集同花顺全量概念资金流...')
    df = fetch_data()
    active = df[df['总额'] > 20]
    med = float(active['能量'].median())
    zones = select_zones(active, med)
    prev_zones = load_yesterday_zones(date_key)
    # 注意：只读缓存不写（当日缓存已由图片版 generate_matrix.py 保存）

    os.makedirs(BASE, exist_ok=True)
    html_paths, mp4_paths = [], []
    for zkey, pno in ZONES:
        zc = zone_content(zkey, zones, date_cn, med, prev_zones)
        html = gen_html(zc, date_cn)
        hp = os.path.join(BASE, f'matrix_p{pno}_video_{date_key}.html')
        with open(hp, 'w', encoding='utf-8') as f:
            f.write(html)
        html_paths.append(hp)
        mp4_paths.append(os.path.join(BASE, f'matrix_p{pno}_video_{date_key}.mp4'))
        print(f'✓ HTML: {hp} ({zkey}: {len(zones[zkey])}条)')

    # 溢出程序化检查
    bad = [(n, b, w) for n, b, w in check_overflow(html_paths) if b > 1920 - 90 or w > 0]
    for n, b, w in bad:
        print(f'✗ 溢出: {n} bottom={b} overW={w}')
    if bad:
        print('⚠ 存在溢出，仍继续（请人工检查）')

    if args.html_only:
        return 0

    dur = (CONTENT_START_MS + 2 * FADE_STEP_MS + FADE_MS) / 1000 + TAIL_MS / 1000
    for hp, mp in zip(html_paths, mp4_paths):
        print(f'录制 {os.path.basename(mp)}（约{dur:.0f}s）...')
        record_video(hp, mp)
        print(f'✓ 视频: {mp} ({os.path.getsize(mp) / 1e6:.1f}MB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
