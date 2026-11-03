#!/usr/bin/env python3
"""复盘报告卡片图生成: 从 cache/review_history/YYYYMMDD.json 提取
今天为什么 / 历史对照 / 今日断言 三部分, 渲染 1080x1920 竖屏卡片PNG。

用法: python3 scripts/daily_content/generate_review_cards.py [YYYYMMDD]
输出: output/review_cards/{date}_why.png / _history.png / _assertions.png
风格与 daily_content 一致(金色), 左右安全边距>=130px, A股红涨绿跌。
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_DIR = os.path.join(ROOT, "output", "review_cards")

BASE_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    width: 1080px; height: 1920px;
    background: linear-gradient(180deg, #faf9f6 0%, #f5f3ee 100%);
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    color: #1a1a1a;
    padding: 120px 130px 80px;
    overflow: hidden;
}
.kicker {
    display: block; text-align: center;
    font-size: 28px; font-weight: 800; letter-spacing: 3px;
    color: #b8860b; margin-bottom: 18px;
}
.kicker span {
    display: inline-block;
    border: 2px solid #d4af37; border-radius: 10px;
    padding: 6px 16px; background: rgba(212,175,55,0.08);
}
.date { text-align: center; font-size: 30px; color: #888; letter-spacing: 4px; margin-bottom: 14px; }
.title {
    text-align: center; font-size: 72px; font-weight: 800; letter-spacing: 6px;
    background: linear-gradient(90deg, #d4af37, #b8860b, #d4af37);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 44px;
}
.red { color: #dc143c; }
.green { color: #1a9c46; }
"""


def _fmt_pct(v):
    if v is None:
        return '<span style="color:#aaa">—</span>'
    cls = "red" if v > 0 else ("green" if v < 0 else "")
    sign = "+" if v > 0 else ""
    return f'<span class="{cls}">{sign}{v:.2f}%</span>'


def card_why(d, date_str):
    e = d["extreme"]["analysis"]
    st = e["structure"]
    triggers = d["extreme"]["triggers"]
    chips = "".join(
        f'<div class="chip">{t}</div>' for t in triggers
    )
    def concept_rows(items, is_loss):
        rows = ""
        for it in items:
            cls = "green" if is_loss else "red"
            sign = "+" if it["pct"] > 0 else ""
            rows += (
                f'<div class="crow"><span class="cname">{it["name"]}</span>'
                f'<span class="cpct {cls}">{sign}{it["pct"]:.2f}%</span></div>'
            )
        return rows
    gainers = concept_rows(st["top_gainers"], False)
    losers = concept_rows(st["top_losers"], True)
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
{BASE_CSS}
.chips {{ display: flex; gap: 16px; justify-content: center; margin-bottom: 40px; flex-wrap: wrap; }}
.chip {{
    background: #fff; border: 2px solid #e8b84b; border-radius: 999px;
    padding: 12px 26px; font-size: 30px; font-weight: 700; color: #8a5a00;
    box-shadow: 0 3px 10px rgba(184,134,11,0.10);
}}
.why {{
    background: #fff; border: 2px solid #d4af37; border-left: 12px solid #b8860b;
    border-radius: 16px; padding: 34px 32px;
    font-size: 34px; line-height: 1.75; text-align: justify;
    box-shadow: 0 4px 14px rgba(184,134,11,0.10);
    margin-bottom: 44px;
}}
.cols {{ display: flex; gap: 24px; }}
.col {{ flex: 1; background: #fff; border: 2px solid #e5d9b8; border-radius: 16px; padding: 24px 26px; }}
.coltitle {{ font-size: 32px; font-weight: 800; margin-bottom: 18px; text-align: center; }}
.crow {{ display: flex; justify-content: space-between; align-items: center; padding: 13px 4px; border-bottom: 1px dashed #eee4cc; }}
.crow:last-child {{ border-bottom: none; }}
.cname {{ font-size: 29px; font-weight: 600; }}
.cpct {{ font-size: 30px; font-weight: 800; }}
.breadth {{ margin-top: 40px; text-align: center; font-size: 30px; color: #666; }}
.breadth b {{ font-size: 34px; }}
</style></head><body>
<div class="kicker"><span>🌪 极端行情</span></div>
<div class="date">{date_str}</div>
<div class="title">今天为什么</div>
<div class="chips">{chips}</div>
<div class="why">{e["why"]}</div>
<div class="cols">
  <div class="col"><div class="coltitle red">领涨概念 TOP5</div>{gainers}</div>
  <div class="col"><div class="coltitle green">领跌概念 TOP5</div>{losers}</div>
</div>
<div class="breadth">上涨 <b class="red">{st["up"]}</b> 家 · 下跌 <b class="green">{st["down"]}</b> 家 · 涨停 <b class="red">{st["limit_up"]}</b> · 跌停 <b class="green">{st["limit_down"]}</b> · 最高连板 <b>{st["max_lianban"]}</b></div>
</body></html>"""


def card_history(d, date_str):
    h = d["extreme"]["analysis"]["history"]
    stat = h["stat"]
    rows = ""
    for m in h["matches"]:
        rows += (
            f'<div class="hrow"><span class="hdate">{m["date"]}</span>'
            f'<span class="hcell">{_fmt_pct(m["sh_pct"])}</span>'
            f'<span class="hcell">{_fmt_pct(m["next1"])}</span>'
            f'<span class="hcell">{_fmt_pct(m["next5"])}</span></div>'
        )
    if h.get("source") == "kline_pattern":
        sub = f'上证近5日形态相似日（位置分位 {h.get("target_pos", "—")}±30，近4年 {stat["n"]} 例）'
        weak_note = ('<div class="sub" style="color:#c0392b;">⚠ 近4年无高相似形态日，以下为最接近参考</div>'
                     if h.get("weak") else '')
    else:  # 旧落盘 source=kline 兼容
        sub = f'上证日K相似涨跌幅日（今日 {h["target_pct"]:.2f}% ±1pct，近2年 {stat["n"]} 例）'
        weak_note = ''
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
{BASE_CSS}
.sub {{ text-align: center; font-size: 30px; color: #8a6d1a; margin-bottom: 34px; }}
.htable {{ background: #fff; border: 2px solid #d4af37; border-radius: 16px; padding: 20px 30px; box-shadow: 0 4px 14px rgba(184,134,11,0.10); margin-bottom: 40px; }}
.hrow {{ display: flex; align-items: center; padding: 17px 6px; border-bottom: 1px dashed #eee4cc; }}
.hrow:last-child {{ border-bottom: none; }}
.hrow.head {{ border-bottom: 2px solid #d4af37; padding: 10px 6px 16px; }}
.hdate {{ width: 250px; font-size: 30px; font-weight: 700; color: #444; }}
.hcell {{ flex: 1; text-align: right; font-size: 31px; font-weight: 800; }}
.hrow.head .hcell, .hrow.head .hdate {{ color: #b8860b; font-size: 28px; }}
.stat {{ background: #fff; border: 2px solid #d4af37; border-left: 12px solid #b8860b; border-radius: 16px; padding: 30px 32px; box-shadow: 0 4px 14px rgba(184,134,11,0.10); }}
.statline {{ display: flex; justify-content: space-between; align-items: center; padding: 12px 0; font-size: 32px; }}
.statline b {{ font-size: 40px; }}
.note {{ margin-top: 30px; text-align: center; font-size: 26px; color: #999; }}
</style></head><body>
<div class="kicker"><span>📚 复盘 · 极端行情</span></div>
<div class="date">{date_str}</div>
<div class="title">历史对照</div>
{weak_note}
<div class="sub">{sub}</div>
<div class="htable">
  <div class="hrow head"><span class="hdate">历史日</span><span class="hcell">当日</span><span class="hcell">次1日</span><span class="hcell">次5日</span></div>
  {rows}
</div>
<div class="stat">
  <div class="statline"><span>次日平均涨幅</span><b>{_fmt_pct(stat["next1_avg"])}</b><span>上涨概率 <b class="red">{stat["next1_up_rate"]:.0f}%</b></span></div>
  <div class="statline"><span>5日平均涨幅</span><b>{_fmt_pct(stat["next5_avg"])}</b><span>上涨概率 <b>{stat["next5_up_rate"]:.0f}%</b></span></div>
</div>
<div class="note">历史统计仅供参考，不构成投资建议</div>
</body></html>"""


def card_assertions(d, date_str):
    items = d["guidance"]["assertions"]
    cards = ""
    for i, a in enumerate(items, 1):
        cards += f'<div class="acard"><div class="anum">{i}</div><div class="atext">{a}</div></div>'
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
{BASE_CSS}
.sub {{ text-align: center; font-size: 30px; color: #8a6d1a; margin-bottom: 50px; }}
.acard {{
    display: flex; align-items: center; gap: 28px;
    background: #fff; border: 2px solid #d4af37; border-radius: 16px;
    padding: 36px 34px; margin-bottom: 32px;
    box-shadow: 0 4px 14px rgba(184,134,11,0.10);
}}
.anum {{
    width: 76px; height: 76px; flex-shrink: 0;
    border-radius: 50%; background: linear-gradient(135deg, #d4af37, #b8860b);
    color: #fff; font-size: 40px; font-weight: 800;
    display: flex; align-items: center; justify-content: center;
}}
.atext {{ font-size: 35px; font-weight: 700; line-height: 1.6; }}
.foot {{ margin-top: 60px; text-align: center; font-size: 28px; color: #999; }}
</style></head><body>
<div class="kicker"><span>📌 复盘 · 研判</span></div>
<div class="date">{date_str}</div>
<div class="title">今日断言</div>
<div class="sub">明日收盘后逐条验证 ✓ / ✗</div>
{cards}
<div class="foot">断言由当日规则指引生成，仅供参考</div>
</body></html>"""


def card_response(d, date_str):
    hh = d["extreme"]["analysis"]["holdings_hint"]
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
{BASE_CSS}
body {{ display: flex; flex-direction: column; justify-content: center; }}
.rsp {{
    background: #fff; border: 2px solid #d4af37; border-left: 12px solid #b8860b;
    border-radius: 16px; padding: 40px 36px;
    font-size: 36px; line-height: 1.8; text-align: justify;
    box-shadow: 0 4px 14px rgba(184,134,11,0.10);
}}
.sub {{ text-align: center; font-size: 30px; color: #8a6d1a; margin-bottom: 50px; }}
.foot {{ margin-top: 60px; text-align: center; font-size: 28px; color: #999; }}
</style></head><body>
<div class="kicker"><span>💼 复盘 · 极端行情</span></div>
<div class="date">{date_str}</div>
<div class="title">持仓应对</div>
<div class="sub">整体仓位策略（不含个股）</div>
<div class="rsp">{hh["overall"]}</div>
<div class="foot">⚠️ 以上应对提示由AI生成，仅供参考，不构成投资决策</div>
</body></html>"""


def card_verify(d, date_str):
    vr = d["verification"]
    prev = vr["prev_date"]
    rows = ""
    for i, r in enumerate(vr["rows"], 1):
        ok = r["verdict"] == "hit"
        mark = "✓" if ok else "✗"
        mcls = "red" if ok else "green"
        rows += (
            f'<div class="vrow"><div class="vmark {mcls}">{mark}</div>'
            f'<div class="vbody"><div class="vtext">{r["text"]}</div>'
            f'<div class="vactual">实际: {r["actual"]}</div></div></div>'
        )
    n_hit = sum(1 for r in vr["rows"] if r["verdict"] == "hit")
    n_tot = len(vr["rows"])
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
{BASE_CSS}
.sub {{ text-align: center; font-size: 30px; color: #8a6d1a; margin-bottom: 44px; }}
.vrow {{
    display: flex; gap: 26px; align-items: flex-start;
    background: #fff; border: 2px solid #e5d9b8; border-radius: 16px;
    padding: 30px 28px; margin-bottom: 26px;
    box-shadow: 0 3px 10px rgba(184,134,11,0.08);
}}
.vmark {{
    width: 72px; height: 72px; flex-shrink: 0; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 44px; font-weight: 800; color: #fff; margin-top: 4px;
}}
.vmark.red {{ background: #dc143c; }}
.vmark.green {{ background: #1a9c46; }}
.vtext {{ font-size: 33px; font-weight: 700; line-height: 1.55; }}
.vactual {{ font-size: 28px; color: #888; line-height: 1.55; margin-top: 12px; }}
.rate {{ margin-top: 40px; text-align: center; font-size: 32px; color: #666; }}
.rate b {{ font-size: 40px; color: #b8860b; }}
.foot {{ margin-top: 36px; text-align: center; font-size: 28px; color: #999; }}
</style></head><body>
<div class="kicker"><span>✅ 复盘 · 研判验证</span></div>
<div class="date">{date_str}</div>
<div class="title">昨日研判结果</div>
<div class="sub">验证 {prev} 大盘断言 · 命中 {n_hit}/{n_tot}</div>
{rows}
<div class="foot">仅大盘断言，持仓个股验证见复盘报告</div>
</body></html>"""


def html_to_png(html_path, png_path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1080, "height": 1920}, device_scale_factor=2)
        page = context.new_page()
        page.goto(f"file://{html_path}")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=png_path, full_page=False)
        browser.close()


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else None
    hist_dir = os.path.join(ROOT, "cache", "review_history")
    if not date_str:
        cands = sorted(f[:-5] for f in os.listdir(hist_dir) if f[:8].isdigit() and f.endswith(".json") and len(f) == 13)
        date_str = cands[-1]
    path = os.path.join(hist_dir, f"{date_str}.json")
    with open(path) as f:
        d = json.load(f)
    pretty = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    os.makedirs(OUT_DIR, exist_ok=True)
    cards = {
        "assertions": card_assertions(d, pretty),
    }
    # 极端行情未触发或验证数据缺失时跳过对应卡（不崩整体）
    if d.get("extreme", {}).get("analysis", {}).get("holdings_hint"):
        cards["why"] = card_why(d, pretty)
        cards["history"] = card_history(d, pretty)
        cards["response"] = card_response(d, pretty)
    if d.get("verification", {}).get("rows"):
        cards["verify"] = card_verify(d, pretty)
    for name, html in cards.items():
        hp = os.path.join(OUT_DIR, f"{date_str}_{name}.html")
        pp = os.path.join(OUT_DIR, f"{date_str}_{name}.png")
        with open(hp, "w") as f:
            f.write(html)
        html_to_png(hp, pp)
        print(pp)


if __name__ == "__main__":
    main()
