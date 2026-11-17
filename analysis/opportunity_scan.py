# -*- coding: utf-8 -*-
"""新机会扫描 — OPPORTUNITY_SCAN_DESIGN.md (2026-11-18确认)

短期信号(导火索) + 长期价值(目标) 双维度, 对未持仓机会票做LLM逻辑梳理。

入池 (每日上限15只):
  A. 新进TOP50 (优先, ≤10只): 当日成交额TOP50且近5个交易日未进榜
     (口径同 generate_new_top50.py, cache_dates日期指针); 金融权重票不硬剔, 交LLM判skip
  B. 点火首放低位 (补足至15): ignition_data事件卡片内 vol_tag=首放 且 p60≤50,
     按事件top1往前取, 同事件内p60升序; 与A去重

判定 (每票一次轻量LLM调用, 标题级催化不抓正文):
  catalyst(催化归因) / signal_quality(短期信号) / value_rating+value_logic(长期价值)
  / action(watchlist进自选·observe观察·skip放弃)

- LLM: 复用 llm_interpret._call_llm_json (qwen3.6-flash/temp=0/config读key)
- 缓存: cache/review_history/opportunity_cache_YYYYMMDD.json (输入hash不变0调用)
- 降级: 单票失败输出纯数据行; 整体失败 result['opportunity_degraded']=True, 不阻塞
- 红线: 成交额只用缓存/腾讯实时, K线备源只吃close/volume (AGENTS.md)
"""

import os
import sys
import json
import time
import hashlib
from datetime import datetime

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)
_DC = os.path.join(_BASE, "scripts", "daily_content")
if _DC not in sys.path:
    sys.path.insert(0, _DC)

CACHE_DIR = os.path.join(_BASE, "cache", "review_history")
IGNITION_DIR = os.path.join(_BASE, "output", "daily_content")

MAX_TOTAL = 15       # 每日入池上限
MAX_NEW_TOP50 = 10   # A类上限
P60_LOW = 50         # B类低位阈值 (2026-11-18决议: 宽口径)
MAX_NEWS = 4         # 每票新闻标题数
MAX_ANN = 4          # 每票公告标题数

_ACTIONS = ("watchlist", "observe", "skip")
_SIGNALS = ("strong", "medium", "weak")
_VALUES = ("high", "medium", "low", "unclear")


# ── A类: 新进TOP50 ──

def _load_amount_cache(date_yyyymmdd):
    """读当日成交额缓存(抖音管线15:35落盘), 返回top50列表或None"""
    path = os.path.join(_BASE, "cache", "daily_content",
                        f"stock_amount_cache_{date_yyyymmdd}.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data[:50] if isinstance(data, list) else None
    except (OSError, json.JSONDecodeError):
        return None


def _collect_new_top50(date_yyyymmdd, verbose=True):
    """新进TOP50: 当日top50 - 近5个缓存日top50并集 (口径同generate_new_top50)"""
    today = _load_amount_cache(date_yyyymmdd)
    if not today:
        if verbose:
            print(f"  ⚠️ 无{date_yyyymmdd}成交额缓存, A类跳过")
        return []
    try:
        from cache_dates import load_cache_dates
        all_dates = [d for d in load_cache_dates() if d < date_yyyymmdd][-5:]
    except Exception as e:
        if verbose:
            print(f"  ⚠️ 缓存日期指针读取失败({e}), A类跳过")
        return []
    prev_union = set()
    for d in all_dates:
        prev = _load_amount_cache(d)
        if prev:
            prev_union |= set(i["code"] for i in prev)
    out = []
    for item in today:
        if item["code"] not in prev_union:
            out.append({
                "source": "new_top50",
                "code": item["code"],
                "name": item.get("name", ""),
                "amount": item.get("amount"),   # 元, 来自缓存(新浪口径), 严禁K线volume冒充
            })
    if verbose:
        print(f"  📥 A类新进TOP50: {len(out)}只 (对比近{len(all_dates)}日)")
    return out[:MAX_NEW_TOP50]


# ── B类: 点火首放低位 ──

def _collect_ignition_burst(date_yyyymmdd, exclude_codes, verbose=True):
    """点火事件卡片内首放低位股, 事件top1往前取, 同事件p60升序, 补足名额"""
    path = os.path.join(IGNITION_DIR, f"ignition_data_{date_yyyymmdd}.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        if verbose:
            print(f"  ⚠️ 无{date_yyyymmdd}点火数据, B类跳过")
        return []
    cands = []
    for rank, ev in enumerate(data.get("events") or []):
        for s in ev.get("members") or []:
            if s.get("vol_tag") != "首放":
                continue
            p60 = s.get("p60")
            if p60 is None or p60 > P60_LOW:
                continue
            if s.get("code") in exclude_codes:
                continue
            cands.append({
                "source": "ignition_burst",
                "event_rank": rank + 1,
                "event_name": ev.get("name", ""),
                "code": s.get("code"),
                "name": s.get("name", ""),
                "price": s.get("price"),
                "change_pct": s.get("change_pct"),
                "amount_w": s.get("amount_w"),       # 万元(点火雷达已采集)
                "turnover": s.get("turnover"),
                "volume_ratio": s.get("volume_ratio"),
                "p60": p60,
                "p250": s.get("p250"),
                "shape": s.get("shape", ""),
                "business": s.get("business", ""),
                "concepts": (s.get("concepts_clean") or s.get("concepts") or [])[:5],
                "is_limit_up": s.get("is_limit_up", False),
                "lianban": s.get("lianban", 1),
            })
    cands.sort(key=lambda c: (c["event_rank"], c["p60"]))
    if verbose:
        print(f"  📥 B类点火首放低位(p60≤{P60_LOW}): 候选{len(cands)}只")
    return cands


# ── 富化 ──

def _batch_tencent(codes):
    """腾讯批量实时: 涨幅/量比/换手/PE/PB/市值。字段索引已验证
    (generate_new_top50.fetch_tencent_extras: 38换手/49量比; daily_report.tencent_detail: 32涨幅/45总市值/46PB/52PE)"""
    out = {}
    if not codes:
        return out
    import requests
    syms = []
    for c in codes:
        prefix = "sh" if c.startswith(("6", "9", "5")) else "sz"
        syms.append(prefix + c)
    for i in range(0, len(syms), 30):
        try:
            r = requests.get("https://qt.gtimg.cn/q=" + ",".join(syms[i:i + 30]), timeout=10)
            r.encoding = "gbk"
            for line in r.text.strip().split(";"):
                line = line.strip()
                if not line or "=" not in line:
                    continue
                parts = line.split("=", 1)[1].strip('"').split("~")
                if len(parts) < 53:
                    continue

                def _f(idx):
                    try:
                        return float(parts[idx]) if parts[idx] else None
                    except (ValueError, IndexError):
                        return None

                out[parts[2]] = {
                    "change_pct": _f(32), "turnover": _f(38),
                    "total_mv": _f(45), "pb": _f(46),
                    "volume_ratio": _f(49), "pe": _f(52),
                }
        except Exception:
            continue
        time.sleep(0.3)
    return out


def _enrich(cands, date_yyyymmdd, verbose=True):
    """补齐行情/位置分位/主营。B类点火数据已富化的字段不重复采集。"""
    import requests
    codes = [c["code"] for c in cands]
    tx = _batch_tencent(codes)
    for c in cands:
        t = tx.get(c["code"], {})
        for k in ("change_pct", "turnover", "total_mv", "pb", "volume_ratio", "pe"):
            if c.get(k) is None and t.get(k) is not None:
                c[k] = t[k]

    # p60/p250: A类需现算(腾讯250日K线, 只吃close, 备源红线合规)
    need_kline = [c for c in cands if c.get("p60") is None]
    if need_kline:
        try:
            from plans.industry_screener import tencent_kline, calc_price_percentile
        except Exception:
            tencent_kline = calc_price_percentile = None
        if tencent_kline:
            for c in need_kline:
                try:
                    klines = tencent_kline(c["code"], days=260)
                    price = None
                    if klines:
                        price = float(klines[-1][2])
                    c["p60"] = calc_price_percentile(klines, price, 60)
                    c["p250"] = calc_price_percentile(klines, price, 250)
                except Exception:
                    pass
                time.sleep(0.3)

    # 主营: B类自带, A类走持久缓存(TTL180天)
    a_codes = [c["code"] for c in cands if not c.get("business")]
    if a_codes:
        try:
            from collectors.ths_stock_business import get_or_fetch_business
            biz = get_or_fetch_business(a_codes, verbose=False)
            for c in cands:
                if not c.get("business"):
                    c["business"] = biz.get(c["code"], "")
        except Exception as e:
            if verbose:
                print(f"  ⚠️ 主营采集失败(降级): {e}")

    # 公告/新闻标题 (东财, 同daily_report链路)
    try:
        from plans.daily_report import fetch_announcements, fetch_stock_news
    except Exception:
        fetch_announcements = fetch_stock_news = None
    if fetch_announcements:
        for c in cands:
            try:
                c["announcements"] = fetch_announcements(c["code"], max_items=MAX_ANN)
            except Exception:
                c["announcements"] = []
            try:
                c["news"] = fetch_stock_news(c["name"], max_items=MAX_NEWS)
            except Exception:
                c["news"] = []
            time.sleep(0.5)
    return cands


# ── LLM判定 ──

_JUDGE_TMPL = '''你是A股机会研究助手。一只未持仓的票今天出现异动信号, 请梳理其逻辑: 短期信号是导火索, 最终目标是找到长期值得投资的票。

【股票】{name}({code})
【信号来源】{source_desc}
【行情快照】涨幅{change_pct}% | 换手{turnover}% | 量比{volume_ratio} | 60日位置分位{p60} | 250日位置分位{p250} | PE {pe} | PB {pb} | 总市值{total_mv}亿
【主营业务】{business}
【概念标签】{concepts}
【今日公告标题】
{announcements}
【近期新闻标题】
{news}

请输出:
1. catalyst: 催化归因。type三选一: announcement(公告驱动)/news(新闻驱动)/none(无明显消息, 纯资金行为); summary一句话(≤40字)说明为什么今天放量
2. signal_quality: 短期信号质量 strong/medium/weak。考量: 放量位置(p60低+首放更好)、是否一字板买不进、涨幅是否已透支、巨量绿柱风险、大盘放量日权重票自然进榜属弱信号
3. value_rating: 长期投资价值 high/medium/low/unclear。考量: 行业空间与景气度、主营竞争地位、估值(PE/PB)合理性、市值体量。仅凭标题信息无法判断时给unclear, 不要编造
4. value_logic: 长期逻辑一句话(≤50字), value_rating为high/medium时必填, 其他可空
5. action: watchlist(短期信号+长期价值双好, 建议加入自选跟踪)/observe(单边好, 继续观察)/skip(双弱或纯炒作无长期价值, 放弃)。规则: signal_quality≥medium且value_rating≥medium→watchlist; 单边好→observe; 其余→skip
6. reason: 建议理由一句话(≤40字)

严格输出JSON对象, 无其他文字:
{{"catalyst":{{"type":"none","summary":"..."}},"signal_quality":"medium","value_rating":"medium","value_logic":"...","action":"observe","reason":"..."}}'''


def _fmt_num(v, suffix=""):
    if v is None:
        return "—"
    try:
        return f"{float(v):.1f}{suffix}"
    except (TypeError, ValueError):
        return "—"


def _build_prompt(c):
    if c["source"] == "new_top50":
        amt = c.get("amount")
        src = f"新进成交额TOP50 (成交额{_fmt_num((amt or 0)/1e8)}亿, 近5日首次进榜)"
    else:
        src = (f"点火雷达TOP{c.get('event_rank')}事件「{c.get('event_name')}」内首放股 "
               f"(首次放量, 形态: {c.get('shape') or '—'}"
               f"{', 涨停' if c.get('is_limit_up') else ''}"
               f"{', 连板' + str(c.get('lianban')) if (c.get('lianban') or 1) > 1 else ''})")
    ann = "\n".join(f'- [{a.get("date")}] {a.get("title")}'
                    for a in (c.get("announcements") or [])) or "(无)"
    news = "\n".join(f'- [{n.get("date")}] {n.get("title")} ({n.get("media", "")})'
                     for n in (c.get("news") or [])) or "(无)"
    return _JUDGE_TMPL.format(
        name=c.get("name", ""), code=c.get("code", ""),
        source_desc=src,
        change_pct=_fmt_num(c.get("change_pct")),
        turnover=_fmt_num(c.get("turnover")),
        volume_ratio=_fmt_num(c.get("volume_ratio")),
        p60=_fmt_num(c.get("p60")), p250=_fmt_num(c.get("p250")),
        pe=_fmt_num(c.get("pe")), pb=_fmt_num(c.get("pb")),
        total_mv=_fmt_num(c.get("total_mv")),
        business=(c.get("business") or "(未知)")[:150],
        concepts="、".join(c.get("concepts") or []) or "(无)",
        announcements=ann, news=news,
    )


def _cache_path(date_yyyymmdd):
    return os.path.join(CACHE_DIR, f"opportunity_cache_{date_yyyymmdd}.json")


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


def _judge_one(c, cache, verbose=True):
    """单票LLM判定, 带缓存。失败返回None(降级纯数据行)。"""
    from analysis.llm_interpret import _call_llm_json
    prompt = _build_prompt(c)
    ih = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:16]
    code = c["code"]
    cached = cache.get(code)
    if cached and cached.get("input_hash") == ih:
        if verbose:
            print(f"  🔭 {c.get('name')}: 缓存命中 [{cached['judge'].get('action')}]")
        return cached["judge"]
    try:
        obj = _call_llm_json(prompt, max_tokens=800)
    except Exception as e:
        if verbose:
            print(f"  ⚠️ {c.get('name')} LLM判定失败(降级纯数据): {e}")
        return None
    cat = obj.get("catalyst")
    if not isinstance(cat, dict):
        cat = {}
    judge = {
        "catalyst": {
            "type": cat.get("type") if cat.get("type") in ("announcement", "news", "none") else "none",
            "summary": str(cat.get("summary", ""))[:80],
        },
        "signal_quality": obj.get("signal_quality") if obj.get("signal_quality") in _SIGNALS else "weak",
        "value_rating": obj.get("value_rating") if obj.get("value_rating") in _VALUES else "unclear",
        "value_logic": str(obj.get("value_logic", ""))[:100],
        "action": obj.get("action") if obj.get("action") in _ACTIONS else "skip",
        "reason": str(obj.get("reason", ""))[:80],
    }
    # action规则兜底校验 (设计§四: 双好→watchlist)
    if judge["action"] == "watchlist" and not (
            judge["signal_quality"] in ("strong", "medium")
            and judge["value_rating"] in ("high", "medium")):
        judge["action"] = "observe"
    cache[code] = {"input_hash": ih, "judge": judge}
    _save_cache(c.get("_date"), cache)
    if verbose:
        print(f"  🔭 {c.get('name')}: [{judge['action']}] 信号{judge['signal_quality']}/"
              f"价值{judge['value_rating']} — {judge['reason']}")
    return judge


# ── 主入口 ──

def collect_candidates(date_yyyymmdd, verbose=True):
    """入池: A类新进TOP50(≤10) + B类点火首放低位(补足15)"""
    a = _collect_new_top50(date_yyyymmdd, verbose=verbose)
    a_codes = set(c["code"] for c in a)
    b = _collect_ignition_burst(date_yyyymmdd, a_codes, verbose=verbose)
    b = b[: max(0, MAX_TOTAL - len(a))]
    cands = a + b
    if verbose:
        print(f"  🔭 机会池合计: {len(cands)}只 (A类{len(a)} + B类{len(b)})")
    return cands


def attach_opportunity(result, verbose=True):
    """daily_report.run() 7f步挂载。result['opportunity_scan'] = {date, candidates}, 每票带judge。
    任何异常降级不抛出。"""
    date = result.get("date") or datetime.now().strftime("%Y%m%d")
    try:
        cands = collect_candidates(date, verbose=verbose)
        if not cands:
            result["opportunity_scan"] = {"date": date, "candidates": []}
            return result
        if verbose:
            print(f"  🔭 富化行情/主营/公告新闻…")
        _enrich(cands, date, verbose=verbose)
        cache = _load_cache(date)
        degraded = False
        for c in cands:
            c["_date"] = date
            judge = _judge_one(c, cache, verbose=verbose)
            if judge is None:
                degraded = True
            c["judge"] = judge
            c.pop("_date", None)
        # 排序: watchlist > observe > skip, 同级A类优先
        order = {"watchlist": 0, "observe": 1, "skip": 2}
        cands.sort(key=lambda c: (
            order.get((c.get("judge") or {}).get("action"), 3),
            0 if c["source"] == "new_top50" else 1,
            -(c.get("amount") or 0),
        ))
        result["opportunity_scan"] = {"date": date, "candidates": cands}
        if degraded:
            result["opportunity_degraded"] = True
    except Exception as e:
        if verbose:
            print(f"  ⚠️ 机会扫描失败(不影响报告): {e}", file=sys.stderr)
        result["opportunity_degraded"] = True
    return result


if __name__ == "__main__":
    # 手动验证: python -m analysis.opportunity_scan 20261117
    date_arg = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y%m%d")
    res = {"date": date_arg}
    attach_opportunity(res, verbose=True)
    scan = res.get("opportunity_scan", {})
    print(f"\n=== {date_arg} 机会扫描: {len(scan.get('candidates', []))}只 ===")
    for c in scan.get("candidates", []):
        j = c.get("judge") or {}
        cat = j.get("catalyst") or {}
        print(f"[{j.get('action', '?')}] {c['name']}({c['code']}) {c['source']} "
              f"信号={j.get('signal_quality')} 价值={j.get('value_rating')} "
              f"催化={cat.get('type') if isinstance(cat, dict) else cat}")
        print(f"    理由: {j.get('reason', '')} | 价值逻辑: {j.get('value_logic', '')}")
