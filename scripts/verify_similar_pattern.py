# -*- coding: utf-8 -*-
"""S8 验证: 多日形态相似 vs 单日涨跌幅相似 对照测试

用法: python3 scripts/verify_similar_pattern.py
测试内容:
1. 数据自检: 1000根日K完整性、收益率序列正确性
2. 单元级: 构造已知形态, 验证位置过滤/去重叠/top_n逻辑
3. 历史真实日对照: 挑近4年内多个典型大跌/大涨日作为"假想今天",
   分别跑旧口径(单日±1pct)与新口径(5日形态+位置), 打印两组匹配结果,
   人工评估新口径匹配日是否形态更接近、统计是否更合理
"""
import sys, os
sys.path.insert(0, os.path.expanduser('~/stock-analysis-pro'))
from plans.daily_report import _fetch_index_kline
from analysis.similar_pattern import (find_similar_pattern, _pct_series, _pos_pct,
                                       PATTERN_LEN, MIN_GAP, TOP_N)
from analysis.extreme_mode import _history_from_kline

FAILS = []
def check(name, cond, detail=""):
    tag = "✓" if cond else "✗"
    print(f"  {tag} {name} {detail}")
    if not cond:
        FAILS.append(name)

print("=" * 70)
print("1. 数据自检")
print("=" * 70)
kl = _fetch_index_kline('sh000001', days=1000)
check("拉取1000根日K", kl is not None and len(kl) >= 990, f"实际{len(kl) if kl else 0}根")
dates = [k[0] for k in kl]
check("日期升序无重复", dates == sorted(dates) and len(set(dates)) == len(dates))
closes = [k[2] for k in kl]
check("close全为正数", all(c > 0 for c in closes))
pcts = _pct_series(closes)
# 抽3根验证收益率计算
import random
random.seed(42)
ok = True
for i in random.sample(range(1, len(closes)), 3):
    manual = (closes[i] - closes[i-1]) / closes[i-1] * 100
    if abs(manual - pcts[i]) > 1e-9:
        ok = False
check("收益率序列计算正确(抽3根)", ok)

print()
print("=" * 70)
print("2. 单元级逻辑")
print("=" * 70)
r = find_similar_pattern(kl, target_idx=len(kl) - 1)
check("今日(11-03)能出结果", r is not None)
if r:
    ms = r["matches"]
    check("匹配数<=TOP_N", len(ms) <= TOP_N, f"n={len(ms)}")
    check("全部为历史日(不含今天)", all(m["date"] != dates[-1] for m in ms))
    js = [dates.index(m["date"]) for m in ms]
    check("相似日间隔>=MIN_GAP", all(abs(js[a] - js[b]) >= MIN_GAP
                                     for a in range(len(js)) for b in range(a+1, len(js))))
    tp = r["target_pos"]
    check("位置过滤生效(分位差<=30)", all(abs(m["pos"] - tp) <= 30 for m in ms),
          f"目标分位{tp}, 匹配分位{[m['pos'] for m in ms]}")
    check("stat齐全", all(k in r["stat"] for k in ("n", "next1_avg", "next1_up_rate", "next5_avg", "next5_up_rate")))
    check("next1全部可算", all(m["next1"] is not None for m in ms))
# 边界: 数据太短
check("短数据返回None", find_similar_pattern(kl[:50]) is None)
# 边界: target_idx过小
check("target_idx<PATTERN_LEN返回None", find_similar_pattern(kl, target_idx=2) is None)

print()
print("=" * 70)
print("3. 历史真实日对照 (旧单日口径 vs 新形态口径)")
print("=" * 70)
# 在近4年(1000根)里挑典型日: 单日跌>=1.5% 或 涨>=1.5% 的极端日, 均匀抽6个
extremes = [(i, pcts[i]) for i in range(PATTERN_LEN + 60, len(kl) - 6)
            if pcts[i] is not None and abs(pcts[i]) >= 1.5]
random.shuffle(extremes)
picks = sorted(extremes[:6])
for i, p in picks:
    d = dates[i]
    print(f"\n── 假想今天: {d}  上证 {p:+.2f}%  (60日分位 {_pos_pct(closes, i):.0f}) ──")
    print(f"   近5日走势: {' → '.join(f'{x:+.2f}%' for x in pcts[i-4:i+1])}")
    old = _history_from_kline(p, days=1000)
    new = find_similar_pattern(kl, target_idx=i)
    if old:
        om = old["matches"]
        print(f"   [旧·单日±1pct] {old['stat']['n']}例, 日期: {[m['date'] for m in om]}")
        print(f"      当日涨跌: {[m['sh_pct'] for m in om]}")
        print(f"      次1日均 {old['stat']['next1_avg']:+.2f}% 上涨率{old['stat']['next1_up_rate']:.0f}% | "
              f"次5日均 {old['stat']['next5_avg']:+.2f}% 上涨率{old['stat']['next5_up_rate']:.0f}%")
    else:
        print("   [旧] 无匹配")
    if new:
        nm = new["matches"]
        print(f"   [新·5日形态+位置] {new['stat']['n']}例")
        for m in nm:
            j = dates.index(m["date"])
            pat = ' → '.join(f'{x:+.2f}%' for x in pcts[j-4:j+1])
            print(f"      {m['date']} 距{m['dist']:.2f} 分位{m['pos']} | {pat} | 次1 {m['next1']:+.2f}% 次5 {m['next5']:+.2f}%")
        print(f"      次1日均 {new['stat']['next1_avg']:+.2f}% 上涨率{new['stat']['next1_up_rate']:.0f}% | "
              f"次5日均 {new['stat']['next5_avg']:+.2f}% 上涨率{new['stat']['next5_up_rate']:.0f}%")
    else:
        print("   [新] 无匹配")

print()
print("=" * 70)
print(f"结果: {'全部通过 ✓' if not FAILS else '失败项: ' + str(FAILS)}")
print("=" * 70)
sys.exit(1 if FAILS else 0)
