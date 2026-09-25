#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「异常信号捕捉」四张动画视频 (1080x1920 mp4 x4)

p1放量滞涨 / p2缩量新高 / p3放量急拉 / p4连板梯队，四个视频同一动画逻辑：
1. 标题区「日期 + 异常信号捕捉」固定顶部全程展示（不动画）
2. 栏目名（图标+名称，不含括号说明）开场居中放大1.5倍展示 → 落位到榜单section标题处
3. 落位后其余内容轻微先后淡入：榜单行 → 页脚免责行（间隔300ms）→ 定格3s
4. 页脚「数据来源：沪深A股 | 仅供参考，不构成投资建议」保留（用户决定 2026-09-26）
5. 数据只读 cache/daily_content/anomaly_cache_{date}.json（由 generate_anomaly.py 写入）；
   当日缓存缺失时回退最近一份缓存（如节假日演示）；--date 可指定日期

流程：缓存JSON → 动画HTML（CSS同源 generate_anomaly.build_css）
     → Playwright录屏 → ffmpeg_static转mp4
输出：output/daily_content/anomaly_p{1..4}_video_{date}.mp4
"""
import sys, os, json, glob, shutil, subprocess, tempfile, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

from generate_anomaly import build_css

BASE = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
CACHE_DIR = os.path.expanduser('~/stock-analysis-pro/cache/daily_content')
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG = os.path.join(SCRIPT_DIR, 'ffmpeg_static')

# ---------- 动画时间参数（四张统一，与四榜视频同款） ----------
TITLE_HOLD_MS = 1600     # 标题居中放大停留
TITLE_MOVE_MS = 900      # 标题落座顶部
CONTENT_START_MS = 2800  # 落座后内容开始淡入（榜单section）
FADE_STEP_MS = 300       # 榜单→页脚 间隔
FADE_MS = 600            # 每块淡入时长
TAIL_MS = 3000           # 结尾定格

# 四张页面: (p编号, 栏目名(图标+名称), 括号说明, 缓存signals键或None=连板)
PAGES = [
    (1, '⚠️ 放量滞涨', '（量比&gt;3 涨幅&lt;1%）', 'vol_high_stagnant'),
    (2, '🚀 缩量新高', '（量比&lt;0.8 涨幅&gt;5%）', 'vol_low_surge'),
    (3, '⚡ 放量急拉', '（量比&gt;2 涨幅&gt;5%）', 'vol_surge'),
    (4, '🔥 连板梯队', '', None),
]


def load_cache(date_key):
    """只读缓存：优先指定日期，缺失回退最近一份（节假日演示用）"""
    exact = os.path.join(CACHE_DIR, f'anomaly_cache_{date_key}.json')
    if os.path.exists(exact):
        return json.load(open(exact, encoding='utf-8')), date_key
    files = sorted(glob.glob(os.path.join(CACHE_DIR, 'anomaly_cache_*.json')))
    if not files:
        print('✗ 无 anomaly 缓存（需先运行 generate_anomaly.py）')
        return None, None
    latest = files[-1]
    key = os.path.basename(latest).replace('anomaly_cache_', '').replace('.json', '')
    print(f'⚠ 当日缓存缺失，回退最近缓存 {key}')
    return json.load(open(latest, encoding='utf-8')), key


def signal_rows_html(items, show_vol=True):
    """与图片版 generate_signal_page 行结构一致"""
    rows = ''
    for i, s in enumerate(items, 1):
        cp = s.get('change_pct', 0) or 0
        vr = s.get('volume_ratio', 0) or 0
        color = '#dc143c' if cp > 0 else '#228b22'
        right_col = f'<div class="signal-vol">量比{vr:.1f}</div>' if show_vol else ''
        rows += f'''
        <div class="signal-row">
            <div class="signal-rank">{i}</div>
            <div class="signal-name">{s.get('name', '')}</div>
            <div class="signal-code">{s.get('code', '')}</div>
            <div class="signal-change" style="color:{color}">{cp:+.2f}%</div>
            {right_col}
        </div>'''
    if not rows:
        rows = '<div style="color:#888;text-align:center;padding:20px;font-size:32px;">暂无符合条件个股</div>'
    return rows


def lianban_rows_html(lb_dist, lb_names):
    """与图片版 generate_lianban_page 行结构一致"""
    rows = ''
    for lb in sorted((int(k) for k in lb_dist.keys()), reverse=True):
        count = lb_dist[str(lb)]
        names = lb_names.get(str(lb), [])
        names_str = '、'.join(names) if count <= 5 else '、'.join(names[:5]) + f'等{count}家'
        rows += f'''
        <div class="lb-item">
            <div class="lb-level">{lb}板</div>
            <div class="lb-count">{count}家</div>
            <div class="lb-names">{names_str}</div>
        </div>'''
    if not rows:
        rows = '<div style="color:#888;text-align:center;padding:20px;font-size:32px;">暂无连板数据</div>'
    return rows


def gen_html(sec_name, sec_note, rows_html, date_cn):
    """标题区固定展示；栏目名(图标+名称)居中放大→落位section标题；随后内容淡入"""
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<style>{build_css()}
/* ---- 视频版覆盖：header固定顶部；栏目名fly层居中放大→落位；内容分层淡入 ---- */
.header {{ position:absolute; left:45px; right:45px; top:100px; margin-bottom:0; z-index:20; }}
.content {{ position:absolute; left:45px; right:45px; top:340px; z-index:10; }}
.content .section {{ margin-bottom:0; opacity:0; transition:opacity 400ms ease; }}
.content .section-title {{ text-align:center; }}
.content #fade0 {{ opacity:0; transition:opacity {FADE_MS}ms ease; }}
.content #fade1 {{ opacity:0; transition:opacity {FADE_MS}ms ease; }}
#fly {{ position:fixed; left:50%; top:50%; z-index:30; white-space:nowrap;
  transform:translate(-50%,-50%) scale(1.6);
  font-size:48px; font-weight:700; color:#b8860b; letter-spacing:2px; }}
</style></head>
<body>
    <div class="header">
        <div class="date">{date_cn}</div>
        <div class="title">异常信号捕捉</div>
    </div>
    <div id="fly">{sec_name}</div>
    <div class="content">
        <div class="section" id="secBox">
            <div class="section-title" id="secTitle"><span id="secNameSpan">{sec_name}</span>{sec_note}</div>
            <div id="fade0">{rows_html}</div>
        </div>
        <div class="footer" id="fade1">数据来源：沪深A股 | 仅供参考，不构成投资建议</div>
    </div>
<script>
const SWAP_MS = {TITLE_HOLD_MS} + {TITLE_MOVE_MS};
// ---- 阶段1：栏目名居中放大停留 → 飞向section标题位置 ----
const fly = document.getElementById('fly');
const secNameSpan = document.getElementById('secNameSpan');
setTimeout(() => {{
  const fr = fly.getBoundingClientRect();
  const range = document.createRange();
  range.selectNodeContents(secNameSpan);
  const tr = range.getBoundingClientRect();
  const dx = (tr.left + tr.width / 2) - (fr.left + fr.width / 2);
  const dy = (tr.top + tr.height / 2) - (fr.top + fr.height / 2);
  fly.style.transition = 'transform {TITLE_MOVE_MS}ms cubic-bezier(.22,1,.36,1)';
  fly.style.transform = 'translate(calc(-50% + ' + dx + 'px), calc(-50% + ' + dy + 'px)) scale(1)';
}}, {TITLE_HOLD_MS});

// ---- 阶段2：落位瞬间 fly→真标题切换，卡片+榜单行→页脚 依次淡入 ----
setTimeout(() => {{
  fly.style.display = 'none';
  document.getElementById('secBox').style.opacity = '1';
}}, SWAP_MS + 30);
setTimeout(() => {{
  document.getElementById('fade0').style.opacity = '1';
}}, SWAP_MS + {CONTENT_START_MS - 2500});
setTimeout(() => {{
  document.getElementById('fade1').style.opacity = '1';
}}, SWAP_MS + {CONTENT_START_MS - 2500} + {FADE_STEP_MS});
</script>
</body></html>'''


def record_video(html_path, mp4_path):
    """Playwright录屏 → ffmpeg_static 转 mp4（与标尺/新进TOP50/全景图/四榜同方案）"""
    from playwright.sync_api import sync_playwright
    total = (CONTENT_START_MS + FADE_STEP_MS + FADE_MS) / 1000 + TAIL_MS / 1000
    vdir = tempfile.mkdtemp(prefix='pw_anomaly_')
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
    """程序化溢出检查：内容底边不得越过1920-80安全区，元素不得超宽"""
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
    from datetime import datetime
    ap = argparse.ArgumentParser()
    ap.add_argument('--html-only', action='store_true', help='只生成HTML不录屏（调试用）')
    ap.add_argument('--date', help='指定缓存日期YYYYMMDD（缺省=今天，缺失回退最近缓存）')
    args = ap.parse_args()

    today = args.date or datetime.now().strftime('%Y%m%d')
    cache, date_key = load_cache(today)
    if cache is None:
        return 1
    date_cn = cache.get('date_cn') or f'{date_key[:4]}年{date_key[4:6]}月{date_key[6:]}日'
    print(f'使用缓存 {date_key}（{date_cn}）')

    os.makedirs(BASE, exist_ok=True)
    html_paths, mp4_paths = [], []
    for pno, sec_name, sec_note, sig_key in PAGES:
        if sig_key:
            items = cache['signals'].get(sig_key, [])
            rows = signal_rows_html(items)
            n = len(items)
        else:
            rows = lianban_rows_html(cache['lb_dist'], cache['lb_names'])
            n = sum(cache['lb_dist'].values())
        html = gen_html(sec_name, sec_note, rows, date_cn)
        hp = os.path.join(BASE, f'anomaly_p{pno}_video_{date_key}.html')
        with open(hp, 'w', encoding='utf-8') as f:
            f.write(html)
        html_paths.append(hp)
        mp4_paths.append(os.path.join(BASE, f'anomaly_p{pno}_video_{date_key}.mp4'))
        print(f'✓ HTML: {hp} ({n}条)')

    # 溢出程序化检查
    bad = [(n, b, w) for n, b, w in check_overflow(html_paths) if b > 1920 - 80 or w > 0]
    for n, b, w in bad:
        print(f'✗ 溢出: {n} bottom={b} overW={w}')
    if bad:
        print('⚠ 存在溢出，仍继续（请人工检查）')

    if args.html_only:
        return 0

    dur = (CONTENT_START_MS + FADE_STEP_MS + FADE_MS) / 1000 + TAIL_MS / 1000
    for hp, mp in zip(html_paths, mp4_paths):
        print(f'录制 {os.path.basename(mp)}（约{dur:.0f}s）...')
        record_video(hp, mp)
        print(f'✓ 视频: {mp} ({os.path.getsize(mp) / 1e6:.1f}MB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
