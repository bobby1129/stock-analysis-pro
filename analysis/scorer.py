# -*- coding: utf-8 -*-
"""分析维度层 — 综合评分

评分范围：-100 ~ +100（四维各 -25 ~ +25，权重由 config/default.yaml 控制）
"""

import os
import yaml
from typing import Dict, List, Tuple

# 加载配置
_config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "default.yaml")
try:
    with open(_config_path, "r") as f:
        _config = yaml.safe_load(f) or {}
except Exception:
    _config = {}

_weights = _config.get("scoring", {})
_W_TECH = _weights.get("weight_technical", 0.25)
_W_FUND = _weights.get("weight_fundamental", 0.25)
_W_CAP = _weights.get("weight_capital", 0.25)
_W_SENT = _weights.get("weight_sentiment", 0.25)


def compute(tech: Dict, fund: Dict, cap: Dict, sent: Dict, basic: Dict, val: Dict) -> Dict:
    """综合评分 — 权重从 config/default.yaml 读取"""
    total = 0.0
    signals = []
    warnings = []
    
    # 技术面评分 (raw: -25 ~ +25, scaled by weight)
    tech_raw, t_sig, t_warn = _score_tech(tech)
    tech_scaled = tech_raw * (_W_TECH / 0.25)
    total += tech_scaled
    signals.extend(t_sig)
    warnings.extend(t_warn)
    
    # 基本面评分
    fund_raw, f_sig, f_warn = _score_fund(fund)
    fund_scaled = fund_raw * (_W_FUND / 0.25)
    total += fund_scaled
    signals.extend(f_sig)
    warnings.extend(f_warn)
    
    # 资金面评分
    cap_raw, c_sig, c_warn = _score_cap(cap)
    cap_scaled = cap_raw * (_W_CAP / 0.25)
    total += cap_scaled
    signals.extend(c_sig)
    warnings.extend(c_warn)
    
    # 舆情面评分
    sent_raw, s_sig, s_warn = _score_sent(sent)
    sent_scaled = sent_raw * (_W_SENT / 0.25)
    total += sent_scaled
    signals.extend(s_sig)
    warnings.extend(s_warn)
    
    # PE  sanity check
    pe = basic.get("pe", 0)
    if pe and pe > 100:
        warnings.append(f"PE过高({pe})")
        total -= 5
    
    # ── 估值水平评估 (±5) ──
    pb = basic.get("pb", 0)
    if pe:
        if pe < 0:
            warnings.append("PE为负(亏损)")
            total -= 3
        elif pe < 15:
            score_val = 3
            signals.append(f"低估值(PE={pe})")
            total += score_val
        elif pe < 30:
            pass  # 合理区间
        elif pe < 60:
            warnings.append(f"偏高估值(PE={pe})")
            total -= 2
        else:
            warnings.append(f"高估值(PE={pe})")
            total -= 4
    
    if pb:
        if pb < 1:
            signals.append(f"破净(PB={pb})")
            total += 2
        elif pb > 10:
            warnings.append(f"PB过高({pb})")
            total -= 2
    
    # ── 多维共振 (±12) ──
    dims = [tech_raw, fund_raw, cap_raw, sent_raw]
    bullish_dims = sum(1 for d in dims if d > 5)
    bearish_dims = sum(1 for d in dims if d < -5)
    
    if bullish_dims >= 4:
        total += 12
        signals.append("🔥四维共振看多")
    elif bullish_dims >= 3:
        total += 8
        signals.append("✨三维共振看多")
    
    if bearish_dims >= 4:
        total -= 12
        warnings.append("🔥四维共振看空")
    elif bearish_dims >= 3:
        total -= 8
        warnings.append("✨三维共振看空")
    
    # 评级
    if total >= 60:
        rating = "强看多"
    elif total >= 30:
        rating = "看多"
    elif total >= 10:
        rating = "偏多"
    elif total >= -10:
        rating = "中性"
    elif total >= -30:
        rating = "偏空"
    elif total >= -60:
        rating = "看空"
    else:
        rating = "强看空"
    
    return {
        "total_score": int(total),
        "rating": rating,
        "technical": tech_raw,
        "fundamental": fund_raw,
        "capital": cap_raw,
        "sentiment": sent_raw,
        "weights": {"tech": _W_TECH, "fund": _W_FUND, "cap": _W_CAP, "sent": _W_SENT},
        "signals": signals[:10],
        "warnings": warnings[:10],
    }


def _score_tech(tech: Dict) -> Tuple[int, List[str], List[str]]:
    """技术面评分 (-25 ~ +25)"""
    score = 0
    signals = []
    warnings = []
    
    price = tech.get("price", 0)
    ma5 = tech.get("ma5")
    ma10 = tech.get("ma10")
    ma20 = tech.get("ma20")
    ma60 = tech.get("ma60")
    
    # MA 位置 (±8)
    for ma_key, ma_val, weight in [("ma5", ma5, 2), ("ma10", ma10, 2), ("ma20", ma20, 2), ("ma60", ma60, 2)]:
        if ma_val and price:
            if price > ma_val:
                score += weight
                signals.append(f"站上{ma_key.upper()}")
            else:
                score -= weight
                warnings.append(f"跌破{ma_key.upper()}")
    
    # MACD (±6)
    macd = tech.get("macd", {})
    if macd:
        if macd.get("signal") == "bullish":
            score += 4
            signals.append("MACD多头")
        else:
            score -= 4
            warnings.append("MACD空头")
        
        if macd.get("golden_cross"):
            score += 2
            signals.append("MACD金叉")
        if macd.get("dead_cross"):
            score -= 1
            warnings.append("MACD死叉")
    
    # 量比 (±4)
    vol_ratio = tech.get("volume_ratio")
    if vol_ratio:
        if vol_ratio > 1.5:
            score += 3
            signals.append(f"放量(量比{vol_ratio:.2f})")
        elif vol_ratio > 1.0:
            score += 1
        elif vol_ratio < 0.5:
            score -= 2
            warnings.append(f"极度缩量(量比{vol_ratio:.2f})")
    
    # ── 量价关系 (±5) ──
    p60 = tech.get("percentile_60d", {}).get("value", 50)
    if vol_ratio and price and ma20:
        above_ma20 = price > ma20
        if vol_ratio > 1.5 and above_ma20:
            score += 4
            signals.append(f"放量突破(量比{vol_ratio:.1f},站上MA20)")
        elif vol_ratio < 0.7 and not above_ma20:
            score += 2  # 缩量回调，健康调整
            signals.append("缩量回调(洗盘特征)")
        elif vol_ratio > 2.5 and p60 > 80:
            score -= 5
            warnings.append(f"天量天价(量比{vol_ratio:.1f},60日高位{p60:.0f}%)")
    
    # ── 均线排列 (±5) ──
    if ma5 is not None and ma10 is not None and ma20 is not None and ma60 is not None:
        if ma5 > ma10 > ma20 > ma60:
            score += 5
            signals.append("多头排列(MA5>10>20>60)")
        elif ma5 < ma10 < ma20 < ma60:
            score -= 5
            warnings.append("空头排列(MA5<10<20<60)")
    
    # 价格分位 (±4)
    p250 = tech.get("percentile_250d", {}).get("value", 50)
    if p60 < 20:
        score += 3
        signals.append("60日超卖区")
    elif p60 > 80:
        score -= 3
        warnings.append("60日超买区")
    
    if p250 < 20:
        score += 2
        signals.append("年线低位")
    elif p250 > 80:
        score -= 2
        warnings.append("年线高位")
    
    # 换手率 (±3)
    tr = tech.get("turnover_rate")
    if tr and tr > 10:
        warnings.append(f"换手过高({tr}%)")
        score -= 2
    elif tr and tr < 1:
        score += 1
    
    return max(-25, min(25, score)), signals, warnings


def _score_fund(fund: Dict) -> Tuple[int, List[str], List[str]]:
    """基本面评分 (-25 ~ +25)"""
    score = 0
    signals = []
    warnings = []
    
    # ROE (±8)
    roe = fund.get("profitability", {}).get("roe", {}).get("value")
    if roe is not None:
        if roe > 20:
            score += 8
            signals.append(f"ROE优秀({roe:.1f}%)")
        elif roe > 10:
            score += 5
            signals.append(f"ROE良好({roe:.1f}%)")
        elif roe > 5:
            score += 2
        elif roe > 0:
            score -= 2
        else:
            score -= 6
            warnings.append("ROE为负")
    
    # 成长 (±8)
    rev_g = fund.get("growth", {}).get("revenue_growth", {}).get("value")
    np_g = fund.get("growth", {}).get("net_profit_growth", {}).get("value")
    if rev_g is not None:
        if rev_g > 30:
            score += 4
            signals.append(f"营收高增({rev_g:.1f}%)")
        elif rev_g > 10:
            score += 2
        elif rev_g < -10:
            score -= 3
            warnings.append(f"营收下滑({rev_g:.1f}%)")
    
    if np_g is not None:
        if np_g > 30:
            score += 4
            signals.append(f"净利高增({np_g:.1f}%)")
        elif np_g > 10:
            score += 2
        elif np_g < -10:
            score -= 3
            warnings.append(f"净利下滑({np_g:.1f}%)")
    
    # 负债 (±5)
    debt = fund.get("health", {}).get("debt_ratio", {}).get("value")
    if debt is not None:
        if debt < 30:
            score += 4
            signals.append(f"低负债({debt:.1f}%)")
        elif debt < 50:
            score += 2
        elif debt > 70:
            score -= 4
            warnings.append(f"高负债({debt:.1f}%)")
    
    # 毛利率 (±4)
    gm = fund.get("profitability", {}).get("gross_margin", {}).get("value")
    if gm is not None:
        if gm > 50:
            score += 4
            signals.append(f"高毛利({gm:.1f}%)")
        elif gm > 30:
            score += 2
        elif gm < 15:
            score -= 2
            warnings.append(f"低毛利({gm:.1f}%)")
    
    return max(-25, min(25, score)), signals, warnings


def _score_cap(cap: Dict) -> Tuple[int, List[str], List[str]]:
    """资金面评分 (-25 ~ +25)"""
    score = 0
    signals = []
    warnings = []
    
    vol = cap.get("volume_stats", {})
    if "stats" in vol:
        stats = vol["stats"]
        vr = stats.get("volume_ratio", 1.0)
        if vr > 1.5:
            score += 6
            signals.append(f"放量交易(量比{vr})")
        elif vr > 1.0:
            score += 2
        elif vr < 0.5:
            score -= 4
            warnings.append(f"极度缩量(量比{vr})")
        else:
            score -= 1
    
    # 北向
    nb = cap.get("northbound", {})
    if "summary" in nb:
        summary = nb["summary"]
        trend = nb.get("trend", {})
        stale = summary.get("stale", False)
        ratio_c = summary.get("ratio", {}).get("current", 0)
        ratio_m = summary.get("ratio", {}).get("median", 0)
        up_days = trend.get("up_days_5d", 0)
        
        # 如果数据过时，降低北向评分权重
        nb_mult = 0.3 if stale else 1.0
        nb_score = 0
        
        if ratio_c and ratio_c > 5:
            nb_score += 8
            signals.append(f"北向重仓({ratio_c:.1f}%)" + ("⚠过时" if stale else ""))
        elif ratio_c and ratio_c > 3:
            nb_score += 5
            signals.append(f"北向关注({ratio_c:.1f}%)" + ("⚠过时" if stale else ""))
        elif ratio_c and ratio_c > 1:
            nb_score += 2
        elif ratio_c is not None and ratio_c < 0.5:
            nb_score -= 3
            warnings.append(f"北向低配({ratio_c:.1f}%)" + ("⚠过时" if stale else ""))
        
        if ratio_c and ratio_m and ratio_c > ratio_m * 1.2:
            nb_score += 2
            signals.append("持股高于中位")
        elif ratio_c and ratio_m and ratio_c < ratio_m * 0.8:
            nb_score -= 2
            warnings.append("持股低于中位")
        
        if up_days >= 4:
            nb_score += 7
            signals.append(f"北向5日{up_days}买")
        elif up_days >= 3:
            nb_score += 4
        elif up_days <= 1:
            nb_score -= 5
            warnings.append(f"北向5日{up_days}买，偏卖")
        
        score += int(nb_score * nb_mult)
    
    return max(-25, min(25, score)), signals, warnings


def _score_sent(sent: Dict) -> Tuple[int, List[str], List[str]]:
    """舆情面评分 (-25 ~ +25)"""
    score = 0
    signals = []
    warnings = []
    
    sig = sent.get("signal", "neutral")
    pos = sent.get("positive_count", 0)
    neg = sent.get("negative_count", 0)
    total = pos + neg
    
    if total > 0:
        ratio = (pos - neg) / total
        score = int(ratio * 25)
        
        if ratio > 0.3:
            signals.append(f"股吧偏多({ratio:.2f})")
        elif ratio < -0.3:
            warnings.append(f"股吧偏空({ratio:.2f})")
    
    return max(-25, min(25, score)), signals, warnings
