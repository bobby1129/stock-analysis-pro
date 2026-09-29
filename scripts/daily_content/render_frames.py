#!/usr/bin/env python3
"""帧精确渲染: HTML(window.__render(t)) -> Playwright逐帧截图 -> ffmpeg合成mp4"""
import asyncio, os, sys, subprocess, math

HTML = sys.argv[1]
OUT_MP4 = sys.argv[2]
FPS = 30
W, H = 1080, 1920

async def main():
    from playwright.async_api import async_playwright
    tmpdir = OUT_MP4.replace('.mp4','_frames')
    os.makedirs(tmpdir, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=['--force-color-profile=srgb','--disable-lcd-text'])
        page = await browser.new_page(viewport={'width':W,'height':H}, device_scale_factor=1)
        await page.goto('file://'+os.path.abspath(HTML))
        await page.wait_for_timeout(500)
        total = await page.evaluate('window.__TOTAL')
        nframes = int(total*FPS)+1
        print(f'total={total}s frames={nframes}')
        for i in range(nframes):
            t = i/FPS
            await page.evaluate(f'window.__render({t})')
            await page.screenshot(path=f'{tmpdir}/f{i:05d}.png')
            if i%100==0: print(f'  frame {i}/{nframes}')
        await browser.close()
    ff = os.path.expanduser('~/stock-analysis-pro/scripts/daily_content/ffmpeg_static')
    subprocess.run([ff,'-y','-framerate',str(FPS),'-i',f'{tmpdir}/f%05d.png',
        '-c:v','libx264','-pix_fmt','yuv420p','-crf','20','-preset','medium',OUT_MP4],
        check=True, capture_output=True)
    print('done:', OUT_MP4)

asyncio.run(main())
