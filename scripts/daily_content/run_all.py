#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运行所有日更内容生成脚本"""

import os
import sys
import subprocess
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.expanduser('~/stock-analysis-pro')
OUTPUT_DIR = os.path.join(PROJECT_DIR, 'output/daily_content')

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
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    
    # 1. 个股成交额TOP10（1张）
    if not run_script('generate_stock_amount.py'):
        return 1
    if not html_to_png(f'stock_amount_top10_{date_str}'):
        return 1
    
    # 2. 概念板块（2张：涨幅TOP10 + 净流入TOP10）
    if not run_script('generate_concept_html.py'):
        return 1
    if not html_to_png(f'concept_p1_{date_str}'):
        return 1
    if not html_to_png(f'concept_p2_{date_str}'):
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
    
    # 4. 异常信号捕捉（4张：放量滞涨/缩量新高/放量急拉/连板梯队）
    if not run_script('generate_anomaly.py'):
        return 1
    for i in range(1, 5):
        if not html_to_png(f'anomaly_p{i}_{date_str}'):
            return 1
    
    print("\n" + "="*60)
    print("✓ 全部完成，共生成8张图")
    print("="*60)
    
    # 列出输出文件
    print(f"\n输出文件 ({OUTPUT_DIR}):")
    files = [
        f'stock_amount_top10_{date_str}.png',
        f'concept_p1_{date_str}.png',
        f'concept_p2_{date_str}.png',
        f'anomaly_p1_{date_str}.png',
        f'anomaly_p2_{date_str}.png',
        f'anomaly_p3_{date_str}.png',
        f'anomaly_p4_{date_str}.png',
    ]
    # 动态添加new_top50文件（单页或多页）
    if os.path.exists(os.path.join(OUTPUT_DIR, f'new_top50_{date_str}.png')):
        files.insert(3, f'new_top50_{date_str}.png')
    else:
        for p in range(1, 10):
            png_name = f'new_top50_p{p}_{date_str}.png'
            if os.path.exists(os.path.join(OUTPUT_DIR, png_name)):
                files.insert(2 + p, png_name)
            else:
                break
    for name in files:
        png_path = os.path.join(OUTPUT_DIR, name)
        if os.path.exists(png_path):
            size = os.path.getsize(png_path) / 1024
            print(f"  ✓ {name} ({size:.0f}KB)")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
