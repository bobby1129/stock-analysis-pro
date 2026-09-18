#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成所有日更内容（3张图）"""

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
    """HTML转PNG"""
    date_str = datetime.now().strftime("%Y%m%d")
    html_path = os.path.join(OUTPUT_DIR, f"{html_name}_{date_str}.html")
    png_path = os.path.join(OUTPUT_DIR, f"{html_name}_{date_str}.png")
    
    if not os.path.exists(html_path):
        print(f"✗ HTML文件不存在: {html_path}")
        return False
    
    result = subprocess.run(
        [sys.executable, '/tmp/html2png.py', html_path, png_path]
    )
    
    if result.returncode != 0:
        print(f"✗ PNG生成失败: {html_name}")
        return False
    
    print(f"✓ {png_path}")
    return True

def main():
    print("="*60)
    print("生成抖音日更内容")
    print(f"日期: {datetime.now().strftime('%Y-%m-%d')}")
    print("="*60)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 1. 个股成交额TOP10
    if not run_script('generate_stock_amount.py'):
        return 1
    if not html_to_png('stock_amount_top10'):
        return 1
    
    # 2. 概念板块
    if not run_script('generate_concept_html.py'):
        return 1
    if not html_to_png('concept'):
        return 1
    
    # 3. 异常信号捕捉（含量比+连板）
    if not run_script('generate_anomaly.py'):
        return 1
    if not html_to_png('anomaly'):
        return 1
    
    print("\n" + "="*60)
    print("✓ 全部完成")
    print("="*60)
    
    # 列出输出文件
    date_str = datetime.now().strftime("%Y%m%d")
    print(f"\n输出文件 ({OUTPUT_DIR}):")
    for name in ['stock_amount_top10', 'concept', 'anomaly']:
        png_path = os.path.join(OUTPUT_DIR, f"{name}_{date_str}.png")
        if os.path.exists(png_path):
            size = os.path.getsize(png_path) / 1024
            print(f"  ✓ {name}_{date_str}.png ({size:.0f}KB)")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
