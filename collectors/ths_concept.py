# -*- coding: utf-8 -*-
"""同花顺概念板块采集 - 资金流向和涨跌幅

接口: https://data.10jqka.com.cn/funds/gnzjl/
无需Cookie，不触发滑块
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict


def fetch_ths_concept_fund_flow(top_n: int = 30, verbose: bool = False) -> List[Dict]:
    """获取同花顺概念资金流向
    
    Returns:
        [
            {
                'name': '概念名称',
                'flow_in': 123.45,      # 流入资金(亿)
                'flow_out': 100.00,     # 流出资金(亿)
                'net': 23.45,           # 净额(亿)
                'change_pct': 2.5,      # 涨跌幅(%)
                'leader': '领涨股',
                'leader_pct': 10.0,     # 领涨股涨幅(%)
            },
            ...
        ]
    """
    url = "https://data.10jqka.com.cn/funds/gnzjl/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://data.10jqka.com.cn/"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = 'gbk'
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        table = soup.find('table')
        
        if not table:
            if verbose:
                print("[ths_concept] 未找到表格")
            return []
        
        rows = table.find_all('tr')[1:]  # 跳过表头
        
        data = []
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 10:
                try:
                    item = {
                        'name': cells[1].get_text(strip=True),
                        'flow_in': float(cells[4].get_text(strip=True)),
                        'flow_out': float(cells[5].get_text(strip=True)),
                        'net': float(cells[6].get_text(strip=True)),
                        'change_pct': float(cells[3].get_text(strip=True).replace('%', '')),
                        'leader': cells[8].get_text(strip=True),
                        'leader_pct': float(cells[9].get_text(strip=True).replace('%', '')),
                    }
                    data.append(item)
                except (ValueError, IndexError) as e:
                    continue
        
        if verbose:
            print(f"[ths_concept] 获取到 {len(data)} 个概念")
        
        # 按净流入排序，取前top_n
        data.sort(key=lambda x: x['net'], reverse=True)
        return data[:top_n]
        
    except Exception as e:
        print(f"[ths_concept] 获取失败: {e}")
        return []


def fetch_ths_concept_by_change(top_n: int = 10, verbose: bool = False) -> List[Dict]:
    """获取同花顺概念涨幅榜
    
    复用fund_flow数据，按涨跌幅排序
    """
    data = fetch_ths_concept_fund_flow(top_n=100, verbose=verbose)
    
    # 按涨跌幅排序
    data.sort(key=lambda x: x['change_pct'], reverse=True)
    return data[:top_n]


if __name__ == "__main__":
    # 测试
    print("概念资金净流入 Top 10:")
    print("=" * 80)
    data = fetch_ths_concept_fund_flow(top_n=10, verbose=True)
    for i, d in enumerate(data, 1):
        print(f"{i:2d}. {d['name']:<16} 净流入{d['net']:>8.2f}亿 涨跌{d['change_pct']:>6.2f}% 领涨:{d['leader']}")
    
    print("\n概念涨幅 Top 10:")
    print("=" * 80)
    data2 = fetch_ths_concept_by_change(top_n=10)
    for i, d in enumerate(data2, 1):
        print(f"{i:2d}. {d['name']:<16} 涨跌{d['change_pct']:>6.2f}% 净流入{d['net']:>8.2f}亿 领涨:{d['leader']}")
