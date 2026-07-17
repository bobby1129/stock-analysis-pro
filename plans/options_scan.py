"""
ETF期权风险收益扫描引擎 v3

调度: 数据采集 → 波动率计算 → 过滤虚值 → 风险收益指标计算 → 卖方/买方排序输出
"""

import math
from collectors.options import (
    fetch_all_options, calculate_volatility_ratio, calculate_risk_metrics,
    UNDERLYINGS
)


# 正态分布CDF (不依赖scipy)
def norm_cdf(x):
    """标准正态分布累积分布函数"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def calc_win_probability(spot, strike, hv_std_ann, days, option_type):
    """
    完整Black-Scholes d2公式估算到达行权价的概率
    
    Args:
        spot: 标的现价
        strike: 行权价
        hv_std_ann: 年化历史波动率标准差 (HV60)
        days: 距到期天数
        option_type: 'C' 或 'P'
    
    Returns:
        概率 (0~1)
    
    公式：
        d2 = (ln(S/K) + (r - σ²/2)*T) / (σ√T)
        认购 P = Φ(d2)
        认沽 P = 1 - Φ(d2)
    """
    if spot <= 0 or strike <= 0 or hv_std_ann <= 0 or days <= 0:
        return 0
    
    T = days / 365.0
    r = 0.02  # 无风险利率 2%
    sigma = hv_std_ann
    
    # d2 公式
    d2 = (math.log(spot / strike) + (r - 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    
    if option_type == 'C':
        # 认购：P(S_T > K) = Φ(d2)
        return norm_cdf(d2)
    else:
        # 认沽：P(S_T < K) = 1 - Φ(d2) = Φ(-d2)
        return 1.0 - norm_cdf(d2)


# 过滤参数
MIN_DAYS_TO_EXPIRY = 7       # 卖方最小天数
MIN_DAYS_BUYER = 10          # 买方最小天数
MAX_DAYS_BUYER = 90          # 买方最大天数
MIN_PREMIUM = 0.005
MARGIN_RATE = 0.12  # 通用保证金比例
CONTRACT_MULTIPLIER = 10000


def run_scan(underlying: str = None, month: str = None, top_n: int = 10) -> dict:
    """
    执行风险收益扫描

    返回: {
        fetch_time, volatility_panorama, seller_top,
        total_contracts, filtered_count, filter_rules
    }
    """
    print("=" * 60)
    print("ETF期权风险收益扫描 v2")
    print("=" * 60)

    # Step 1: 采集期权数据
    print("\n[1/4] 采集期权数据...")
    options_data = fetch_all_options(underlying=underlying, month=month)
    contracts = options_data["contracts"]
    underlyings_info = options_data["underlyings"]
    print(f"  共采集 {len(contracts)} 个合约, {len(underlyings_info)} 个品种")

    # Step 2: 计算各标的波动率
    print("\n[2/4] 计算标的波动率...")
    volatility_panorama = []
    vol_map = {}  # code -> vol_data
    for code, info in underlyings_info.items():
        print(f"  {info['name']}...", end=" ")
        vol = calculate_volatility_ratio(code)
        if vol:
            vol["name"] = info["name"]
            vol["price"] = info["price"]
            vol["code"] = code
            volatility_panorama.append(vol)
            vol_map[code] = vol
            print(f"V={vol['v_ratio']:.2f} P{vol['percentile']} {vol['signal']}")
        else:
            print("数据不足")

    # Step 3: 过滤 + 计算风险指标
    print(f"\n[3/4] 过滤 & 计算风险收益...")
    scored_contracts = []
    filtered_reasons = {"otm": 0, "days": 0, "premium": 0, "metrics": 0}

    for c in contracts:
        code = c.get("underlying_code", "")
        spot = c.get("underlying_price", 0)
        vol = vol_map.get(code)
        if not vol:
            continue

        strike = c.get("strike", 0)
        option_type = c.get("option_type", "")
        days = c.get("days_to_expiry", 0)
        premium = c.get("last_price", 0)

        # 过滤: 虚值
        if option_type == "C" and strike <= spot:
            filtered_reasons["otm"] += 1
            continue
        if option_type == "P" and strike >= spot:
            filtered_reasons["otm"] += 1
            continue

        # 过滤: 距到期 >= 7天
        if days < MIN_DAYS_TO_EXPIRY:
            filtered_reasons["days"] += 1
            continue

        # 过滤: 权利金 >= 0.005
        if premium < MIN_PREMIUM:
            filtered_reasons["premium"] += 1
            continue

        # 计算保证金和实际权利金（统一用每张口径）
        margin = strike * CONTRACT_MULTIPLIER * MARGIN_RATE
        actual_premium = premium * CONTRACT_MULTIPLIER

        # 构建适配dict
        contract_for_calc = {
            "strike_price": strike,
            "premium": actual_premium,
            "days_to_expiry": days,
            "margin": margin,
        }

        metrics = calculate_risk_metrics(contract_for_calc, spot, vol["amp_60"])
        if not metrics:
            filtered_reasons["metrics"] += 1
            continue

        scored_contracts.append({
            "name": c.get("name", ""),
            "option_type": "认购" if option_type == "C" else "认沽",
            "type_code": option_type,
            "strike": strike,
            "days": days,
            "premium": premium,
            "premium_per_contract": actual_premium,
            "margin": margin,
            "direct_yield": metrics["direct_yield"],
            "annualized_yield": metrics["annualized_yield"],
            "D": metrics["D"],
            "R": metrics["R"],
            "S": metrics["S"],
            "underlying_name": c.get("underlying_name", ""),
            "underlying_code": code,
            "spot": spot,
            "win_prob": calc_win_probability(spot, strike, vol["hv60_std"], days, option_type),
        })

    print(f"  过滤后: {len(scored_contracts)} 个合约")
    print(f"  过滤原因: 非虚值={filtered_reasons['otm']}, "
          f"天数不足={filtered_reasons['days']}, "
          f"权利金不足={filtered_reasons['premium']}, "
          f"指标异常={filtered_reasons['metrics']}")

    # Step 4: 排序
    print(f"\n[4/4] 排序...")
    
    # 卖方: S值最高 → 优先卖出
    scored_contracts.sort(key=lambda x: x["S"], reverse=True)
    seller_top = scored_contracts[:top_n]
    
    # 买方: 卖方不合适 = 买方机会
    # 过滤条件：
    # - 天数 10~90天
    # - 虚值幅度 > 3%
    # - 直接收益率 < 20%
    # - 胜率 >= 10%
    buyer_candidates = []
    for c in scored_contracts:
        # 天数限制
        if c["days"] < MIN_DAYS_BUYER or c["days"] > MAX_DAYS_BUYER:
            continue
        # 虚值幅度 > 3%
        otm_ratio = abs(c["spot"] - c["strike"]) / c["spot"]
        if otm_ratio < 0.03:
            continue
        # 直接收益率 < 20%
        dy = c["premium_per_contract"] / c["margin"]
        if dy >= 0.20:
            continue
        # 胜率 >= 10%
        if c["win_prob"] < 0.10:
            continue
        c["otm_ratio"] = otm_ratio
        buyer_candidates.append(c)
    
    buyer_candidates.sort(key=lambda x: x["S"])
    buyer_top = buyer_candidates[:top_n]

    result = {
        "fetch_time": options_data["fetch_time"],
        "volatility_panorama": volatility_panorama,
        "seller_top": seller_top,
        "buyer_top": buyer_top,
        "total_contracts": len(contracts),
        "filtered_count": len(scored_contracts),
        "filter_rules": {
            "min_days": MIN_DAYS_TO_EXPIRY,
            "min_days_buyer": MIN_DAYS_BUYER,
            "max_days_buyer": MAX_DAYS_BUYER,
            "min_premium": MIN_PREMIUM,
            "margin_rate": MARGIN_RATE,
            "contract_multiplier": CONTRACT_MULTIPLIER,
            "buyer_otm_min": 0.03,
            "buyer_max_yield": 0.20,
            "buyer_win_prob_min": 0.10,
        },
    }

    return result


def print_summary(result: dict):
    """终端文字摘要"""
    print("\n" + "=" * 60)
    print("波动率全景")
    print("=" * 60)

    for v in result["volatility_panorama"]:
        print(f"  {v['name']:12s} 现价={v['price']:.4f} "
              f"V={v['v_ratio']:.2f} P{v['percentile']} {v['signal']} "
              f"20d={v['amp_20']:.4f} 60d={v['amp_60']:.4f}")

    print(f"\n卖方Top{len(result['seller_top'])} (S值最高 → 优先卖出):")
    hdr = f"{'#':>2s} {'合约':18s} {'方向':4s} {'天':>3s} {'权利金':>7s} {'直接收益':>8s} {'年化收益':>8s} {'D':>6s} {'R':>6s} {'S':>8s}"
    print(hdr)
    print("-" * len(hdr))
    for i, s in enumerate(result["seller_top"], 1):
        print(f"  {i:2d} {s['name']:18s} {s['option_type']:4s} {s['days']:3d} "
              f"{s['premium']:7.4f} "
              f"{s['direct_yield']*100:7.2f}% "
              f"{s['annualized_yield']*100:7.1f}% "
              f"{s['D']:6.3f} {s['R']:6.3f} {s['S']:8.2f}")

    print(f"\n买方Top{len(result['buyer_top'])} (S值最低 + 胜率≥10% → 优先买入):")
    hdr = f"{'#':>2s} {'合约':18s} {'方向':4s} {'天':>3s} {'权利金':>7s} {'直接收益':>8s} {'年化收益':>8s} {'胜率':>6s} {'D':>6s} {'R':>6s} {'S':>8s}"
    print(hdr)
    print("-" * len(hdr))
    for i, s in enumerate(result["buyer_top"], 1):
        print(f"  {i:2d} {s['name']:18s} {s['option_type']:4s} {s['days']:3d} "
              f"{s['premium']:7.4f} "
              f"{s['direct_yield']*100:7.2f}% "
              f"{s['annualized_yield']*100:7.1f}% "
              f"{s['win_prob']*100:5.1f}% "
              f"{s['D']:6.3f} {s['R']:6.3f} {s['S']:8.2f}")
