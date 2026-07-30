# -*- coding: utf-8 -*-
"""概念板块采集器 — 新浪源为主"""
import requests
import json
import time

FILTER_KEYWORDS = [
    '昨日', '两融', '融资融券', '证金', '社保', '预盈', '预增', '破净',
    '股权激励', '新股', '次新', '含H', '含B', 'AB股', '基金重仓',
    '社保重仓', 'QFII', '保险重仓', '券商重仓', '外资重仓', '信托重仓',
    '央企50', '上证380', '深成500', '沪深300', '中证500', '中证1000',
    'MSCI中国', '央视50', '上证50', '上证180', '业绩预升', '业绩预降', '高送转',
    '整体上市', '重组', '超大盘', '中盘', '小盘', '创业', '科创', 'ST',
    '摘帽', '高市净', '低价', '高价', '高市盈率', '低市盈率', '破发',
    '高商誉', '减持', '增持', '员工持股', '高送转预期', '参股新三板',
    '沪股通', '深股通', '区域', '板块', '概念', '产业', '行业',
    '新能源', '节能环保', '低碳', '稀缺', '涉矿'
]

_HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': 'http://finance.sina.com.cn'}


def _is_float(s):
    try:
        float(s)
        return True
    except:
        return False


def concept_stocks(node_code, num=30, sort='changepercent', asc=False):
    """
    获取概念成分股 (按涨跌幅排序, 默认降序)
    node_code: 新浪概念代码, 如 gn_hwqc
    返回: list of dict
    """
    url = (
        f'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
        f'Market_Center.getHQNodeData?page=1&num={num}&sort={sort}'
        f'&asc={1 if asc else 0}&node={node_code}&symbol=&_s_r_a=auto'
    )
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        if resp.text.startswith('['):
            return json.loads(resp.text)
        return []
    except Exception as e:
        print(f"成分股获取失败({node_code}): {e}")
        return []


def concept_leader_kline(symbol, datalen=60):
    """
    获取龙头股/个股日K线 (新浪源)
    symbol: 如 sz002976, sh603893
    返回: list of dict [{day, open, high, low, close, volume}, ...]
    """
    url = (
        f'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
        f'CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={datalen}'
    )
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        if resp.text.strip() and resp.text.strip() != 'null' and resp.text.startswith('['):
            return json.loads(resp.text)
        return []
    except Exception as e:
        print(f"K线获取失败({symbol}): {e}")
        return []


# ── K线缓存 (当日有效) ──
_kline_cache = {}  # {symbol: [{day, close, volume}, ...]}


def batch_klines(symbols: list, datalen=30, delay=0.15, verbose=False, max_workers=10) -> dict:
    """
    批量获取日K线，带内存缓存去重 + 并发加速
    symbols: list of symbol strings (e.g. ['sz300068', 'sh603893'])
    返回: {symbol: [{day, close, volume}, ...]} 只保留close和volume节省带宽
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}
    new_symbols = [s for s in symbols if s not in _kline_cache]

    if verbose and new_symbols:
        print(f"    K线缓存: {len(symbols) - len(new_symbols)}只命中, {len(new_symbols)}只待拉取")

    if new_symbols:
        def _fetch_one(sym):
            klines = concept_leader_kline(sym, datalen=datalen)
            return sym, klines

        done_count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_fetch_one, sym): sym for sym in new_symbols}
            for fut in as_completed(futures):
                sym, klines = fut.result()
                if klines:
                    _kline_cache[sym] = [{'day': k['day'], 'open': float(k['open']), 'high': float(k['high']), 'low': float(k['low']), 'close': float(k['close']), 'volume': float(k['volume'])} for k in klines]
                else:
                    _kline_cache[sym] = []
                done_count += 1
                if verbose and done_count % 20 == 0:
                    print(f"    K线进度: {done_count}/{len(new_symbols)}")

    # 返回结果
    for sym in symbols:
        results[sym] = _kline_cache.get(sym, [])

    return results


def clear_kline_cache():
    """清空K线缓存"""
    _kline_cache.clear()


# 概念名称 → 扩展搜索关键词映射
_NEWS_KEYWORDS = {
    '风电': ['风电', '风力', '风能', '海上风电', '风机'],
    '锂电池': ['锂电', '电池', '储能', '磷酸铁锂', '碳酸锂'],
    '光伏': ['光伏', '太阳能', '硅片', '组件', '逆变器'],
    '半导体': ['半导体', '芯片', '晶圆', '封测', '光刻'],
    '人工智能': ['人工智能', 'AI', '大模型', '算力', '机器人'],
    '汽车': ['汽车', '新能源车', '电动车', '智能驾驶', '自动驾驶'],
    '医药': ['医药', '药品', '集采', '创新药', '生物制品'],
    '军工': ['军工', '国防', '航天', '航空', '导弹'],
    '白酒': ['白酒', '酱香', '浓香', '酒类'],
    '房地产': ['房地产', '楼市', '房企', '保交楼'],
}


def concept_news(keyword: str, max_items: int = 5) -> list:
    """
    东方财富搜索API — 按概念关键词搜索新闻
    keyword: 概念名称
    返回: list of {title, date, media, summary, url}
    """
    import urllib.parse

    encoded = urllib.parse.quote(keyword)
    url = (
        f'https://search-api-web.eastmoney.com/search/jsonp?cb=jQuery&param='
        f'%7B%22uid%22%3A%22%22%2C%22keyword%22%3A%22{encoded}%22%2C'
        f'%22type%22%3A%5B%22cmsArticleWebOld%22%5D%2C%22client%22%3A%22web%22%2C'
        f'%22clientType%22%3A%22web%22%2C%22clientVersion%22%3A%22curr%22%2C'
        f'%22param%22%3A%7B%22cmsArticleWebOld%22%3A%7B%22searchScope%22%3A%22default%22%2C'
        f'%22sort%22%3A%22default%22%2C%22pageIndex%22%3A1%2C%22pageSize%22%3A{max_items}%2C'
        f'%22preTag%22%3A%22%22%2C%22postTag%22%3A%22%22%7D%7D%7D'
    )
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        text = resp.text
        if text.startswith('jQuery('):
            text = text[7:-1]
        data = json.loads(text)
        articles = data.get('result', {}).get('cmsArticleWebOld', [])
        results = []
        for a in articles:
            title = a.get('title', '').replace('<em>', '').replace('</em>', '')
            content = a.get('content', '').replace('<em>', '').replace('</em>', '')[:150]
            results.append({
                'title': title,
                'date': a.get('date', ''),
                'media': a.get('mediaName', ''),
                'summary': content,
            })
        return results
    except Exception as e:
        print(f"新闻获取失败({keyword}): {e}")
        return []


def concept_trend_analysis(name, code):
    """旧接口保留，已弃用"""
    return {'status': 'unknown', 'reason': 'K线数据源暂不可用'}
