# -*- coding: utf-8 -*-
"""极端行情特别模式 — REVIEW_UPGRADE_DESIGN.md §五.4 (S6, F5)

触发判断(规则引擎) → 触发才执行:
1. 归因: Google News RSS(走proxy)检索当日宏观/政策关键词 → LLM 2-3句"今天为什么"
2. 结构拆解: 涨跌停分布、领涨/领跌板块(复用概念TOP数据)、权重vs题材(指数分化)
3. 历史对照: 情绪库相似日(load_similar_days)之后1/5日指数表现;
   库不足(<2条)时用上证/创业板日K找历史相似涨跌幅日(**只用close**, 红线: K线volume严禁当成交额)
4. 持仓应对提示: LLM基于thesis+当日行情, 注明"仅供参考不构成决策"

- 触发阈值: 上证或创业板≥±2%; 上涨家数<1000或>4000; 跌停>30或涨停>150; 成交额较20日均值偏离>±30%
- 缓存: cache/review_history/extreme_cache_YYYYMMDD.json (LLM/RSS结果, 输入hash不变不重调)
- 降级: 任何子项失败只降级该子项(None), 整体失败 result['extreme']保持未触发占位, 不阻塞报告
- 输出: result['extreme'] = {triggered, triggers[], analysis:{why, structure, history, holdings_hint}} → 落盘
"""

import os
import re
import json
import time
import hashlib
from datetime import datetime

import requests

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_BASE, "cache", "review_history")

_PROXIES = {"http": "http://127.0.0.1:10809", "https": "http://127.0.0.1:10809"}

# 触发阈值(DESIGN §五.4)
_IDX_PCT = 2.0          # 上证/创业板涨跌幅 ≥±2%
_UP_LOW, _UP_HIGH = 1000, 4000
_LD_HIGH, _LU_HIGH = 30, 150
_AMT_DEV = 0.30         # 成交额较20日均值偏离 >±30%


# ── 缓存 ──

def _cache_path(date_yyyymmdd):
    return os.path.join(CACHE_DIR, f"extreme_cache_{date_yyyymmdd}.json")

def _load_cache(date_yyyymmdd):
    try:
        with open(_cache_path(date_yyyymmdd), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}

def _save_cache(date_yyyymmdd, cache):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(date_yyyymmdd)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)

def _hash(payload):
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:16]


def _cached_llm_json(date_yyyymmdd, key, prompt, max_tokens=2000):
    """带当日缓存的LLM JSON调用(共用llm_interpret基础)。"""
    from analysis.llm_interpret import _call_llm_json
    ih = _hash(prompt)
    cache = _load_cache(date_yyyymmdd)
    if cache.get(key, {}).get("input_hash") == ih:
        return cache[key]["data"]
    obj = _call_llm_json(prompt, max_tokens=max_tokens)
    cache[key] = {"input_hash": ih, "data": obj}
    _save_cache(date_yyyymmdd, cache)
    return obj


# ── 1. 触发判断(纯规则, 无网络) ──

def check_triggers(result) -> list:
    """返回触发原因列表(空=未触发)。数据缺失的项跳过不误报。"""
    triggers = []
    idx_map = {i.get("code"): i for i in result.get("indices") or []}
    for code, name in (("sh000001", "上证指数"), ("sz399006", "创业板指")):
        pct = (idx_map.get(code) or {}).get("change_pct")
        if pct is not None and abs(pct) >= _IDX_PCT:
            triggers.append(f"{name} {pct:+.2f}% (≥±{_IDX_PCT:.0f}%)")
    b = result.get("breadth") or {}
    up, ld, lu = b.get("up_count", b.get("up")), b.get("limit_down"), b.get("limit_up")
    if up is not None and up < _UP_LOW:
        triggers.append(f"上涨家数 {up} < {_UP_LOW}")
    elif up is not None and up > _UP_HIGH:
        triggers.append(f"上涨家数 {up} > {_UP_HIGH}")
    if ld is not None and ld > _LD_HIGH:
        triggers.append(f"跌停 {ld}家 > {_LD_HIGH}")
    if lu is not None and lu > _LU_HIGH:
        triggers.append(f"涨停 {lu}家 > {_LU_HIGH}")
    # 成交额偏离: result.macro无此字段, 现算(与落盘层同口径, 历史不足返回None跳过)
    dev = (result.get("macro") or {}).get("amount_vs_ma20")
    if dev is None:
        try:
            from analysis.review_history import _calc_amount_vs_ma20
            dev = _calc_amount_vs_ma20((result.get("macro") or {}).get("total_market_amount"),
                                       result.get("date") or datetime.now().strftime("%Y%m%d"))
        except Exception:
            dev = None
    if dev is not None and abs(dev) > _AMT_DEV:
        triggers.append(f"成交额较20日均值偏离 {dev*100:+.0f}% (>±30%)")
    return triggers


# ── 2. RSS归因 ──

def _rss_titles(query, limit=6):
    """Google News RSS 当日检索(走proxy), 同generate_ignition模式。失败返回[]。"""
    from urllib.parse import quote as _quote
    url = (f'https://news.google.com/rss/search?q={_quote(query)}+when:1d'
           f'&hl=zh-CN&gl=CN&ceid=CN:zh-Hans')
    try:
        r = requests.get(url, proxies=_PROXIES, timeout=10,
                         headers={'User-Agent': 'Mozilla/5.0'})
        titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', r.text)
        if not titles:
            titles = re.findall(r'<title>(.*?)</title>', r.text)
        items = []
        for t in titles:
            ts = t.strip()
            if ts in ('Google 新闻', 'Google News') or ts == query or 'when:1d' in ts or ts.startswith('"'):
                continue
            t2 = re.sub(r'\s*-\s*[^-]+$', '', ts).strip()
            if t2:
                items.append(t2)
            if len(items) >= limit:
                break
        return items
    except Exception:
        return []


_WHY_TMPL = '''你是A股复盘助手。今日({date})市场触发极端行情模式，触发原因: {triggers}。

今日市场数据:
{market_data}

当日新闻标题(Google News检索):
{news}

请用2-3句中文概括"今天市场为什么这样走"(归因: 宏观/政策/资金/外围/事件驱动)，只依据上面的数据和新闻标题，不得编造具体事件。如果新闻标题不足以归因，就基于市场数据描述结构特征(如普跌/分化/缩量)。

严格输出JSON对象, 无其他文字:
{{"why": "……(2-3句)"}}'''


def _market_data_text(result):
    b = result.get("breadth") or {}
    m = result.get("macro") or {}
    idx_lines = []
    for idx in result.get("indices") or []:
        pct = idx.get("change_pct")
        if pct is not None:
            idx_lines.append(f"{idx.get('name')} {pct:+.2f}%")
    parts = [
        "指数: " + ", ".join(idx_lines),
        f"涨跌家数: 涨{b.get('up', b.get('up_count'))}/跌{b.get('down', b.get('down_count'))}, "
        f"涨停{b.get('limit_up')}/跌停{b.get('limit_down')}, 最高连板{b.get('max_lianban')}",
        f"两市成交额: {m.get('total_market_amount')}亿",
    ]
    return "\n".join(parts)


def _why(date_yyyymmdd, triggers, result, verbose=False):
    direction = "大跌" if any("-" in t and "%" in t for t in triggers) else "大涨"
    queries = [f"A股 {direction}", "A股 央行 政策", "股市 今日"]
    news = []
    for q in queries:
        ts = _rss_titles(q, 5)
        news.extend(t for t in ts if t not in news)
        time.sleep(0.3)
    news = news[:14]
    if verbose:
        print(f"  📰 RSS归因检索: {len(news)}条标题")
    prompt = _WHY_TMPL.format(
        date=f"{date_yyyymmdd[:4]}-{date_yyyymmdd[4:6]}-{date_yyyymmdd[6:8]}",
        triggers="; ".join(triggers), market_data=_market_data_text(result),
        news="\n".join(f"- {t}" for t in news) or "(检索失败, 无新闻)")
    obj = _cached_llm_json(date_yyyymmdd, "why", prompt, max_tokens=600)
    why = str((obj or {}).get("why", "")).strip()
    return {"why": why[:300], "news": news[:8]} if why else None


# ── 3. 结构拆解(纯规则) ──

def _structure(result):
    b = result.get("breadth") or {}
    idx_map = {i.get("code"): i for i in result.get("indices") or []}
    sh = (idx_map.get("sh000001") or {}).get("change_pct")
    cy = (idx_map.get("sz399006") or {}).get("change_pct")
    divergence = None
    if sh is not None and cy is not None:
        gap = cy - sh
        if abs(gap) >= 1.0:
            divergence = ("题材/成长显著弱于权重" if gap < 0 else "题材/成长显著强于权重") + \
                         f" (创业板-上证 {gap:+.2f}pct)"
        else:
            divergence = f"权重与题材同步 (创业板-上证 {gap:+.2f}pct)"
    gainers = [{"name": c.get("name"), "pct": c.get("change_pct"), "net": c.get("net")}
               for c in (result.get("concepts_change") or [])[:5]]
    losers = [{"name": c.get("name"), "pct": c.get("change_pct"), "net": c.get("net")}
              for c in (result.get("concepts_decline") or [])[:5]]
    return {
        "limit_up": b.get("limit_up"), "limit_down": b.get("limit_down"),
        "up": b.get("up", b.get("up_count")), "down": b.get("down", b.get("down_count")),
        "max_lianban": b.get("max_lianban"),
        "divergence": divergence,
        "top_gainers": gainers, "top_losers": losers,
    }


# ── 4. 历史对照 ──

def _history_from_library(date_yyyymmdd, up_count, amount_dev):
    """情绪库相似日(S2 load_similar_days) + 其后1/5日上证表现(从后续落盘文件取)。"""
    from analysis.review_history import load_similar_days, load_recent, load
    similar = load_similar_days(up_count, amount_dev, exclude_date=date_yyyymmdd)
    all_recs = {r.get("date", "").replace("-", ""): r for r in load_recent(0)}
    dates_sorted = sorted(all_recs.keys())
    out = []
    for s in similar[:6]:
        d = s.get("date", "").replace("-", "")
        if d not in all_recs:
            continue
        try:
            i = dates_sorted.index(d)
        except ValueError:
            continue
        base = ((all_recs[d].get("sentiment", {}).get("indices") or {})
                .get("sh000001") or {}).get("close")
        row = {"date": s.get("date"), "up_count": s.get("up_count"),
               "sh_pct": s.get("sh_pct"), "next1": None, "next5": None}
        if base:
            for key, off in (("next1", 1), ("next5", 5)):
                if i + off < len(dates_sorted):
                    nxt = ((all_recs[dates_sorted[i + off]].get("sentiment", {}).get("indices") or {})
                           .get("sh000001") or {}).get("close")
                    if nxt:
                        row[key] = round((nxt - base) / base * 100, 2)
        out.append(row)
    return out


def _history_from_kline(target_pct, code="sh000001", days=1000):
    """库不足时兜底: 指数日K找历史相似形态日 (S8, 2026-11-03升级)。

    旧版为单日涨跌幅±1pct匹配(丢失位置/路径信息, 且有前视/自我匹配缺陷),
    现委托 analysis/similar_pattern.find_similar_pattern:
    近5日收益率序列欧氏距离 + 60日位置分位过滤(差>30排除) + 相似日去重叠。
    红线: 只用close, 严禁碰volume当成交额。
    target_pct 参数保留(调用方兼容), 匹配本身不再依赖它;
    最近邻距离>4 时加 weak=True(近4年无高相似形态日, 展示层需标注)。
    """
    from plans.daily_report import _fetch_index_kline
    from analysis.similar_pattern import find_similar_pattern
    klines = _fetch_index_kline(code, days=days)
    if not klines or len(klines) < 30:
        return None
    r = find_similar_pattern(klines, target_idx=len(klines) - 1)
    if r:
        r["code"] = code
        # 弱相似标注: 所有匹配距离都>4 → 近4年无高相似形态
        if r["matches"] and min(m["dist"] for m in r["matches"]) > 4:
            r["weak"] = True
    return r


def _history(date_yyyymmdd, result, verbose=False):
    b = result.get("breadth") or {}
    up = b.get("up", b.get("up_count")) or 0
    dev = None
    try:
        from analysis.review_history import _calc_amount_vs_ma20
        dev = _calc_amount_vs_ma20((result.get("macro") or {}).get("total_market_amount"),
                                   date_yyyymmdd)
    except Exception:
        pass
    lib = _history_from_library(date_yyyymmdd, up, dev) if up else []
    if len(lib) >= 2:
        return {"source": "library", "days": lib}
    # 库不足 → 日K兜底(找与今日上证涨跌幅相似的历史日)
    idx_map = {i.get("code"): i for i in result.get("indices") or []}
    sh_pct = (idx_map.get("sh000001") or {}).get("change_pct")
    if sh_pct is None or abs(sh_pct) < 0.5:
        return {"source": "library", "days": lib} if lib else None
    kl = _history_from_kline(sh_pct)
    if verbose:
        n = len(kl["matches"]) if kl else 0
        print(f"  📚 历史对照: 情绪库{len(lib)}条(不足), 日K兜底{n}条相似日")
    return kl or ({"source": "library", "days": lib} if lib else None)


# ── 5. 持仓应对提示(LLM) ──

_HINT_TMPL = '''你是A股复盘助手。今日({date})市场触发极端行情: {triggers}。
归因: {why}

持仓个股(thesis摘要+今日表现):
{stocks}

请针对极端行情给出持仓应对提示:
1. overall: 1-2句总体仓位/节奏建议(结合极端行情历史规律, 如恐慌杀跌不追杀、放量分化减仓强势股等)
2. per_stock: 每票一句话({codes}), 结合该股thesis逻辑与今日表现, 说清"拿住/减仓/观察什么信号"
3. 只依据给定信息, 不编造数据; 语言直接可操作

严格输出JSON对象, 无其他文字:
{{"overall": "……", "per_stock": {{"600000": "……"}}}}'''


def _holdings_hint(date_yyyymmdd, triggers, why_text, result, verbose=False):
    stocks = result.get("portfolio") or []
    if not stocks:
        return None
    lines, codes = [], []
    for p in stocks:
        code = p.get("code")
        if not code:
            continue
        codes.append(code)
        thesis = (p.get("thesis") or "").strip().replace("\n", " ")[:120]
        pct = p.get("change_pct")
        pct_s = f"{pct:+.2f}%" if pct is not None else "数据缺失"
        lines.append(f"- {p.get('name')} {code}: 今日{pct_s}; thesis: {thesis or '(未设置)'}")
    prompt = _HINT_TMPL.format(
        date=f"{date_yyyymmdd[:4]}-{date_yyyymmdd[4:6]}-{date_yyyymmdd[6:8]}",
        triggers="; ".join(triggers), why=why_text or "(归因不可用)",
        stocks="\n".join(lines), codes="/".join(codes))
    try:
        obj = _cached_llm_json(date_yyyymmdd, "hint", prompt, max_tokens=1500)
    except Exception as e:
        if verbose:
            print(f"  ⚠️ 持仓应对提示LLM失败(降级跳过): {e}")
        return None
    if not isinstance(obj, dict):
        return None
    name_map = {p.get("code"): p.get("name", "") for p in stocks}
    per = obj.get("per_stock") or {}
    per_clean = {f"{name_map.get(str(k), '')} {k}".strip(): str(v)[:100]
                 for k, v in per.items() if str(k) in codes}
    return {"overall": str(obj.get("overall", ""))[:200], "per_stock": per_clean,
            "disclaimer": "仅供参考，不构成投资决策"}


# ── 主入口 ──

def attach_extreme(result, verbose=True):
    """触发判断→专区数据挂载 result['extreme']。未触发/失败均不阻塞。"""
    date_yyyymmdd = result.get("date") or datetime.now().strftime("%Y%m%d")
    triggers = check_triggers(result)
    if not triggers:
        result["extreme"] = {"triggered": False, "triggers": [], "analysis": None}
        return result
    if verbose:
        print(f"🌪 极端行情触发: {'; '.join(triggers)}")
    analysis = {}
    # 归因(RSS+LLM)
    try:
        w = _why(date_yyyymmdd, triggers, result, verbose=verbose)
        if w:
            analysis["why"] = w["why"]
            analysis["news"] = w["news"]
    except Exception as e:
        if verbose:
            print(f"  ⚠️ 归因失败(降级跳过): {e}")
    # 结构拆解(纯规则, 不会失败)
    analysis["structure"] = _structure(result)
    # 历史对照
    try:
        analysis["history"] = _history(date_yyyymmdd, result, verbose=verbose)
    except Exception as e:
        if verbose:
            print(f"  ⚠️ 历史对照失败(降级跳过): {e}")
    # 持仓应对
    analysis["holdings_hint"] = _holdings_hint(
        date_yyyymmdd, triggers, analysis.get("why"), result, verbose=verbose)
    result["extreme"] = {"triggered": True, "triggers": triggers, "analysis": analysis}
    return result
