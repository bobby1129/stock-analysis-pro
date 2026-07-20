# -*- coding: utf-8 -*-
"""分析计划层 — 个股多维分析"""

import sys
import os
import json
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.company import analyze as analyze_company
from analysis.technical import analyze as analyze_technical
from analysis.fundamental import analyze as analyze_fundamental
from analysis.capital import analyze as analyze_capital
from analysis.sentiment import analyze as analyze_sentiment
from analysis.valuation import analyze as analyze_valuation
from analysis.scorer import compute as compute_score

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")


def _save_snapshot(symbol: str, data: dict):
    """保存分析快照用于历史对比"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"snap_{symbol}.json")
    snapshot = {
        "timestamp": time.time(),
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "price": data.get("basic", {}).get("price"),
        "pe": data.get("basic", {}).get("pe"),
        "pb": data.get("basic", {}).get("pb"),
        "total_score": data.get("score", {}).get("total_score"),
        "rating": data.get("score", {}).get("rating"),
        # 新增：技术面信号
        "tech_signals": data.get("technicals", {}).get("signals", [])[:5],
        "tech_warnings": data.get("technicals", {}).get("warnings", [])[:5],
        # 新增：资金面状态
        "capital_signals": data.get("capital", {}).get("signals", [])[:3],
        "capital_warnings": data.get("capital", {}).get("warnings", [])[:3],
        # 新增：估值 PEG
        "peg": data.get("valuation", {}).get("peg"),
        # 新增：风险指标
        "volatility_20d": data.get("technicals", {}).get("volatility_20d"),
        "max_drawdown_60d": data.get("technicals", {}).get("max_drawdown_60d"),
    }
    try:
        with open(path, "w") as f:
            json.dump(snapshot, f, ensure_ascii=False)
    except Exception:
        pass


def _load_prev_snapshot(symbol: str) -> dict:
    """加载上一次的分析快照"""
    path = os.path.join(CACHE_DIR, f"snap_{symbol}.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def run(symbol: str) -> dict:
    """执行个股分析计划"""
    result = {"symbol": symbol}
    
    # 1. 实时行情 (被多个维度共享, 走腾讯不限速)
    from collectors.quote import realtime, market_indices
    basic = realtime(symbol)
    result["basic"] = basic
    
    # 1b. 大盘指数环境 (Item 9)
    indices = market_indices()
    stock_chg = basic.get("change_pct", 0)
    sh_chg = indices.get("上证指数", {}).get("change_pct", 0)
    relative_strength = round(stock_chg - sh_chg, 2) if sh_chg else 0
    result["market"] = {
        "indices": indices,
        "relative_strength": relative_strength,  # 个股 vs 上证
        "stronger_than_market": relative_strength > 0,
    }
    
    # 2. 东财数据 (Playwright 统一获取，避免直连被限流)
    em_data = None
    try:
        from collectors.em_browser import fetch_all_stock_data
        em_data = fetch_all_stock_data(symbol, verbose=True)
    except Exception as e:
        print(f"  [警告] Playwright 东财数据采集失败: {e}, 回退到直连")
    
    # 3. 公司概况
    f10_data = em_data.get("f10") if em_data else None
    result["company"] = analyze_company(symbol, em_data=f10_data)
    
    # 4. 技术面
    result["technicals"] = analyze_technical(symbol, basic=basic)
    
    # 5. 基本面
    result["fundamentals"] = analyze_fundamental(symbol)
    
    # 6. 资金面
    result["capital"] = analyze_capital(symbol)
    
    # 7. 舆情面 (传入股票名称用于新闻搜索)
    stock_name = basic.get("name", "")
    sent_data = None
    if em_data:
        sent_data = {
            "guba": em_data.get("guba", []),
            "news": em_data.get("news", []),
            "ratings": em_data.get("ratings", {}),
        }
    result["sentiment"] = analyze_sentiment(symbol, stock_name=stock_name, em_data=sent_data)
    
    # 8. 估值面
    result["valuation"] = analyze_valuation(symbol, basic=basic)
    
    # 9. 综合评分
    result["score"] = compute_score(
        tech=result["technicals"],
        fund=result["fundamentals"],
        cap=result["capital"],
        sent=result["sentiment"],
        basic=result["basic"],
        val=result["valuation"],
    )
    
    # 10. 历史对比 (Item 12)
    prev = _load_prev_snapshot(symbol)
    if prev and prev.get("date"):
        price_prev = prev.get("price")
        score_prev = prev.get("total_score")
        rating_prev = prev.get("rating")
        price_now = result["basic"].get("price")
        score_now = result["score"].get("total_score")
        
        comparison = {
            "prev_date": prev["date"],
            "prev_price": price_prev,
            "prev_score": score_prev,
            "prev_rating": rating_prev,
        }
        if price_prev and price_now:
            comparison["price_change"] = round(price_now - price_prev, 2)
            comparison["price_change_pct"] = round((price_now - price_prev) / price_prev * 100, 2)
        if score_prev is not None and score_now is not None:
            comparison["score_change"] = score_now - score_prev
        if rating_prev and result["score"].get("rating"):
            comparison["rating_change"] = f"{rating_prev} → {result['score']['rating']}"
        result["comparison"] = comparison
    
    # 11. 保存快照 (覆盖旧的)
    _save_snapshot(symbol, result)
    
    # 12. 业务深度分析（LLM 生成：行业/产业链/竞争/业务/技术解读）
    try:
        from analysis.business import analyze as analyze_business
        print("  [业务分析] LLM 生成行业/产业链/竞争/技术解读...")
        result["business"] = analyze_business(
            symbol, result["company"], result["fundamentals"], result["technicals"]
        )
    except Exception as e:
        print(f"  [业务分析] 跳过: {e}")
        result["business"] = {}
    
    # 13. 关闭浏览器
    try:
        from collectors.em_browser import close_browser
        close_browser()
    except Exception:
        pass
    
    return result
