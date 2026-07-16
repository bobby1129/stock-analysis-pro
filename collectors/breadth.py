# -*- coding: utf-8 -*-
"""市场宽度采集 — 涨跌家数 + 涨跌停统计

数据源:
  1. 东财 push2 API (上证+深证合并) — 带Cookie防限流
  2. akshare 涨跌停池

用法:
    from collectors.breadth import fetch_breadth, fetch_limit_stats
    breadth = fetch_breadth()  # {up, down, flat, limit_up, limit_down}
    limits = fetch_limit_stats(date='20260716')
"""

import json
import time
import requests
from datetime import datetime
from typing import Optional

# 复用config中的cookie
def _get_cookie():
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from config import load_config
        cfg = load_config()
        return cfg.get('eastmoney', {}).get('cookie', '')
    except Exception:
        return ''


def _east_breadth(secid, retries=3):
    """查询单个市场的涨跌家数，带重试 (使用 Cookie 绕过拦截)"""
    url = (
        "https://push2.eastmoney.com/api/qt/ulist.np/get?"
        f"fltt=2&fields=f104,f105,f106,f107,f108&secids={secid}"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }
    cookie = _get_cookie()
    if cookie:
        headers["Cookie"] = cookie

    for attempt in range(retries):
        try:
            time.sleep(0.5)  # 防抖
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                items = data.get("data", {}).get("diff", [])
                if items:
                    i = items[0]
                    return {
                        "up": i.get("f104", 0) or 0,
                        "down": i.get("f105", 0) or 0,
                        "flat": i.get("f106", 0) or 0,
                        "limit_up": i.get("f107", 0) or 0,
                        "limit_down": i.get("f108", 0) or 0,
                    }
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
            continue
    return {}


def fetch_breadth() -> dict:
    """获取涨跌家数 (东财HTTP API, 带Cookie)"""
    result = {'up': 0, 'down': 0, 'flat': 0, 'limit_up': 0, 'limit_down': 0}

    sh = _east_breadth("1.000001")
    time.sleep(0.5)
    sz = _east_breadth("0.399001")

    result['up'] = sh.get('up', 0) + sz.get('up', 0)
    result['down'] = sh.get('down', 0) + sz.get('down', 0)
    result['flat'] = sh.get('flat', 0) + sz.get('flat', 0)
    result['limit_up'] = sh.get('limit_up', 0) + sz.get('limit_up', 0)
    result['limit_down'] = sh.get('limit_down', 0) + sz.get('limit_down', 0)

    return result


def fetch_limit_stats(date: Optional[str] = None) -> dict:
    """涨跌停统计 (akshare)"""
    import akshare as ak

    if not date:
        date = datetime.now().strftime("%Y%m%d")

    result = {
        'zt_count': 0, 'dt_count': 0,
        'zt_stocks': [], 'dt_stocks': [],
        'date': date,
    }

    try:
        zt_df = ak.stock_zt_pool_em(date=date)
        if zt_df is not None and not zt_df.empty:
            result['zt_count'] = len(zt_df)
            for _, row in zt_df.head(30).iterrows():
                result['zt_stocks'].append({
                    'code': str(row.get('代码', '')),
                    'name': str(row.get('名称', '')),
                    'change_pct': float(row.get('涨跌幅', 0)),
                    'amount': float(row.get('成交额', 0)),
                    'first_time': str(row.get('首次封板时间', '')),
                    'last_time': str(row.get('最后封板时间', '')),
                    'reason': str(row.get('所属行业', '')),
                    'lianban': int(row.get('连板数', 1)),
                })
    except Exception as e:
        print(f"[breadth] 涨停池获取异常: {e}")

    try:
        dt_df = ak.stock_zt_pool_dtgc_em(date=date)
        if dt_df is not None and not dt_df.empty:
            result['dt_count'] = len(dt_df)
            for _, row in dt_df.head(20).iterrows():
                result['dt_stocks'].append({
                    'code': str(row.get('代码', '')),
                    'name': str(row.get('名称', '')),
                    'change_pct': float(row.get('涨跌幅', 0)),
                    'amount': float(row.get('成交额', 0)),
                })
    except Exception as e:
        print(f"[breadth] 跌停池获取异常: {e}")

    return result


if __name__ == '__main__':
    print("=== 涨跌家数 ===")
    b = fetch_breadth()
    print(json.dumps(b, ensure_ascii=False))

    print("\n=== 涨跌停统计 ===")
    ls = fetch_limit_stats()
    print(f"涨停: {ls['zt_count']}, 跌停: {ls['dt_count']}")
    for s in ls['zt_stocks'][:5]:
        print(f"  {s['name']}({s['code']}) {s['change_pct']:+.1f}% 连板{s['lianban']}")
