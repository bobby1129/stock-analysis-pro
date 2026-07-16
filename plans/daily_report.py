# -*- coding: utf-8 -*-
"""每日复盘计划 — 完整吸收 stock_review 全部逻辑

编排流程:
  1. 指数行情 (sina批量)
  2. 市场宽度: 涨跌家数 (eastmoney HTTP API + Cookie)
  3. 涨跌停统计 (akshare)
  4. 概念资金流 Top10 (collectors/em_concept.py)
  5. 持仓股行情: 价格+PE/PB/市值/振幅+5日20日K线+公告/研报/新闻
  6. 自选股行情 (同持仓)
  7. 宏观快照: 美债/美联储/黄金/原油/汇率

用法:
    from plans.daily_report import run, format_report
    data = run(verbose=True)
    html = render(data, "review_report")
"""

import sys
import os
import json
import time
import re
import random
import requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import load_config
from collectors.em_concept import fetch_concept_list

# ── 全局请求会话 ──
SESSION = requests.Session()
from requests.adapters import HTTPAdapter
_adapter = HTTPAdapter(max_retries=3, pool_connections=10, pool_maxsize=10)
SESSION.mount("https://", _adapter)
SESSION.mount("http://", _adapter)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"

_LAST_REQUEST_TIME = 0

def _auto_sleep(min_gap=1.0):
    global _LAST_REQUEST_TIME
    now = time.time()
    elapsed = now - _LAST_REQUEST_TIME
    if elapsed < min_gap:
        time.sleep(min_gap - elapsed)
    _LAST_REQUEST_TIME = time.time()


def safe_request(url, timeout=10, headers=None, max_retries=2, rate_limit=True):
    """带防抖重试的 HTTP 请求"""
    if headers is None:
        headers = {"User-Agent": UA}
    for attempt in range(max_retries + 1):
        if attempt > 0:
            wait_sec = random.randint(15, 30)
            print(f"  ⚠️ 请求失败，等待 {wait_sec} 秒后重试 ({attempt}/{max_retries})...", file=sys.stderr)
            time.sleep(wait_sec)
        if rate_limit:
            _auto_sleep(0.8)
        try:
            r = SESSION.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200 or r.content:
                return r.content
        except Exception as e:
            continue
    return None


def eastmoney_headers():
    config = load_config()
    cookie = config.get('eastmoney', {}).get('cookie', '')
    return {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/bk/", "Cookie": cookie}


# ── 股票代码前缀 ──

def get_sina_prefix(code):
    return "sh" if code.startswith("6") else "sz"


# ── 新浪行情 ──

def sina_fetch(codes):
    """批量新浪行情: codes=['sh000001','sz399001'] → {code: fields}"""
    code_list = ",".join(codes)
    url = f"https://hq.sinajs.cn/list={code_list}"
    raw = safe_request(url, timeout=10, headers={"Referer": "https://finance.sina.com.cn"}, rate_limit=False)
    if not raw:
        return {}
    try:
        text = raw.decode("gbk")
    except:
        text = raw.decode("utf-8", errors="replace")
    results = {}
    for line in text.strip().split("\n"):
        if "=" not in line or '"' not in line:
            continue
        var = line.split("=")[0]
        code = var.split("_")[-1]
        content = line.split('"')[1]
        if content:
            results[code] = content.split(",")
    return results


# ── 腾讯详情 (PE/PB/市值/振幅/量比) ──

def tencent_detail(code):
    prefix = get_sina_prefix(code)
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    raw = safe_request(url, timeout=6, rate_limit=False)
    if not raw:
        return {}
    try:
        text = raw.decode("gbk")
    except:
        text = raw.decode("utf-8", errors="replace")
    if "~" not in text:
        return {}
    parts = text.split("~")
    if len(parts) < 50:
        return {}
    return {
        "name": parts[1],
        "code": parts[2],
        "price": float(parts[3]) if parts[3] else 0,
        "prev_close": float(parts[4]) if parts[4] else 0,
        "open": float(parts[5]) if parts[5] else 0,
        "volume": float(parts[36]) if len(parts) > 36 and parts[36] else 0,
        "amount": float(parts[35].split("/")[2]) if len(parts) > 35 and "/" in parts[35] else 0,
        "pe": float(parts[52]) if len(parts) > 52 and parts[52] else None,
        "pb": float(parts[46]) if len(parts) > 46 and parts[46] else None,
        "total_mv": float(parts[45]) if len(parts) > 45 and parts[45] else None,
        "float_mv": float(parts[44]) if len(parts) > 44 and parts[44] else None,
        "amplitude": float(parts[43]) if len(parts) > 43 and parts[43] else 0,
        "volume_ratio": float(parts[49]) if len(parts) > 49 and parts[49] else 0,
        "change": float(parts[31]) if len(parts) > 31 and parts[31] else 0,
        "change_pct": float(parts[32]) if len(parts) > 32 and parts[32] else 0,
        "high": float(parts[33]) if len(parts) > 33 and parts[33] else 0,
        "low": float(parts[34]) if len(parts) > 34 and parts[34] else 0,
    }


# ── 腾讯K线 ──

def tencent_kline(code, days=30):
    prefix = get_sina_prefix(code)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{days},qfq"
    raw = safe_request(url, timeout=6, rate_limit=False)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except:
        return []
    stock_data = data.get("data", {}).get(f"{prefix}{code}", {})
    klines = stock_data.get("qfqday", stock_data.get("day", []))
    if not klines:
        for k, v in stock_data.items():
            if isinstance(v, list) and len(v) > 0:
                klines = v
                break
    return klines


def calc_multi_day_change(klines):
    """计算多日涨跌幅"""
    if not klines or len(klines) < 5:
        return {}
    closes = [float(k[2]) for k in klines]
    result = {}
    if len(closes) >= 5:
        result["chg_5d"] = round((closes[-1] - closes[-5]) / closes[-5] * 100, 2)
    if len(closes) >= 10:
        result["chg_10d"] = round((closes[-1] - closes[-10]) / closes[-10] * 100, 2)
    if len(closes) >= 20:
        result["chg_20d"] = round((closes[-1] - closes[-20]) / closes[-20] * 100, 2)
    return result


# ── 公告/研报/新闻 ──

def fetch_announcements(code, max_items=3):
    url = f"https://np-anotice-stock.eastmoney.com/api/security/ann?page_size={max_items}&page_index=1&ann_type=A&stock_list={code}"
    raw = safe_request(url, timeout=6, headers={
        "User-Agent": UA, "Referer": "https://data.eastmoney.com/"
    })
    if not raw:
        return []
    try:
        data = json.loads(raw)
        items = data.get("data", {}).get("list", [])
        result = []
        for item in items[:max_items]:
            title = item.get("title", "")
            if ":" in title:
                title = title.split(":", 1)[1]
            date = item.get("notice_date", "")[:10] if item.get("notice_date") else ""
            result.append({"title": title, "date": date})
        return result
    except:
        return []


def fetch_research_reports(code, max_items=3):
    url = f"https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_WEB_RESEARCHREPORTDETAIL&columns=ALL&filter=(SECURITY_CODE%3D%22{code}%22)&pageNumber=1&pageSize={max_items}&sortColumns=REPORT_DATE&sortTypes=-1&source=WEB&client=WEB"
    raw = safe_request(url, timeout=6, headers={
        "User-Agent": UA, "Referer": "https://data.eastmoney.com/"
    })
    if not raw:
        return []
    try:
        data = json.loads(raw)
        items = data.get("result", {}).get("data", [])
        if not items:
            return []
        result = []
        for item in items[:max_items]:
            result.append({
                "title": item.get("TITLE", "")[:60],
                "date": item.get("REPORT_DATE", "")[:10],
                "org": item.get("ORG_NAME", ""),
                "rating": item.get("RATING_NAME", ""),
            })
        return result
    except:
        return []


def fetch_stock_news(name, max_items=3):
    import urllib.parse
    param_str = json.dumps({
        "uid": "", "keyword": name, "type": ["cmsArticleWebOld"],
        "client": "web", "clientType": "web", "clientVersion": "curr",
        "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default",
            "pageIndex": 1, "pageSize": max_items, "preTag": "", "postTag": ""}}
    })
    url = f"https://search-api-web.eastmoney.com/search/jsonp?cb=jQuery&param={urllib.parse.quote(param_str)}"
    raw = safe_request(url, timeout=8, headers={
        "User-Agent": UA, "Referer": "https://so.eastmoney.com/",
    })
    if not raw:
        return []
    try:
        text = raw.decode("utf-8", errors="replace")
        start = text.find("({")
        end = text.rfind("})")
        if start >= 0 and end > start:
            text = text[start+1:end+1]
        data = json.loads(text)
        items = data.get("result", {}).get("cmsArticleWebOld", [])
        result = []
        for item in items[:max_items]:
            title = re.sub(r"</?em>", "", item.get("title", ""))
            result.append({"title": title[:80], "date": item.get("date", "")[:10],
                "media": item.get("mediaName", ""), "url": item.get("url", "")})
        return result
    except:
        return []


# ── 涨跌家数 (HTTP API) ──

def fetch_market_breadth():
    """获取涨跌家数（东财HTTP接口）及涨跌停家数（AKShare）"""
    result = {"up": 0, "down": 0, "flat": 0, "limit_up": 0, "limit_down": 0}

    # 涨跌家数
    for secid in ["1.000001", "0.399001"]:
        url = (f"https://push2.eastmoney.com/api/qt/ulist.np/get?"
               f"fltt=2&fields=f104,f105,f106,f107,f108&secids={secid}")
        raw = safe_request(url, timeout=10, headers=eastmoney_headers())
        if raw:
            try:
                data = json.loads(raw)
                items = data.get("data", {}).get("diff", [])
                if items:
                    i = items[0]
                    result["up"] += i.get("f104", 0) or 0
                    result["down"] += i.get("f105", 0) or 0
                    result["flat"] += i.get("f106", 0) or 0
                    result["limit_up"] += i.get("f107", 0) or 0
                    result["limit_down"] += i.get("f108", 0) or 0
            except:
                pass
        time.sleep(0.5)

    # 涨跌停 (akshare 更精确)
    today = datetime.now().strftime("%Y%m%d")
    try:
        import akshare as ak
        df_zt = ak.stock_zt_pool_em(date=today)
        if df_zt is not None and not df_zt.empty:
            result["limit_up"] = len(df_zt)
    except:
        pass
    try:
        import akshare as ak
        df_dt = ak.stock_zt_pool_dtgc_em(date=today)
        if df_dt is not None and not df_dt.empty:
            result["limit_down"] = len(df_dt)
    except:
        pass

    return result


# ── 宏观数据 ──

def fetch_fred_data():
    """从 FRED API 获取美国宏观数据"""
    result = {}
    for sid, name in [("DGS10", "us_10y_treasury"), ("FEDFUNDS", "fed_funds_rate")]:
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}&api_key=fd274b774f3863bfac60cc5a41227e63&file_type=json&sort_order=desc&limit=1"
        raw = safe_request(url, timeout=8, rate_limit=False)
        if raw:
            try:
                data = json.loads(raw)
                obs = data.get("observations", [])
                if obs:
                    result[name] = {"value": float(obs[0]["value"]), "date": obs[0]["date"]}
            except:
                pass
    return result


def fetch_commodities():
    """从新浪获取黄金、白银、原油价格"""
    raw = sina_fetch(["hf_GC", "hf_SI", "hf_CL"])
    result = {}
    for key, name in [("GC", "gold"), ("SI", "silver"), ("CL", "crude")]:
        row = raw.get(key)
        if row and len(row) > 3:
            price = float(row[0]) if row[0] else 0
            prev_close = float(row[2]) if len(row) > 2 and row[2] else price
            change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
            result[name] = {"price": price, "change_pct": change_pct,
                "name": row[13] if len(row) > 13 else ""}
    return result


# ── 个股详情 (含K线+公告+研报+新闻) ──

def fetch_single_stock(s, sina_data=None):
    """获取单只持仓的完整数据"""
    code = s["code"]
    stock = {"code": code, "name": s.get("name", ""), "note": s.get("note", ""),
             "cost": s.get("cost", 0), "shares": s.get("shares", 0)}

    # 腾讯详情
    detail = tencent_detail(code)
    if detail:
        stock.update({
            "name": stock["name"] or detail.get("name", ""),
            "price": detail.get("price", 0),
            "prev_close": detail.get("prev_close", 0),
            "open": detail.get("open", 0),
            "high": detail.get("high", 0),
            "low": detail.get("low", 0),
            "volume": detail.get("volume", 0),
            "amount": detail.get("amount", 0),
            "pe": detail.get("pe"),
            "pb": detail.get("pb"),
            "total_mv": detail.get("total_mv"),
            "float_mv": detail.get("float_mv"),
            "amplitude": detail.get("amplitude"),
            "volume_ratio": detail.get("volume_ratio"),
            "change": detail.get("change", 0),
            "change_pct": detail.get("change_pct", 0),
        })

    # 新浪日期/时间
    if sina_data:
        prefix = get_sina_prefix(code)
        row = sina_data.get(f"{prefix}{code}")
        if row and len(row) > 30:
            stock["date"] = row[30]
            stock["time"] = row[31]

    # K线 → 5日/20日涨跌
    klines = tencent_kline(code, days=30)
    if klines and len(klines) >= 5:
        stock.update(calc_multi_day_change(klines))

    # 公告/研报/新闻
    stock["announcements"] = fetch_announcements(code, max_items=3)
    stock["research_reports"] = fetch_research_reports(code, max_items=3)
    stock["news"] = fetch_stock_news(s.get("name", code), max_items=3)

    time.sleep(0.15)
    return stock


# ── 配置加载 ──

def _get_portfolio() -> list:
    config = load_config()
    portfolio = config.get('portfolio', [])
    if portfolio:
        return portfolio
    pf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'portfolio.json')
    if os.path.exists(pf_path):
        with open(pf_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def _get_indices() -> list:
    config = load_config()
    return config.get('indices', [
        {'code': 'sh000001', 'name': '上证指数'},
        {'code': 'sz399001', 'name': '深证成指'},
        {'code': 'sz399006', 'name': '创业板指'},
    ])


def _get_watchlist() -> list:
    wl_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'watchlist.json')
    if os.path.exists(wl_path):
        with open(wl_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


# ── 主流程 ──

def run(date=None, verbose=True):
    """执行每日复盘"""
    if not date:
        date = datetime.now().strftime("%Y%m%d")

    result = {'date': date, 'fetch_time': datetime.now().strftime("%Y-%m-%d %H:%M")}

    config = load_config()

    # 1. 指数行情 (新浪)
    if verbose:
        print("📊 采集指数行情...", file=sys.stderr)
    indices_cfg = _get_indices()
    index_codes = [i['code'] for i in indices_cfg]
    index_names = {i['code']: i['name'] for i in indices_cfg}
    index_raw = sina_fetch(index_codes)

    indices = []
    total_amount = 0
    for idx in indices_cfg:
        code = idx['code']
        row = index_raw.get(code)
        info = {"name": index_names.get(code, code), "code": code}
        if row and len(row) > 30:
            info["price"] = float(row[3])
            info["prev_close"] = float(row[2])
            info["open"] = float(row[1])
            info["high"] = float(row[4])
            info["low"] = float(row[5])
            info["amount"] = float(row[9])
            info["date"] = row[30]
            info["time"] = row[31]
            info["change"] = round(info["price"] - info["prev_close"], 2)
            info["change_pct"] = round(
                (info["price"] - info["prev_close"]) / info["prev_close"] * 100, 2
            )
            if code in ("sh000001", "sz399001"):
                total_amount += info["amount"]
        indices.append(info)
    result['indices'] = indices

    # 2. 市场宽度
    if verbose:
        print("📈 采集涨跌家数...", file=sys.stderr)
    try:
        result['breadth'] = fetch_market_breadth()
    except Exception as e:
        if verbose:
            print(f"  ⚠️ 涨跌家数异常: {e}", file=sys.stderr)
        result['breadth'] = {"up": 0, "down": 0, "flat": 0, "limit_up": 0, "limit_down": 0}

    # 3. 概念资金流 Top10
    if verbose:
        print("💰 采集概念资金流...", file=sys.stderr)
    try:
        concepts = fetch_concept_list(top_n=10)
        result['concepts'] = concepts
    except Exception as e:
        if verbose:
            print(f"  ⚠️ 概念资金流异常: {e}", file=sys.stderr)
        result['concepts'] = []

    time.sleep(0.5)

    # 4. 宏观数据
    if verbose:
        print("🌍 采集宏观数据...", file=sys.stderr)
    usd_cny = None
    forex_raw = sina_fetch(["fx_susdcnh", "USDCNY"])
    for key in ["susdcnh", "USDCNY"]:
        if forex_raw.get(key) and len(forex_raw[key]) > 3:
            usd_cny = float(forex_raw[key][3])
            break

    fred = fetch_fred_data()
    commodities = fetch_commodities()
    result['macro'] = {
        "us_treasury_10y": fred.get("us_10y_treasury", {}).get("value"),
        "us_treasury_10y_date": fred.get("us_10y_treasury", {}).get("date"),
        "fed_rate": fred.get("fed_funds_rate", {}).get("value"),
        "fed_rate_date": fred.get("fed_funds_rate", {}).get("date"),
        "usd_cny": usd_cny,
        "total_market_amount": round(total_amount / 1e8, 2),
        "gold": commodities.get("gold"),
        "silver": commodities.get("silver"),
        "crude": commodities.get("crude"),
    }

    # 5. 持仓个股 (完整数据)
    if verbose:
        print("💼 采集持仓行情...", file=sys.stderr)
    portfolio = _get_portfolio()
    if portfolio:
        pf_codes = [f"{get_sina_prefix(p['code'])}{p['code']}" for p in portfolio]
        sina_all = sina_fetch(pf_codes)
        result['portfolio'] = []
        for p in portfolio:
            stock = fetch_single_stock(p, sina_all)
            result['portfolio'].append(stock)
    else:
        result['portfolio'] = []

    # 6. 自选股行情
    if verbose:
        print("👀 采集自选股行情...", file=sys.stderr)
    watchlist = _get_watchlist()
    if watchlist:
        wl_codes = [f"{get_sina_prefix(w['code'])}{w['code']}" if isinstance(w, dict) else f"{get_sina_prefix(w)}{w}" for w in watchlist]
        wl_raw = sina_fetch(wl_codes)
        result['watchlist'] = []
        for w in watchlist:
            if isinstance(w, dict):
                code = w['code']
                name = w.get('name', code)
            else:
                code = w
                name = code
            stock = fetch_single_stock({"code": code, "name": name, "note": ""}, wl_raw)
            result['watchlist'].append(stock)
    else:
        result['watchlist'] = []

    if verbose:
        print("✅ 每日复盘完成", file=sys.stderr)

    return result


def format_report(data: dict) -> str:
    """格式化为文本报告"""
    lines = []
    sep = "=" * 50
    lines.append(sep)
    lines.append(f"  📋 每日复盘 — {data.get('fetch_time', data.get('date', ''))}")
    lines.append(sep)

    # 指数
    indices = data.get('indices', [])
    if indices:
        lines.append("\n【指数概览】")
        for idx in indices:
            pct = idx.get('change_pct', 0)
            arrow = "🔴" if pct < 0 else "🟢" if pct > 0 else "⚪"
            amount_yi = idx.get('amount', 0) / 1e8 if idx.get('amount') else 0
            lines.append(f"  {arrow} {idx['name']}: {idx['price']:.2f} ({pct:+.2f}%) 成交{amount_yi:.0f}亿")

    # 宏观
    macro = data.get('macro', {})
    if macro:
        lines.append("\n【宏观环境】")
        us10y = macro.get('us_treasury_10y')
        fed = macro.get('fed_rate')
        usd = macro.get('usd_cny')
        total_amt = macro.get('total_market_amount', 0)
        if us10y: lines.append(f"  10Y美债: {us10y}%")
        if fed: lines.append(f"  美联储利率: {fed}%")
        if usd: lines.append(f"  美元/人民币: {usd}")
        if total_amt: lines.append(f"  A股总成交额: {total_amt}亿")
        for k, name in [('gold', 'COMEX黄金'), ('silver', 'COMEX白银'), ('crude', 'WTI原油')]:
            c = macro.get(k)
            if c:
                lines.append(f"  {name}: {c['price']:.2f} ({c['change_pct']:+.2f}%)")

    # 市场宽度
    breadth = data.get('breadth', {})
    if breadth.get('up') or breadth.get('down'):
        lines.append(f"\n【市场宽度】")
        lines.append(f"  上涨: {breadth['up']}  下跌: {breadth['down']}  平盘: {breadth.get('flat', 0)}")
        lines.append(f"  涨停: {breadth.get('limit_up', 0)}  跌停: {breadth.get('limit_down', 0)}")

    # 概念资金流
    concepts = data.get('concepts', [])
    if concepts:
        lines.append(f"\n【概念资金流 Top10】")
        for i, c in enumerate(concepts, 1):
            inflow = c.get('net_inflow', 0) / 1e8 if c.get('net_inflow') else 0
            pct = c.get('change_pct', 0)
            lines.append(f"  {i:2d}. {c['name']:<8s} 涨跌{pct:+.2f}% 净流入{inflow:+.2f}亿")

    # 持仓
    portfolio = data.get('portfolio', [])
    if portfolio:
        lines.append(f"\n【持仓明细】")
        for p in portfolio:
            price = p.get('price', 0)
            pct = p.get('change_pct', 0)
            lines.append(f"  {p['name']}({p['code']}) ¥{price:.2f} {pct:+.2f}% PE={p.get('pe','--')} 持仓{p.get('shares',0)}股")

    lines.append(f"\n{sep}")
    return "\n".join(lines)
