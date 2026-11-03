#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""点火雷达回测：底部首放长阳信号的次日/5日胜率

设计文档: IGNITION_RADAR_DESIGN.md §9.1.2
样本定义:
  - 从 ignition_data_*.json 提取事件卡片成员股
  - 筛选条件: 底部(p60<30) + 首放(vol_tag=='首放') + 长阳(🔥长阳点火/🔥涨停 或 change_pct>=5)
  - 样本单位: 单只股票
胜率计算:
  - 次日收益: T+1收盘价 / T收盘价 - 1
  - 5日收益: T+5收盘价 / T收盘价 - 1
  - 胜率 = 收益>0的样本数 / 总样本数
数据源:
  - 信号日: ignition_data_*.json (已有p60/vol_tag/shape/change_pct)
  - 后续K线: tencent_kline (腾讯主源+新浪备源, 只吃close)
落盘: analysis/ignition_backtest_result.json
"""

import sys
import os
import json
import glob
from datetime import datetime, timedelta

sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))

# 禁用代理
for k in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
    os.environ.pop(k, None)

import requests
from plans.industry_screener import tencent_kline

_ROOT = os.path.expanduser('~/stock-analysis-pro')
_DATA_DIR = os.path.join(_ROOT, 'output', 'daily_content')
_RESULT_FILE = os.path.join(_ROOT, 'analysis', 'ignition_backtest_result.json')


def is_bottom_first_burst_long_yang(stock):
    """判断是否满足「底部 + 首放 + 长阳」"""
    p60 = stock.get('p60')
    vol_tag = stock.get('vol_tag')
    shape = stock.get('shape', '')
    change_pct = stock.get('change_pct', 0)
    
    # 底部: p60 < 30
    if p60 is None or p60 >= 30:
        return False
    # 首放
    if vol_tag != '首放':
        return False
    # 长阳: 🔥长阳点火/🔥涨停 或 change_pct >= 5
    if '🔥' not in shape and change_pct < 5:
        return False
    return True


def calc_return(code, signal_date_str, days_after):
    """计算信号日后N日收益
    
    Args:
        code: 股票代码 (6位数字)
        signal_date_str: 信号日 YYYYMMDD
        days_after: 信号后交易日数 (1=次日, 5=5日)
    Returns:
        (return_pct, exit_date_str) 或 (None, None) 如果数据不足
    """
    try:
        # 拉取信号日后 days_after+5 日K线 (多拉几天防休市)
        klines = tencent_kline(code, days=days_after + 10)
        if not klines:
            return None, None
        
        # klines[-1]是最新日, 需找到信号日
        signal_date = datetime.strptime(signal_date_str, '%Y%m%d')
        signal_idx = None
        for i, k in enumerate(klines):
            k_date = datetime.strptime(k[0], '%Y-%m-%d')
            if k_date == signal_date:
                signal_idx = i
                break
        
        if signal_idx is None:
            return None, None
        
        # 信号日收盘价
        signal_close = float(klines[signal_idx][2])
        
        # 信号后第N日收盘价
        target_idx = signal_idx + days_after
        if target_idx >= len(klines):
            return None, None
        
        exit_close = float(klines[target_idx][2])
        exit_date = klines[target_idx][0]
        
        return_pct = (exit_close / signal_close - 1) * 100
        return return_pct, exit_date.replace('-', '')
        
    except Exception as e:
        print(f"  ⚠ {code} 收益计算失败: {e}")
        return None, None


def run_backtest():
    """执行回测"""
    print("=== 点火雷达回测: 底部首放长阳胜率 ===\n")
    
    # 扫描所有 ignition_data_*.json
    pattern = os.path.join(_DATA_DIR, 'ignition_data_*.json')
    files = sorted(glob.glob(pattern))
    print(f"找到 {len(files)} 个交易日数据文件\n")
    
    samples = []
    for fpath in files:
        try:
            with open(fpath, encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"⚠ 读取失败 {fpath}: {e}")
            continue
        
        date_str = data.get('date')
        if not date_str:
            continue
        
        events = data.get('events', [])
        for event in events:
            members = event.get('members', [])
            for stock in members:
                if is_bottom_first_burst_long_yang(stock):
                    samples.append({
                        'date': date_str,
                        'event': event.get('name'),
                        'code': stock.get('code'),
                        'name': stock.get('name'),
                        'price': stock.get('price'),
                        'change_pct': stock.get('change_pct'),
                        'p60': stock.get('p60'),
                        'vol_tag': stock.get('vol_tag'),
                        'shape': stock.get('shape'),
                    })
    
    print(f"筛选出 {len(samples)} 只「底部首放长阳」样本股\n")
    
    if not samples:
        print("无样本, 回测终止")
        return None
    
    # 计算次日/5日收益
    print("计算收益 (腾讯K线, 每只间隔0.6s)...")
    results = []
    for i, s in enumerate(samples):
        code = s['code']
        date_str = s['date']
        
        ret1, exit1 = calc_return(code, date_str, 1)
        ret5, exit5 = calc_return(code, date_str, 5)
        
        results.append({
            **s,
            'return_1d': ret1,
            'exit_date_1d': exit1,
            'return_5d': ret5,
            'exit_date_5d': exit5,
        })
        
        if (i + 1) % 10 == 0:
            print(f"  进度: {i+1}/{len(samples)}")
    
    # 统计
    valid_1d = [r for r in results if r['return_1d'] is not None]
    valid_5d = [r for r in results if r['return_5d'] is not None]
    
    win_1d = sum(1 for r in valid_1d if r['return_1d'] > 0)
    win_5d = sum(1 for r in valid_5d if r['return_5d'] > 0)
    
    avg_1d = sum(r['return_1d'] for r in valid_1d) / len(valid_1d) if valid_1d else 0
    avg_5d = sum(r['return_5d'] for r in valid_5d) / len(valid_5d) if valid_5d else 0
    
    stats = {
        'total_samples': len(samples),
        'valid_1d': len(valid_1d),
        'valid_5d': len(valid_5d),
        'win_1d': win_1d,
        'win_5d': win_5d,
        'win_rate_1d': win_1d / len(valid_1d) * 100 if valid_1d else 0,
        'win_rate_5d': win_5d / len(valid_5d) * 100 if valid_5d else 0,
        'avg_return_1d': avg_1d,
        'avg_return_5d': avg_5d,
        'samples': results,
    }
    
    print(f"\n=== 回测结果 ===")
    print(f"总样本: {len(samples)} 只")
    print(f"次日有效: {len(valid_1d)} 只, 胜率: {stats['win_rate_1d']:.1f}%, 平均收益: {avg_1d:+.2f}%")
    print(f"5日有效: {len(valid_5d)} 只, 胜率: {stats['win_rate_5d']:.1f}%, 平均收益: {avg_5d:+.2f}%")
    
    # 落盘
    os.makedirs(os.path.dirname(_RESULT_FILE), exist_ok=True)
    with open(_RESULT_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"\n结果已落盘: {_RESULT_FILE}")
    
    return stats


if __name__ == '__main__':
    run_backtest()
