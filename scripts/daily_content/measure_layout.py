"""测量已生成HTML的各区块高度(不重新fetch数据)"""
import os
from playwright.sync_api import sync_playwright
OUT = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width':1080,'height':1920})
    for name in ['matrix_p1','matrix_p3']:
        pg.goto(f'file://{OUT}/prototype_{name}.html')
        pg.wait_for_load_state('networkidle')
        r = pg.evaluate("""() => {
            const h = s => { const e=document.querySelector(s); return e? Math.round(e.getBoundingClientRect().height):0; };
            const bot = s => { const e=document.querySelector(s); return e? Math.round(e.getBoundingClientRect().bottom):0; };
            const rows = document.querySelectorAll('.erow').length;
            const rowH = rows? Math.round(document.querySelector('.erow').getBoundingClientRect().height):0;
            return {header:h('.header'), verdict:h('.verdict'), quad:h('.quad'),
                    section:h('.section'), secnote:h('.sec-note'), rows, rowH,
                    lastSecBottom: bot('.section'), footerTop: Math.round(document.querySelector('.footer').getBoundingClientRect().top)};
        }""")
        gap = r['footerTop'] - r['lastSecBottom']
        print(f"{name}: header={r['header']} verdict={r['verdict']} quad={r['quad']} sec-note={r['secnote']} | {r['rows']}行 x {r['rowH']}px | 余量={gap}px {'✗溢出' if gap<0 else '✓'}")
    b.close()
