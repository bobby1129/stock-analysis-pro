# -*- coding: utf-8 -*-
"""每日复盘落盘层 — REVIEW_UPGRADE_DESIGN.md §三

每交易日一个文件 cache/review_history/YYYYMMDD.json，供 F3情绪时序 / F4研判验证 / F5极端行情对照 共用。
- save_from_result(data): review 流水线末尾调用，从 run() 结果提取字段落盘。
- load(date) / load_recent(n) / load_similar_days(...): 读取容错——文件缺失/损坏返回空，不抛异常。
- 写入原子化: 先写 .tmp 再 rename，避免中途崩溃留下半截JSON。
- 同日重跑覆盖（以最新一次为准）。
"""

import os
import json
import glob
from datetime import datetime
from typing import Optional

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_DIR = os.path.join(_BASE, "cache", "review_history")


def _path(date_yyyymmdd: str) -> str:
    return os.path.join(HISTORY_DIR, f"{date_yyyymmdd}.json")


# ── 写入 ──

def save_from_result(data: dict) -> str:
    """从 daily_report.run() 结果提取落盘字段，返回写入路径。

    只做提取和计算，任何字段缺失都降级为 None/空，不抛异常。
    thesis_checks / info_digest 由S4填充，assertions / verification 由S5填充，extreme 由S6填充，
    此处从 run() 结果直接取，缺失落空占位，保证 schema 稳定。
    """
    date = data.get("date") or datetime.now().strftime("%Y%m%d")

    breadth = data.get("breadth") or {}
    macro = data.get("macro") or {}

    # 指数快照 {code: {close, pct}}
    indices = {}
    for idx in data.get("indices") or []:
        code = idx.get("code")
        if code and idx.get("price"):
            indices[code] = {"close": idx.get("price"), "pct": idx.get("change_pct")}

    total_amount = macro.get("total_market_amount")  # 两市成交额(亿), 新浪实时口径

    sentiment = {
        "up_count": breadth.get("up"),
        "down_count": breadth.get("down"),
        "flat_count": breadth.get("flat"),
        "limit_up": breadth.get("limit_up"),
        "limit_down": breadth.get("limit_down"),
        "broken_board": None,           # 炸板率暂无数据源, 预留
        "max_lianban": breadth.get("max_lianban"),
        "total_amount": total_amount,
        "amount_vs_ma20": None,         # 下方用历史计算
        "indices": indices,
        "cycle_phase": (data.get("sentiment_cycle") or {}).get("phase"),  # S3规则引擎(attach_sentiment_cycle先于落盘执行)
    }
    sentiment["amount_vs_ma20"] = _calc_amount_vs_ma20(total_amount, date)

    # 大盘短线指引(规则引擎输出原文; assertions 由 S5 LLM 断言化后填充)
    market_view = []
    for idx in data.get("indices") or []:
        ti = (idx.get("technical_indicators") or {}).get("short_term")
        if ti:
            market_view.append({
                "index": idx.get("name"), "code": idx.get("code"),
                "score": ti.get("score"), "advice": ti.get("advice"),
            })

    # 持仓个股短线操作提示原文
    stock_tips = {}
    for p in data.get("portfolio") or []:
        ti = (p.get("technical_indicators") or {}).get("short_term")
        if ti:
            stock_tips[p.get("code")] = {
                "name": p.get("name"),
                "score": ti.get("score"),
                "advice": ti.get("advice"),
                "price": p.get("price"),
                "change_pct": p.get("change_pct"),
            }

    record = {
        "date": f"{date[:4]}-{date[4:6]}-{date[6:8]}",
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sentiment": sentiment,
        "guidance": {
            "market_view": market_view,
            "assertions": data.get("assertions_today") or [],   # S5 verify_guidance生成
            "stock_tips": stock_tips,
        },
        "thesis_checks": data.get("thesis_checks") or {},   # S4 llm_interpret填充
        "info_digest": data.get("info_digest") or {},       # S4 llm_interpret填充
        "verification": data.get("verification"),           # S5: 昨日断言/提示验证结果+命中率
        "extreme": data.get("extreme") or {"triggered": False, "triggers": [], "analysis": None},  # S6
    }

    # 保留后续步骤可能已写入的字段(同日重跑时不覆盖非空值)
    old = load(date)
    if old:
        for key in ("thesis_checks", "info_digest"):
            if old.get(key) and not record[key]:
                record[key] = old[key]
        if old.get("extreme", {}).get("triggered"):
            record["extreme"] = old["extreme"]
        if not record["guidance"]["assertions"] and old.get("guidance", {}).get("assertions"):
            record["guidance"]["assertions"] = old["guidance"]["assertions"]
        if not record["verification"] and old.get("verification"):
            record["verification"] = old["verification"]

    os.makedirs(HISTORY_DIR, exist_ok=True)
    path = _path(date)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return path


def _calc_amount_vs_ma20(total_amount, date: str):
    """今日成交额相对此前20个交易日均值的偏离。历史不足返回 None。"""
    if not total_amount:
        return None
    prev = [r["sentiment"].get("total_amount")
            for r in load_recent(21, before=date)
            if r.get("sentiment", {}).get("total_amount")]
    prev = prev[:20]
    if len(prev) < 5:  # 历史太少没有统计意义
        return None
    ma = sum(prev) / len(prev)
    if ma <= 0:
        return None
    return round((total_amount - ma) / ma, 4)


# ── 读取(容错) ──

def load(date_yyyymmdd: Optional[str]):
    """读单日记录。缺失/损坏返回 None。"""
    if not date_yyyymmdd:
        return None
    try:
        with open(_path(date_yyyymmdd), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def load_recent(n: int = 20, before: Optional[str] = None) -> list:
    """按日期升序返回最近 n 个交易日记录（含今日，除非指定 before 则只取该日期之前）。
    损坏文件跳过。before: YYYYMMDD，不含当日。"""
    files = sorted(glob.glob(os.path.join(HISTORY_DIR, "2*.json")))
    files = [f for f in files if not f.endswith(".tmp")]
    if before:
        files = [f for f in files if os.path.basename(f)[:8] < before]
    else:
        files = files[-n:] if n else files
    out = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                out.append(json.load(fh))
        except (OSError, json.JSONDecodeError):
            continue
    if before:
        out = out[-n:] if n else out
    return out


def load_similar_days(up_count: int, amount_dev: float, exclude_date: str = None,
                      up_tol: int = 300, dev_tol: float = 0.15) -> list:
    """F5历史对照: 在情绪库中找相似日(上涨家数±up_tol、成交额偏离同向±dev_tol内)。
    返回 [{date, up_count, amount_vs_ma20}]，库不足时返回已找到的（可能为空）。"""
    out = []
    for r in load_recent(0):
        d = r.get("date", "").replace("-", "")
        if exclude_date and d == exclude_date:
            continue
        s = r.get("sentiment") or {}
        u, dev = s.get("up_count"), s.get("amount_vs_ma20")
        if u is None:
            continue
        if abs(u - up_count) > up_tol:
            continue
        if amount_dev is not None and dev is not None:
            if amount_dev * dev < 0:      # 必须同向(同放量或同缩量)
                continue
            if abs(dev - amount_dev) > dev_tol:
                continue
        out.append({"date": r.get("date"), "up_count": u, "amount_vs_ma20": dev,
                    "sh_pct": (s.get("indices") or {}).get("sh000001", {}).get("pct")})
    return out
