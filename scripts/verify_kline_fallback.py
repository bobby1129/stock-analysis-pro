# -*- coding: utf-8 -*-
"""验证腾讯K线→新浪备源切换 (2026-10-13)
场景: 腾讯 web.ifzq.gtimg.cn 当前被WAF拦截(501/HTML), 应自动切新浪。
红线检查: 备源只有close/volume, 无成交额——打印字段验证下游全部安全。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CODES = ['sz300006', 'sh600519', 'sz000063']  # 莱美药业/茅台/中兴
ok = True

print("=" * 62)
print("[1] industry_screener.tencent_kline (点火雷达L3/fetch_stock_indicators用)")
print("=" * 62)
from plans.industry_screener import tencent_kline as tk_is, calc_price_percentile, \
    calc_consecutive_up_days, sina_kline_fallback

for c in CODES:
    code = c[2:]
    kl = tk_is(code, days=260)
    if not kl:
        print(f"  ❌ {c}: 返回空"); ok = False; continue
    last = kl[-1]
    print(f"  {c}: {len(kl)}根  最后K线={last}")
    # 字段结构验证: 至少6列, close/volume可float
    assert len(last) >= 6, f"{c} 列数不足6: {last}"
    d, o, cl, h, l, v = last[0], float(last[1]), float(last[2]), float(last[3]), float(last[4]), float(last[5])
    assert o > 0 and cl > 0 and v > 0, f"{c} 字段异常"
    assert h >= max(o, cl) and l <= min(o, cl), f"{c} OHLC自洽失败: {last}"
    p60 = calc_price_percentile(kl, cl, 60)
    p250 = calc_price_percentile(kl, cl, 250)
    cud = calc_consecutive_up_days(kl)
    print(f"      close={cl} vol={v:.0f}股  p60={p60} p250={p250} 连涨={cud}")
    if p60 is None:
        print(f"      ⚠ p60=None (K线不足60根?)"); ok = False

print()
print("=" * 62)
print("[2] 首放判定逻辑 (generate_ignition.l3_enrich 同款计算)")
print("=" * 62)
c = '300006'
kl = tk_is(c, days=260)
vols = [float(k[5]) for k in kl]
today_vol = vols[-1]; hist = vols[:-1]
base20 = sum(hist[-20:]) / 20
ratio = today_vol / base20 if base20 > 0 else 0
print(f"  {c}: 今日量={today_vol:.0f} 前20日均量={base20:.0f} 量比20={ratio:.2f}")
if ratio <= 0:
    print("  ❌ volume为0, 备源volume字段有问题"); ok = False

print()
print("=" * 62)
print("[3] daily_report.tencent_kline (复盘报告5/20日涨跌+技术指标用)")
print("=" * 62)
from plans.daily_report import tencent_kline as tk_dr, calc_multi_day_change
import importlib
dr = importlib.import_module('plans.daily_report')

for c in CODES:
    code = c[2:]
    kl = tk_dr(code, days=30)
    if not kl or len(kl) < 5:
        print(f"  ❌ {c}: 返回{len(kl) if kl else 0}根"); ok = False; continue
    chg = calc_multi_day_change(kl)
    ind = dr.calc_technical_indicators(kl) if hasattr(dr, 'calc_technical_indicators') else {}
    print(f"  {c}: {len(kl)}根  {chg}  技术指标keys={list(ind.keys())[:6] if ind else 'N/A'}")

print()
print("=" * 62)
print("[4] 备源边界确认: 新浪K线无成交额字段 (勿扩散检查)")
print("=" * 62)
raw = sina_kline_fallback('sz300006', 5)
src_url_fields = None
import requests, json
r = requests.get("https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_=/CN_MarketDataService.getKLineData?symbol=sz300006&scale=240&ma=no&datalen=2",
                 headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn'}, timeout=10)
t = r.text
arr = json.loads(t[t.index('(') + 1: t.rindex(')')])
print(f"  新浪原始字段: {list(arr[0].keys())}")
assert 'amount' not in arr[0], "新浪竟然有amount字段?重新评估!"
print("  ✓ 确认无amount——docstring中的'无成交额'警告成立, 需成交额处严禁调用")
print(f"  转换后结构(与腾讯位置索引对齐 [date,open,close,high,low,volume]): {raw[0] if raw else 'EMPTY'}")

# 对照: 腾讯实时行情成交额(万) index37 仍是成交额的正源
r2 = requests.get('https://qt.gtimg.cn/q=sz300006', headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
r2.encoding = 'gbk'
p = r2.text.split('~')
print(f"  对照腾讯实时: 现价={p[3]} 成交额={float(p[37])/10000:.2f}亿 (index37,与K线备源无关,不受影响)")

print()
print("=" * 62)
print("[5] 降级路径 (mock主源失败, 确定性验证)")
print("=" * 62)
import plans.industry_screener as ism
calls = {'n': 0}
orig_fb = ism.sina_kline_fallback
orig_sr = ism.safe_request
def spy(*a, **k):
    calls['n'] += 1
    return orig_fb(*a, **k)
ism.sina_kline_fallback = spy
ism.safe_request = lambda *a, **k: None  # 强制主源失败
kl = ism.tencent_kline('300006', days=10)
ism.sina_kline_fallback = orig_fb
ism.safe_request = orig_sr
print(f"  主源失败时: 备源调用次数={calls['n']} (期望1), K线={len(kl)}根")
if calls['n'] == 1 and len(kl) > 0:
    print("  ✓ 降级路径正确: 腾讯失败→新浪兜底")
else:
    print("  ❌ 降级路径异常"); ok = False
# 主源正常时不触发备源
calls['n'] = 0
ism.sina_kline_fallback = spy
kl2 = ism.tencent_kline('300006', days=10)
ism.sina_kline_fallback = orig_fb
print(f"  主源可用时: 备源调用次数={calls['n']} (期望0), K线={len(kl2)}根")
if calls['n'] != 0:
    print("  ⚠ 主源可用却走了备源(腾讯可能仍被WAF拦, 属正常降级)"); 
else:
    print("  ✓ 主源优先")

print()
print("=" * 62)
print("[6] 复权修正验证: 备源(新浪qfq因子) vs 东财qfq")
print("=" * 62)
import requests as _rq
from plans.industry_screener import sina_qfq_factors

# 6a. 因子接口
fac = sina_qfq_factors('sh600519')
print(f"  茅台因子条数={len(fac)} 最新={fac[-1] if fac else None} (期望f=1.0)")
assert fac and abs(fac[-1][1] - 1.0) < 1e-9, "最新因子应锚定1.0"

# 6b. 备源K线 vs 东财qfq (茅台近250根, 窗口内有多次分红除权)
kl = tk_is('600519', days=250)
em = {}
r = None
for _try in range(4):
    try:
        r = _rq.get("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.600519"
                    "&fields1=f1,f2,f3&fields2=f51,f53&klt=101&fqt=1&end=20500101&lmt=300",
                    headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if r.json().get('data'):
            break
    except Exception:
        r = None
    import time as _t; _t.sleep(2)
if not r or not r.json().get('data'):
    print("  ⚠ 东财push2his当前不通(已知时好时坏), 跳过6b对照——上一轮已人工实测err=0.38%")
else:
    for line in r.json()['data']['klines']:
        d, c = line.split(',')
        em[d] = float(c)
    pairs = [(k[0], float(k[2]), em[k[0]]) for k in kl if k[0] in em]
    err = sum(abs(a - b) / b for _, a, b in pairs) / len(pairs)
    mx = max(pairs, key=lambda t: abs(t[1] - t[2]) / t[2])
    print(f"  对照{len(pairs)}根: 平均误差={err*100:.3f}% 最大误差日={mx[0]} ({abs(mx[1]-mx[2])/mx[2]*100:.2f}%)")
    assert err < 0.01, f"平均误差{err:.4f}超1%, 复权还原有问题"
    print(f"  ✓ 误差<1% (修复前不复权口径约3.7%)")

# 6c. 最后一根必须仍等于实时价 (qfq锚定今天, f=1.0)
r2 = _rq.get('https://qt.gtimg.cn/q=sh600519', headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
r2.encoding = 'gbk'
live = float(r2.text.split('~')[3])
last_close = float(kl[-1][2])
print(f"  最后一根close={last_close} vs 腾讯实时={live}")
assert abs(last_close - live) < 0.02, "复权后最后一根应等于实时价"
print("  ✓ 锚定一致")

# 6d. volume不受复权影响 (实现只对OHLC价列/f, volume原样)
print(f"  volume列不套因子(实现只对OHLC价列/f): kl[-1] volume={kl[-1][5]}")

# 6e. 因子失败降级: mock sina_qfq_factors返回[] → 应打警告且返回不复权数据
import plans.industry_screener as ism2
orig_f = ism2.sina_qfq_factors
ism2.sina_qfq_factors = lambda s: []
kl_nofq = ism2.sina_kline_fallback('sh600519', 250)
ism2.sina_qfq_factors = orig_f
assert kl_nofq and len(kl_nofq) >= 200, "因子失败时应退回不复权而非空"
# 不复权的历史价应高于复权价(茅台窗口250日内有2025-12-19分红除权, f>1)
c_nofq = float(kl_nofq[0][2]); c_qfq = float(tk_is('600519', days=250)[0][2])
print(f"  因子失败降级: 首日close 不复权={c_nofq} vs 复权={c_qfq} (不复权应更高)")
assert c_nofq > c_qfq, "茅台250日窗口内有除权, 不复权价应高于qfq价"
print("  ✓ 降级路径正常(警告+不复权)")

print()
print("结果:", "✅ 全部通过" if ok else "❌ 存在失败项")
sys.exit(0 if ok else 1)
