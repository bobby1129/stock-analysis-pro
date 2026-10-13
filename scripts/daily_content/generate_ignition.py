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

# 概念名→885码 (v5概念聚合用; 加载失败不阻塞, 仅卡片少一个码字段)
try:
    with open(os.path.join(_ROOT, 'data', 'ths_concept_885_mapping.json'), encoding='utf-8') as _f:
        _CONCEPT_885 = json.load(_f)['concepts']
except Exception:
    _CONCEPT_885 = {}

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


# ── v5 概念聚合 (2026-10-12, IGNITION_RADAR_DESIGN.md §11) ──
CONCEPT_MIN_TRIGGER = 3     # 入围门槛: 同概念触发≥3只
PEN_FULL = 0.10             # 渗透率满分线: 触发数/成分家数 ≥10%
VR_LO, VR_HI = 0.8, 2.0     # 板块量比打分区间(0.8→0分, 2.0→满分)
W_PEN, W_VR, W_BURST = 1.2, 1.0, 0.8   # 打分权重(Phase 2回测校准)


def fetch_concept_member_counts():
    """概念成分家数 (gnzjl全口径'公司家数'字段, 与885概念名同体系)
    仅用于渗透率分母(全量口径), 与触发样本线严格分离(§11.1红线)"""
    import akshare as ak
    try:
        df = ak.stock_fund_flow_concept(symbol="即时")
        return {str(r['行业']): int(r['公司家数']) for _, r in df.iterrows()}
    except Exception as e:
        print(f'  ⚠ gnzjl成分家数不可用: {e}')
        return {}


def l2_concept_cluster(pool, member_counts, board_ratios):
    """L2' 概念聚合: F10个股→概念缓存反向聚合, 事件=885概念
    v6(2026-10-13, IGNITION_RADAR_DESIGN.md §12):
      - 聚合前LLM标签净化(llm_label_filter.purify_labels): 按F10主营业务剔擦边标签,
        只筛不造; 属性直通标签(专精特新/一带一路等)保留在个股标签但不参与聚合排名
      - 排序改绝对数量: 主键=净化后触发家数, tiebreaker=板块量比>首放占比
        (v5加权打分退役; score字段仍计算落盘供Phase2回测对比)
    返回 (events, isolated, f10_failed)
      events 含: name(=概念名)/concept_885/members/n_trigger/n_comp/penetration/
                 vr/burst_ratio/score/secondary_concepts
    """
    from collectors.ths_stock_concept import get_or_fetch
    from generate_concept_html import is_bucket_concept
    from llm_label_filter import purify_labels, is_attribute_concept

    cmap = get_or_fetch([s['code'] for s in pool])
    covered, failed = [], []
    for s in pool:
        c = cmap.get(s['code'])
        if c and c['names']:
            s['concepts'] = [n for n in c['names'] if not is_bucket_concept(n)]
            s['concept_source'] = c['source']
            covered.append(s)
        else:
            s['concepts'] = []
            failed.append(s)
    print(f"  F10概念覆盖: {len(covered)}/{len(pool)} (未覆盖{len(failed)})")

    # ── v6标签净化 (LLM按主营业务剔擦边标签, 带持久缓存) ──
    stats = purify_labels(covered)
    print(f"  标签净化: LLM{stats['llm']}只 缓存{stats['cached']}只 失败降级{stats['failed']}只")

    # ── 概念桶聚合 (净化标签, 属性直通标签不参与) ──
    buckets = {}   # 概念名 → [stocks]
    for s in covered:
        for cn in s.get('concepts_clean') or []:
            if is_attribute_concept(cn):
                continue
            buckets.setdefault(cn, []).append(s)
    cands = {cn: ms for cn, ms in buckets.items() if len(ms) >= CONCEPT_MIN_TRIGGER}
    print(f"  概念桶(净化后): {len(buckets)}个, 入围(≥{CONCEPT_MIN_TRIGGER}只): {len(cands)}个")

    # ── 首放占比需L3数据: 先对候选成员批量富化 ──
    cand_syms = {s['symbol'] for ms in cands.values() for s in ms}
    cand_stocks = [s for s in covered if s['symbol'] in cand_syms]
    l3_enrich(cand_stocks)

    # ── 打分 (v6: 排序用绝对数量, score仅落盘回测对比用) ──
    events = []
    for cn, ms in cands.items():
        n_trig = len(ms)
        n_comp = member_counts.get(cn)
        pen = (n_trig / n_comp) if n_comp else None
        pen_score = min((pen or 0.05) / PEN_FULL, 1.0)   # 家数缺失→中性0.05
        vr = (board_ratios.get(cn) or {}).get('ratio')
        vr_score = min(max(((vr if vr is not None else 1.0) - VR_LO) / (VR_HI - VR_LO), 0), 1)
        n_burst = sum(1 for s in ms if s.get('vol_tag') == '首放')
        burst = n_burst / n_trig
        score = W_PEN * pen_score + W_VR * vr_score + W_BURST * burst
        # 次级概念: ≥2只成员共同挂靠的其它概念(剔自身/属性标签), 按挂靠数取前2
        sec_count = {}
        for s in ms:
            for c2 in s.get('concepts_clean') or []:
                if c2 != cn and not is_attribute_concept(c2):
                    sec_count[c2] = sec_count.get(c2, 0) + 1
        secondary = sorted([c for c, n in sec_count.items() if n >= 2],
                           key=lambda c: (-sec_count[c], c))[:2]
        events.append({
            'level': 'concept', 'name': cn,
            'concept_885': _CONCEPT_885.get(cn),
            'members': sorted(ms, key=lambda s: -s['change_pct']),
            'n_trigger': n_trig, 'n_comp': n_comp,
            'penetration': round(pen, 3) if pen else None,
            'vr': vr, 'burst_ratio': round(burst, 2), 'n_burst': n_burst,
            'score': round(score, 3),
            'secondary_concepts': [{'name': c, 'n': sec_count[c],
                                    'vr': (board_ratios.get(c) or {}).get('ratio')}
                                   for c in secondary],
        })

    # v6排序: 绝对触发家数 > 板块量比 > 首放占比 (v5的score加权退役)
    events.sort(key=lambda e: (-e['n_trigger'],
                               -(e['vr'] if e['vr'] is not None else -1),
                               -e['burst_ratio']))

    # ── 重叠去重: 成员重叠率≥50%(交集/较小事件)视为同一事件簇, 只留分最高的 ──
    # (概念反向聚合下强相关概念会各自成事件霸屏, 如 短剧游戏⊂文化传媒概念 15/16)
    selected = []
    for e in events:
        syms = {s['symbol'] for s in e['members']}
        dup_of = None
        for k in selected:
            ksyms = {s['symbol'] for s in k['members']}
            inter = len(syms & ksyms)
            if inter / min(len(syms), len(ksyms)) >= 0.5:
                dup_of = k
                break
        if dup_of:
            e['duplicate_of'] = dup_of['name']
            # 被并事件的名字挂到主事件上作"兼"标注(信息不丢)
            dup_of.setdefault('alias_concepts', []).append(
                {'name': e['name'], 'score': e['score']})
        else:
            selected.append(e)
        if len(selected) >= MAX_EVENTS:
            break
    events = selected

    # ── 主属归一 / 共振 (沿用v4机制) ──
    primary_of = {}
    for e in events:
        for s in e['members']:
            if s['symbol'] not in primary_of:
                primary_of[s['symbol']] = e['name']
    for e in events:
        e['main_members'] = [s for s in e['members'] if primary_of.get(s['symbol']) == e['name']]
        e['aux_members'] = [s for s in e['members'] if primary_of.get(s['symbol']) != e['name']]
        other_syms = {s['symbol'] for x in events if x is not e for s in x['members']}
        e['resonance'] = sum(1 for s in e['main_members'] if s['symbol'] in other_syms) >= 2

    event_syms = {s['symbol'] for e in events for s in e['members']}
    isolated = [s for s in pool if s['symbol'] not in event_syms]
    return events, isolated, failed


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


def _llm_fallback_cluster(failed_stocks, events, isolated, member_counts, board_ratios):
    """F10未覆盖股的兜底: LLM归类主标签作伪概念桶, ≥3只成事件(level=llm_fallback)
    写回F10缓存(source=llm, 30天TTL)供次日聚合复用; 不成桶的归孤立"""
    from llm_industry import classify_batch
    from collectors.ths_stock_concept import save_llm_fallback
    cls = classify_batch([{'code': s['code'], 'name': s['name']} for s in failed_stocks])
    buckets = {}
    for s in failed_stocks:
        c = cls.get(s['code'], {})
        labels = c.get('labels', [])
        if labels:
            s['concepts'] = [labels[0]['l2']]
            s['concept_source'] = 'llm'
            save_llm_fallback(s['code'], s['concepts'])
            buckets.setdefault(labels[0]['l2'], []).append(s)
        else:
            s['concepts'] = []
    fb_events = []
    for cn, ms in buckets.items():
        if len(ms) >= CONCEPT_MIN_TRIGGER:
            l3_enrich(ms)
            n_trig = len(ms)
            n_comp = member_counts.get(cn)
            pen = (n_trig / n_comp) if n_comp else None
            pen_score = min((pen or 0.05) / PEN_FULL, 1.0)
            vr = (board_ratios.get(cn) or {}).get('ratio')
            vr_score = min(max(((vr if vr is not None else 1.0) - VR_LO) / (VR_HI - VR_LO), 0), 1)
            n_burst = sum(1 for s in ms if s.get('vol_tag') == '首放')
            score = (W_PEN * pen_score + W_VR * vr_score + W_BURST * n_burst / n_trig) * 0.8
            fb_events.append({
                'level': 'llm_fallback', 'name': cn, 'concept_885': None,
                'members': sorted(ms, key=lambda s: -s['change_pct']),
                'main_members': sorted(ms, key=lambda s: -s['change_pct']), 'aux_members': [],
                'resonance': False,
                'n_trigger': n_trig, 'n_comp': n_comp,
                'penetration': round(pen, 3) if pen else None,
                'vr': vr, 'burst_ratio': round(n_burst / n_trig, 2), 'n_burst': n_burst,
                'score': round(score, 3), 'secondary_concepts': [],
            })
    # 兜底事件与概念事件合并竞争TOP5 (v6排序口径一致: 绝对家数>量比>首放; ×0.8折减保留在score字段供回测)
    all_ev = sorted(events + fb_events,
                    key=lambda e: (-e['n_trigger'],
                                   -(e['vr'] if e['vr'] is not None else -1),
                                   -e['burst_ratio']))[:MAX_EVENTS]
    kept_syms = {s['symbol'] for e in all_ev for s in e['members']}
    iso_syms = {x['symbol'] for x in isolated}
    new_isolated = ([s for s in isolated if s['symbol'] not in kept_syms] +
                    [s for s in failed_stocks
                     if s['symbol'] not in kept_syms and s['symbol'] not in iso_syms])
    if fb_events:
        print(f"  LLM兜底事件: {[e['name'] for e in fb_events]}")
    return all_ev, new_isolated


def l3_enrich(members):
    """L3 位置/首放/形态 — 腾讯250日K线 (已富化的跳过, v5概念聚合层已预富化候选)"""
    from plans.industry_screener import tencent_kline, calc_price_percentile

    for s in members:
        if s.get('vol_tag') and s.get('vol_tag') != '?':
            continue
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


def _rss_titles(query, proxies, limit=5):
    """Google News RSS 搜索当日新闻标题 (走本地代理), 去频道名/查询回显/来源后缀"""
    from urllib.parse import quote as _quote
    url = (f'https://news.google.com/rss/search?q={_quote(query)}+when:1d'
           f'&hl=zh-CN&gl=CN&ceid=CN:zh-Hans')
    r = requests.get(url, proxies=proxies, timeout=10,
                     headers={'User-Agent': 'Mozilla/5.0'})
    titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', r.text)
    if not titles:
        titles = re.findall(r'<title>(.*?)</title>', r.text)
    items = []
    for t in titles:
        ts = t.strip()
        if ts in ('Google 新闻', 'Google News') or ts == query or 'when:1d' in ts or ts.startswith('"'):
            continue
        t2 = re.sub(r'\s*-\s*[^-]+$', '', ts).strip()
        if t2:
            items.append(t2)
        if len(items) >= limit:
            break
    return items


_CAT_PROMPT = '''你是A股短线研究员。板块"{name}"今日放量异动，成员股: {members}。
下面是当日检索到的新闻标题(方括号前缀标注来源: 行业=板块名检索, 个股=成员股名检索)。
请筛选与该板块今日异动可能相关的催化，去重合并后按重要性排序，输出最多3条。

重要性排序: 成员个股直接催化(订单/中标/业绩/并购/产品) > 行业政策或行业事件 > 泛板块观点
规则:
1. 剔除明显无关、旧闻复述、广告软文
2. 每条输出 source(催化所属成员股名; 行业级催化填"行业") 和 text(≤26字, 说清事实, 保留关键数字; text中不要重复source名称)
3. 无相关催化则输出空数组 []
4. 严格输出JSON数组, 无其他文字

新闻标题:
{lines}

输出格式:
[{{"source":"力勤资源","text":"中标印尼钴镍项目23亿"}}]'''


def _llm_summarize_catalyst(name, member_names, titled):
    """LLM汇集排序催化 (复用llm_industry的qwen3.6-flash链路), 失败返回[]"""
    from llm_industry import _call_llm
    lines = '\n'.join(f'[{src}] {t}' for src, t in titled[:40])
    prompt = _CAT_PROMPT.format(name=name,
                                members='、'.join(member_names[:8]),
                                lines=lines)
    for attempt in range(2):
        out = ''
        try:
            out = _call_llm(prompt, max_tokens=800).strip()
            if '```' in out:
                out = out.split('```')[1]
                if out.startswith('json'):
                    out = out[4:]
            arr = json.loads(out[out.index('['):out.rindex(']') + 1])
            items = []
            for it in arr[:3]:
                src = str(it.get('source', '行业'))[:12] or '行业'
                txt = str(it.get('text', '')).strip()[:30]
                if txt:
                    items.append({'source': src, 'text': txt})
            return items
        except Exception as ex:
            print(f'  ⚠ 催化LLM失败({attempt + 1}/2): {ex}; 输出前120字: {out[:120]}')
            time.sleep(2)
    return []


def l4_catalyst(events):
    """L4 催化: 行业+个股(主属前5)双层RSS检索 → LLM汇集按重要性排序
    返回 {event_name: {'items': [{'source','text'}], 'raw': {...}, 'llm': bool}}
    LLM失败时降级为原始标题罗列(items仍可用, llm=False)。"""
    catalysts = {}
    proxies = {'http': 'http://127.0.0.1:10809', 'https': 'http://127.0.0.1:10809'}
    for e in events:
        name = e['name']
        # 个股检索对象: 主属成员按卡片展示序(首放优先,涨幅降序)取前5
        ms = sorted(e['main_members'],
                    key=lambda s: (0 if s.get('vol_tag') == '首放' else 1,
                                   -(s.get('change_pct') or 0)))[:5]
        raw = {'industry': [], 'stocks': {}}
        try:
            raw['industry'] = _rss_titles(name, proxies, 5)
        except Exception as ex:
            print(f'  ⚠ {name} 行业新闻检索失败: {ex}')
        for s in ms:
            try:
                ts = _rss_titles(s['name'], proxies, 5)
                if ts:
                    raw['stocks'][s['name']] = ts
            except Exception:
                pass
            time.sleep(0.3)
        titled = [(f'行业', t) for t in raw['industry']] + \
                 [(n, t) for n, tl in raw['stocks'].items() for t in tl]
        items, llm_ok = [], False
        if titled:
            items = _llm_summarize_catalyst(name, [s['name'] for s in e['main_members']], titled)
            llm_ok = bool(items)
            if not items:
                # 降级: 原始标题罗列(行业优先, 各取前2), 保持旧行为不断链
                items = [{'source': '行业', 'text': t[:26]} for t in raw['industry'][:2]]
                items += [{'source': n, 'text': tl[0][:26]} for n, tl in list(raw['stocks'].items())[:1]]
        catalysts[name] = {'items': items, 'raw': raw, 'llm': llm_ok}
        print(f"  {name}: 行业{len(raw['industry'])}条 个股{sum(len(v) for v in raw['stocks'].values())}条"
              f" → {'LLM汇总' if llm_ok else ('降级罗列' if items else '无催化')}")
    return catalysts


def fetch_lianban():
    """连板梯队 (复用breadth.fetch_limit_stats)"""
    from collectors.breadth import fetch_limit_stats
    return fetch_limit_stats()


# LLM标签→板块名 手工映射兜底(模糊规则搞不定的高频标签; 值为881行业名或885概念名)
_BOARD_VR_ALIAS = {
    # 881一级行业方向
    '影视/动漫': '文化传媒',
    '出版/教育': '文化传媒',
    '文旅': '旅游及酒店',
    '输配电设备': '电网设备',
    '软件服务': '软件开发',
    # 885概念方向
    '算力': '东数西算(算力)',
    'AIDC': '数据中心(AIDC)',
    'CPO': '共封装光学(CPO)',
    '光模块': '共封装光学(CPO)',
    '谷子经济': 'IP经济(谷子经济)',
    'eVTOL': '飞行汽车(eVTOL)',
    '并购重组': '股权转让(并购重组)',
    '折叠屏': '柔性屏(折叠屏)',
}

# 行业级宽词, 无单一对应板块, 禁止模糊匹配(宁缺勿假):
# "电力设备"(储能+电机+风电混合)会误配"电力"(发电公用事业), 量比语义错误;
# "商贸/文旅"实际多为零售股, 误配"贸易"(11亿小行业)语义错误 (2026-10-12实测教训)
_BOARD_VR_SKIP = {'电力设备', '化工', '基础化工', '新材料', '机械', '医药', '消费',
                  '商贸/文旅', '商贸', '科技', '制造'}


def match_board_vr(event_name, ratios):
    """事件名(LLM标签)→板块量比。匹配不到返回None(不硬凑, 宁缺勿假)。
    LLM标签多为行业级宽词(化工/新材料/软件服务), 885概念多为题材级窄词, 因此
    只接受 板块名⊆事件名 方向(板块同级或更窄的组成部分), 严禁 事件名⊂板块名
    (如"化工"误匹配"磷化工"——以宽配窄是错的, 2026-10-12实测教训)。
    规则: 跳过名单 > 精确 > 别名表 > "/、"拆分逐段精确 > 归一化板块⊆事件(取最长=最具体)"""
    if not ratios or not event_name or event_name in _BOARD_VR_SKIP:
        return None

    def hit(name):
        r = ratios.get(name)
        if r:
            return {'concept': name, 'ratio': r['ratio'], 'today_amt': r['today_amt'],
                    'avg20': r['avg20'], 'date': r['date']}
        return None

    v = hit(event_name)
    if v:
        return v
    v = hit(_BOARD_VR_ALIAS.get(event_name, ''))
    if v:
        return v

    def norm(s):
        return s.replace('概念', '').replace('板块', '').replace(' ', '')

    # "/"拆分逐段: "锂电池/材料" → ["锂电池","材料"]
    parts = [p.strip() for p in re.split(r'[/、]', event_name) if len(p.strip()) >= 2]
    for p in parts:
        v = hit(p) or hit(_BOARD_VR_ALIAS.get(p, ''))
        if v:
            return v

    n_ev = norm(event_name)
    if len(n_ev) < 2:
        return None
    # 概念⊆事件 方向: 归一化概念名是事件名的子串
    cands = [n for n in ratios if len(norm(n)) >= 2 and norm(n) in n_ev]
    if cands:
        best = max(cands, key=lambda n: len(norm(n)))   # 取最长=最具体
        return hit(best)
    return None


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

    # ── v5前置: 全量板块线数据 (概念885量比 + gnzjl成分家数) ──
    print("\n=== 板块量比/成分家数(全量线) ===")
    try:
        from collectors.ths_board_hist import load_board_volume_ratio, ensure_history_fresh
        ensure_history_fresh(trade_date=date_str)   # 幂等: matrix已刷过则秒回
        board_ratios = load_board_volume_ratio()
        print(f"  概念量比: {len(board_ratios)}个")
    except Exception as ex:
        print(f"  ⚠ 板块量比不可用: {ex}")
        board_ratios = {}
    member_counts = fetch_concept_member_counts()
    print(f"  成分家数: {len(member_counts)}个概念")

    print("\n=== L2' 概念聚合(F10反向索引) ===")
    events, isolated, f10_failed = l2_concept_cluster(pool, member_counts, board_ratios)

    # F10未覆盖兜底: LLM归类主标签作伪概念入桶(标注source=llm); 仍失败归孤立
    if f10_failed:
        events, isolated = _llm_fallback_cluster(f10_failed, events, isolated,
                                                 member_counts, board_ratios)

    for e in events:
        pen = f"{e['penetration']*100:.1f}%" if e.get('penetration') else '—'
        vr = e.get('vr')
        print(f"  {e['name']}: 触发{e['n_trigger']}/{e.get('n_comp') or '?'}家"
              f" 渗透{pen} 量比{vr if vr else '—'} 首放{e['n_burst']}只"
              f" (score={e['score']:.2f}回测用)"
              f"{' [LLM兜底]' if e.get('level') == 'llm_fallback' else ''}")
    print(f"  孤立异动: {len(isolated)}")

    print("\n=== L3 位置/首放/形态 ===")
    for e in events:
        l3_enrich(e['members'])   # 已富化的自动跳过

    print("\n=== L4 催化 ===")
    catalysts = l4_catalyst(events)
    for n, c in catalysts.items():
        for it in c['items']:
            print(f"  {n}: [{it['source']}] {it['text']}")

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
        elif not (catalysts.get(e['name']) or {}).get('items') and good >= 1:
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

    # ── 板块量比: v5事件=概念, 直查自身885量比(全量线); LLM兜底事件走旧匹配链 ──
    try:
        from collectors.ths_board_hist import (load_board_volume_ratio,
                                               load_industry_volume_ratio)
        ratios885 = load_board_volume_ratio()
        for e in events:
            if e.get('level') == 'concept':
                r = ratios885.get(e['name'])
                e['board_vr'] = ({'concept': e['name'], 'ratio': r['ratio'],
                                  'today_amt': r['today_amt'], 'avg20': r['avg20'],
                                  'date': r['date']} if r else None)
            else:   # llm_fallback事件: 沿用v3.22b模糊匹配链
                all_ratios = {**ratios885, **load_industry_volume_ratio()}
                e['board_vr'] = match_board_vr(e['name'], all_ratios)
            if e.get('board_vr'):
                print(f"  {e['name']}: 板块量比{e['board_vr']['ratio']}")
    except Exception as ex:
        print(f"  (板块量比不可用: {ex})")
        for e in events:
            e.setdefault('board_vr', None)

    # ── 中间数据落盘(调试/回测) ──
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    dump = {
        'date': date_str,
        'overview': overview,
        'pool_size': len(pool),
        'events': [{k: v for k, v in e.items()} for e in events],
        'catalysts': catalysts,
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
