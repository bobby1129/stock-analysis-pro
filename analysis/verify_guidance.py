# -*- coding: utf-8 -*-
"""昨日研判验证 + 指引断言化 — REVIEW_UPGRADE_DESIGN.md §五.9/10 (S5, F4)

两个能力(共用 llm_interpret 的 LLM 基础函数):
1. generate_assertions(result): 将当日规则引擎指引(指数advice+情绪数据)用LLM改写成
   3-5条"次日可验证断言"，供明日验证闭环。result['assertions_today'] → 落盘 guidance.assertions。
2. verify_previous(result): 读取前一交易日落盘的 assertions + stock_tips，
   对照今日实际数据(指数/宽度/成交额/概念/个股涨跌)由LLM逐条判 hit/miss/unclear，
   输出 result['verification'] → 落盘 verification 字段；命中率从历史文件滚动统计(近5/20日)。

- 缓存: cache/review_history/verify_cache_YYYYMMDD.json，同日重跑输入hash不变不重复调LLM。
- 降级: 任何失败 result['verification']=None / 断言为空，不阻塞报告。
- 持仓「短线操作提示」为规则输出原文落盘(S2已做)，验证时LLM对照次日该股实际走势判✓✗。
"""

import os
import json
import hashlib
from datetime import datetime

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_BASE, "cache", "review_history")

_VERDICT_OK = ("hit", "miss", "unclear")


# ── 缓存 ──

def _cache_path(date_yyyymmdd):
    return os.path.join(CACHE_DIR, f"verify_cache_{date_yyyymmdd}.json")


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


# ── 1. 指引断言化 ──

_ASSERT_TMPL = '''你是A股复盘助手。下面是今日({date})复盘的规则引擎输出和市场数据。请把它改写成3-5条**明日可验证的断言**，用于次日对照实际行情判对错。

规则引擎指数指引(打分-100~+100, advice):
{market_view}

今日市场数据:
{market_data}

要求:
1. 每条断言必须是可以用明日公开数据客观验证的具体陈述，如"上证指数明日收涨(震荡偏强)"/"AI算力方向资金延续净流入"/"两市成交额维持1.5万亿以上"/"涨停家数回升至50家以上"。
2. 断言来源于上面的规则输出和数据，不得凭空捏造方向；模糊到无法验证的话(如"注意风险")不要。
3. 每条≤30字，3-5条。

严格输出JSON数组, 无其他文字:
["断言1","断言2","断言3"]'''


def _market_view_text(result):
    lines = []
    for idx in result.get("indices") or []:
        ti = (idx.get("technical_indicators") or {}).get("short_term")
        if ti:
            lines.append(f"- {idx.get('name')} {idx.get('code')}: {ti.get('score'):+d}分 → {ti.get('advice')}")
    return "\n".join(lines) or "(无)"


def _market_data_text(result):
    b = result.get("breadth") or {}
    m = result.get("macro") or {}
    sc = result.get("sentiment_cycle") or {}
    idx_lines = []
    for idx in result.get("indices") or []:
        pct = idx.get("change_pct")
        if pct is not None:
            idx_lines.append(f"{idx.get('name')} {pct:+.2f}%")
    concepts = [f"{c.get('name')}({c.get('net', 0):+.1f}亿)"
                for c in (result.get("concepts_fund") or [])[:5]]
    parts = [
        "指数: " + ", ".join(idx_lines),
        f"涨跌家数: 涨{b.get('up')}/跌{b.get('down')}, 涨停{b.get('limit_up')}/跌停{b.get('limit_down')}, 最高连板{b.get('max_lianban')}",
        f"两市成交额: {m.get('total_market_amount')}亿",
        f"情绪周期: {sc.get('phase', '未知')}(热度{sc.get('score', '?')}/100)",
        "主力净流入TOP5概念: " + ", ".join(concepts),
    ]
    return "\n".join(p for p in parts if p)


def generate_assertions(result, verbose=True):
    """当日指引→3-5条可验证断言, 写 result['assertions_today']。失败降级空列表。"""
    from analysis.llm_interpret import _call_llm_json
    date = result.get("date") or datetime.now().strftime("%Y%m%d")
    result["assertions_today"] = []
    mv = _market_view_text(result)
    if mv == "(无)":
        return result
    prompt = _ASSERT_TMPL.format(
        date=f"{date[:4]}-{date[4:6]}-{date[6:8]}",
        market_view=mv, market_data=_market_data_text(result))
    ih = _hash(prompt)
    cache = _load_cache(date)
    try:
        if cache.get("assertions", {}).get("input_hash") == ih:
            arr = cache["assertions"]["data"]
            if verbose:
                print(f"  ✅ 断言生成: 缓存命中 {len(arr)}条")
        else:
            arr = _call_llm_json(prompt, max_tokens=800)
            if not isinstance(arr, list):
                arr = []
            arr = [str(a).strip()[:60] for a in arr if str(a).strip()][:5]
            cache["assertions"] = {"input_hash": ih, "data": arr}
            _save_cache(date, cache)
            if verbose:
                print(f"  ✅ 断言生成: {len(arr)}条 → {'; '.join(arr)}")
        result["assertions_today"] = arr
    except Exception as e:
        if verbose:
            print(f"  ⚠️ 断言生成失败(降级跳过): {e}")
    return result


# ── 2. 昨日研判验证 ──

_VERIFY_TMPL = '''你是A股复盘助手。下面是前一交易日({prev_date})复盘给出的研判断言和持仓短线提示，以及今日({today})的实际市场数据。逐条对照验证。

昨日断言(i=序号):
{assertions}

昨日持仓短线提示(code=股票代码):
{tips}

今日实际数据:
{actual}

个股今日实际涨跌:
{stock_actual}

判定标准:
- hit(✓): 实际走势与断言/提示方向一致
- miss(✗): 实际走势与断言/提示方向相反
- unclear(无法验证): 数据不足以判断，或断言含糊
- 提示判定: "偏多/可持仓加仓"→今日上涨hit、下跌miss; "偏空/减仓离场"→今日下跌hit(提示规避了风险)、上涨miss; "中性观望"→涨跌幅±1%内hit, ±1%~3%判unclear, 超过±3%判miss(该给方向而未给)。
- actual字段: 一句话(≤40字)说明实际走势依据(引用具体数字)。

严格输出JSON对象, 无其他文字:
{{"asserts":[{{"i":1,"verdict":"hit","actual":"..."}}],"tips":[{{"code":"603893","verdict":"miss","actual":"..."}}]}}'''


def _load_previous(date_yyyymmdd):
    """前一交易日落盘记录(有assertions或stock_tips才返回)。"""
    from analysis.review_history import load_recent
    for r in reversed(load_recent(6, before=date_yyyymmdd)):
        g = r.get("guidance") or {}
        if g.get("assertions") or g.get("stock_tips"):
            return r
    return None


def _stock_actual_text(result, codes):
    lines = []
    for p in result.get("portfolio") or []:
        if p.get("code") in codes:
            lines.append(f"- {p.get('name')} {p.get('code')}: 今日{p.get('change_pct'):+.2f}% (收{p.get('price')})"
                         if p.get("change_pct") is not None else
                         f"- {p.get('name')} {p.get('code')}: 今日数据缺失")
    return "\n".join(lines) or "(今日无对应个股数据)"


def _hit_rates(date_yyyymmdd, current):
    """近5/20日滚动命中率: 扫历史verification字段 + 今日current。返回{d5:{hit,total},d20:{...}}"""
    from analysis.review_history import load_recent
    rows = []
    for r in load_recent(20, before=date_yyyymmdd):
        v = r.get("verification")
        if v:
            rows.append(v)
    rows.append(current)  # 今日验证结果计入
    rows = rows[-20:]

    def _rate(rs):
        hit = total = 0
        for v in rs:
            for row in (v.get("rows") or []) + (v.get("tip_rows") or []):
                if row.get("verdict") in ("hit", "miss"):
                    total += 1
                    hit += row["verdict"] == "hit"
        return {"hit": hit, "total": total,
                "pct": round(hit / total * 100) if total else None}

    return {"d5": _rate(rows[-5:]), "d20": _rate(rows)}


def verify_previous(result, verbose=True):
    """验证前一交易日断言+提示, 写 result['verification']。无历史/失败降级None。"""
    from analysis.llm_interpret import _call_llm_json
    date = result.get("date") or datetime.now().strftime("%Y%m%d")
    result["verification"] = None
    prev = _load_previous(date)
    if not prev:
        if verbose:
            print("  ℹ️ 无昨日研判记录, 跳过验证")
        return result
    prev_date = prev.get("date", "?")
    g = prev.get("guidance") or {}
    assertions = g.get("assertions") or []
    tips = g.get("stock_tips") or {}

    a_lines = [f"{i+1}. {a}" for i, a in enumerate(assertions)] or ["(昨日无断言)"]
    t_lines = [f"- {code} {t.get('name')}: {t.get('score'):+d}分 → {t.get('advice')}"
               for code, t in tips.items()] or ["(昨日无提示)"]
    prompt = _VERIFY_TMPL.format(
        prev_date=prev_date, today=f"{date[:4]}-{date[4:6]}-{date[6:8]}",
        assertions="\n".join(a_lines), tips="\n".join(t_lines),
        actual=_market_data_text(result),
        stock_actual=_stock_actual_text(result, set(tips.keys())))
    ih = _hash(prompt)
    cache = _load_cache(date)
    try:
        if cache.get("verify", {}).get("input_hash") == ih:
            obj = cache["verify"]["data"]
            if verbose:
                print(f"  ✅ 昨日研判验证: 缓存命中 ({prev_date})")
        else:
            obj = _call_llm_json(prompt, max_tokens=2500)
            cache["verify"] = {"input_hash": ih, "data": obj}
            _save_cache(date, cache)
    except Exception as e:
        if verbose:
            print(f"  ⚠️ 研判验证失败(降级跳过): {e}")
        return result

    # 组装行(断言)
    vmap = {o.get("i"): o for o in (obj.get("asserts") or []) if isinstance(o.get("i"), int)}
    rows = []
    for i, a in enumerate(assertions):
        o = vmap.get(i + 1) or {}
        v = o.get("verdict") if o.get("verdict") in _VERDICT_OK else "unclear"
        rows.append({"text": a, "verdict": v, "actual": str(o.get("actual", ""))[:80]})
    # 组装行(个股提示)
    tmap = {str(o.get("code")): o for o in (obj.get("tips") or [])}
    tip_rows = []
    for code, t in tips.items():
        o = tmap.get(str(code)) or {}
        v = o.get("verdict") if o.get("verdict") in _VERDICT_OK else "unclear"
        tip_rows.append({"code": code, "name": t.get("name", code),
                         "advice": t.get("advice", ""), "verdict": v,
                         "actual": str(o.get("actual", ""))[:80]})

    verification = {"prev_date": prev_date, "rows": rows, "tip_rows": tip_rows}
    verification["hit_rate"] = _hit_rates(date, verification)
    result["verification"] = verification
    if verbose:
        nhit = sum(1 for r in rows + tip_rows if r["verdict"] == "hit")
        nmiss = sum(1 for r in rows + tip_rows if r["verdict"] == "miss")
        print(f"  ✅ 昨日研判验证({prev_date}): ✓{nhit} ✗{nmiss} 共{len(rows)+len(tip_rows)}条")
    return result
