# -*- coding: utf-8 -*-
"""东财 Playwright 浏览器会话 — 共享一个浏览器实例，通过页面导航+拦截获取数据

解决东财 API 直连被限流/超时的问题。所有东财数据统一通过真实浏览器上下文获取。
"""

import json
import re
import time
import os
from typing import Dict

_BROWSER = None
_CONTEXT = None


def _ensure_browser():
    """确保浏览器实例存在"""
    global _BROWSER, _CONTEXT
    if _BROWSER is not None:
        return _BROWSER, _CONTEXT

    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    _BROWSER = pw.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
    )
    _CONTEXT = _BROWSER.new_context(
        user_agent=(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/125.0.0.0 Safari/537.36'
        ),
        viewport={'width': 1920, 'height': 1080},
    )
    return _BROWSER, _CONTEXT


def close_browser():
    """关闭共享浏览器"""
    global _BROWSER, _CONTEXT
    if _CONTEXT:
        try:
            _CONTEXT.close()
        except Exception:
            pass
    if _BROWSER:
        try:
            _BROWSER.close()
        except Exception:
            pass
    _BROWSER = None
    _CONTEXT = None


def fetch_f10(symbol: str, verbose: bool = False) -> Dict:
    """通过 F10 页面获取公司基本信息
    
    导航到 emweb F10 页面，让浏览器自然发出 CompanySurveyAjax 请求，拦截响应。
    """
    _, ctx = _ensure_browser()
    page = ctx.new_page()
    captured = {}

    code = f"SZ{symbol}" if symbol.startswith(("0", "3")) else f"SH{symbol}"
    f10_url = f"https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/Index?type=web&code={code}"

    def handle_response(response):
        url = response.url
        if 'CompanySurvey' in url and ('Ajax' in url or 'PageAjax' in url):
            try:
                captured['data'] = response.json()
            except Exception:
                pass

    page.on('response', handle_response)

    try:
        if verbose:
            print(f"    [Playwright] F10 页面: {symbol}...")
        page.goto(f10_url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(5000)  # 等待 AJAX 完成
    except Exception as e:
        if verbose:
            print(f"    [Playwright] F10 导航失败: {e}")
    finally:
        page.remove_listener('response', handle_response)
        page.close()

    return captured.get('data', {})


def fetch_guba(symbol: str, limit: int = 10, verbose: bool = False) -> list:
    """通过股吧页面获取热帖
    
    导航到股吧列表页，直接从 HTML 提取帖子标题。
    """
    _, ctx = _ensure_browser()
    page = ctx.new_page()

    code = symbol.zfill(6)
    guba_url = f"https://guba.eastmoney.com/list,{code}.html"

    try:
        if verbose:
            print(f"    [Playwright] 股吧页面: {symbol}...")
        page.goto(guba_url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(3000)

        # 直接从页面 HTML 提取帖子
        html = page.content()
        posts = []
        pattern = r'<a[^>]*href="(/news,[^"]+)"[^>]*>([^<]+)</a>'
        matches = re.findall(pattern, html)

        for href, title in matches[:limit]:
            title = title.strip()
            if title and len(title) > 5:
                posts.append({
                    "title": title,
                    "url": f"https://guba.eastmoney.com{href}",
                    "source": "guba",
                })

        return posts
    except Exception as e:
        if verbose:
            print(f"    [Playwright] 股吧导航失败: {e}")
        return []
    finally:
        page.close()


def fetch_news(keyword: str, limit: int = 5, verbose: bool = False) -> list:
    """通过东财搜索页获取新闻
    
    导航到搜索页，拦截 search-api 的 JSONP 响应。
    """
    _, ctx = _ensure_browser()
    page = ctx.new_page()
    captured = {}

    search_url = f"https://so.eastmoney.com/news/s?keyword={keyword}"

    def handle_response(response):
        url = response.url
        if 'search-api-web' in url and 'cmsArticle' not in captured:
            try:
                text = response.text()
                # 解析 JSONP: jQuery(...)
                start = text.index("(") + 1
                end = text.rindex(")")
                data = json.loads(text[start:end])
                # 只保留包含文章数据的响应
                articles = data.get("result", {}).get("cmsArticleWebOld", [])
                if articles:
                    captured['data'] = data
            except Exception:
                pass

    page.on('response', handle_response)

    try:
        if verbose:
            print(f"    [Playwright] 搜索页面: {keyword}...")
        page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(5000)
    except Exception as e:
        if verbose:
            print(f"    [Playwright] 搜索导航失败: {e}")
    finally:
        page.remove_listener('response', handle_response)
        page.close()

    # 解析搜索结果
    data = captured.get('data', {})
    articles = data.get("result", {}).get("cmsArticleWebOld", [])
    if not isinstance(articles, list):
        return []

    results = []
    for a in articles[:limit]:
        title = a.get("title", "").replace("<em>", "").replace("</em>", "")
        content = a.get("content", "").replace("<em>", "").replace("</em>", "")
        results.append({
            "title": title,
            "date": a.get("date", "")[:10],
            "media": a.get("mediaName", ""),
            "content": content[:200],
            "url": a.get("url", ""),
            "source": "eastmoney_search",
        })

    return results


def fetch_analyst_ratings(symbol: str, days: int = 180, limit: int = 10, verbose: bool = False) -> Dict:
    """通过东财 F10 研报页面获取分析师评级
    
    导航到 F10 研报 tab，拦截 ResearchReport/PageAjax 响应。
    """
    from datetime import datetime, timedelta

    _, ctx = _ensure_browser()
    page = ctx.new_page()
    captured = {}

    code = f"SZ{symbol}" if symbol.startswith(("0", "3")) else f"SH{symbol}"
    f10_url = f"https://emweb.securities.eastmoney.com/PC_HSF10/ResearchReport/Index?type=web&code={code}"

    def handle_response(response):
        url = response.url
        if 'ResearchReport' in url and 'PageAjax' in url:
            try:
                captured['data'] = response.json()
            except Exception:
                pass

    page.on('response', handle_response)

    try:
        if verbose:
            print(f"    [Playwright] 研报页面: {symbol}...")
        page.goto(f10_url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(5000)
    except Exception as e:
        if verbose:
            print(f"    [Playwright] 研报导航失败: {e}")
    finally:
        page.remove_listener('response', handle_response)
        page.close()

    data = captured.get('data', {})
    
    # F10 研报页面: gsyb=个股研报, hyyb=行业研报
    raw_list = data.get("gsyb", [])
    if not raw_list:
        raw_list = data.get("data", [])
    if not raw_list and isinstance(data, dict):
        for key in ['hyyb', 'yjbg', 'reportList', 'list']:
            if key in data and isinstance(data[key], list):
                raw_list = data[key]
                break
    
    if not raw_list:
        return {"reports": [], "summary": {"total": 0}}

    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    reports = []
    rating_counts = {}

    for r in raw_list[:limit]:
        # 兼容新旧字段名 (F10: em_rating_name/publish_time/source, reportapi: emRatingName/publishDate/orgSName)
        rating = (r.get("em_rating_name") or r.get("emRatingName") or 
                  r.get("ratingName") or r.get("s_rating_name") or r.get("sRatingName") or "")
        rating_counts[rating] = rating_counts.get(rating, 0) + 1

        report = {
            "date": (r.get("publish_time") or r.get("publishDate") or r.get("date") or "")[:10],
            "org": r.get("source") or r.get("orgSName") or r.get("orgName") or "",
            "title": r.get("title", ""),
            "rating": rating,
            "s_rating": r.get("s_rating_name") or r.get("sRatingName") or "",
            "researcher": r.get("researcher", ""),
        }

        for key, field in [("eps_this_year", "predictThisYearEps"),
                           ("eps_next_year", "predictNextYearEps"),
                           ("eps_next2_year", "predictNextTwoYearEps"),
                           ("pe_this_year", "predictThisYearPe"),
                           ("pe_next_year", "predictNextYearPe")]:
            val = r.get(field)
            if val:
                try:
                    report[key] = round(float(val), 2)
                except (ValueError, TypeError):
                    pass

        reports.append(report)

    # 汇总
    eps_this_vals = [r.get("eps_this_year") for r in reports if r.get("eps_this_year")]
    eps_next_vals = [r.get("eps_next_year") for r in reports if r.get("eps_next_year")]

    summary = {
        "total": len(reports),
        "rating_distribution": rating_counts,
        "period": f"{start} ~ {end}",
    }

    if eps_this_vals:
        summary["avg_eps_this_year"] = round(sum(eps_this_vals) / len(eps_this_vals), 2)
        summary["eps_this_year_count"] = len(eps_this_vals)
    if eps_next_vals:
        summary["avg_eps_next_year"] = round(sum(eps_next_vals) / len(eps_next_vals), 2)
        summary["eps_next_year_count"] = len(eps_next_vals)

    buy = rating_counts.get("买入", 0) + rating_counts.get("强烈推荐", 0)
    overweight = rating_counts.get("增持", 0) + rating_counts.get("推荐", 0)
    hold = rating_counts.get("持有", 0) + rating_counts.get("中性", 0)
    sell = rating_counts.get("减持", 0) + rating_counts.get("卖出", 0)

    summary["buy"] = buy
    summary["overweight"] = overweight
    summary["hold"] = hold
    summary["sell"] = sell

    total_rated = buy + overweight + hold + sell
    if total_rated > 0:
        bull_ratio = (buy + overweight) / total_rated
        if bull_ratio >= 0.8:
            summary["consensus"] = "强烈看多"
        elif bull_ratio >= 0.6:
            summary["consensus"] = "偏多"
        elif bull_ratio >= 0.4:
            summary["consensus"] = "分歧"
        else:
            summary["consensus"] = "偏空"
    else:
        summary["consensus"] = "无评级"

    return {"reports": reports, "summary": summary}


def fetch_all_stock_data(symbol: str, verbose: bool = False) -> Dict:
    """一次性获取个股所有东财数据
    
    在同一个浏览器会话中依次访问各页面，返回全部数据。
    
    Returns:
        {
            "f10": {...},        # 公司F10信息
            "guba": [...],       # 股吧热帖
            "news": [...],       # 新闻搜索
            "ratings": {...},    # 分析师评级
        }
    """
    stock_name = ""
    # 先从腾讯拿股票名称用于新闻搜索
    try:
        from collectors.quote import realtime
        rt = realtime(symbol)
        stock_name = rt.get("name", symbol)
    except Exception:
        stock_name = symbol

    if verbose:
        print(f"  [Playwright] 启动东财浏览器会话...")

    f10 = fetch_f10(symbol, verbose=verbose)
    time.sleep(2)

    guba = fetch_guba(symbol, verbose=verbose)
    time.sleep(2)

    news = fetch_news(stock_name or symbol, verbose=verbose)
    time.sleep(2)

    ratings = fetch_analyst_ratings(symbol, verbose=verbose)

    if verbose:
        f10_ok = "✓" if f10 else "✗"
        guba_ok = f"{len(guba)}条" if guba else "✗"
        news_ok = f"{len(news)}条" if news else "✗"
        ratings_ok = f"{ratings['summary']['total']}条" if ratings.get('reports') else "✗"
        print(f"  [Playwright] 东财数据: F10={f10_ok} 股吧={guba_ok} 新闻={news_ok} 研报={ratings_ok}")

    return {
        "f10": f10,
        "guba": guba,
        "news": news,
        "ratings": ratings,
    }
