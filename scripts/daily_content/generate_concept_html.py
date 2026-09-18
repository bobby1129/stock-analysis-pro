#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成概念生命周期日报HTML - 同花顺源"""

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


def generate_html(data):
    """生成HTML"""
    
    # 涨幅排行
    hot_concepts = data[:10]
    
    # 流入排行
    flow_concepts = sorted(data, key=lambda x: x['flow_in'], reverse=True)[:8]
    
    # 涨幅排行HTML
    hot_html = ""
    for i, c in enumerate(hot_concepts[:8], 1):
        color = "#ff4757" if c['change_today'] > 0 else "#2ed573"
        hot_html += f'''
        <div class="concept-row">
            <div class="rank">{i}</div>
            <div class="concept-name">{c['name']}</div>
            <div class="concept-change" style="color:{color}">{c['change_today']:+.2f}%</div>
            <div class="concept-leader">{c['leader']} {c['leader_pct']:+.1f}%</div>
        </div>
        '''
    
    # 流入排行HTML
    flow_html = ""
    for i, c in enumerate(flow_concepts[:6], 1):
        flow_color = "#ff4757" if c['flow_in'] > 0 else "#2ed573"
        flow_html += f'''
        <div class="flow-row">
            <div class="flow-rank">{i}</div>
            <div class="flow-name">{c['name']}</div>
            <div class="flow-value" style="color:{flow_color}">{c['flow_in']:.1f}亿</div>
        </div>
        '''
    
    html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    width: 1080px;
    height: 1920px;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    color: #fff;
    padding: 120px 50px 120px;
    overflow: hidden;
}}
.header {{
    text-align: center;
    margin-bottom: 25px;
}}
.date {{
    font-size: 28px;
    color: #888;
    margin-bottom: 5px;
}}
.title {{
    font-size: 56px;
    font-weight: bold;
    background: linear-gradient(90deg, #ffd700, #ffb700);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}}
.section {{
    background: rgba(255,255,255,0.05);
    border-radius: 15px;
    padding: 25px 30px;
    margin-bottom: 20px;
    border: 1px solid rgba(255,215,0,0.2);
}}
.section-title {{
    font-size: 34px;
    color: #ffd700;
    margin-bottom: 15px;
    padding-bottom: 10px;
    border-bottom: 2px solid rgba(255,215,0,0.3);
}}
.concept-row {{
    display: flex;
    align-items: center;
    padding: 12px 15px;
    background: rgba(0,0,0,0.2);
    border-radius: 8px;
    margin-bottom: 8px;
}}
.rank {{
    font-size: 28px;
    font-weight: bold;
    color: #ffd700;
    width: 40px;
}}
.concept-name {{
    font-size: 26px;
    flex: 1;
}}
.concept-change {{
    font-size: 28px;
    font-weight: bold;
    width: 100px;
    text-align: right;
}}
.concept-leader {{
    font-size: 22px;
    color: #888;
    width: 200px;
    text-align: right;
}}
.flow-row {{
    display: flex;
    align-items: center;
    padding: 14px 15px;
    background: rgba(0,0,0,0.2);
    border-radius: 8px;
    margin-bottom: 8px;
}}
.flow-rank {{
    font-size: 26px;
    font-weight: bold;
    color: #ffd700;
    width: 40px;
}}
.flow-name {{
    font-size: 26px;
    flex: 1;
}}
.flow-value {{
    font-size: 28px;
    font-weight: bold;
    width: 120px;
    text-align: right;
}}
.footer {{
    text-align: center;
    margin-top: 20px;
    font-size: 22px;
    color: #666;
}}
</style>
</head>
<body>
    <div class="header">
        <div class="date">{datetime.now().strftime("%Y年%m月%d日")}</div>
        <div class="title">概念板块资金流向</div>
    </div>
    
    <div class="section">
        <div class="section-title">今日涨幅排行</div>
        {hot_html}
    </div>
    
    <div class="section">
        <div class="section-title">💰 净流入排行（亿元）</div>
        {flow_html}
    </div>
    
    <div class="footer">
        数据来源：同花顺概念板块 | 仅供参考，不构成投资建议
    </div>
</body>
</html>'''
    
    return html


if __name__ == '__main__':
    print("采集概念数据...")
    data = analyze_concepts()
    
    print(f"获取 {len(data)} 个概念")
    
    print("生成HTML...")
    html = generate_html(data)
    
    output_dir = os.path.expanduser('~/stock-analysis-pro/output/daily_content')
    os.makedirs(output_dir, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    output_file = os.path.join(output_dir, f'concept_{date_str}.html')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✓ HTML已生成: {output_file}")
