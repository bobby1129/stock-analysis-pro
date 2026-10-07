#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""点火雷达 — 自下而上资金聚集扫描 (替换异常信号3张, 连板梯队保留在generate_anomaly)

设计文档: IGNITION_RADAR_DESIGN.md
管线: L1全市场触发扫描 → L2反向概念聚类 → L3位置/首放/形态 → L4催化新闻
输出: ignition_p0(概览) + ignition_p1..pn(事件卡片) + anomaly_p4(连板梯队, 沿用)

用法:
    cd ~/stock-analysis-pro && python3 scripts/daily_content/generate_ignition.py
    可选: --date YYYYMMDD (默认今天)
          --debug-keep (保留中间数据JSON)
"""

import sys, os, json, time, argparse, re
from datetime import datetime

sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))

for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

import requests

_ROOT = os.path.expanduser('~/stock-analysis-pro')
_INDEX_FILE = os.path.join(_ROOT, 'data', 'stock_concept_index.json')
_OUTPUT_DIR = os.path.join(_ROOT, 'output', 'daily_content')

# ── 触发层参数 (设计文档 §3) ──
TRIGGER_VOL_RATIO = 2.0       # 量比阈值
TRIGGER_CHANGE_PCT = 3.0      # 涨幅门槛%
TRIGGER_TURNOVER = 3.0        # 换手率门槛%
MAX_LIANBAN = 2               # 剔除连板>N天的(资金早已在场)
CLUSTER_THRESHOLD = 3.0       # 加权聚类阈值 (设计文档 §4.2)
MAX_EVENTS = 5                # 事件卡片上限(用户确认: 按实际需要, 默认5)
MAX_STOCKS_PER_CARD = 6       # 卡片内触发股上限

# ── 涨停限幅 ──
def limit_pct_of(code):
    """板块限幅: 创业30/科创68 = 20%, 主板 = 10%"""
    if code.startswith(('30', '68')):
        return 20.0
    return 10.0


def detect_quote_date():
    """上证指数行情日期 YYYYMMDD (节假日运行=上一交易日)"""
    try:
        r = requests.get('https://hq.sinajs.cn/list=sh000001',
                         headers={'User-Agent': 'Mozilla/5.0',
                                  'Referer': 'https://finance.sina.com.cn'},
                         timeout=10)
        r.encoding = 'gbk'
        parts = r.text.split('"')[1].split(',')
        return parts[30].replace('-', '')   # YYYY-MM-DD → YYYYMMDD
    except Exception:
        return None


def fetch_all_market():
    """全A股行情(腾讯批量, 含OHLC/量比/换手) — 复用generate_anomaly的股票列表逻辑"""
    # 股票代码列表: 新浪翻页 (breadth.py 同口径)
    url = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           "Market_Center.getHQNodeData")
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://finance.sina.com.cn"}
    all_codes = []
    for node in ["sh_a", "sz_a"]:
        for page in range(1, 60):
            params = {"page": page, "num": 100, "sort": "symbol", "asc": 1,
                      "node": node, "symbol": "", "_s_r_a": "page"}
            try:
                r = requests.get(url, params=params, headers=headers, timeout=15)
                if not r.text.startswith('['):
                    break
                data = json.loads(r.text)
                if not data:
                    break
                all_codes.extend(item['symbol'] for item in data if item.get('symbol'))
            except Exception:
                break
            time.sleep(0.15)
    print(f"股票代码: {len(all_codes)}")

    # 腾讯批量行情 (字段索引已验证 2026-10-07: 1名称 3现价 5开盘 32涨跌幅 33最高 34最低 37成交额万 38换手 49量比)
    all_stocks = []
    for i in range(0, len(all_codes), 50):
        batch = all_codes[i:i+50]
        try:
            resp = requests.get(f"https://qt.gtimg.cn/q={','.join(batch)}", timeout=10)
            resp.encoding = 'gbk'
            for line in resp.text.strip().split(';'):
                line = line.strip()
                if not line or '=' not in line or 'unknown' in line:
                    continue
                var_part, data_part = line.split("=", 1)
                sym = var_part.replace("v_", "").strip()
                parts = data_part.strip('"').split("~")
                if len(parts) < 50:
                    continue
                try:
                    all_stocks.append({
                        'symbol': sym,
                        'name': parts[1],
                        'code': parts[2],
                        'price': float(parts[3] or 0),
                        'open': float(parts[5] or 0),
                        'change_pct': float(parts[32] or 0),
                        'high': float(parts[33] or 0),
                        'low': float(parts[34] or 0),
                        'amount_w': float(parts[37] or 0),   # 成交额(万)
                        'turnover': float(parts[38] or 0),   # 换手率%
                        'volume_ratio': float(parts[49] or 0),
                    })
                except (ValueError, IndexError):
                    continue
        except Exception:
            pass
        if (i // 50) % 20 == 0:
            print(f"  行情 {len(all_stocks)}/{len(all_codes)}")
        time.sleep(0.1)
    return all_stocks


def l1_trigger(stocks, zt_lianban_map):
    """L1 触发层 → (触发池, 概览四档统计)"""
    # 概览统计: 全部量比>2的股票按涨幅四档 (用户提议的P0)
    overview = {'up3': 0, 'up0_3': 0, 'dn0_3': 0, 'dn3': 0, 'total': 0}
    valid = []
    for s in stocks:
        name = s.get('name', '')
        cp = s.get('change_pct')
        if not isinstance(cp, (int, float)):
            continue
        if name.startswith('ST') or name.startswith('*') or name.startswith('退'):
            continue
        valid.append(s)

    for s in valid:
        vr = s.get('volume_ratio') or 0
        if vr <= TRIGGER_VOL_RATIO:
            continue
        overview['total'] += 1
        cp = s['change_pct']
        if cp >= 3:
            overview['up3'] += 1
        elif cp >= 0:
            overview['up0_3'] += 1
        elif cp >= -3:
            overview['dn0_3'] += 1
        else:
            overview['dn3'] += 1

    # 触发池: 量比>2 + 涨幅>=3 + 换手>=3 + 剔连板>=3
    pool = []
    for s in valid:
        vr = s.get('volume_ratio') or 0
        if vr <= TRIGGER_VOL_RATIO:
            continue
        if s['change_pct'] < TRIGGER_CHANGE_PCT:
            continue
        if (s.get('turnover') or 0) < TRIGGER_TURNOVER:
            continue
        lb = zt_lianban_map.get(s['code'], 1)
        if lb > MAX_LIANBAN:
            continue
        # 涨停判定(板块限幅)
        lim = limit_pct_of(s['code'])
        s['is_limit_up'] = s['change_pct'] >= lim - 0.2
        s['lianban'] = lb
        pool.append(s)

    pool.sort(key=lambda x: x['change_pct'], reverse=True)
    print(f"L1: 放量股{overview['total']} 触发池{len(pool)}")
    return pool, overview


def l2_cluster(pool):
    """L2 聚类层 (LLM多标签归类 + 三轮合并) → 事件列表 + 孤立异动

    设计文档 §4 (2026-10-07修订: LLM归类替代反向索引)
    三轮合并解决"相似二级标签被强拆"碎片化:
      R1 主标签精确匹配(权重1.0), 加权和>=3 成事件
      R2 未满3的桶并入次标签命中(权重0.5), 加权和>=3 成事件
      R3 仍未满的, 同一级行业下二级桶合并再判(R3事件标注'一级行业')
    一股多事件: 归入加权得分最高事件为主属, 其余标"(兼)"
    """
    from llm_industry import classify_batch

    cls = classify_batch([{'code': s['code'], 'name': s['name']} for s in pool])
    for s in pool:
        c = cls.get(s['code'], {})
        s['labels'] = c.get('labels', [])
        s['label_reason'] = c.get('reason', '')
        s['unknown'] = not s['labels']

    unknown = [s for s in pool if s['unknown']]
    if unknown:
        print(f"  LLM无法归类: {len(unknown)}只 {[s['name'] for s in unknown[:5]]}")
    classified = [s for s in pool if not s['unknown']]

    # ── R1+R2: 按二级标签桶(主标签1.0/次标签0.5) ──
    buckets = {}   # l2 → {'score': float, 'members': [(stock, weight, l1)]}
    for s in classified:
        for i, lb in enumerate(s['labels']):
            w = 1.0 if i == 0 else 0.5
            b = buckets.setdefault(lb['l2'], {'score': 0.0, 'members': [], 'l1': lb['l1']})
            b['score'] += w
            b['members'].append((s, w, lb['l1']))

    events = []
    consumed_l2 = set()   # 已并入事件的二级桶
    for l2, b in sorted(buckets.items(), key=lambda kv: -kv[1]['score']):
        if b['score'] >= CLUSTER_THRESHOLD and l2 not in consumed_l2:
            consumed_l2.add(l2)
            # R2: 吸收未满阈值但含该l2次标签的桶? — 次标签已计入本桶score, 无需二次吸收;
            # R2实际作用: 主标签桶不满3时, 等待R3一级合并
            events.append({
                'level': 'l2', 'name': l2, 'l1': b['l1'],
                'score': b['score'],
                'members': [m[0] for m in b['members']],
                'merged_from': [l2],
            })

    # ── R3: 未满阈值的二级桶按一级行业合并 ──
    l1_left = {}
    for l2, b in buckets.items():
        if l2 in consumed_l2:
            continue
        l1_left.setdefault(b['l1'], {'score': 0.0, 'members': {}, 'l2s': []})
        l1_left[b['l1']]['score'] += b['score']
        l1_left[b['l1']]['l2s'].append(l2)
        for s, w, _l1 in b['members']:
            # 同股去重取最大权重
            prev = l1_left[b['l1']]['members'].get(s['symbol'], (s, 0.0))
            l1_left[b['l1']]['members'][s['symbol']] = (s, max(prev[1], w))
    for l1, agg in sorted(l1_left.items(), key=lambda kv: -kv[1]['score']):
        if len(agg['l2s']) < 2:
            continue  # 单桶未满3不构成合并事件, 归孤立
        if agg['score'] >= CLUSTER_THRESHOLD:
            for l2 in agg['l2s']:
                consumed_l2.add(l2)
            events.append({
                'level': 'l1', 'name': l1, 'l1': l1,
                'score': agg['score'],
                'members': [m[0] for m in agg['members'].values()],
                'merged_from': agg['l2s'],
            })

    events.sort(key=lambda e: e['score'], reverse=True)
    events = events[:MAX_EVENTS]

    # ── 主属归一: 每只股归入得分最高事件为主属, 其余标(兼) ──
    primary_of = {}
    for e in events:
        for s in e['members']:
            if s['symbol'] not in primary_of:
                primary_of[s['symbol']] = e['name']
    for e in events:
        e['main_members'] = [s for s in e['members'] if primary_of.get(s['symbol']) == e['name']]
        e['aux_members'] = [s for s in e['members'] if primary_of.get(s['symbol']) != e['name']]

    # 共振标记: 主属成员中≥2只同时出现在其他事件
    for e in events:
        reso = 0
        other_syms = {s['symbol'] for x in events if x is not e for s in x['members']}
        for s in e['main_members']:
            if s['symbol'] in other_syms:
                reso += 1
        e['resonance'] = reso >= 2

    # 孤立异动: 不属于任何事件的(含LLM无法归类的)
    event_syms = {s['symbol'] for e in events for s in e['members']}
    isolated = [s for s in pool if s['symbol'] not in event_syms]

    return events, isolated


def l3_enrich(members):
    """L3 位置/首放/形态 — 腾讯250日K线"""
    from plans.industry_screener import tencent_kline, calc_price_percentile

    for s in members:
        try:
            klines = tencent_kline(s['code'], days=260)
        except Exception:
            klines = []
        if len(klines) < 25:
            s.update({'p60': None, 'vol_tag': '?', 'shape': ''})
            continue

        price = s['price']
        s['p60'] = calc_price_percentile(klines, price, 60)
        s['p250'] = calc_price_percentile(klines, price, 250)

        # 首次放量判定: 今日量 vs 前20日均量×1.5; 前20日内有无放量日
        vols = [float(k[5]) for k in klines]  # klines[-1]是今日
        today_vol = vols[-1]
        hist = vols[:-1]
        burst_n = 0
        first_burst = False
        if len(hist) >= 20:
            base20 = sum(hist[-20:]) / 20
            if base20 > 0 and today_vol > base20 * 1.5:
                # 前20日内有无其他放量日 (滚动20日均量)
                for j in range(len(hist) - 20, len(hist)):
                    if j < 20:
                        continue
                    b = sum(hist[j-20:j]) / 20
                    if b > 0 and hist[j] > b * 1.5:
                        burst_n += 1
                first_burst = burst_n == 0
        if first_burst:
            s['vol_tag'] = '首放'
        else:
            s['vol_tag'] = f'第{burst_n + 1}次'
        s['burst_n'] = burst_n

        # K柱形态 (当日OHLC)
        o, c = s['open'], s['price']
        h, l = s['high'], s['low']
        full = (h - l) if h > l else (c * 0.01)
        body = abs(c - o)
        upper = h - max(o, c)
        lower = min(o, c) - l
        cp = s['change_pct']
        if s.get('is_limit_up'):
            s['shape'] = '🔥涨停'
        elif cp >= 5 and body / full >= 0.6 and c > o:
            s['shape'] = '🔥长阳点火'
        elif upper >= body * 2 and cp < 5:
            s['shape'] = '⚠长上影'
        elif lower >= body * 2 and cp >= 0:
            s['shape'] = '🟢长下影'
        elif body / full <= 0.2:
            s['shape'] = '十字星'
        else:
            s['shape'] = '阳线' if c > o else '阴线'
        time.sleep(0.6)


def l4_catalyst(event_names):
    """L4 催化: Google News RSS (走本地代理)"""
    catalysts = {}
    proxies = {'http': 'http://127.0.0.1:10809', 'https': 'http://127.0.0.1:10809'}
    for name in event_names:
        try:
            from urllib.parse import quote as _quote
            q = _quote(name)
            url = (f'https://news.google.com/rss/search?q={q}+when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans')
            r = requests.get(url, proxies=proxies, timeout=10,
                             headers={'User-Agent': 'Mozilla/5.0'})
            titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', r.text)
            if not titles:
                titles = re.findall(r'<title>(.*?)</title>', r.text)
            # 去掉频道名(Google 新闻/RSS名)和来源后缀
            items = []
            for t in titles:
                ts = t.strip()
                # 跳过频道名/查询回显(形如 "XXX when:1d" 或 Google 新闻)
                if ts in ('Google 新闻', 'Google News', name) or 'when:1d' in ts or ts.startswith('"'):
                    continue
                t = re.sub(r'\s*-\s*[^-]+$', '', ts).strip()
                if t:
                    items.append(t)
                if len(items) >= 3:
                    break
            catalysts[name] = items
        except Exception:
            catalysts[name] = []
    return catalysts


def fetch_lianban():
    """连板梯队 (复用breadth.fetch_limit_stats)"""
    from collectors.breadth import fetch_limit_stats
    return fetch_limit_stats()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=None, help='默认取行情数据实际日期(节假日=上一交易日)')
    parser.add_argument('--debug-keep', action='store_true')
    args = parser.parse_args()

    print("\n=== 全市场行情 ===")
    stocks = fetch_all_market()
    print(f"行情: {len(stocks)}只")

    # 行情实际日期 (节假日/假期后运行=上一交易日数据, 用于验证回跑)
    date_str = args.date or detect_quote_date() or datetime.now().strftime('%Y%m%d')
    print(f"数据日期: {date_str}")

    print("\n=== 连板数据 ===")
    limit_stats = fetch_lianban()
    zt_lianban_map = {s['code']: s['lianban'] for s in limit_stats.get('zt_stocks', [])}
    print(f"涨停{limit_stats['zt_count']} 跌停{limit_stats['dt_count']}")

    print("\n=== L1 触发层 ===")
    pool, overview = l1_trigger(stocks, zt_lianban_map)

    print("\n=== L2 聚类层(LLM多标签) ===")
    events, isolated = l2_cluster(pool)
    for e in events:
        tag = '合并:' + '+'.join(e['merged_from']) if e['level'] == 'l1' else ''
        print(f"  {e['name']}: score={e['score']:.1f} 成员{len(e['members'])} "
              f"主属{len(e['main_members'])} 共振={e['resonance']} {tag}")
    print(f"  孤立异动: {len(isolated)}")

    print("\n=== L3 位置/首放/形态 ===")
    for e in events:
        l3_enrich(e['members'])

    print("\n=== L4 催化 ===")
    catalysts = l4_catalyst([e['name'] for e in events])
    for n, c in catalysts.items():
        print(f"  {n}: {c[:2]}")

    # ── 结论标签 ──
    for e in events:
        ms = e['main_members']
        good = sum(1 for s in ms if (s.get('p60') is not None and s['p60'] < 70
                                     and s.get('vol_tag') == '首放'))
        bad = sum(1 for s in ms if (s.get('p60') is not None and s['p60'] > 70
                                    and s.get('vol_tag', '').startswith('第')
                                    and int(re.sub(r'\D', '', s.get('vol_tag') or '2') or 2) >= 2))
        if good >= 2:
            e['verdict'] = '🔥点火确认'
        elif bad > len(ms) / 2:
            e['verdict'] = '⚠高位勿追'
        elif not catalysts.get(e['name']) and good >= 1:
            e['verdict'] = '👁暗流观察'
        else:
            e['verdict'] = '👁观察'

    # ── 概念主力净流入 (ths_mainforce当日缓存, 缺失不阻塞) ──
    mf = {}
    try:
        from collectors.ths_mainforce import fetch_concept_main_force
        mf = fetch_concept_main_force(names=[e['name'] for e in events],
                                      verbose=False, use_cache=True)
    except Exception as ex:
        print(f"  (主力净流入不可用: {ex})")
    for e in events:
        e['main_net'] = mf.get(e['name'], {}).get('main_net')

    # ── 中间数据落盘(调试/回测) ──
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    dump = {
        'date': date_str,
        'overview': overview,
        'pool_size': len(pool),
        'events': [{k: v for k, v in e.items()} for e in events],
        'isolated': [{'symbol': s['symbol'], 'name': s['name'],
                      'change_pct': s['change_pct'], 'volume_ratio': s['volume_ratio']}
                     for s in isolated[:20]],
        'lianban': {'zt_count': limit_stats['zt_count'], 'dt_count': limit_stats['dt_count']},
    }
    dump_path = os.path.join(_OUTPUT_DIR, f'ignition_data_{date_str}.json')
    with open(dump_path, 'w', encoding='utf-8') as f:
        json.dump(dump, f, ensure_ascii=False, indent=1, default=str)
    if not args.debug_keep:
        print(f"中间数据: {dump_path} (回测用, 保留)")

    # ── HTML生成 ──
    from generate_ignition_html import build_pages
    pages = build_pages(events, isolated, overview, catalysts, date_str)
    for fname, html in pages:
        path = os.path.join(_OUTPUT_DIR, fname)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"✓ {path}")


if __name__ == '__main__':
    main()
