"""最坏情况溢出测试: 强制对倒区凑满5条, 检查p1是否溢出"""
import os, sys
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro/scripts/daily_content'))
import generate_matrix as pm

date_cn, date_key = pm.trading_date()
df = pm.fetch_data()
active = df[df['总额'] > 20]
med = active['能量'].median()
zones = pm.select_zones(active, med)

html = pm.gen_p1(zones, date_cn, med, None)

# 定位对倒区(section含"对倒嫌疑榜")的最后一行, 复制一份作为第5行
sec2_idx = html.find('对倒嫌疑榜')
row_start = html.rfind('<div class="erow">', 0, html.find('<div class="footer">'))
# 该行结束: 匹配到对应 </div>\n    </div>
row_end = html.find('</div>\n    </div>', row_start) + len('</div>\n    </div>')
last_row = html[row_start:row_end]
dup_row = last_row.replace('erank">4<', 'erank">5<', 1)
test_html = html[:row_end] + dup_row + html[row_end:]

test_path = os.path.join(pm.OUT_DIR, 'test_p1_worst.html')
with open(test_path, 'w', encoding='utf-8') as f:
    f.write(test_html)
print(f'已构造对倒5条测试页 (原HTML含"对倒嫌疑榜": {sec2_idx>0})')

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width':1080,'height':1920})
    pg.goto(f'file://{test_path}')
    pg.wait_for_load_state('networkidle')
    r = pg.evaluate("""() => {
        const secs = document.querySelectorAll('.section');
        const last = secs[secs.length-1];
        const footer = document.querySelector('.footer');
        return {lastBottom: last.getBoundingClientRect().bottom,
                footerTop: footer.getBoundingClientRect().top,
                scrollH: document.body.scrollHeight};
    }""")
    gap = r['footerTop'] - r['lastBottom']
    verdict = f'✗溢出 {-gap:.0f}px' if gap < 0 else f'✓余量 {gap:.0f}px'
    print(f"最坏情况(对倒5条): 内容底{r['lastBottom']:.0f} footer顶{r['footerTop']:.0f} scrollH{r['scrollH']} -> {verdict}")
    pg.screenshot(path=os.path.join(pm.OUT_DIR, 'test_p1_worst.png'))
    b.close()
