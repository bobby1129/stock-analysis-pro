#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证881行业资金流接口（同花顺字段红线：必须打印验证）

测试881行业码是否能复用 ths_mainforce.fetch_one() 接口
"""
import sys, os
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))

from collectors.ths_mainforce import fetch_one
import json

# 测试3个881行业码
test_industries = {
    '半导体': '881121',
    '白酒': '881273',
    '电力': '881145',
}

print("=== 881行业资金流接口验证 ===\n")
for name, code in test_industries.items():
    print(f"测试: {name} ({code})")
    result = fetch_one(code)
    if result:
        print(f"  ✓ 成功: 主力净额={result['main_net']:.2f}亿")
        print(f"    字段: {list(result.keys())}")
    else:
        print(f"  ✗ 失败: 接口返回None")
    print()

# 对比885概念（已知可用）
print("=== 885概念对照 ===\n")
test_concepts = {
    '存储芯片': '886042',
    '白酒概念': '885525',
    '电力物联网': '885819',
}
for name, code in test_concepts.items():
    print(f"测试: {name} ({code})")
    result = fetch_one(code)
    if result:
        print(f"  ✓ 成功: 主力净额={result['main_net']:.2f}亿")
    else:
        print(f"  ✗ 失败")
    print()
