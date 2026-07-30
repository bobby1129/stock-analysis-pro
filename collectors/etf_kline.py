"""
ETF K线数据采集器 — 用于计算历史波动率(HV)

数据源: 新浪K线API
"""

import requests
import re
import json
from collectors.options import UNDERLYINGS


def fetch_kline(underlying: str, datalen: int = 120) -> list:
    """
    获取ETF日K线数据
    返回: [{"day": "2026-07-09", "open": 3.08, "high": 3.12, "low": 3.05, "close": 3.09, "volume": 123456}, ...]
    """
    info = UNDERLYINGS.get(underlying)
    if not info:
        return []

    symbol = f"{info['exchange']}{underlying}"
    url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    params = {
        "symbol": symbol,
        "scale": 240,  # 日K
        "ma": "no",
        "datalen": datalen,
    }
    headers = {"Referer": "https://finance.sina.com.cn"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        raw = r.text.strip()
        # 新浪返回JS风格JSON (key无引号)
        raw = re.sub(r'(\w+):', r'"\1":', raw)
        data = json.loads(raw)

        result = []
        for item in data:
            result.append({
                "day": item["day"],
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": int(item["volume"]),
            })
        return result
    except Exception as e:
        print(f"  [WARN] K线获取失败 {underlying}: {e}")
        return []


def fetch_all_klines() -> dict:
    """
    获取所有品种的K线数据
    返回: {"510050": [kline_list], "510300": [kline_list], ...}
    """
    result = {}
    for code in UNDERLYINGS:
        print(f"  K线 {UNDERLYINGS[code]['name']}...", end=" ")
        klines = fetch_kline(code, datalen=120)
        result[code] = klines
        print(f"{len(klines)}日")
    return result
