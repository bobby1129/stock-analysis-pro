#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""概念板块资金意图矩阵（正式版, 2026-09-24转正接入run_all.py）
p0「资金全景图」: 四象限计数大卡片 + 资金面研判
p1「失血强度榜」: 抽血率TOP5 (避坑)
p2「对倒嫌疑榜」: 巨量不留钱TOP5 (避坑)
p3「主攻方向榜」: 三共振TOP5 (寻宝)
p4「潜伏吸筹榜」: 钱进价未动TOP5 (寻宝)
指标: 留存率=净额/总成交(决心), 能量=总成交/公司家数(活跃度,亿/只)
空区诚实显示, 不放宽门槛凑数
数据源: akshare同花顺全量概念资金流(全口径)
"""
import os, sys, json
for k in ['HTTPS_PROXY','https_proxy','HTTP_PROXY','http_proxy']: os.environ.pop(k, None)
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro/scripts/daily_content'))
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta

from generate_concept_html import is_bucket_concept

OUT_DIR = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
CACHE_DIR = os.path.expanduser('~/stock-analysis-pro/cache/daily_content')

MIN_AMOUNT = 50     # 失血榜总成交门槛(亿)
MIN_NET = 3         # |净额|门槛(亿)
N_PER_ZONE = 5      # 每区显示条数
N_CACHE = 10        # 每区缓存条数(>10取top10, 不足全缓存)
ZONE_NAMES = ['bleed', 'fake', 'firm', 'lurk']


def trading_date():
    now = datetime.now()
    d = now if (now.hour, now.minute) >= (15, 30) else now - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime('%Y年%m月%d日'), d.strftime('%Y%m%d')


def fetch_data():
    df = ak.stock_fund_flow_concept(symbol="即时")
    for c in ['流入资金','流出资金','净额','行业-涨跌幅','公司家数','领涨股-涨跌幅']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df[~df['行业'].apply(is_bucket_concept)].copy()
    df['总额'] = df['流入资金'] + df['流出资金']
    df['留存率'] = df['净额'] / df['总额'] * 100
    df['能量'] = df['总额'] / df['公司家数']
    return df


CSS_BASE = '''
* { margin:0; padding:0; box-sizing:border-box; }
body { width:1080px; height:1920px; overflow:hidden;
  background:linear-gradient(160deg,#faf9f6 0%,#f5f3ee 55%,#f0ece2 100%);
  font-family:"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif; position:relative; }
.header { padding:62px 46px 0; }
.kicker { display:inline-block; font-size:28px; font-weight:800; letter-spacing:3px; color:#b8860b;
  border:2px solid #d4af37; border-radius:10px; padding:6px 16px; background:rgba(212,175,55,0.08); }
.title { font-size:86px; font-weight:900; color:#1a1a1a; margin-top:20px; letter-spacing:2px; }
.title .gold { color:#b8860b; } .title .red { color:#c0141c; } .title .green { color:#1d7a2f; }
.sub { font-size:32px; color:#888; margin-top:12px; font-weight:600; }
.verdict { margin:30px 46px 0; background:#fff; border:2px solid #d4af37; border-left:12px solid #b8860b;
  border-radius:16px; padding:24px 30px; font-size:38px; font-weight:800; color:#1a1a1a;
  line-height:1.5; box-shadow:0 4px 14px rgba(184,134,11,0.10); word-break:keep-all; }
.verdict .red { color:#dc143c; } .verdict .green { color:#228b22; }
.vsub { display:block; font-size:28px; font-weight:700; color:#888; margin-top:8px; }
.section { margin:28px 46px 0; background:#fff; border:2px solid #d4af37; border-radius:22px;
  padding:30px 28px 22px; box-shadow:0 4px 18px rgba(212,175,55,0.12); }
.sec-title { font-size:48px; font-weight:900; color:#1a1a1a; margin-bottom:6px; letter-spacing:1px; }
.sec-title .tag { font-size:27px; font-weight:700; color:#fff; border-radius:8px; padding:5px 14px;
  margin-left:12px; vertical-align:middle; letter-spacing:2px; }
.tag.warn { background:linear-gradient(90deg,#c0392b,#922b21); }
.tag.gold { background:linear-gradient(90deg,#d4af37,#b8860b); }
.tag.green { background:linear-gradient(90deg,#27ae60,#1d7a2f); }
.sec-note { font-size:28px; color:#999; margin-bottom:18px; font-weight:600; line-height:1.4; }
.footer { position:absolute; bottom:34px; left:0; right:0; text-align:center;
  font-size:26px; color:#999; font-weight:600; letter-spacing:1px; }
.footer .brand { color:#b8860b; font-weight:800; }
.lempty { font-size:34px; color:#aaa; padding:40px 4px; font-weight:600; text-align:center; }
.erow { display:flex; align-items:center; padding:28px 6px 24px; border-bottom:1px solid #f0ead9; }
.erow:last-child { border-bottom:none; }
.erank { width:64px; font-size:52px; font-weight:900; color:#d4af37; text-align:center; }
.emain { flex:1; min-width:0; padding-right:14px; }
.eline { display:flex; align-items:baseline; gap:14px; }
.ename { font-size:50px; font-weight:800; color:#1a1a1a; }
.ebadge { font-size:24px; font-weight:800; border-radius:6px; padding:3px 11px; white-space:nowrap; }
.badge-fire { color:#fff; background:linear-gradient(90deg,#e67e22,#c0392b); }
.badge-calm { color:#7a5c00; background:#f4e9c8; border:1px solid #e0cd90; }
.badge-dv { color:#fff; background:#c0392b; }
.badge-new { color:#fff; background:linear-gradient(90deg,#d4af37,#b8860b); }
.echg { font-size:34px; font-weight:700; margin-left:auto; white-space:nowrap; }
.etrack { height:16px; background:#f4efe2; border-radius:8px; margin:14px 0 11px; overflow:hidden; }
.ebar { height:100%; border-radius:7px; }
.emeta { font-size:28px; color:#999; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.eval { width:210px; text-align:right; font-size:60px; font-weight:900; letter-spacing:-1px; }
.eval .unit { font-size:30px; font-weight:700; margin-left:2px; }
.quad { margin:24px 46px 0; display:flex; gap:14px; }
.qbox { flex:1; background:#fff; border:2px solid #e0d9c8; border-radius:16px; padding:16px 8px; text-align:center; }
.qbox .qn { font-size:54px; font-weight:900; }
.qbox .ql { font-size:25px; color:#666; font-weight:700; margin-top:4px; }
.qbox.h .qn { color:#dc143c; } .qbox.w .qn { color:#b8860b; }
.qbox.l .qn { color:#228b22; } .qbox.b .qn { color:#666; }
'''


def energy_badge(e, med):
    if e >= med * 1.6:
        return f'<span class="ebadge badge-fire">🔥能量{e:.1f}</span>'
    return f'<span class="ebadge badge-calm">能量{e:.1f}亿/只</span>'


# ---------- 四区选择 + 缓存 ----------
def select_zones(active, med):
    """四区筛选, 每区按排序取前N_CACHE(10)条用于缓存, 显示时取前N_PER_ZONE(5)"""
    zones = {}
    zones['bleed'] = active[(active['净额'] <= -MIN_NET) & (active['总额'] >= MIN_AMOUNT)] \
        .sort_values('留存率').head(N_CACHE)
    zones['fake'] = active[(active['行业-涨跌幅'] > 0.8) & (active['净额'] > 0) &
                           (active['留存率'] < 1.5) & (active['总额'] >= 100)] \
        .sort_values('总额', ascending=False).head(N_CACHE)
    zones['firm'] = active[(active['行业-涨跌幅'] >= 0.5) & (active['净额'] >= MIN_NET) &
                           (active['留存率'] >= 3) & (active['能量'] >= med)] \
        .sort_values('留存率', ascending=False).head(N_CACHE)
    zones['lurk'] = active[(active['行业-涨跌幅'] < 0.5) & (active['净额'] >= MIN_NET) &
                           (active['留存率'] >= 4)] \
        .sort_values('留存率', ascending=False).head(N_CACHE)
    return zones


def save_zones_cache(zones, date_key):
    os.makedirs(CACHE_DIR, exist_ok=True)
    data = {}
    for zname, zdf in zones.items():
        data[zname] = [{'name': r['行业'], '留存率': round(float(r['留存率']), 2),
                        '净额': round(float(r['净额']), 2), '涨幅': round(float(r['行业-涨跌幅']), 2)}
                       for _, r in zdf.iterrows()]
    path = os.path.join(CACHE_DIR, f'matrix_zone_cache_{date_key}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f'✓ 四区缓存已保存: {path}')


def load_yesterday_zones(date_key):
    """往前找最近一个交易日的四区缓存, 返回 {zone: set(names)}; 找不到返回None"""
    d = datetime.strptime(date_key, '%Y%m%d')
    for back in range(1, 10):
        prev = (d - timedelta(days=back)).strftime('%Y%m%d')
        path = os.path.join(CACHE_DIR, f'matrix_zone_cache_{prev}.json')
        if os.path.exists(path):
            try:
                with open(path, encoding='utf-8') as f:
                    cached = json.load(f)
                print(f'✓ 加载昨日四区缓存: {path}')
                return {z: set(item['name'] for item in cached.get(z, [])) for z in ZONE_NAMES}
            except Exception as e:
                print(f'⚠ 缓存加载失败: {e}')
                return None
    print('⚠ 无历史四区缓存, 本次全部标记NEW')
    return None


def build_row(i, r, med, mode, is_new=False):
    """mode: bleed(失血,绿条) / fake(对倒,红条) / firm(主攻,金条) / lurk(潜伏,金条)"""
    name = r['行业']
    chg = r['行业-涨跌幅']
    chg_color = '#dc143c' if chg > 0 else '#228b22'
    badge = energy_badge(r['能量'], med)
    new_badge = '<span class="ebadge badge-new">NEW</span>' if is_new else ''

    if mode == 'bleed':
        dv = '<span class="ebadge badge-dv">⚠背离</span>' if chg > 0.3 else ''
        bar_pct = min(abs(r['留存率']) / 30 * 100, 100)
        bar = 'linear-gradient(90deg,#5cb87a,#1d7a2f)'
        val_color = '#1d7a2f'
        val = f"-{abs(r['留存率']):.1f}<span class='unit'>%</span>"
        meta = f"净流出{abs(r['净额']):.1f}亿 · 成交{r['总额']:.0f}亿 · 龙头{r['领涨股']} {r['领涨股-涨跌幅']:+.1f}%"
    elif mode == 'fake':
        dv = ''
        bar_pct = min(r['总额'] / 2000 * 100, 100)
        bar = 'linear-gradient(90deg,#e08573,#a04030)'
        val_color = '#a04030'
        val = f"{r['留存率']:.1f}<span class='unit'>%</span>"
        meta = f"成交{r['总额']:.0f}亿 · 流入+{r['净额']:.1f}亿 · 龙头{r['领涨股']} {r['领涨股-涨跌幅']:+.1f}%"
    else:  # firm / lurk
        dv = ''
        bar_pct = min(r['留存率'] / 12 * 100, 100)
        bar = 'linear-gradient(90deg,#e6c762,#b8860b)'
        val_color = '#b8860b'
        val = f"+{r['留存率']:.1f}<span class='unit'>%</span>"
        meta = f"净流入+{r['净额']:.1f}亿 · 成交{r['总额']:.0f}亿 · 龙头{r['领涨股']} {r['领涨股-涨跌幅']:+.1f}%"

    return f'''
    <div class="erow">
      <div class="erank">{i}</div>
      <div class="emain">
        <div class="eline"><span class="ename">{name}</span>{new_badge}{dv}{badge}
          <span class="echg" style="color:{chg_color}">{chg:+.2f}%</span></div>
        <div class="etrack"><div class="ebar" style="width:{bar_pct:.0f}%;background:{bar}"></div></div>
        <div class="emeta">{meta}</div>
      </div>
      <div class="eval" style="color:{val_color}">{val}</div>
    </div>'''


def empty_zone(msg):
    return f'<div class="lempty">— {msg} —</div>'


def page(kicker, title_html, sub, verdict, sections, footer):
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<style>{CSS_BASE}</style></head>
<body>
  <div class="header">
    <span class="kicker">{kicker}</span>
    <div class="title">{title_html}</div>
    <div class="sub">{sub}</div>
  </div>
  <div class="verdict">💡 {verdict}</div>
  {sections}
  <div class="footer">{footer}</div>
</body></html>'''


def zone_rows(zone_df, med, mode, empty_msg, prev_names=None):
    """显示前N_PER_ZONE条; prev_names=昨日该区名单(set)用于NEW标记, None则全标NEW"""
    show = zone_df.head(N_PER_ZONE)
    rows = ''.join(
        build_row(i, r, med, mode, is_new=(prev_names is None or r['行业'] not in prev_names))
        for i, (_, r) in enumerate(show.iterrows(), 1))
    return rows or empty_zone(empty_msg)


def compute_quadrants(df):
    """四象限统计（图片p0与动画视频共用，数据逻辑单一来源）
    返回 dict: active/q1~q4/total/mood + 每区之最头条"""
    active = df[df['总额'] > 20].copy()
    chg, net = active['行业-涨跌幅'], active['净额']
    q1 = active[(chg > 0.3) & (net > 0)]
    q2 = active[(chg > 0.3) & (net < 0)]
    q3 = active[(chg < -0.3) & (net > 0)]
    q4 = active[(chg < -0.3) & (net < 0)]

    def top_of(qdf, sortcol, asc, sign):
        if len(qdf):
            t = qdf.sort_values(sortcol, ascending=asc).iloc[0]
            return f"{t['行业']} {sign}{abs(t[sortcol]):.1f}{'%' if sortcol == '留存率' else '亿'}"
        return '—'

    total = len(active)
    up_ratio = len(q1) / total * 100 if total else 0
    if up_ratio >= 50:
        mood = f"资金面健康：{len(q1)}/{total} 板块价涨钱进，多头主导"
    elif len(q4) / total >= 0.6:
        mood = f"资金面恶劣：{len(q4)}/{total} 板块价跌钱出，普跌行情，轻仓观望"
    else:
        mood = f"资金面分化：健康上涨仅{len(q1)}个，跌且流出{len(q4)}个，结构性行情"

    return {
        'active': active, 'q1': q1, 'q2': q2, 'q3': q3, 'q4': q4,
        'total': total, 'mood': mood,
        'tops': {
            'q1': top_of(q1, '净额', False, '+'),
            'q2': top_of(q2, '净额', True, ''),
            'q3': top_of(q3, '净额', False, '+'),
            'q4': top_of(q4, '净额', True, ''),
        },
    }


def gen_p0(df, date_cn, med):
    """市场概览页: 象限四宫格(大卡片) + 各区头条摘要"""
    qs = compute_quadrants(df)
    active, q1, q2, q3, q4 = qs['active'], qs['q1'], qs['q2'], qs['q3'], qs['q4']

    def qcard(cls, icon, label, sub, qdf, sortcol, asc, sign):
        if len(qdf):
            t = qdf.sort_values(sortcol, ascending=asc).iloc[0]
            head = f"{t['行业']} {sign}{abs(t[sortcol]):.1f}{'%' if sortcol=='留存率' else '亿'}"
        else:
            head = '—'
        return f'''<div class="qcard {cls}">
      <div class="qhead"><span class="qicon">{icon}</span><span class="qnum">{len(qdf)}</span></div>
      <div class="qlabel">{label}</div>
      <div class="qsub">{sub}</div>
      <div class="qfoot">之最：{head}</div>
    </div>'''

    cards = (
        qcard('h', '📈', '健康上涨', '价涨 + 资金流入', q1, '净额', False, '+') +
        qcard('w', '⚠️', '涨但流出', '价涨 + 资金撤离（背离）', q2, '净额', True, '') +
        qcard('l', '🕵️', '跌却流入', '价跌 + 资金逆势进场', q3, '净额', False, '+') +
        qcard('b', '📉', '跌且流出', '价跌 + 资金撤离（回避）', q4, '净额', True, '')
    )

    total = qs['total']
    mood = qs['mood']

    html = f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<style>{CSS_BASE}
.qgrid {{ margin:36px 46px 0; display:grid; grid-template-columns:1fr 1fr; gap:26px; }}
.qcard {{ background:#fff; border:3px solid #e0d9c8; border-radius:24px; padding:36px 34px 30px;
  box-shadow:0 4px 18px rgba(0,0,0,0.05); }}
.qcard.h {{ border-color:#f0b8bc; background:linear-gradient(165deg,#fff 60%,#fdf1f2); }}
.qcard.w {{ border-color:#ecd9a0; background:linear-gradient(165deg,#fff 60%,#fdf8ea); }}
.qcard.l {{ border-color:#b8dfc2; background:linear-gradient(165deg,#fff 60%,#f0f9f2); }}
.qcard.b {{ border-color:#d8d4cc; background:linear-gradient(165deg,#fff 60%,#f6f5f2); }}
.qhead {{ display:flex; align-items:center; gap:14px; }}
.qicon {{ font-size:44px; }}
.qnum {{ font-size:88px; font-weight:900; line-height:1; letter-spacing:-2px; }}
.qcard.h .qnum {{ color:#dc143c; }} .qcard.w .qnum {{ color:#b8860b; }}
.qcard.l .qnum {{ color:#1d7a2f; }} .qcard.b .qnum {{ color:#888; }}
.qlabel {{ font-size:40px; font-weight:900; color:#1a1a1a; margin-top:14px; letter-spacing:2px; }}
.qsub {{ font-size:26px; color:#999; font-weight:600; margin-top:6px; }}
.qfoot {{ font-size:27px; font-weight:800; color:#555; margin-top:18px; padding-top:16px;
  border-top:1px dashed #e0d9c8; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
</style></head>
<body>
  <div class="header">
    <span class="kicker">盘后情报局 · 资金意图矩阵 0/4</span>
    <div class="title">资金<span class="gold">全景图</span></div>
    <div class="sub">{date_cn} 收盘 ｜ {total}个活跃板块（成交&gt;20亿）按 价格×资金 分四象限</div>
  </div>
  <div class="verdict">💡 {mood}</div>
  <div class="qgrid">{cards}</div>
  <div class="footer">象限判据：涨跌幅±0.3% × 净额正负 ｜ 全口径（含散户）｜ <span class="brand">盘后情报局</span> 每日16:00</div>
</body></html>'''
    return html


def zone_content(zkey, zones, date_cn, med, prev_zones):
    """四榜内容单一来源（图片p1-p4与动画视频共用，2026-09-26抽取）
    返回 dict: title_html / sub / verdict / section"""
    zdf = zones[zkey]
    pz = prev_zones and prev_zones.get(zkey)

    if zkey == 'bleed':
        rows = zone_rows(zdf, med, 'bleed', '今日无明显失血板块', pz)
        if len(zdf):
            t = zdf.iloc[0]
            verdict = f"失血最狠：<span class='green'>{t['行业']}</span>，每100元成交撤走{abs(t['留存率']):.0f}元（{t['净额']:.1f}亿）"
        else:
            verdict = "今日无显著失血板块，资金面平稳"
        section = f'''<div class="section">
    <div class="sec-title">🩸 抽血率排行<span class="tag warn">失血</span></div>
    <div class="sec-note">成交每100元被抽走多少，大小板块同尺度可比 ｜ ⚠背离=还在涨但钱在撤（拉高出货嫌疑）</div>
    {rows}
  </div>'''
        title_html = '资金<span class="green">失血榜</span>'
        sub = f'{date_cn} 收盘 ｜ 抽血率=净流出/成交额，越高失血越狠'
    elif zkey == 'fake':
        rows = zone_rows(zdf, med, 'fake', '今日无明显对倒板块', pz)
        if len(zdf):
            t = zdf.iloc[0]
            verdict = f"最大绞肉机：<span class='red'>{t['行业']}</span> 成交{t['总额']:.0f}亿，100元只留下{t['留存率']:.1f}元——涨是涨了，钱没留下"
        else:
            verdict = "今日无巨量对倒板块，涨幅含金量普遍较高"
        section = f'''<div class="section">
    <div class="sec-title">🎭 巨量不留钱<span class="tag warn">对倒</span></div>
    <div class="sec-note">涨幅&gt;0.8%、净流入为正，但留存率&lt;1.5%：天量换手后净额勉强为正，小心边拉边出 ｜ 红条=成交规模</div>
    {rows}
  </div>'''
        title_html = '对倒<span class="red">嫌疑榜</span>'
        sub = f'{date_cn} 收盘 ｜ 流入是假象：成交巨大但钱留不住'
    elif zkey == 'firm':
        rows = zone_rows(zdf, med, 'firm', '今日无三共振主攻板块，资金观望', pz)
        if len(zdf):
            t = zdf.iloc[0]
            verdict = f"最坚决资金在 <span class='red'>{t['行业']}</span>：每100元成交留下{t['留存率']:.0f}元（+{t['净额']:.1f}亿），买了不撒手"
        else:
            verdict = "今日无价涨+高留存+高能量的三共振板块，主线不明"
        section = f'''<div class="section">
    <div class="sec-title">💪 三共振主攻<span class="tag gold">价涨+钱进+锁仓</span></div>
    <div class="sec-note">涨幅≥0.5% + 净流入≥3亿 + 留存率≥3% + 能量≥全市场中位（{med:.1f}亿/只）｜ 金条=留存率，越高越坚决</div>
    {rows}
  </div>'''
        title_html = '主攻<span class="gold">方向榜</span>'
        sub = f'{date_cn} 收盘 ｜ 按<b>留存率</b>排名：不看流入多少，看流入后<b>卖不卖</b>'
    else:  # lurk
        rows = zone_rows(zdf, med, 'lurk', '今日无潜伏吸筹信号', pz)
        if len(zdf):
            t = zdf.iloc[0]
            verdict = f"最隐蔽的吸筹：<span class='red'>{t['行业']}</span> 价格几乎没动（{t['行业-涨跌幅']:+.2f}%），资金却留下{t['留存率']:.1f}%（+{t['净额']:.1f}亿）——埋伏期特征"
        else:
            verdict = "今日无高留存潜伏板块，资金没有悄悄布局的动作"
        section = f'''<div class="section">
    <div class="sec-title">🕵️ 钱进价未动<span class="tag green">潜伏</span></div>
    <div class="sec-note">涨幅&lt;0.5%但留存率≥4%进场：不等拉升才追，专找资金已埋伏、价格未启动的板块 ｜ 金条=留存率</div>
    {rows}
  </div>'''
        title_html = '潜伏<span class="green">吸筹榜</span>'
        sub = f'{date_cn} 收盘 ｜ 主力埋伏期信号：资金进场，价格未动'

    return {'title_html': title_html, 'sub': sub, 'verdict': verdict, 'section': section}


# 各榜图片版页脚规则（前端图片保留；视频版不展示，规则存档DAILY_CONTENT.md）
ZONE_FOOTERS = {
    'bleed': '门槛：成交≥50亿·净流出≥3亿 ｜ 全口径净额（含散户）｜ <span class="brand">盘后情报局</span> 每日16:00',
    'fake': '门槛：成交≥100亿·涨幅&gt;0.8%·留存&lt;1.5% ｜ 全口径（含散户）｜ <span class="brand">盘后情报局</span> 每日16:00',
    'firm': '全口径净额（含散户）｜ <span class="brand">盘后情报局</span> 每日16:00',
    'lurk': '门槛：净流入≥3亿·留存≥4% ｜ 全口径净额（含散户）｜ <span class="brand">盘后情报局</span> 每日16:00',
}
ZONE_KICKERS = {'bleed': '盘后情报局 · 资金意图矩阵 1/4', 'fake': '盘后情报局 · 资金意图矩阵 2/4',
                'firm': '盘后情报局 · 资金意图矩阵 3/4', 'lurk': '盘后情报局 · 资金意图矩阵 4/4'}


def gen_p1(zones, date_cn, med, prev_zones):
    zc = zone_content('bleed', zones, date_cn, med, prev_zones)
    return page(ZONE_KICKERS['bleed'], zc['title_html'], zc['sub'],
                zc['verdict'], zc['section'], ZONE_FOOTERS['bleed'])

def gen_p2(zones, date_cn, med, prev_zones):
    zc = zone_content('fake', zones, date_cn, med, prev_zones)
    return page(ZONE_KICKERS['fake'], zc['title_html'], zc['sub'],
                zc['verdict'], zc['section'], ZONE_FOOTERS['fake'])

def gen_p3(zones, date_cn, med, prev_zones):
    zc = zone_content('firm', zones, date_cn, med, prev_zones)
    return page(ZONE_KICKERS['firm'], zc['title_html'], zc['sub'],
                zc['verdict'], zc['section'], ZONE_FOOTERS['firm'])

def gen_p4(zones, date_cn, med, prev_zones):
    zc = zone_content('lurk', zones, date_cn, med, prev_zones)
    return page(ZONE_KICKERS['lurk'], zc['title_html'], zc['sub'],
                zc['verdict'], zc['section'], ZONE_FOOTERS['lurk'])


def main():
    date_cn, date_key = trading_date()
    df = fetch_data()
    active = df[df['总额'] > 20]
    med = float(active['能量'].median())
    print(f'概念总数: {len(df)}, 活跃板块: {len(active)}, 能量中位数: {med:.2f}亿/只, 交易日 {date_cn}')

    # 四区筛选 + 缓存 + NEW标记
    zones = select_zones(active, med)
    prev_zones = load_yesterday_zones(date_key)
    save_zones_cache(zones, date_key)
    for z in ZONE_NAMES:
        n_new = sum(1 for _, r in zones[z].head(N_PER_ZONE).iterrows()
                    if prev_zones is None or r['行业'] not in prev_zones.get(z, set()))
        print(f'  {z}: 候选{len(zones[z])}个, 显示前{min(len(zones[z]), N_PER_ZONE)}条, 其中NEW {n_new}条')

    from playwright.sync_api import sync_playwright
    pages = [(f'matrix_p0_{date_key}', gen_p0(df, date_cn, med)),
             (f'matrix_p1_{date_key}', gen_p1(zones, date_cn, med, prev_zones)),
             (f'matrix_p2_{date_key}', gen_p2(zones, date_cn, med, prev_zones)),
             (f'matrix_p3_{date_key}', gen_p3(zones, date_cn, med, prev_zones)),
             (f'matrix_p4_{date_key}', gen_p4(zones, date_cn, med, prev_zones))]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={'width':1080,'height':1920}, device_scale_factor=2)
        for name, html in pages:
            hpath = os.path.join(OUT_DIR, f'{name}.html')
            with open(hpath,'w',encoding='utf-8') as f: f.write(html)
            pg = context.new_page()
            pg.goto(f'file://{hpath}')
            pg.wait_for_load_state('networkidle')
            r = pg.evaluate("""() => {
                const sels = ['.section','.qgrid'];
                let last = null;
                for (const s of sels) { const es=document.querySelectorAll(s); if(es.length) last=es[es.length-1]; }
                const footer = document.querySelector('.footer');
                return {lastBottom: last? Math.round(last.getBoundingClientRect().bottom):0,
                        footerTop: Math.round(footer.getBoundingClientRect().top),
                        scrollH: document.body.scrollHeight};
            }""")
            ok = r['lastBottom'] < r['footerTop'] and r['scrollH'] <= 1920
            png = os.path.join(OUT_DIR, f'{name}.png')
            pg.screenshot(path=png, full_page=False)
            pg.close()
            gap = r['footerTop'] - r['lastBottom']
            print(f'✓ {name}: {os.path.getsize(png)/1024:.0f}KB 溢出检测{"✓余量"+format(gap,".0f")+"px" if ok else "✗溢出"}')
        context.close(); browser.close()


if __name__ == '__main__':
    main()
