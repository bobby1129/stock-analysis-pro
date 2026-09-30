# -*- coding: utf-8 -*-
"""市场宽度采集 — 涨跌家数 + 涨跌停统计

数据源(优先级):
  1. 东财 push2 API (上证+深证合并) — 带Cookie防限流; 2026-09-30 本机返回全0(封禁), 不可靠
  2. 新浪 Market_Center.getHQNodeData 全量翻页 (hs_a, ~56页) — 2026-09-30 与同花顺APP对照验证通过:
     新浪 涨2566/平181/跌2824 (5571只) vs APP 涨2567/平170/跌2824 (5561只), 仅时点/边缘差异
     ⚠️ 腾讯 proxy.finance.qq.com getBoardRankList 已验证弃用: aStock板块仅4606只, 覆盖不全(缺~955只)
  3. akshare 涨跌停池

用法:
    from collectors.breadth import fetch_breadth, fetch_limit_stats
    breadth = fetch_breadth()  # {up, down, flat, limit_up, limit_down}  (东财失败自动降级新浪)
    limits = fetch_limit_stats(date='20260716')
"""

import json
import time
import requests
from datetime import datetime
from typing import Optional

_SINA_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://vip.stock.finance.sina.com.cn/',
}


def _sina_breadth(node: str = 'hs_a', max_pages: int = 70) -> dict:
    """新浪全量翻页统计涨跌家数。返回 {up, down, flat, total}; 失败返回 {}"""
    up = down = flat = total = 0
    page = 1
    try:
        while page <= max_pages:
            r = requests.get(
                'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
                'Market_Center.getHQNodeData',
                params={'page': page, 'num': 100, 'sort': 'symbol', 'asc': 1,
                        'node': node, 'symbol': '', '_s_r_a': 'init'},
                headers=_SINA_HEADERS, timeout=15)
            txt = r.text.strip()
            if not txt or txt == 'null':
                break
            data = json.loads(txt)
            if not data:
                break
            for it in data:
                try:
                    c = float(it['changepercent'])
                except (KeyError, ValueError, TypeError):
                    continue
                total += 1
                if c > 0:
                    up += 1
                elif c < 0:
                    down += 1
                else:
                    flat += 1
            page += 1
            time.sleep(0.08)
        if total > 0:
            return {'up': up, 'down': down, 'flat': flat, 'total': total}
    except Exception as e:
        print(f"[breadth] 新浪家数统计异常: {e}")
    return {}


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
    """获取涨跌家数。新浪全量翻页优先(2026-09-30与同花顺APP对照一致), 东财push2兜底。
    东财同日返回 涨2393/跌2730 与APP(2567/2824)偏差大, 口径存疑, 仅作兜底。
    新浪源不含涨跌停字段, 涨跌停由 fetch_limit_stats(akshare涨停池) 单独提供。"""
    result = {'up': 0, 'down': 0, 'flat': 0, 'limit_up': 0, 'limit_down': 0, 'source': ''}

    sb = _sina_breadth()
    if sb:
        result.update({'up': sb['up'], 'down': sb['down'], 'flat': sb['flat'],
                       'total': sb['total'], 'source': 'sina'})
        return result

    print("[breadth] 新浪统计失败, 降级东财push2")
    sh = _east_breadth("1.000001")
    time.sleep(0.5)
    sz = _east_breadth("0.399001")

    result.update({
        'up': sh.get('up', 0) + sz.get('up', 0),
        'down': sh.get('down', 0) + sz.get('down', 0),
        'flat': sh.get('flat', 0) + sz.get('flat', 0),
        'limit_up': sh.get('limit_up', 0) + sz.get('limit_up', 0),
        'limit_down': sh.get('limit_down', 0) + sz.get('limit_down', 0),
        'source': 'eastmoney',
    })
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
            for _, row in zt_df.iterrows():  # 全量遍历: head(30)会截断连板分布(涨停>30时首板家数被低估)
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
            for _, row in dt_df.iterrows():  # 全量遍历, 同涨停池
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
