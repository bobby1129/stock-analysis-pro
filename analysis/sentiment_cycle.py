# -*- coding: utf-8 -*-
"""情绪周期定位 + 近20日情绪时序 (F3, REVIEW_UPGRADE_DESIGN.md §五.5)

规则引擎(非LLM, 可解释):
- 热度分 H(0~100) = 上涨家数(0-30) + 涨停数(0-25) + 最高连板(0-20) + 成交额偏离MA20(0-25)
- 趋势 T = 今日H - 前3日H均值(历史不足则为None, 只按当日水平定位)
- 定档: H<20冰点 / 20~40修复 / 40~65发酵 / >=65高潮; T明显下行(<-8)判退潮
- 硬覆盖: 上涨家数<800 → 冰点(极端普跌, 如2026-10-29涨781)

时序SVG: 纯字符串拼接内嵌SVG(无外部库), 三联小图——
上涨家数柱状 / 涨跌停折线 / 成交额与MA20折线。有多少天画多少天(冷启动首日1个点)。

数据源: cache/review_history/YYYYMMDD.json (analysis/review_history.py 落盘层)。
"""

from typing import Optional

PHASES = ["冰点", "修复", "发酵", "高潮", "退潮"]
PHASE_COLORS = {"冰点": "#3b82c4", "修复": "#8e6bbf", "发酵": "#f0873b",
                "高潮": "#e74c3c", "退潮": "#27ae60"}

# ── 热度打分(规则引擎) ──

def _score_up_count(v) -> tuple:
    """上涨家数 0-30分。全市场约5400只, 绝对阈值。"""
    if v is None:
        return 12, "上涨家数缺失"
    if v < 800:   return 0,  f"上涨{v}家(<800极端普跌)"
    if v < 1500:  return 8,  f"上涨{v}家(<1500普跌)"
    if v < 2500:  return 16, f"上涨{v}家(偏弱)"
    if v < 3500:  return 24, f"上涨{v}家(偏强)"
    return 30, f"上涨{v}家(>3500普涨)"


def _score_limit_up(v) -> tuple:
    """涨停数 0-25分。"""
    if v is None:
        return 10, "涨停数缺失"
    if v < 25:  return 3,  f"涨停{v}家(赚钱效应差)"
    if v < 45:  return 8,  f"涨停{v}家(一般)"
    if v < 70:  return 15, f"涨停{v}家(活跃)"
    if v < 100: return 21, f"涨停{v}家(火热)"
    return 25, f"涨停{v}家(>100爆热)"


def _score_lianban(v) -> tuple:
    """最高连板高度 0-20分。"""
    if v is None:
        return 8, "连板高度缺失"
    v = int(v)
    if v <= 2: return 3,  f"最高{v}连板(无梯队)"
    if v == 3: return 8,  f"最高3连板(梯队初现)"
    if v == 4: return 11, f"最高4连板"
    if v <= 6: return 16, f"最高{v}连板(空间打开)"
    return 20, f"最高{v}连板(>=7妖股横行)"


def _score_amount_dev(v) -> tuple:
    """成交额较MA20偏离 0-25分。None(历史不足)给中位12。"""
    if v is None:
        return 12, "成交额历史不足(按中位计)"
    pct = v * 100
    if pct < -20: return 3,  f"成交额较20日均值{pct:+.0f}%(深度缩量)"
    if pct < -5:  return 8,  f"成交额{pct:+.0f}%(缩量)"
    if pct <= 5:  return 13, f"成交额{pct:+.0f}%(持平)"
    if pct <= 20: return 19, f"成交额{pct:+.0f}%(温和放量)"
    return 25, f"成交额{pct:+.0f}%(显著放量)"


def compute_heat(sent: dict) -> tuple:
    """输入单日sentiment dict, 返回 (score:int, reasons:list[str])。"""
    parts = [
        _score_up_count(sent.get("up_count")),
        _score_limit_up(sent.get("limit_up")),
        _score_lianban(sent.get("max_lianban")),
        _score_amount_dev(sent.get("amount_vs_ma20")),
    ]
    score = sum(p[0] for p in parts)
    return score, [p[1] for p in parts]


def _map_phase(h: int, trend: Optional[float], up_count) -> str:
    # 硬覆盖: 极端普跌直接冰点
    if up_count is not None and up_count < 800:
        return "冰点"
    if trend is not None and trend < -8:
        return "退潮"
    if h < 30:
        return "冰点"
    if h < 45:
        return "修复"
    if h < 70:
        return "发酵"
    return "高潮"


def determine_cycle(today_sent: dict, history: list) -> dict:
    """定位情绪周期档位。

    today_sent: 今日sentiment dict (字段同落盘schema)
    history: 此前交易日sentiment dict列表(升序, 不含今日)
    返回 {phase, score, trend, reason, days} — 全部可解释, 失败不抛异常。
    """
    try:
        score, reasons = compute_heat(today_sent)
        trend = None
        if len(history) >= 3:
            prev = [compute_heat(h)[0] for h in history[-3:]]
            trend = round(score - sum(prev) / len(prev), 1)
        phase = _map_phase(score, trend, today_sent.get("up_count"))
        trend_s = ""
        if trend is None:
            trend_s = "历史<3日暂无趋势"
        elif trend > 8:
            trend_s = f"热度较前3日均值{trend:+.0f}(升温)"
        elif trend < -8:
            trend_s = f"热度较前3日均值{trend:+.0f}(降温)"
        else:
            trend_s = f"热度较前3日均值{trend:+.0f}(持平)"
        reason = "；".join(reasons) + f"。热度{score}/100，{trend_s}"
        return {"phase": phase, "score": score, "trend": trend,
                "reason": reason, "days": len(history) + 1}
    except Exception as e:
        return {"phase": None, "score": None, "trend": None,
                "reason": f"定位失败: {e}", "days": len(history) + 1}


# ── 近20日情绪时序 SVG (三联小图, 纯字符串, 无外部库) ──

def build_timeseries_svg(series: list, width: int = 960, height: int = 230) -> str:
    """series: [{date:'2026-10-29', up_count, limit_up, limit_down, total_amount}, ...] 升序。
    返回内嵌SVG字符串。有多少画多少; 空序列返回''。"""
    series = [s for s in series if s.get("date")]
    if not series:
        return ""
    n = len(series)
    pw = width // 3          # 每联宽
    pad_l, pad_r = 10, 10
    pad_t, pad_b = 30, 20    # 顶部标题 / 底部日期
    plot_w = pw - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    def _x(i):  # 点中心x(联内坐标)
        if n == 1:
            return pad_l + plot_w / 2
        return pad_l + plot_w * i / (n - 1)

    def _dates(panel_off):
        d0 = series[0]["date"][5:].replace("-", "/")
        d1 = series[-1]["date"][5:].replace("-", "/")
        if n == 1:
            return (f'<text x="{panel_off + pw/2}" y="{height-6}" font-size="11" '
                    f'fill="#999" text-anchor="middle">{d1}</text>')
        return (f'<text x="{panel_off + pad_l}" y="{height-6}" font-size="11" fill="#999">{d0}</text>'
                f'<text x="{panel_off + pw - pad_r}" y="{height-6}" font-size="11" '
                f'fill="#999" text-anchor="end">{d1}</text>')

    def _title(panel_off, text):
        return (f'<text x="{panel_off + pw/2}" y="18" font-size="13" fill="#333" '
                f'text-anchor="middle" font-weight="600">{text}</text>')

    def _ymax_label(panel_off, vmax, fmt="{:.0f}"):
        return (f'<text x="{panel_off + pad_l}" y="{pad_t - 4}" font-size="10" '
                f'fill="#bbb">{fmt.format(vmax)}</text>')

    svg = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
           f'style="max-width:{width}px;font-family:inherit;" '
           f'xmlns="http://www.w3.org/2000/svg">']

    # 分隔线
    for k in (1, 2):
        svg.append(f'<line x1="{pw*k}" y1="6" x2="{pw*k}" y2="{height-16}" stroke="#eee"/>')

    # ── 联1: 上涨家数柱状 ──
    vals = [s.get("up_count") for s in series]
    vmax = max([v for v in vals if v is not None] or [1])
    vmax = max(vmax, 100) * 1.08
    # 柱宽上限40px: 小样本(n=2)时 plot_w/n 过大, 会画成越界巨块
    bar_w = max(2.0, min((plot_w / n) * 0.62, 40.0))
    def _bar_cx(i):
        # n<=4 用槽位居中(端点式首尾贴边会让柱心落在面板边缘, 半柱越界);
        # n>4 沿用端点式 _x(i)
        if n <= 4:
            return pad_l + plot_w * (i + 0.5) / n
        return _x(i)
    svg.append(_title(0, "上涨家数"))
    svg.append(_ymax_label(0, vmax))
    for i, v in enumerate(vals):
        if v is None:
            continue
        bh = plot_h * v / vmax
        x = _bar_cx(i) - bar_w / 2
        x = max(1.0, min(x, pw - bar_w - 1.0))  # clamp不出面板
        svg.append(f'<rect x="{x:.1f}" y="{pad_t + plot_h - bh:.1f}" width="{bar_w:.1f}" '
                   f'height="{bh:.1f}" fill="#e74c3c" opacity="0.85" rx="1"/>')
    svg.append(_dates(0))

    # ── 联2: 涨停(红)/跌停(绿)折线 ──
    lu = [s.get("limit_up") for s in series]
    ld = [s.get("limit_down") for s in series]
    vmax2 = max([v for v in lu + ld if v is not None] or [1]) * 1.15
    vmax2 = max(vmax2, 10)
    svg.append(_title(pw, "涨停 / 跌停家数"))
    svg.append(_ymax_label(pw, vmax2))

    def _polyline(vals_, color, dash=""):
        pts = []
        for i, v in enumerate(vals_):
            if v is None:
                continue
            x = pw + _x(i)
            y = pad_t + plot_h * (1 - v / vmax2)
            pts.append((x, y))
        if not pts:
            return ""
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        da = f' stroke-dasharray="{dash}"' if dash else ""
        out = [f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="2"{da}/>']
        for x, y in pts:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{color}"/>')
        return "".join(out)

    svg.append(_polyline(lu, "#e74c3c"))
    svg.append(_polyline(ld, "#27ae60"))
    svg.append(_dates(pw))

    # ── 联3: 成交额(亿)与MA20 ──
    amts = [s.get("total_amount") for s in series]
    ma20 = []
    for i in range(n):
        window = [v for v in amts[max(0, i - 19):i + 1] if v is not None]
        ma20.append(sum(window) / len(window) if window else None)
    valid = [v for v in amts + ma20 if v is not None]
    vmax3 = (max(valid) if valid else 1) * 1.1
    vmax3 = max(vmax3, 1)
    svg.append(_title(pw * 2, "成交额(亿) 与 MA20"))
    svg.append(_ymax_label(pw * 2, vmax3, "{:.0f}"))

    def _polyline3(vals_, color, dash="", width_: float = 2.0):
        pts = []
        for i, v in enumerate(vals_):
            if v is None:
                continue
            x = pw * 2 + _x(i)
            y = pad_t + plot_h * (1 - v / vmax3)
            pts.append((x, y))
        if not pts:
            return ""
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        da = f' stroke-dasharray="{dash}"' if dash else ""
        return f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="{width_}"{da}/>'

    svg.append(_polyline3(amts, "#4a6fa5"))
    svg.append(_polyline3(ma20, "#f5a623", dash="5,3", width_=1.6))
    svg.append(_dates(pw * 2))

    svg.append("</svg>")
    return "".join(svg)


# ── 对 daily_report.run() 结果的接线 ──

def attach_sentiment_cycle(result: dict) -> dict:
    """读落盘历史+今日数据 → result['sentiment_cycle'] + result['sentiment_ts_svg']。
    任何异常只降级(字段为None/'')，不影响报告。返回result便于链式调用。"""
    try:
        from analysis import review_history as rh

        date = result.get("date") or ""
        hist = rh.load_recent(20, before=date) or []
        hist_sent = [r.get("sentiment") or {} for r in hist]
        # 对齐date字段
        for r, s in zip(hist, hist_sent):
            s.setdefault("date", r.get("date"))

        breadth = result.get("breadth") or {}
        macro = result.get("macro") or {}
        total_amount = macro.get("total_market_amount")
        today_sent = {
            "date": f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else date,
            "up_count": breadth.get("up") or None,
            "down_count": breadth.get("down"),
            "limit_up": breadth.get("limit_up"),
            "limit_down": breadth.get("limit_down"),
            "max_lianban": breadth.get("max_lianban"),
            "total_amount": total_amount,
            "amount_vs_ma20": rh._calc_amount_vs_ma20(total_amount, date),
        }
        result["sentiment_cycle"] = determine_cycle(today_sent, hist_sent)

        series = [{k: s.get(k) for k in ("date", "up_count", "limit_up",
                                          "limit_down", "total_amount")}
                  for s in hist_sent]
        series.append(today_sent)
        series = series[-20:]
        result["sentiment_ts_svg"] = build_timeseries_svg(series)
        result["sentiment_ts_days"] = len([s for s in series if s.get("up_count") is not None])
    except Exception as e:
        result["sentiment_cycle"] = {"phase": None, "score": None, "trend": None,
                                     "reason": f"情绪周期计算失败: {e}", "days": 0}
        result["sentiment_ts_svg"] = ""
        result["sentiment_ts_days"] = 0
    return result
