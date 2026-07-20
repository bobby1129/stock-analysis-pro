# -*- coding: utf-8 -*-
"""分析维度层 — 舆情面"""

from collectors.sentiment import guba_posts, stock_news, analyst_ratings, interactive_qa


def analyze(symbol: str, stock_name: str = "", em_data: dict = None) -> dict:
    """舆情面分析：股吧热帖 + 个股新闻 + 分析师评级 + 情绪评分

    Args:
        symbol: 股票代码
        stock_name: 股票名称 (用于新闻搜索, 可选)
        em_data: Playwright 预获取的东财数据 (可选)
            结构: {"guba": [...], "news": [...], "ratings": {...}}
    """
    # 使用预获取的数据（Playwright）或回退到直连
    if em_data:
        posts = em_data.get("guba", []) or []
        news = em_data.get("news", []) or []
        ratings = em_data.get("ratings", {"reports": [], "summary": {"total": 0}})
    else:
        posts = guba_posts(symbol, limit=10)
        keyword = stock_name if stock_name else symbol
        news = stock_news(keyword, limit=5)
        ratings = analyst_ratings(symbol, days=180, limit=10)

    # 互动易问答 (仍走直连，风险较低)
    qa = interactive_qa(symbol, limit=10)

    # 关键词情绪评分 (股吧 + 新闻合并，新闻有时间衰减)
    positive_keywords = ["利好", "买入", "加仓", "看好", "突破", "上涨", "主力",
                         "增长", "新高", "分红", "回购", "增持", "超预期"]
    negative_keywords = ["利空", "卖出", "减持", "看空", "跌破", "下跌", "套牢",
                         "下滑", "亏损", "处罚", "诉讼", "质押", "低于预期"]

    pos_count = 0
    neg_count = 0

    # 股吧帖子 (无时间信息，权重=1)
    for p in posts:
        text = p.get("title", "")
        pos_count += sum(1 for kw in positive_keywords if kw in text)
        neg_count += sum(1 for kw in negative_keywords if kw in text)

    # 新闻 (有时间衰减：7天内权重1.0，7-14天0.7，14天+0.4)
    from datetime import datetime, timedelta
    now = datetime.now()
    for n in news:
        text = n.get("title", "") + n.get("content", "")
        date_str = n.get("date", "")
        weight = 1.0
        if date_str:
            try:
                d = datetime.strptime(date_str[:10], "%Y-%m-%d")
                age_days = (now - d).days
                if age_days <= 7:
                    weight = 1.0
                elif age_days <= 14:
                    weight = 0.7
                else:
                    weight = 0.4
            except (ValueError, TypeError):
                weight = 1.0
        
        pos_count += sum(1 for kw in positive_keywords if kw in text) * weight
        neg_count += sum(1 for kw in negative_keywords if kw in text) * weight

    total = pos_count + neg_count
    if total == 0:
        signal = "neutral"
        label = "中性"
    elif pos_count > neg_count:
        signal = "bullish"
        label = "偏多"
    else:
        signal = "bearish"
        label = "偏空"

    # 分析师评级信号
    consensus = ratings.get("summary", {}).get("consensus", "")

    return {
        "signal": signal,
        "label": label,
        "post_count": len(posts),
        "news_count": len(news),
        "qa_count": len(qa),
        "positive_count": pos_count,
        "negative_count": neg_count,
        "raw_posts": posts[:5],
        "news": news[:5],
        "interactive_qa": qa[:5],
        "analyst_ratings": ratings,
        "analyst_consensus": consensus,
    }
