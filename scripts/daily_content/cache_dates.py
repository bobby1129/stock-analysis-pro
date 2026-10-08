#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""成交额缓存日期指针

维护 cache/daily_content/amount_cache_dates.json，记录所有已写入
stock_amount_cache_YYYYMMDD.json 的日期列表。

读取"昨日"数据时不再用固定天数回溯窗口（长假后会失效，
2026-10-08教训：国庆休市8天导致top10/top50对比数据全空），
而是从列表中取"今天之前最近的一个缓存日期"。

指针文件缺失/损坏时自动扫描缓存目录重建（兼容历史缓存）。
"""

import os
import re
import json
import glob
from datetime import datetime

CACHE_DIR = os.path.expanduser('~/stock-analysis-pro/cache/daily_content')
POINTER_FILE = os.path.join(CACHE_DIR, 'amount_cache_dates.json')
CACHE_PATTERN = re.compile(r'stock_amount_cache_(\d{8})\.json$')


def _scan_cache_dir():
    """扫描缓存目录，返回所有存在的缓存日期（升序）"""
    dates = []
    for path in glob.glob(os.path.join(CACHE_DIR, 'stock_amount_cache_*.json')):
        m = CACHE_PATTERN.search(os.path.basename(path))
        if m:
            dates.append(m.group(1))
    return sorted(set(dates))


def load_cache_dates():
    """读取缓存日期列表（升序）。指针缺失/损坏时扫描目录重建。"""
    if os.path.exists(POINTER_FILE):
        try:
            with open(POINTER_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            dates = sorted(set(d for d in data.get('dates', [])
                               if re.fullmatch(r'\d{8}', str(d))))
            if dates:
                return dates
        except Exception as e:
            print(f"⚠ 缓存日期指针读取失败({e})，扫描目录重建")
    else:
        print("⚠ 缓存日期指针不存在，扫描目录重建")
    dates = _scan_cache_dir()
    if dates:
        _save_pointer(dates)
    return dates


def _save_pointer(dates):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(POINTER_FILE, 'w', encoding='utf-8') as f:
        json.dump({'dates': sorted(set(dates)),
                   'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                  f, ensure_ascii=False, indent=1)


def record_cache_date(date_key):
    """缓存写入后登记日期（save_amount_cache 调用）"""
    dates = load_cache_dates()
    if date_key not in dates:
        dates.append(date_key)
    _save_pointer(dates)


def get_prev_cache_date(today_key=None):
    """返回今天之前最近的缓存日期(YYYYMMDD)，没有则返回None"""
    if today_key is None:
        today_key = datetime.now().strftime('%Y%m%d')
    for d in reversed(load_cache_dates()):
        if d < today_key:
            return d
    return None


def get_cache_file(date_key):
    return os.path.join(CACHE_DIR, f'stock_amount_cache_{date_key}.json')


if __name__ == '__main__':
    print("缓存日期列表:", load_cache_dates())
    print("上一缓存日:", get_prev_cache_date())
