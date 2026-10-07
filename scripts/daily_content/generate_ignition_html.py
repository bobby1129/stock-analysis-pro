#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""点火雷达 HTML 页面构建 (P0概览 + 事件卡片)

版式约束 (AGENTS.md 抖音教训):
- 竖屏1080×1920, 左右边距≥130px (内容区≤820px)
- A股配色: 红涨绿跌
- 金色高级感风格沿用现有daily_content
"""

from datetime import datetime

_BODY_BASE = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    width: 1080px; height: 1920px;
    background: linear-gradient(180deg, #faf9f6 0%, #f5f3ee 100%);
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    color: #1a1a1a;
    padding: 120px 130px 80px;
    overflow: hidden;
}
.header { text-align: center; margin-bottom: 46px; }
.date { font-size: 40px; color: #666; margin-bottom: 14px; letter-spacing: 4px; }
.title {
    font-size: 76px; font-weight: 800;
    background: linear-gradient(90deg, #d4af37, #b8860b, #d4af37);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    letter-spacing: 6px;
}
.subtitle { font-size: 36px; color: #8a7440; margin-top: 12px; letter-spacing: 2px; }
.section {
    background: #fff; border-radius: 24px;
    padding: 40px 36px; margin-bottom: 28px;
    border: 2px solid #d4af37;
    box-shadow: 0 4px 24px rgba(212,175,55,0.15);
}
.footer { text-align: center; margin-top: 24px; font-size: 26px; color: #999; }
"""


def _fmt_date(date_str):
    try:
        d = datetime.strptime(date_str, '%Y%m%d')
        return d.strftime('%Y年%m月%d日')
    except ValueError:
        return date_str


def _page(title_html, body_html, date_str):
    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>{_BODY_BASE}</style>
</head>
<body>
    <div class="header">
        <div class="date">{_fmt_date(date_str)}</div>
        <div class="title">资金点火雷达</div>
        {title_html}
    </div>
    {body_html}
    <div class="footer">数据来源：沪深A股 | 仅供参考，不构成投资建议</div>
</body>
</html>'''


def build_overview_page(overview, events, isolated, date_str):
    """P0: 全市场放量扫描概览 (四档分布)"""
    total = overview['total']
    up_sum = overview['up3'] + overview['up0_3']
    ratio = (up_sum / total * 100) if total else 0
    if ratio > 60:
        mood, mood_color = '资金进攻', '#dc143c'
    elif ratio >= 40:
        mood, mood_color = '多空分歧', '#b8860b'
    else:
        mood, mood_color = '资金出逃', '#228b22'

    bars = [
        ('≥ +3%', overview['up3'], '#dc143c', '点火主力段'),
        ('0% ~ +3%', overview['up0_3'], '#e8737f', ''),
        ('-3% ~ 0%', overview['dn0_3'], '#6cae6c', ''),
        ('≤ -3%', overview['dn3'], '#228b22', '出货/恐慌段'),
    ]
    max_n = max((n for _, n, _, _ in bars), default=1) or 1
    bars_html = ''
    for label, n, color, note in bars:
        w = max(int(n / max_n * 100), 2) if n else 2
        note_html = f'<span style="font-size:28px;color:#999;margin-left:14px;">{note}</span>' if note else ''
        bars_html += f'''
        <div style="margin-bottom:34px;">
            <div style="display:flex;justify-content:space-between;font-size:38px;margin-bottom:10px;">
                <span style="font-weight:700;">{label}</span>
                <span style="font-weight:800;color:{color};">{n}只{note_html}</span>
            </div>
            <div style="background:#f0ede4;border-radius:12px;height:44px;">
                <div style="width:{w}%;height:44px;background:{color};border-radius:12px;"></div>
            </div>
        </div>'''

    event_line = f'点火事件 {len(events)} 个' if events else '今日无点火事件'
    iso_line = f' · 孤立异动 {len(isolated)} 只' if isolated else ''

    body = f'''
    <div class="section">
        <div style="text-align:center;margin-bottom:34px;">
            <div style="font-size:40px;color:#666;">全市场放量股（量比&gt;2）</div>
            <div style="font-size:110px;font-weight:800;color:#b8860b;line-height:1.2;">{total}<span style="font-size:44px;color:#888;font-weight:600;"> 只</span></div>
        </div>
        {bars_html}
    </div>
    <div class="section" style="text-align:center;">
        <div style="font-size:44px;font-weight:700;margin-bottom:16px;">
            上涨段占比 <span style="color:{mood_color};font-size:64px;font-weight:800;">{ratio:.0f}%</span>
        </div>
        <div style="display:inline-block;background:{mood_color};color:#fff;font-size:42px;font-weight:800;padding:14px 48px;border-radius:40px;letter-spacing:4px;">{mood}</div>
        <div style="font-size:34px;color:#8a7440;margin-top:26px;">{event_line}{iso_line}</div>
    </div>'''
    return f'ignition_p0_{date_str}.html', _page(
        '<div class="subtitle">全市场放量扫描 · 情绪概览</div>', body, date_str)


def _pos_tag(p60):
    if p60 is None:
        return '—', '#888'
    if p60 < 30:
        return f'底部p{p60:.0f}', '#b8860b'
    if p60 <= 70:
        return f'中部p{p60:.0f}', '#666'
    return f'高位p{p60:.0f}', '#8a4a9e'


def build_event_page(idx, event, catalysts, date_str):
    """事件卡片 P1..Pn"""
    members = sorted(event['members'],
                     key=lambda s: (0 if s.get('vol_tag') == '首放' else 1,
                                    -(s.get('change_pct') or 0)))
    shown = members[:6]
    rest = len(members) - len(shown)

    rows = ''
    for s in shown:
        cp = s.get('change_pct', 0)
        color = '#dc143c' if cp > 0 else '#228b22'
        cp_str = '涨停' if s.get('is_limit_up') else f'{cp:+.1f}%'
        pos, pos_color = _pos_tag(s.get('p60'))
        vol_tag = s.get('vol_tag', '?')
        vol_style = 'color:#d4af37;font-weight:800;' if vol_tag == '首放' else 'color:#999;'
        shape = s.get('shape', '')
        aux = ' <span style="font-size:24px;color:#aaa;">(兼)</span>' if s in event.get('aux_members', []) else ''
        rows += f'''
        <div style="display:flex;align-items:center;padding:20px 10px;border-bottom:1px solid #eee;">
            <div style="width:170px;font-size:36px;font-weight:700;">{s['name']}{aux}</div>
            <div style="width:110px;font-size:36px;font-weight:800;color:{color};text-align:right;">{cp_str}</div>
            <div style="width:150px;font-size:30px;color:{pos_color};text-align:center;">{pos}</div>
            <div style="width:110px;font-size:30px;{vol_style}text-align:center;">{vol_tag}</div>
            <div style="flex:1;font-size:30px;text-align:right;color:#555;">{shape}</div>
        </div>'''
    if rest > 0:
        rows += f'<div style="text-align:center;font-size:30px;color:#999;padding:14px;">等 {len(members)} 只触发（其余 {rest} 只未列）</div>'
    if not rows:
        rows = '<div style="text-align:center;font-size:32px;color:#888;padding:20px;">暂无</div>'

    # 催化 (LLM汇总排序, items=[{'source','text'}])
    cat = catalysts.get(event['name']) or {}
    cats = cat.get('items') or []
    if cats:
        cat_html = '<div style="font-size:32px;color:#555;line-height:1.7;">' + \
            '<br>'.join(f'· <span style="color:#b8860b;font-weight:700;">{c["source"]}</span>｜{c["text"][:26]}'
                        for c in cats[:3]) + '</div>'
        cat_title = '📰 当日催化'
    else:
        cat_html = '<div style="font-size:34px;color:#8a7440;font-weight:700;">无公开催化 — 纯资金聚集，留意"暗流"埋伏</div>'
        cat_title = '👁 催化检索'

    net = event.get('main_net')
    net_html = ''
    if net is not None:
        nc = '#dc143c' if net >= 0 else '#228b22'
        net_html = f'<div style="font-size:32px;color:#666;margin-top:10px;">概念当日主力净流入 <span style="color:{nc};font-weight:800;">{net:+.1f}亿</span></div>'

    reso = '<span style="font-size:30px;background:#b8860b;color:#fff;padding:6px 18px;border-radius:20px;margin-left:16px;">板块共振</span>' if event.get('resonance') else ''
    verdict = event.get('verdict', '')
    v_color = {'🔥点火确认': '#dc143c', '⚠高位勿追': '#8a4a9e'}.get(verdict, '#b8860b')

    body = f'''
    <div class="section">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <div style="font-size:52px;font-weight:800;color:#b8860b;">{event['name']}{reso}</div>
            <div style="font-size:34px;font-weight:800;color:{v_color};background:#faf6ec;padding:10px 22px;border-radius:16px;border:1px solid #e8dcc0;">{verdict}</div>
        </div>
        <div style="font-size:34px;color:#666;">触发 {event['score']:.0f} 只（加权）· 涨停 {sum(1 for s in event['members'] if s.get('is_limit_up'))} 只 · 首放 {sum(1 for s in event['members'] if s.get('vol_tag')=='首放')} 只</div>
        {net_html}
    </div>
    <div class="section">
        <div style="display:flex;font-size:28px;color:#999;padding:0 10px 12px;border-bottom:2px solid #d4af37;">
            <div style="width:170px;">名称</div>
            <div style="width:110px;text-align:right;">涨幅</div>
            <div style="width:150px;text-align:center;">位置(60日)</div>
            <div style="width:110px;text-align:center;">量能</div>
            <div style="flex:1;text-align:right;">形态</div>
        </div>
        {rows}
    </div>
    <div class="section">
        <div style="font-size:36px;font-weight:700;color:#b8860b;margin-bottom:16px;">{cat_title}</div>
        {cat_html}
    </div>'''
    return f'ignition_p{idx}_{date_str}.html', _page(
        f'<div class="subtitle">点火事件 #{idx}</div>', body, date_str)


def build_empty_events_page(date_str):
    """无事件日的替代页(保证图集不缺页)"""
    body = '''
    <div class="section" style="text-align:center;padding:80px 40px;">
        <div style="font-size:48px;font-weight:700;color:#8a7440;margin-bottom:24px;">今日无板块点火事件</div>
        <div style="font-size:34px;color:#999;line-height:1.8;">放量股未形成同概念聚集（同一概念加权触发&lt;3只）<br>资金分散，等待下一次集结</div>
    </div>'''
    return f'ignition_p1_{date_str}.html', _page(
        '<div class="subtitle">点火事件</div>', body, date_str)


def build_pages(events, isolated, overview, catalysts, date_str):
    """返回 [(filename, html), ...]"""
    pages = [build_overview_page(overview, events, isolated, date_str)]
    if events:
        for i, e in enumerate(events, 1):
            pages.append(build_event_page(i, e, catalysts, date_str))
    else:
        pages.append(build_empty_events_page(date_str))
    return pages
