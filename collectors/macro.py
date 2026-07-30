# -*- coding: utf-8 -*-
"""宏观数据采集 — 国际宏观 + 国内宏观 + 事件驱动(涨停池)

数据源:
  - 国际: akshare(美债10Y/美联储利率) + 新浪(黄金/白银/原油)
  - 国内: akshare(CPI/PMI/M2/LPR)
  - 事件: akshare(涨停池/强势涨停/昨日涨停今日表现)

注意: akshare 接口需要 HTTPS_PROXY 环境变量或在 config.yaml 中配置 proxy.https
"""

import os
import re
import requests
from typing import Dict, List, Optional
from datetime import datetime


def _ensure_proxy():
    """确保代理已设置。如果 HTTPS_PROXY 未设置，尝试从配置文件读取，否则跳过"""
    if "HTTPS_PROXY" not in os.environ and "https_proxy" not in os.environ:
        try:
            from config import load_config
            proxy = load_config().get("proxy", {}).get("https", "")
            if proxy:
                os.environ["HTTPS_PROXY"] = proxy
        except Exception:
            pass


def _safe_latest(df, value_col=None, date_col=None) -> Dict:
    """安全提取 DataFrame 最后一行的值，自动探测列名"""
    if df is None or df.empty:
        return {"value": None, "date": None}
    
    # 自动探测值列
    if value_col is None:
        for candidate in ["今值", "数值", "value", "Value", "收益率", "利率"]:
            if candidate in df.columns:
                value_col = candidate
                break
        if value_col is None:
            # 取第一个数值列
            for col in df.columns:
                if df[col].dtype in ('float64', 'int64', 'float32'):
                    value_col = col
                    break
    
    # 自动探测日期列
    if date_col is None:
        for candidate in ["日期", "date", "Date", "月份", "报告期", "TRADE_DATE"]:
            if candidate in df.columns:
                date_col = candidate
                break
    
    if value_col is None:
        return {"value": None, "date": None, "columns": list(df.columns)}
    
    try:
        valid = df[df[value_col].notna()]
        if valid.empty:
            return {"value": None, "date": None}
        latest = valid.iloc[-1]
        result = {"value": float(latest[value_col])}
        if date_col and date_col in df.columns:
            result["date"] = str(latest[date_col])
        return result
    except Exception as e:
        return {"value": None, "date": None, "error": str(e)}


# ─────────────────────────────────────────────
# 1. 国际宏观
# ─────────────────────────────────────────────

def global_macro() -> Dict:
    """国际宏观指标: 美债10Y / 美联储利率 / 黄金 / 白银 / 原油"""
    _ensure_proxy()
    import akshare as ak
    
    result = {}
    
    # 1.1 美债10Y收益率
    try:
        df = ak.bond_zh_us_rate()
        us_col = None
        for col in df.columns:
            if "10年" in str(col) and "美国" in str(col):
                us_col = col
                break
        if us_col is None:
            us_col = "美国国债收益率10年" if "美国国债收益率10年" in df.columns else None
        
        if us_col:
            valid = df[df[us_col].notna()]
            if not valid.empty:
                latest = valid.iloc[-1]
                result["us_10y_yield"] = {
                    "value": float(latest[us_col]),
                    "date": str(latest.get("日期", "")),
                }
        else:
            result["us_10y_yield"] = {"error": "column not found", "columns": list(df.columns)}
    except Exception as e:
        result["us_10y_yield"] = {"error": str(e)}
    
    # 1.2 美联储利率
    try:
        df = ak.macro_bank_usa_interest_rate()
        result["fed_rate"] = _safe_latest(df)
    except Exception as e:
        result["fed_rate"] = {"error": str(e)}
    
    # 1.3 大宗商品 (新浪 hf_ 接口, 直连)
    commodities = [
        ("hf_GC", "gold", "纽约黄金"),
        ("hf_SI", "silver", "纽约白银"),
        ("hf_CL", "crude_oil", "WTI原油"),
    ]
    for symbol, key, name in commodities:
        try:
            data = _fetch_sina_commodity(symbol, name)
            result[key] = data
        except Exception as e:
            result[key] = {"error": str(e)}
    
    return result


def _fetch_sina_commodity(symbol: str, name: str) -> Optional[Dict]:
    """新浪国际商品行情 (hq.sinajs.cn)"""
    url = f"http://hq.sinajs.cn/list={symbol}"
    headers = {"Referer": "https://finance.sina.com.cn"}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.encoding = "gbk"
    text = resp.text.strip()
    
    if '=""' in text or "=''" in text:
        return None
    
    match = re.search(r'="([^"]*)"', text)
    if not match:
        return None
    
    fields = match.group(1).split(",")
    if len(fields) < 10:
        return None
    
    return {
        "name": name,
        "price": float(fields[0]) if fields[0] else None,
        "prev_close": float(fields[2]) if fields[2] else None,
        "change_pct": round((float(fields[0]) - float(fields[2])) / float(fields[2]) * 100, 2) if fields[0] and fields[2] and float(fields[2]) > 0 else None,
        "open": float(fields[3]) if fields[3] else None,
        "high": float(fields[4]) if fields[4] else None,
        "low": float(fields[5]) if fields[5] else None,
        "time": fields[6] if fields[6] else None,
    }


# ─────────────────────────────────────────────
# 2. 国内宏观
# ─────────────────────────────────────────────

def domestic_macro() -> Dict:
    """国内宏观指标: CPI / PMI / M2 / LPR"""
    _ensure_proxy()
    import akshare as ak
    
    result = {}
    
    # 2.1 CPI (月度)
    try:
        df = ak.macro_china_cpi_monthly()
        result["cpi"] = _safe_latest(df)
    except Exception as e:
        result["cpi"] = {"error": str(e)}
    
    # 2.2 制造业PMI
    try:
        df = ak.macro_china_pmi_yearly()
        result["pmi_manufacturing"] = _safe_latest(df)
    except Exception as e:
        result["pmi_manufacturing"] = {"error": str(e)}
    
    # 2.3 非制造业PMI
    try:
        df = ak.macro_china_non_man_pmi()
        result["pmi_non_manufacturing"] = _safe_latest(df)
    except Exception as e:
        result["pmi_non_manufacturing"] = {"error": str(e)}
    
    # 2.4 M2 同比
    try:
        df = ak.macro_china_m2_yearly()
        result["m2_yoy"] = _safe_latest(df)
    except Exception as e:
        result["m2_yoy"] = {"error": str(e)}
    
    # 2.5 LPR (1Y + 5Y)
    try:
        df = ak.macro_china_lpr()
        if not df.empty and "LPR1Y" in df.columns:
            latest = df.iloc[-1]
            result["lpr"] = {
                "1y": float(latest["LPR1Y"]),
                "5y": float(latest["LPR5Y"]),
                "date": str(latest.get("TRADE_DATE", "")),
            }
        else:
            result["lpr"] = {"error": "columns not found", "columns": list(df.columns) if not df.empty else []}
    except Exception as e:
        result["lpr"] = {"error": str(e)}
    
    return result


# ─────────────────────────────────────────────
# 3. 事件驱动 (涨停池)
# ─────────────────────────────────────────────

def zt_pool(date: Optional[str] = None) -> Dict:
    """涨停复盘: 涨停池 + 统计 + 强势股 + 昨日涨停今日表现
    
    Args:
        date: YYYYMMDD, 默认今天
    """
    _ensure_proxy()
    import akshare as ak
    
    if date is None:
        date = datetime.now().strftime("%Y%m%d")
    
    result = {"date": date}
    
    # 3.1 今日涨停池
    try:
        df = ak.stock_zt_pool_em(date=date)
        if not df.empty:
            result["zt_list"] = _format_zt(df)
            result["zt_stats"] = _calc_zt_stats(df)
        else:
            result["zt_list"] = []
            result["zt_stats"] = {"count": 0}
    except Exception as e:
        result["zt_error"] = str(e)
        result["zt_list"] = []
        result["zt_stats"] = {"count": 0}
    
    # 3.2 强势涨停 (创新高等)
    try:
        df = ak.stock_zt_pool_strong_em(date=date)
        result["strong_list"] = _format_strong(df) if not df.empty else []
    except Exception:
        result["strong_list"] = []
    
    # 3.3 昨日涨停今日表现
    try:
        df = ak.stock_zt_pool_previous_em(date=date)
        result["prev_zt_perf"] = _format_prev_zt(df) if not df.empty else []
    except Exception:
        result["prev_zt_perf"] = []
    
    return result


def _format_zt(df) -> List[Dict]:
    """格式化涨停池"""
    stocks = []
    for _, row in df.iterrows():
        stocks.append({
            "code": str(row.get("代码", "")),
            "name": str(row.get("名称", "")),
            "price": float(row.get("最新价", 0)),
            "pct": round(float(row.get("涨跌幅", 0)), 2),
            "turnover": round(float(row.get("换手率", 0)), 2),
            "sealed_amount": int(row.get("封板资金", 0)),
            "height": int(row.get("连板数", 1)),
            "first_seal_time": str(row.get("首次封板时间", "")),
            "bomb_count": int(row.get("炸板次数", 0)),
            "sector": str(row.get("所属行业", "")),
        })
    return stocks


def _calc_zt_stats(df) -> Dict:
    """涨停池统计: 总数/最高连板/热门行业"""
    total = len(df)
    
    # 最高连板
    max_height = 0
    max_stocks = []
    if "连板数" in df.columns and not df.empty:
        max_height = int(df["连板数"].max())
        if max_height > 0:
            max_stocks = df[df["连板数"] == max_height]["名称"].tolist()
    
    # 连板分布
    height_dist = {}
    if "连板数" in df.columns:
        for h, cnt in df["连板数"].value_counts().items():
            height_dist[int(h)] = int(cnt)
    
    # 热门行业 Top5
    hot_sectors = {}
    if "所属行业" in df.columns:
        hot_sectors = df["所属行业"].value_counts().head(5).to_dict()
        hot_sectors = {k: int(v) for k, v in hot_sectors.items()}
    
    # 封板资金
    total_sealed = 0
    if "封板资金" in df.columns:
        total_sealed = int(df["封板资金"].sum())
    
    return {
        "count": total,
        "max_height": max_height,
        "max_height_stocks": max_stocks,
        "height_distribution": height_dist,
        "hot_sectors": hot_sectors,
        "total_sealed_amount": total_sealed,
    }


def _format_strong(df) -> List[Dict]:
    """格式化强势涨停"""
    stocks = []
    for _, row in df.iterrows():
        stocks.append({
            "code": str(row.get("代码", "")),
            "name": str(row.get("名称", "")),
            "price": float(row.get("最新价", 0)),
            "pct": round(float(row.get("涨跌幅", 0)), 2),
            "reason": str(row.get("入选理由", "")),
            "sector": str(row.get("所属行业", "")),
        })
    return stocks


def _format_prev_zt(df) -> List[Dict]:
    """格式化昨日涨停今日表现"""
    stocks = []
    for _, row in df.iterrows():
        stocks.append({
            "code": str(row.get("代码", "")),
            "name": str(row.get("名称", "")),
            "price": float(row.get("最新价", 0)),
            "pct": round(float(row.get("涨跌幅", 0)), 2),
            "amplitude": round(float(row.get("振幅", 0)), 2),
            "prev_height": int(row.get("昨日连板数", 1)),
            "sector": str(row.get("所属行业", "")),
        })
    return stocks
