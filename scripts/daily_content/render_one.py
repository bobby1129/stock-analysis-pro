#!/usr/bin/env python3
"""渲染单张HTML为PNG (2x)，并检测内容是否溢出1920"""
import sys
from playwright.sync_api import sync_playwright

html_path = sys.argv[1]
png_path = sys.argv[2]

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1080, "height": 1920}, device_scale_factor=2)
    page = context.new_page()
    page.goto(f"file://{html_path}")
    page.wait_for_load_state("networkidle")
    # 溢出检测
    overflow = page.evaluate("document.body.scrollHeight")
    print(f"body scrollHeight: {overflow} (viewport 1920)")
    if overflow > 1920:
        print(f"⚠️ 溢出 {overflow - 1920}px!")
    else:
        print(f"✓ 底部余量 {1920 - overflow}px")
    page.screenshot(path=png_path, full_page=False)
    context.close()
    browser.close()
print(f"✓ {png_path}")
