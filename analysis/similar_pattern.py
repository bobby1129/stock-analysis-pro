# -*- coding: utf-8 -*-
"""日K多日形态相似日匹配 (S8 候选实现, 验证通过后替换 extreme_mode._history_from_kline)

口径:
- 特征 = 近5日收益率序列(5维, pct单位) 欧氏距离, 距离越小越相似
- 位置过滤 = 当日收盘在近60日区间的分位(0-100), 与目标日分位差 >30 直接排除
  (避免"高位破位跌"匹配到"低位缩量阴跌")
- 去重叠 = 已选相似日之间至少间隔3个交易日(避免连续日互相匹配刷屏)
- 窗口 = 近1000交易日(实测新浪datalen=1000可用, 2000返回None)
- 红线: 只用close, 严禁碰volume(新浪指数K线volume不是成交额)

产出结构与旧版 _history_from_kline 一致(matches+stat), 卡片/模板无需改动;
matches 每行新增 dist(形态距离) 与 cum5(5日累计涨跌幅) 字段。
"""

WINDOW_DAYS = 1000      # K线拉取长度(交易日)
PATTERN_LEN = 5         # 形态窗口: 近5日收益率
POS_LOOKBACK = 60       # 位置分位回看窗口
POS_MAX_DIFF = 30       # 位置分位差上限
MIN_GAP = 3             # 相似日之间最小间隔(交易日)
TOP_N = 10


def _pct_series(closes):
    """收益率序列(pct), 与closes等长, 第0位None。"""
    return [None] + [(closes[i] - closes[i - 1]) / closes[i - 1] * 100
                     for i in range(1, len(closes))]


def _pos_pct(closes, i, lookback=POS_LOOKBACK):
    """closes[i] 在近lookback日区间(含当日)的分位 0-100。"""
    lo = max(0, i - lookback + 1)
    seg = closes[lo:i + 1]
    mn, mx = min(seg), max(seg)
    if mx == mn:
        return 50.0
    return (closes[i] - mn) / (mx - mn) * 100


def _dist(v1, v2):
    return sum((a - b) ** 2 for a, b in zip(v1, v2)) ** 0.5


def find_similar_pattern(klines, target_idx=None, top_n=TOP_N):
    """在klines中找与target_idx日形态最相似的历史日。

    klines: [[date, open, close, ...], ...] 升序
    target_idx: 目标日下标, 默认最后一根(今天)
    返回: {"source": "kline_pattern", "code", "target_pct", "target_pos", "matches", "stat"}
          或 None(数据不足/无匹配)
    """
    if not klines or len(klines) < POS_LOOKBACK + PATTERN_LEN + 2:
        return None
    closes = [k[2] for k in klines]
    dates = [k[0] for k in klines]
    pcts = _pct_series(closes)
    if target_idx is None:
        target_idx = len(closes) - 1
    ti = target_idx
    if ti < PATTERN_LEN or pcts[ti] is None:
        return None

    t_vec = pcts[ti - PATTERN_LEN + 1: ti + 1]
    if any(v is None for v in t_vec):
        return None
    tp = pcts[ti]
    assert tp is not None
    t_pct = float(tp)
    t_pos = _pos_pct(closes, ti)

    cands = []
    # 候选日j: 需完整5日形态 + 后续至少1日可算next1; 排除目标日本身及未来
    for j in range(PATTERN_LEN, ti):
        vec = pcts[j - PATTERN_LEN + 1: j + 1]
        if any(v is None for v in vec):
            continue
        pos = _pos_pct(closes, j)
        if abs(pos - t_pos) > POS_MAX_DIFF:
            continue
        d = _dist(vec, t_vec)
        cands.append((d, j))
    cands.sort()

    matches = []
    for d, j in cands:
        if any(abs(j - m["_j"]) < MIN_GAP for m in matches):
            continue
        cum5 = (closes[j] - closes[j - PATTERN_LEN]) / closes[j - PATTERN_LEN] * 100
        row = {
            "_j": j, "date": dates[j], "sh_pct": round(pcts[j], 2),
            "dist": round(d, 2), "cum5": round(cum5, 2),
            "pos": round(_pos_pct(closes, j)),
            "next1": round((closes[j + 1] - closes[j]) / closes[j] * 100, 2) if j + 1 < len(closes) else None,
            "next5": round((closes[min(j + 5, len(closes) - 1)] - closes[j]) / closes[j] * 100, 2) if j + 5 < len(closes) else None,
        }
        matches.append(row)
        if len(matches) >= top_n:
            break
    if not matches:
        return None
    matches.sort(key=lambda m: m["date"])
    n1 = [m["next1"] for m in matches if m["next1"] is not None]
    n5 = [m["next5"] for m in matches if m["next5"] is not None]
    for m in matches:
        m.pop("_j")
    return {
        "source": "kline_pattern", "code": "sh000001",
        "target_pct": round(t_pct, 2), "target_pos": round(t_pos),
        "matches": matches,
        "stat": {
            "n": len(matches),
            "next1_avg": round(sum(n1) / len(n1), 2) if n1 else None,
            "next1_up_rate": round(sum(1 for x in n1 if x > 0) / len(n1) * 100) if n1 else None,
            "next5_avg": round(sum(n5) / len(n5), 2) if n5 else None,
            "next5_up_rate": round(sum(1 for x in n5 if x > 0) / len(n5) * 100) if n5 else None,
        },
    }
