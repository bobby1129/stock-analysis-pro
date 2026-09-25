#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行所有日更内容生成脚本"""

import os
import sys
import subprocess
from datetime import datetime
import requests

for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.expanduser('~/stock-analysis-pro')
OUTPUT_DIR = os.path.join(PROJECT_DIR, 'output/daily_content')

def is_trading_day():
    """交易日检查：周末直接否；工作日对比上证指数行情日期与今天。
    节假日休市时新浪返回的仍是上一交易日日期 → 判定非交易日。
    行情接口异常时保守放行（宁可生成旧数据也不误杀正常交易日），并打印警告。"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False, '周末休市'
    try:
        r = requests.get('https://hq.sinajs.cn/list=sh000001',
                         headers={'User-Agent': 'Mozilla/5.0',
                                  'Referer': 'https://finance.sina.com.cn'},
                         timeout=10)
        r.encoding = 'gbk'
        # 格式: var hq_str_sh000001="上证指数,开盘,昨收,现价,最高,最低,...,日期,时间,...";
        parts = r.text.split('"')[1].split(',')
        quote_date = parts[30]  # YYYY-MM-DD
        today = now.strftime('%Y-%m-%d')
        if quote_date == today:
            return True, f'交易日（行情日期 {quote_date}）'
        return False, f'非交易日：行情日期为 {quote_date}，今天是 {today}（节假日休市）'
    except Exception as e:
        return True, f'⚠ 行情接口异常({e})，保守放行按交易日处理'

def run_script(script_name):
    """运行单个生成脚本"""
    script_path = os.path.join(SCRIPT_DIR, script_name)
    print(f"\n{'='*60}")
    print(f"运行: {script_name}")
    print('='*60)
    
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=PROJECT_DIR
    )
    
    if result.returncode != 0:
        print(f"✗ {script_name} 失败")
        return False
    return True

def html_to_png(html_name):
    """HTML转PNG（2x分辨率）"""
    html_path = os.path.join(OUTPUT_DIR, f"{html_name}.html")
    png_path = os.path.join(OUTPUT_DIR, f"{html_name}.png")
    
    if not os.path.exists(html_path):
        print(f"✗ HTML文件不存在: {html_path}")
        return False
    
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(
                viewport={"width": 1080, "height": 1920},
                device_scale_factor=2
            )
            page = context.new_page()
            page.goto(f"file://{html_path}")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=png_path, full_page=False)
            context.close()
            browser.close()
        print(f"✓ {png_path}")
        return True
    except Exception as e:
        print(f"✗ PNG生成失败: {e}")
        return False

def main():
    print("="*60)
    print("生成抖音日更内容")
    print(f"日期: {datetime.now().strftime('%Y-%m-%d')}")
    print("="*60)
    
    # 交易日检查：非交易日（周末/节假日）直接退出，避免用旧数据生成内容
    ok, reason = is_trading_day()
    print(f"交易日检查: {reason}")
    if not ok:
        print("非交易日，跳过生成。")
        return 0
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    
    # 1. 个股成交额TOP10（1张）
    if not run_script('generate_stock_amount.py'):
        return 1
    if not html_to_png(f'stock_amount_top10_{date_str}'):
        return 1
    # 1b. 交易额TOP10 龙虎标尺动画视频（mp4，数据同源）
    run_script('generate_ruler_video.py')
    
    # 2. 概念板块资金意图矩阵（5张: p0全景+p1失血+p2对倒+p3主攻+p4潜伏，脚本自带截图）
    if not run_script('generate_matrix.py'):
        return 1
    
    # 3. 新进成交额TOP50（1张或多张）
    if not run_script('generate_new_top50.py'):
        return 1
    # 单页
    if os.path.exists(os.path.join(OUTPUT_DIR, f'new_top50_{date_str}.html')):
        if not html_to_png(f'new_top50_{date_str}'):
            return 1
    # 多页
    for p in range(1, 10):
        html_name = f'new_top50_p{p}_{date_str}'
        if os.path.exists(os.path.join(OUTPUT_DIR, f'{html_name}.html')):
            if not html_to_png(html_name):
                return 1
        else:
            break
    # 3b. 交易额新进TOP50 动画视频（mp4，数据同源，失败不阻断）
    run_script('generate_new_top50_video.py')
    
    # 4. 异常信号捕捉（4张：放量滞涨/缩量新高/放量急拉/连板梯队）
    if not run_script('generate_anomaly.py'):
        return 1
    for i in range(1, 5):
        if not html_to_png(f'anomaly_p{i}_{date_str}'):
            return 1
    
    print("\n" + "="*60)
    print("✓ 全部完成，共生成11张图 + 2个动画视频")
    print("="*60)
    
    # 列出输出文件
    print(f"\n输出文件 ({OUTPUT_DIR}):")
    files = [
        f'stock_amount_top10_{date_str}.png',
        f'ruler_top10_{date_str}.mp4',
        f'matrix_p0_{date_str}.png',
        f'matrix_p1_{date_str}.png',
        f'matrix_p2_{date_str}.png',
        f'matrix_p3_{date_str}.png',
        f'matrix_p4_{date_str}.png',
        f'anomaly_p1_{date_str}.png',
        f'anomaly_p2_{date_str}.png',
        f'anomaly_p3_{date_str}.png',
        f'anomaly_p4_{date_str}.png',
    ]
    # 动态添加new_top50文件（单页或多页）+ 动画视频
    if os.path.exists(os.path.join(OUTPUT_DIR, f'new_top50_{date_str}.png')):
        files.insert(6, f'new_top50_{date_str}.png')
        if os.path.exists(os.path.join(OUTPUT_DIR, f'new_top50_video_{date_str}.mp4')):
            files.insert(7, f'new_top50_video_{date_str}.mp4')
    else:
        inserted = 0
        for p in range(1, 10):
            png_name = f'new_top50_p{p}_{date_str}.png'
            if os.path.exists(os.path.join(OUTPUT_DIR, png_name)):
                files.insert(5 + p, png_name)
                inserted = p
            else:
                break
        if os.path.exists(os.path.join(OUTPUT_DIR, f'new_top50_video_{date_str}.mp4')):
            files.insert(6 + inserted, f'new_top50_video_{date_str}.mp4')
    # matrix文件名带交易日后缀（15:30前运行=上一交易日，与run_all的date_str可能不同），动态补入
    matrix_files = [f for f in files if f.startswith('matrix_')]
    if not all(os.path.exists(os.path.join(OUTPUT_DIR, f)) for f in matrix_files):
        files = [f for f in files if not f.startswith('matrix_')]
        from datetime import timedelta
        td = datetime.now()
        if (td.hour, td.minute) < (15, 30):
            td -= timedelta(days=1)
        while td.weekday() >= 5:
            td -= timedelta(days=1)
        mdate = td.strftime('%Y%m%d')
        for i in range(5):
            files.insert(1 + i, f'matrix_p{i}_{mdate}.png')
    for name in files:
        png_path = os.path.join(OUTPUT_DIR, name)
        if os.path.exists(png_path):
            size = os.path.getsize(png_path) / 1024
            print(f"  ✓ {name} ({size:.0f}KB)")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
