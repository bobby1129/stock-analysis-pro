# -*- coding: utf-8 -*-
import sys, json
sys.path.insert(0, '.')
from plans.daily_report import tencent_kline

def calc_technical_indicators(klines):
    if not klines or len(klines) < 20:
        return {}
    closes = [float(k[2]) for k in klines]
    highs = [float(k[3]) for k in klines]
    lows = [float(k[4]) for k in klines]
    volumes = [float(k[5]) for k in klines]
    n = len(closes)
    result = {}

    # MA
    ma5 = sum(closes[-5:]) / 5
    ma10 = sum(closes[-10:]) / 10
    ma20 = sum(closes[-20:]) / 20
    cur = closes[-1]
    if ma5 > ma10 > ma20:
        ma_arr = "多头排列"
    elif ma5 < ma10 < ma20:
        ma_arr = "空头排列"
    elif cur > ma5 > ma10:
        ma_arr = "向上发散"
    elif cur < ma5 < ma10:
        ma_arr = "向下发散"
    else:
        ma_arr = "交叉缠绕"
    result['ma'] = {'ma5': round(ma5,2), 'ma10': round(ma10,2), 'ma20': round(ma20,2), 'arrangement': ma_arr}

    # KDJ(9,3,3)
    period = 9
    rsv_list = []
    for i in range(period - 1, n):
        h9 = max(highs[i-period+1:i+1])
        l9 = min(lows[i-period+1:i+1])
        rsv = (closes[i] - l9) / (h9 - l9) * 100 if h9 != l9 else 50.0
        rsv_list.append(rsv)
    k_val = d_val = 50.0
    for rsv in rsv_list:
        k_val = 2.0/3.0 * k_val + 1.0/3.0 * rsv
        d_val = 2.0/3.0 * d_val + 1.0/3.0 * k_val
    j_val = 3 * k_val - 2 * d_val
    k_prev = d_prev = 50.0
    for rsv in rsv_list[:-1]:
        k_prev = 2.0/3.0 * k_prev + 1.0/3.0 * rsv
        d_prev = 2.0/3.0 * d_prev + 1.0/3.0 * k_prev
    kdj_cross = ""
    if k_val > d_val and k_prev <= d_prev:
        kdj_cross = "金叉"
    elif k_val < d_val and k_prev >= d_prev:
        kdj_cross = "死叉"
    if j_val > 100:
        kdj_zone = "超买"
    elif j_val < 0:
        kdj_zone = "超卖"
    elif k_val > 80:
        kdj_zone = "高位"
    elif k_val < 20:
        kdj_zone = "低位"
    else:
        kdj_zone = "中性"
    result['kdj'] = {'k': round(k_val,1), 'd': round(d_val,1), 'j': round(j_val,1), 'cross': kdj_cross, 'zone': kdj_zone}

    # RSI6
    gains, losses = [], []
    for i in range(-6, 0):
        diff = closes[i] - closes[i-1]
        gains.append(diff if diff > 0 else 0)
        losses.append(-diff if diff < 0 else 0)
    avg_gain = sum(gains) / 6
    avg_loss = sum(losses) / 6
    if avg_loss == 0:
        rsi6 = 100.0
    else:
        rsi6 = 100 - 100 / (1 + avg_gain / avg_loss)
    if rsi6 > 80:
        rsi_zone = "超买"
    elif rsi6 > 60:
        rsi_zone = "偏强"
    elif rsi6 > 40:
        rsi_zone = "中性"
    elif rsi6 > 20:
        rsi_zone = "偏弱"
    else:
        rsi_zone = "超卖"
    result['rsi'] = {'rsi6': round(rsi6,1), 'zone': rsi_zone}

    # MACD(12,26,9)
    e12 = e26 = closes[0]
    dif_list = []
    for c in closes:
        e12 = c * 2.0/13.0 + e12 * 11.0/13.0
        e26 = c * 2.0/27.0 + e26 * 25.0/27.0
        dif_list.append(e12 - e26)
    dea_v = dif_list[0]
    dea_list = []
    for d in dif_list:
        dea_v = d * 2.0/10.0 + dea_v * 8.0/10.0
        dea_list.append(dea_v)
    dif = dif_list[-1]
    dea = dea_list[-1]
    bar = 2 * (dif - dea)
    bar_prev = 2 * (dif_list[-2] - dea_list[-2])
    macd_cross = ""
    if dif > dea and dif_list[-2] <= dea_list[-2]:
        macd_cross = "金叉"
    elif dif < dea and dif_list[-2] >= dea_list[-2]:
        macd_cross = "死叉"
    if bar > 0 and bar > bar_prev:
        trend = "红柱放大"
    elif bar > 0:
        trend = "红柱缩短"
    elif bar < bar_prev:
        trend = "绿柱放大"
    else:
        trend = "绿柱缩短"
    result['macd'] = {'dif': round(dif,3), 'dea': round(dea,3), 'bar': round(bar,3), 'cross': macd_cross, 'trend': trend}

    # 量价
    vol_5 = sum(volumes[-5:]) / 5
    vr = volumes[-1] / vol_5 if vol_5 > 0 else 1
    chg = closes[-1] - closes[-2]
    if vr > 1.5 and chg > 0:
        vp = "放量上涨"
    elif vr > 1.5 and chg < 0:
        vp = "放量下跌"
    elif vr < 0.7 and chg > 0:
        vp = "缩量上涨"
    elif vr < 0.7 and chg < 0:
        vp = "缩量下跌"
    else:
        vp = "量价平稳"
    result['vol_price'] = {'ratio': round(vr,2), 'desc': vp}

    # 连涨跌
    streak = 0
    for i in range(n-1, 0, -1):
        if closes[i] > closes[i-1]:
            if streak >= 0:
                streak += 1
            else:
                break
        elif closes[i] < closes[i-1]:
            if streak <= 0:
                streak -= 1
            else:
                break
        else:
            break
    if streak > 0:
        result['streak'] = str(streak) + "日涨"
    elif streak < 0:
        result['streak'] = str(abs(streak)) + "日跌"
    else:
        result['streak'] = "平盘"

    # 支撑/压力
    recent_lows = sorted(lows[-10:])[:3]
    recent_highs = sorted(highs[-10:], reverse=True)[:3]
    result['levels'] = {
        'support': round(sum(recent_lows)/3, 2),
        'resistance': round(sum(recent_highs)/3, 2),
    }

    # 综合评分
    score = 0
    signals = []
    if result['kdj']['cross'] == '金叉':
        score += 25; signals.append("KDJ金叉→短线买入信号")
    elif result['kdj']['cross'] == '死叉':
        score -= 25; signals.append("KDJ死叉→短线卖出信号")
    if result['kdj']['zone'] == '超卖':
        score += 15; signals.append("KDJ超卖区→关注反弹")
    elif result['kdj']['zone'] == '超买':
        score -= 15; signals.append("KDJ超买区→注意回调")
    if result['rsi']['zone'] == '超卖':
        score += 15; signals.append("RSI超卖→可能反弹")
    elif result['rsi']['zone'] == '超买':
        score -= 15; signals.append("RSI超买→注意风险")
    if result['macd']['cross'] == '金叉':
        score += 20; signals.append("MACD金叉→趋势转多")
    elif result['macd']['cross'] == '死叉':
        score -= 20; signals.append("MACD死叉→趋势转空")
    if result['macd']['trend'] == '红柱放大':
        score += 10
    elif result['macd']['trend'] == '绿柱放大':
        score -= 10
    if ma_arr == '多头排列':
        score += 15; signals.append("均线多头排列→趋势向上")
    elif ma_arr == '空头排列':
        score -= 15; signals.append("均线空头排列→趋势向下")
    if vp == '放量上涨':
        score += 10; signals.append("放量上涨→多方强势")
    elif vp == '放量下跌':
        score -= 10; signals.append("放量下跌→空方强势")
    elif vp == '缩量上涨':
        score -= 5; signals.append("缩量上涨→上涨乏力")
    if streak >= 4:
        signals.append("已" + str(streak) + "连涨→获利了结压力")
        score -= 10
    elif streak <= -4:
        signals.append("已" + str(abs(streak)) + "连跌→关注超跌反弹")
        score += 10

    score = max(-100, min(100, score))
    if score >= 40:
        advice = "🟢 短线偏多，可持仓或加仓"
    elif score >= 15:
        advice = "🟢 短线偏多，谨慎持有"
    elif score <= -40:
        advice = "🔴 短线偏空，建议减仓或离场"
    elif score <= -15:
        advice = "🔴 短线偏空，注意控制仓位"
    else:
        advice = "⚪ 短线中性，观望为主"

    result['short_term'] = {'score': score, 'signals': signals, 'advice': advice}
    return result

# 测试多只股票
for code in ['000063', '600519', '300750']:
    klines = tencent_kline(code, days=30)
    ind = calc_technical_indicators(klines)
    print(f"\n{'='*50}")
    print(f"股票: {code}")
    print(json.dumps(ind, ensure_ascii=False, indent=2))
