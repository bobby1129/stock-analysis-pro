# -*- coding: utf-8 -*-
"""东方财富概念板块采集器

主链路: HTTP API + Cookie (fetch_concept_list + fetch_concept_stocks) — 稳定, 不触发滑块
辅助: fetch_concepts_batch (Playwright) — 仅F10等动态页面需要
Cookie: 从 config/config.yaml 读取, 过期时向用户索要

用法:
    from collectors.em_concept import fetch_concept_list, fetch_concept_stocks
    
    concepts = fetch_concept_list(top_n=10)
    for c in concepts:
        stocks = fetch_concept_stocks(c['bk_code'], name=c['name'], limit=100)
        time.sleep(1.0)  # 概念间间隔, 避免限流
"""

import re
import os
import json
import time
import requests
import yaml
from typing import Optional

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config')
_CONFIG_FILE = os.path.join(_CONFIG_DIR, 'config.yaml')
_CACHE_FILE = os.path.join(_DATA_DIR, 'concept_cache.json')

import socket
import urllib3.util.connection as _urllib3_conn

# 强制IPv4 — 东财push2的IPv6端点TLS握手成功但HTTP层返回Empty reply
# IPv4 (43.144.251.121) 稳定可用
_urllib3_conn.allowed_gai_family = lambda: socket.AF_INET


# ── 东财通用参数 ──
_UT = "8dec03ba335b81bf4ebdf7b29ec27d15"

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
    'Referer': 'https://quote.eastmoney.com/bk/',
}

_BASE_URL = 'https://push2.eastmoney.com/api/qt/clist/get'

# 请求间隔 (带Cookie, 控制频率)
_request_interval = 1.0
_last_request_time = 0


# ── Cookie 管理 ──

def _load_config() -> dict:
    """加载配置文件"""
    if os.path.exists(_CONFIG_FILE):
        with open(_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_config(config: dict):
    """保存配置文件"""
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_CONFIG_FILE, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)


def get_cookie() -> str:
    """从 config/config.yaml 读取东方财富Cookie"""
    config = _load_config()
    return config.get('eastmoney', {}).get('cookie', '')


def set_cookie(cookie: str):
    """保存Cookie到 config/config.yaml"""
    config = _load_config()
    if 'eastmoney' not in config:
        config['eastmoney'] = {}
    config['eastmoney']['cookie'] = cookie.strip()
    _save_config(config)
    print(f"[em_concept] Cookie已保存到 {_CONFIG_FILE}")


def _throttle():
    """请求限速"""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _request_interval:
        time.sleep(_request_interval - elapsed)
    _last_request_time = time.time()


# ── 滑块检测 (连续断连计数器) ──
_captcha_disconnect_count = 0
_captcha_alerted = False

def _alert_captcha(context: str, verbose: bool = True):
    """
    HTTP API路径的滑块检测:
    RemoteDisconnected连续出现 → 大概率触发滑块, 需手动验证
    
    东财对HTTP API的滑块拦截方式 = 直接TCP断开(Empty reply), 不返回验证页面
    """
    global _captcha_disconnect_count, _captcha_alerted
    _captcha_disconnect_count += 1
    if _captcha_disconnect_count >= 2 and not _captcha_alerted:
        _captcha_alerted = True
        print()
        print("=" * 60)
        print("⚠️  疑似触发东财滑块验证!")
        print(f"   连续断连 {_captcha_disconnect_count} 次 ({context})")
        print("   → 浏览器打开: https://data.eastmoney.com/bkzj/gn.html")
        print("   → 手动完成滑块验证")
        print("   → 验证后重试即可恢复")
        print("=" * 60)
        print()

def _reset_captcha_state():
    """请求成功后重置计数器"""
    global _captcha_disconnect_count, _captcha_alerted
    if _captcha_disconnect_count > 0:
        _captcha_disconnect_count = 0
        _captcha_alerted = False


def _jsonp_parse(text: str) -> Optional[dict]:
    """解析 JSONP 响应: jQuery...({...}) → dict"""
    match = re.search(r'\((.*)\)', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


def _make_params(fs: str, fields: str, pz: int = 50, pn: int = 1, fid: str = 'f62', po: int = 1) -> dict:
    """构造通用请求参数"""
    return {
        'cb': f'jQuery112306_{int(time.time()*1000)}',
        'fid': fid,
        'po': str(po),
        'pz': str(pz),
        'pn': str(pn),
        'np': '1',
        'fltt': '2',
        'invt': '2',
        'ut': _UT,
        'fs': fs,
        'fields': fields,
    }


# ── 概念板块过滤关键词 (唯一过滤点, 所有非行业/主题概念在此过滤) ──
FILTER_KEYWORDS = [
    # 持仓/机构类
    '两融', '融资融券', '证金', '社保', '基金重仓', '社保重仓',
    'QFII', '保险重仓', '券商重仓', '外资重仓', '信托重仓',
    # 业绩预告类
    '预盈', '预增', '业绩预升', '业绩预降', '预减', '扭亏',
    # 估值/价格类
    '破净', '高市净', '低价', '高价', '高市盈率', '低市盈率', '破发', '百元股',
    # 市值/规模/指数类
    '超大盘', '中盘', '小盘', '大盘', '央企50',
    '上证380', '深成500', '沪深300', '中证500', '中证1000',
    'MSCI中国', '央视50', '上证50', '上证180',
    # 股票特征类
    '新股', '次新', '含H', '含B', 'AB股', 'B股', 'ST', '摘帽', '创业', '科创',
    # 资本运作/交易类
    '股权激励', '整体上市', '重组', '高送转', '高送转预期',
    '员工持股', '参股新三板', '配股股', '举牌',
    '减持', '增持', '沪股通', '深股通',
    # 风格/因子/题材标签类
    '风格', '红利', '权重', '破增发', '超跌',
    '新高', '趋势', '反转', '题材',
    '昨日', '昨日连板', '昨日涨停',
    '科技风格', '大盘成长', '大盘价值', '中盘成长', '中盘价值',
    '小盘成长', '小盘价值', '质量成长', '低波动', '高股息',
    '动量因子', '价值因子',
    # 泛化标签
    '高商誉', '区域', '板块',
    # 指数/基金/宽基类
    '富时罗素', '标准普尔', 'HS300', '深证100',
    '东方财富热股', '价值股', '成长股',
    '道琼斯', '纳斯达克', '恒生', '日经',
]

REGIONS = [
    '北京', '上海', '深圳', '广东', '江苏', '浙江', '山东', '福建',
    '安徽', '四川', '湖北', '湖南', '西部', '东北', '长三角', '珠三角',
    '京津冀', '雄安', '海南', '重庆', '天津', '成渝', '特区', '海峡',
    '中部', '西北', '西南', '粤港澳', '自贸区',
]


def _should_filter(name: str) -> bool:
    """判断概念是否应该被过滤 (非行业/主题类)"""
    if any(kw in name for kw in FILTER_KEYWORDS):
        return True
    if len(name) < 2 or len(name) > 10:
        return True
    if any(r in name for r in REGIONS):
        return True
    return False


# ── 离线概念缓存 ──

def _load_cache() -> dict:
    """加载离线概念缓存 {bk_code: {name, stocks: [{symbol, name}, ...]}}"""
    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(cache: dict):
    """保存离线概念缓存"""
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _merge_stocks_to_cache(bk_code: str, name: str, stocks: list):
    """
    将新获取的成分股合并到离线缓存
    - 已有的股票保留
    - 新增的股票追加
    - 更新名称
    """
    cache = _load_cache()
    
    existing = cache.get(bk_code, {'name': name, 'stocks': []})
    existing_stocks = {s['symbol']: s for s in existing.get('stocks', [])}
    
    new_count = 0
    for s in stocks:
        sym = s.get('symbol', '')
        if sym and sym not in existing_stocks:
            existing_stocks[sym] = {
                'symbol': sym,
                'name': s.get('name', ''),
            }
            new_count += 1
        elif sym and sym in existing_stocks:
            # 更新名称 (可能改名)
            existing_stocks[sym]['name'] = s.get('name', '') or existing_stocks[sym].get('name', '')
    
    cache[bk_code] = {
        'name': name,
        'stocks': list(existing_stocks.values()),
    }
    
    if new_count > 0:
        print(f"  [缓存] {name} 新增{new_count}只成分股, 总计{len(existing_stocks)}只")
    
    _save_cache(cache)


def get_cached_stocks(bk_code: str) -> list:
    """从离线缓存获取成分股 (在线失败时的兜底)"""
    cache = _load_cache()
    info = cache.get(bk_code, {})
    return info.get('stocks', [])


# ── 公共API ──

def _jsonp_extract(text: str):
    """从JSONP或纯JSON文本中提取数据"""
    if not text:
        return None
    text = text.strip()
    if text.startswith('(') or (text[0].isalpha() and '(' in text[:50]):
        m = re.search(r'\((.*)\)', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_items_from_response(data: dict) -> list:
    """从push2 API响应中提取items列表"""
    if not data:
        return []
    if isinstance(data, dict) and 'data' in data:
        inner = data['data']
        if inner is None:
            return []
        if isinstance(inner, dict):
            return inner.get('diff', [])
        if isinstance(inner, list):
            return inner
    return []


# ── Playwright 批量获取 (一个浏览器会话完成全部请求) ──

async def _fetch_concepts_playwright(
    top_n: int = 10,
    fetch_stocks_for: list | None = None,
    stocks_limit: int = 100,
    verbose: bool = False,
    filter_fn=None,
) -> dict:
    """
    用Playwright获取概念列表 + 指定概念的成分股

    一个浏览器会话完成所有请求，Cookie由浏览器自动管理，不会被封IP。

    Args:
        top_n: 保留前N个概念 (过滤后)
        fetch_stocks_for: 需要拉成分股的概念 [{bk_code, name}, ...]，None=不拉
        stocks_limit: 每个概念拉多少只成分股
        verbose: 打印日志
        filter_fn: 过滤函数 (concepts) -> filtered_concepts
                  传入后自动对过滤结果拉成分股，无需手动指定fetch_stocks_for

    Returns:
        {
            'concepts': [...],
            'stocks_map': {bk_code: [...]},
            'filtered': [...],  # 仅当filter_fn存在时
        }
    """
    from playwright.async_api import async_playwright
    import time as _time

    concept_api_data = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        )

        # 注入Cookie到浏览器上下文 (让push2 API能返回完整数据)
        cookie_str = get_cookie()
        if cookie_str:
            cookies = []
            for part in cookie_str.split(';'):
                part = part.strip()
                if '=' in part:
                    name, value = part.split('=', 1)
                    cookies.append({
                        'name': name.strip(),
                        'value': value.strip(),
                        'domain': '.eastmoney.com',
                        'path': '/',
                    })
            if cookies:
                await context.add_cookies(cookies)
                if verbose:
                    print(f'  [Playwright] 已注入 {len(cookies)} 个Cookie')

        page = await context.new_page()

        # 拦截概念列表 API 响应 (新版 dataapi + 旧版 push2 兼容)
        async def on_response(response):
            url = response.url
            if response.status != 200:
                return
            is_list_api = ('dataapi/bkzj' in url and 'getbkzj' in url) or \
                          ('clist/get' in url and 'm:90' in url)
            if is_list_api:
                try:
                    body = await response.json()
                    concept_api_data['list'] = body
                except:
                    pass

        page.on('response', on_response)

        # ── 1. 加载概念资金流向页面，触发API请求 ──
        if verbose:
            print('  [Playwright] 加载概念板块页面...')
        try:
            await page.goto(
                'https://data.eastmoney.com/bkzj/gn.html',
                wait_until='domcontentloaded',
                timeout=30000,
            )
            # 等待概念列表API响应到达，而非networkidle
            try:
                await page.wait_for_event(
                    'response',
                    lambda r: ('dataapi/bkzj' in r.url and 'getbkzj' in r.url) or
                              ('clist/get' in r.url and 'm:90' in r.url),
                    timeout=10000,
                )
            except Exception:
                if verbose:
                    print('  [Playwright] 等待API响应超时，检查已拦截的数据...')
            await page.wait_for_timeout(2000)
        except Exception as e:
            if verbose:
                print(f'  [Playwright] 页面加载异常: {e}')

        # 从拦截的API响应解析概念列表
        list_items = _extract_items_from_response(concept_api_data.get('list', {}))

        concepts = []
        for item in list_items:
            name = item.get('f14', '')
            if _should_filter(name):
                continue

            bk_code = item.get('f12', '')
            leader_name = item.get('f140', '')
            leader_code_raw = item.get('f141', '')
            leader_market = item.get('f136', 0)

            if leader_code_raw:
                prefix = 'sh' if leader_market == 1 else 'sz'
                leader_sym = f'{prefix}{leader_code_raw}'
            else:
                leader_sym = ''

            concepts.append({
                'bk_code': bk_code,
                'name': name,
                'change_pct': item.get('f3', 0),
                'net_inflow': item.get('f62', 0),
                'up_count': item.get('f104', 0),
                'down_count': item.get('f105', 0),
                'leader': leader_name,
                'leader_code': leader_sym,
                'leader_pct': item.get('f136', 0) if isinstance(item.get('f136', 0), (int, float)) else 0,
            })

            if len(concepts) >= top_n * 3:  # 多拉一些，给后续过滤留余量
                break

        if verbose:
            print(f'  [Playwright] 概念列表: {len(concepts)} 个 (过滤后)')

        # ── 2. 确定要拉成分股的概念列表 ──
        stocks_to_fetch = []
        filtered_concepts = None
        
        if filter_fn:
            # 传了filter_fn: 自动过滤并对结果拉成分股
            filtered_concepts = filter_fn(concepts)
            if filtered_concepts:
                stocks_to_fetch = [{'bk_code': c['bk_code'], 'name': c['name']} for c in filtered_concepts]
                if verbose:
                    print(f'  [Playwright] 过滤后{len(stocks_to_fetch)}个概念, 拉成分股')
        elif fetch_stocks_for:
            # 手动指定模式
            stocks_to_fetch = fetch_stocks_for

        # ── 3. 拉成分股 (导航详情页 + response拦截, 不用route) ──
        stocks_map = {}
        if stocks_to_fetch:
            import asyncio as _aio
            for i, info in enumerate(stocks_to_fetch):
                bk_code = info['bk_code']
                name = info.get('name', bk_code)

                if verbose:
                    print(f'  [Playwright] 成分股 ({i+1}/{len(stocks_to_fetch)}): {name}...')

                if i > 0:
                    await _aio.sleep(3)

                detail_data = {}
                async def on_detail_response(response, code=bk_code):
                    url = response.url
                    if response.status != 200:
                        return
                    if 'clist/get' in url and (f'b:{code}' in url or f'b%3A{code}' in url):
                        try:
                            text = await response.text()
                            if text.startswith('jQuery'):
                                json_str = text[text.index('(') + 1:text.rindex(')')]
                                data = json.loads(json_str)
                            else:
                                data = json.loads(text)
                            detail_data['stocks'] = data
                        except:
                            pass

                page.on('response', on_detail_response)

                try:
                    await page.goto(
                        f'https://data.eastmoney.com/bkzj/{bk_code}.html',
                        wait_until='domcontentloaded',
                        timeout=15000,
                    )
                    await page.wait_for_timeout(3000)

                    # ── 滑块验证检测 ──
                    slider_detected = False
                    for frame in page.frames:
                        if 'captcha' in frame.url or 'slidervalid' in frame.url:
                            slider_detected = True
                            break
                    if slider_detected:
                        screenshot_path = '/tmp/stock-analysis-pro/cache/slider_captcha.png'
                        await page.screenshot(path=screenshot_path)
                        print(f'\n⚠️ 东财滑块验证触发！截图: {screenshot_path}')
                        print(f'请手动完成验证，等待中...')
                        # 等待滑块消失 (最多120秒)
                        for _wait in range(24):
                            await page.wait_for_timeout(5000)
                            still_blocked = False
                            for frame in page.frames:
                                if 'captcha' in frame.url or 'slidervalid' in frame.url:
                                    still_blocked = True
                                    break
                            if not still_blocked:
                                print(f'  ✅ 验证通过，继续...')
                                # 验证通过后重新加载页面拿数据
                                await page.goto(
                                    f'https://data.eastmoney.com/bkzj/{bk_code}.html',
                                    wait_until='domcontentloaded',
                                    timeout=15000,
                                )
                                await page.wait_for_timeout(3000)
                                break
                        else:
                            print(f'  ❌ 等待超时(120s)，跳过 {name}')

                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await page.wait_for_timeout(5000)

                    if 'stocks' in detail_data:
                        items = _extract_items_from_response(detail_data['stocks'])

                        stocks = []
                        for item in items:
                            code = item.get('f12', '')
                            market = item.get('f13', 0)
                            prefix = 'sh' if market == 1 else 'sz'
                            stocks.append({
                                'symbol': f'{prefix}{code}',
                                'code': code,
                                'market': market,
                                'name': item.get('f14', ''),
                                'price': item.get('f2', 0),
                                'flow_market_cap': item.get('f21', 0),
                                'change_pct': item.get('f3', 0),
                                'amount': item.get('f6', 0),
                                'turnover': item.get('f8', 0),
                            })

                        stocks_map[bk_code] = stocks

                        if verbose:
                            print(f'  [Playwright] {name}: {len(stocks)} 只')

                        if stocks and name:
                            _merge_stocks_to_cache(bk_code, name, stocks)
                    else:
                        if verbose:
                            print(f'  [Playwright] {name}: 未拦截到API')
                        cached = get_cached_stocks(bk_code)
                        if cached:
                            stocks_map[bk_code] = cached
                            if verbose:
                                print(f'  [Playwright] {name}: 使用离线缓存 {len(cached)} 只')

                except Exception as e:
                    if verbose:
                        print(f'  [Playwright] {name} 成分股失败: {e}')
                    cached = get_cached_stocks(bk_code)
                    if cached:
                        stocks_map[bk_code] = cached
                        if verbose:
                            print(f'  [Playwright] {name}: 使用离线缓存 {len(cached)} 只')
                finally:
                    page.remove_listener('response', on_detail_response)

        await browser.close()

    result = {
        'concepts': concepts,
        'stocks_map': stocks_map,
    }
    if filtered_concepts is not None:
        result['filtered'] = filtered_concepts
    return result


def fetch_concepts_batch(
    top_n: int = 60,
    fetch_stocks_for: list | None = None,
    stocks_limit: int = 100,
    verbose: bool = False,
    filter_fn = None,
) -> dict:
    """
    批量获取概念数据 (同步接口, 内部用Playwright)

    一个浏览器会话完成: 概念列表 + 可选的成分股

    Args:
        top_n: 拉取概念列表数量 (过滤前)
        fetch_stocks_for: 需要拉成分股的概念 [{bk_code, name}, ...]，None=不拉
        stocks_limit: 每概念成分股数量
        verbose: 日志
        filter_fn: 过滤函数 (concepts) -> filtered_concepts
                  传入后自动对过滤结果拉成分股

    Returns:
        {
            'concepts': [...],
            'stocks_map': {bk_code: [{symbol, name, ...}, ...]},
            'filtered': [...],  # 仅当filter_fn存在时
        }
    """
    import asyncio
    
    return asyncio.run(_fetch_concepts_playwright(
        top_n=top_n,
        fetch_stocks_for=fetch_stocks_for,
        stocks_limit=stocks_limit,
        verbose=verbose,
        filter_fn=filter_fn,
    ))


def fetch_concept_stocks(bk_code: str, name: str = '', limit: int = 100, verbose: bool = False) -> list:
    """
    获取概念成分股 (按涨幅排序, HTTP API + Cookie)

    成功后自动合并到离线缓存; 失败时从离线缓存兜底

    Returns:
        [
            {
                'symbol': 'sh688766',
                'code': '688766',
                'market': 1,
                'name': '普冉股份',
                'price': 45.67,
                'flow_market_cap': 12345678900,
                'change_pct': 3.45,
                'amount': 123456789,
                'turnover': 2.5,
            },
            ...
        ]
    """
    _throttle()

    cookie = get_cookie()
    if not cookie:
        cached = get_cached_stocks(bk_code)
        if cached:
            if verbose:
                print(f"  [离线] {bk_code} 使用缓存 {len(cached)} 只成分股")
            return cached
        return []

    headers = {**_HEADERS, 'Cookie': cookie}
    params = _make_params(
        fs=f'b:{bk_code}',
        fields='f2,f3,f4,f5,f6,f7,f8,f12,f13,f14,f15,f16,f17,f21',
        pz=limit,
        fid='f6',  # 按成交额排序 (非涨幅排序, 避免采样偏差导致分布失真)
    )

    try:
        resp = None
        for _attempt in range(2):
            try:
                resp = requests.get(_BASE_URL, params=params, headers=headers, timeout=15)
                break
            except requests.exceptions.ConnectionError as e:
                if _attempt == 0:
                    if verbose:
                        print(f"  [重试] {bk_code} 连接断开, 重试...")
                    _throttle()
                    continue
                _alert_captcha(f"成分股({bk_code})", verbose)
                raise
        if not resp or not resp.text or 'jQuery' not in resp.text:
            cached = get_cached_stocks(bk_code)
            if cached:
                if verbose:
                    print(f"  [离线兜底] {bk_code} 在线失败, 使用缓存 {len(cached)} 只")
                return cached
            return []

        data = _jsonp_parse(resp.text)
        if not data or not data.get('data'):
            cached = get_cached_stocks(bk_code)
            if cached:
                if verbose:
                    print(f"  [离线兜底] {bk_code} 解析失败, 使用缓存 {len(cached)} 只")
                return cached
            return []

        _reset_captcha_state()
        items = data['data'].get('diff', [])
        results = []

        for item in items:
            code = item.get('f12', '')
            market = item.get('f13', 0)
            prefix = 'sh' if market == 1 else 'sz'

            results.append({
                'symbol': f'{prefix}{code}',
                'code': code,
                'market': market,
                'name': item.get('f14', ''),
                'price': item.get('f2', 0),
                'flow_market_cap': item.get('f21', 0),
                'change_pct': item.get('f3', 0),
                'amount': item.get('f6', 0),
                'turnover': item.get('f8', 0),
            })

        if verbose:
            print(f"  [在线] {bk_code} 获取到 {len(results)} 只成分股")

        if results and name:
            _merge_stocks_to_cache(bk_code, name, results)

        return results

    except Exception as e:
        print(f"[em_concept] 获取成分股失败({bk_code}): {e}")
        cached = get_cached_stocks(bk_code)
        if cached:
            if verbose:
                print(f"  [离线兜底] {bk_code} 异常, 使用缓存 {len(cached)} 只")
            return cached
        return []


def fetch_concept_list(top_n: int = 30, verbose: bool = False) -> list:
    """
    获取东方财富概念板块列表 (按资金流入排序, 过滤非行业概念, 保留top_n个)
    
    Returns:
        [
            {
                'bk_code': 'BK1137',
                'name': '存储芯片',
                'change_pct': 4.25,
                'net_inflow': 1234567890,
                'up_count': 35,
                'down_count': 15,
                'leader': '兆易创新',
                'leader_code': 'sh603986',
                'leader_pct': 8.5,
            },
            ...
        ]
    """
    _throttle()
    
    cookie = get_cookie()
    if not cookie:
        print("[em_concept] ❌ 未配置东方财富Cookie!")
        print("  → 步骤1: cp config/config.example.yaml config/config.yaml")
        print("  → 步骤2: 编辑 config/config.yaml，填入 eastmoney.cookie")
        print("  → Cookie获取: 浏览器打开 https://quote.eastmoney.com/bk/ → F12 → Network → 复制Cookie")
        print("  ⚠️ 概念板块功能需要Cookie才能工作，将降级使用离线缓存")
        return []
    
    headers = {**_HEADERS, 'Cookie': cookie}
    
    # 多拉一些, 过滤后取top_n
    fetch_count = top_n * 3
    params = _make_params(
        fs='m:90+t:3',
        fields='f2,f3,f12,f13,f14,f21,f62,f66,f69,f72,f75,f78,f81,f84,f87,f104,f105,f124,f128,f136,f140,f141',
        pz=fetch_count,
        fid='f62',  # 按资金流入排序
        po=1,       # 降序
    )
    
    try:
        resp = None
        for _attempt in range(2):
            try:
                resp = requests.get(_BASE_URL, params=params, headers=headers, timeout=15)
                break
            except requests.exceptions.ConnectionError as e:
                if _attempt == 0:
                    if verbose:
                        print(f"  [重试] 概念列表连接断开, 重试...")
                    _throttle()
                    continue
                _alert_captcha("概念列表", verbose)
                raise
        if not resp or not resp.text or 'jQuery' not in resp.text:
            print("[em_concept] ⚠️ Cookie可能已过期或无效")
            print("  → 请重新获取: 浏览器打开 https://quote.eastmoney.com/bk/ → F12 → Network → 复制新Cookie")
            print("  → 更新配置: 编辑 config/config.yaml，替换 eastmoney.cookie 的值")
            print("  ⚠️ 将降级使用离线缓存（数据可能不是最新的）")
            return []
            
        data = _jsonp_parse(resp.text)
        if not data or not data.get('data'):
            if verbose:
                print(f"[em_concept] 解析失败: {resp.text[:200]}")
            return []
        
        items = data['data'].get('diff', [])
        results = []

        for item in items:
            name = item.get('f14', '')
            if _should_filter(name):
                continue

            bk_code = item.get('f12', '')

            # 领涨股
            leader_name = item.get('f140', '')
            leader_code_raw = item.get('f141', '')
            leader_market = item.get('f136', 0)

            if leader_code_raw:
                prefix = 'sh' if leader_market == 1 else 'sz'
                leader_sym = f'{prefix}{leader_code_raw}'
            else:
                leader_sym = ''

            results.append({
                'bk_code': bk_code,
                'name': name,
                'change_pct': item.get('f3', 0),
                'net_inflow': item.get('f62', 0),
                'up_count': item.get('f104', 0),
                'down_count': item.get('f105', 0),
                'leader': leader_name,
                'leader_code': leader_sym,
                'leader_pct': item.get('f136', 0) if isinstance(item.get('f136', 0), (int, float)) else 0,
            })

            if len(results) >= top_n:
                break

        _reset_captcha_state()
        if verbose:
            print(f"[em_concept] 资金流入排序, 过滤后保留 {len(results)} 个概念 (拉取{fetch_count}个)")

        return results
        
    except Exception as e:
        print(f"[em_concept] 获取概念列表失败: {e}")
        return []
