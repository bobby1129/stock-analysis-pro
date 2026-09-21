#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成概念板块日报HTML - 同花顺源（拆分为2张：涨幅TOP10 + 净流入TOP10）"""

import sys, os, json, time
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))

for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

from datetime import datetime
from collectors.ths_concept import fetch_ths_concept_fund_flow


def analyze_concepts():
    """用同花顺概念资金流向"""
    concepts = fetch_ths_concept_fund_flow(top_n=30, verbose=True)
    
    results = []
    for c in concepts:
        results.append({
            'name': c['name'],
            'change_today': c.get('change_pct', 0),
            'flow_in': c.get('net', 0),  # 净流入(亿)
            'leader': c.get('leader', ''),
            'leader_pct': c.get('leader_pct', 0),
        })
    
    # 按涨幅排序
    results.sort(key=lambda x: x['change_today'], reverse=True)
    return results


def generate_hot_html(data):
    """生成涨幅排行HTML（10条）"""
    
    hot_concepts = data[:10]
    
    rows_html = ''
    for i, c in enumerate(hot_concepts, 1):
        color = "#dc143c" if c['change_today'] > 0 else "#228b22"
        rows_html += f'''
        <div class="concept-row">
            <div class="rank">{i}</div>
            <div class="concept-name">{c['name']}</div>
            <div class="concept-change" style="color:{color}">{c['change_today']:+.2f}%</div>
            <div class="concept-leader">{c['leader']} {c['leader_pct']:+.1f}%</div>
        </div>
        '''
    
    css = '''
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    width: 1080px;
    height: 1920px;
    background: linear-gradient(180deg, #faf9f6 0%, #f5f3ee 100%);
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    color: #1a1a1a;
    padding: 100px 45px 80px;
    overflow: hidden;
}
.header { text-align: center; margin-bottom: 40px; }
.date { font-size: 36px; color: #666; margin-bottom: 12px; letter-spacing: 4px; }
.title {
    font-size: 72px; font-weight: 800;
    background: linear-gradient(90deg, #d4af37, #b8860b, #d4af37);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    letter-spacing: 6px;
}
.section {
    background: #fff; border-radius: 20px;
    padding: 30px 35px; margin-bottom: 28px;
    border: 2px solid #d4af37;
    box-shadow: 0 4px 24px rgba(212,175,55,0.15);
}
.section-title {
    font-size: 38px; color: #b8860b;
    margin-bottom: 20px; padding-bottom: 14px;
    border-bottom: 2px solid #d4af37; font-weight: 700;
}
.concept-header {
    display: flex; align-items: center;
    padding: 16px 22px; background: rgba(212,175,55,0.08);
    border-radius: 10px; margin-bottom: 12px;
    border: 1px solid #e8e4d9;
}
.concept-header .rank,
.concept-header .concept-name,
.concept-header .concept-change,
.concept-header .concept-leader {
    font-size: 28px; color: #b8860b; font-weight: 600;
}
.concept-row {
    display: flex; align-items: center;
    padding: 16px 22px; background: #faf9f6;
    border-radius: 10px; margin-bottom: 12px;
    border: 1px solid #e8e4d9;
}
.rank { font-size: 36px; font-weight: 800; color: #b8860b; width: 50px; }
.concept-name { font-size: 34px; font-weight: 600; color: #1a1a1a; flex: 1; }
.concept-change { font-size: 36px; font-weight: 800; width: 130px; text-align: right; }
.concept-leader { font-size: 28px; color: #666; width: 240px; text-align: right; }
.footer { text-align: center; margin-top: 24px; font-size: 26px; color: #999; }
'''
    
    date_str = datetime.now().strftime("%Y年%m月%d日")
    
    html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>{css}</style>
</head>
<body>
    <div class="header">
        <div class="date">{date_str}</div>
        <div class="title">概念板块表现</div>
    </div>
    <div class="section">
        <div class="section-title">📈 今日涨幅排行</div>
        <div class="concept-header">
            <div class="rank">排名</div>
            <div class="concept-name">概念名称</div>
            <div class="concept-change">涨跌幅</div>
            <div class="concept-leader">领涨股</div>
        </div>
        {rows_html}
    </div>
    <div class="footer">数据来源：同花顺概念板块 | 仅供参考，不构成投资建议</div>
</body>
</html>'''
    
    return html


def generate_flow_html(data):
    """生成净流入排行HTML（10条）"""
    
    flow_concepts = sorted(data, key=lambda x: x['flow_in'], reverse=True)[:10]
    
    rows_html = ''
    for i, c in enumerate(flow_concepts, 1):
        flow_color = "#dc143c" if c['flow_in'] > 0 else "#228b22"
        change_color = "#dc143c" if c['change_today'] > 0 else "#228b22"
        rows_html += f'''
        <div class="flow-row">
            <div class="flow-rank">{i}</div>
            <div class="flow-name">{c['name']}</div>
            <div class="flow-change" style="color:{change_color}">{c['change_today']:+.2f}%</div>
            <div class="flow-value" style="color:{flow_color}">{c['flow_in']:.1f}亿</div>
        </div>
        '''
    
    css = '''
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    width: 1080px;
    height: 1920px;
    background: linear-gradient(180deg, #faf9f6 0%, #f5f3ee 100%);
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    color: #1a1a1a;
    padding: 100px 45px 80px;
    overflow: hidden;
}
.header { text-align: center; margin-bottom: 40px; }
.date { font-size: 36px; color: #666; margin-bottom: 12px; letter-spacing: 4px; }
.title {
    font-size: 72px; font-weight: 800;
    background: linear-gradient(90deg, #d4af37, #b8860b, #d4af37);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    letter-spacing: 6px;
}
.section {
    background: #fff; border-radius: 20px;
    padding: 30px 35px; margin-bottom: 28px;
    border: 2px solid #d4af37;
    box-shadow: 0 4px 24px rgba(212,175,55,0.15);
}
.section-title {
    font-size: 38px; color: #b8860b;
    margin-bottom: 20px; padding-bottom: 14px;
    border-bottom: 2px solid #d4af37; font-weight: 700;
}
.flow-header {
    display: flex; align-items: center;
    padding: 16px 22px; background: rgba(212,175,55,0.08);
    border-radius: 10px; margin-bottom: 12px;
    border: 1px solid #e8e4d9;
}
.flow-header .flow-rank,
.flow-header .flow-name,
.flow-header .flow-change,
.flow-header .flow-value {
    font-size: 28px; color: #b8860b; font-weight: 600;
}
.flow-row {
    display: flex; align-items: center;
    padding: 16px 22px; background: #faf9f6;
    border-radius: 10px; margin-bottom: 12px;
    border: 1px solid #e8e4d9;
}
.flow-rank { font-size: 36px; font-weight: 800; color: #b8860b; width: 50px; }
.flow-name { font-size: 34px; font-weight: 600; color: #1a1a1a; flex: 1; }
.flow-change { font-size: 34px; font-weight: 700; width: 130px; text-align: right; }
.flow-value { font-size: 36px; font-weight: 800; width: 150px; text-align: right; }
.footer { text-align: center; margin-top: 24px; font-size: 26px; color: #999; }
'''
    
    date_str = datetime.now().strftime("%Y年%m月%d日")
    
    html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>{css}</style>
</head>
<body>
    <div class="header">
        <div class="date">{date_str}</div>
        <div class="title">概念板块表现</div>
    </div>
    <div class="section">
        <div class="section-title">💰 净流入排行（亿元）</div>
        <div class="flow-header">
            <div class="flow-rank">排名</div>
            <div class="flow-name">概念名称</div>
            <div class="flow-change">涨跌幅</div>
            <div class="flow-value">净流入</div>
        </div>
        {rows_html}
    </div>
    <div class="footer">数据来源：同花顺概念板块 | 仅供参考，不构成投资建议</div>
</body>
</html>'''
    
    return html


if __name__ == '__main__':
    print("采集概念数据...")
    data = analyze_concepts()
    
    print(f"获取 {len(data)} 个概念")
    
    output_dir = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
    os.makedirs(output_dir, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    
    # 生成涨幅排行HTML（10条）
    print("生成涨幅排行HTML...")
    hot_html = generate_hot_html(data)
    output_file = os.path.join(output_dir, f'concept_p1_{date_str}.html')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(hot_html)
    
    print(f"✓ 涨幅排行HTML已生成: {output_file}")
    
    # 生成净流入排行HTML（10条）
    print("生成净流入排行HTML...")
    flow_html = generate_flow_html(data)
    output_file = os.path.join(output_dir, f'concept_p2_{date_str}.html')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(flow_html)
    
    print(f"✓ 净流入排行HTML已生成: {output_file}")
