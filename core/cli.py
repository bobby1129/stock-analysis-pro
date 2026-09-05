#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stock Analysis Pro CLI — 入口调度"""

import sys
import os
import json
import argparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
DATA_DIR = os.path.join(BASE_DIR, "data")
WATCHLIST_PATH = os.path.join(DATA_DIR, "watchlist.json")


def get_watchlist():
    if not os.path.exists(WATCHLIST_PATH):
        return []
    with open(WATCHLIST_PATH, "r") as f:
        return json.load(f)


def save_watchlist(lst):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(WATCHLIST_PATH, "w") as f:
        json.dump(lst, f, indent=2)


def print_summary(data):
    """Compact JSON summary — key conclusions only, ~200 tokens"""
    b = data.get("basic", {})
    s = data.get("score", {})
    sent = data.get("sentiment", {})
    fund = data.get("fundamentals", {})
    
    out = {
        "symbol": data.get("symbol"),
        "name": b.get("name"),
        "price": b.get("price"),
        "change_pct": b.get("change_pct"),
        "pe": b.get("pe"),
        "pb": b.get("pb"),
        "rating": s.get("rating"),
        "total_score": s.get("total_score"),
        "scores": {
            "tech": s.get("technical"),
            "fund": s.get("fundamental"),
            "cap": s.get("capital"),
            "sent": s.get("sentiment"),
        },
        "signals": s.get("signals", [])[:5],
        "warnings": s.get("warnings", [])[:5],
        "sentiment": sent.get("signal"),
        "analyst_consensus": sent.get("analyst_ratings", {}).get("summary", {}).get("consensus"),
        "roe": fund.get("profitability", {}).get("roe", {}).get("value"),
        "revenue_growth": fund.get("growth", {}).get("revenue_growth", {}).get("value"),
        "net_profit_growth": fund.get("growth", {}).get("net_profit_growth", {}).get("value"),
    }
    print(json.dumps(out, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Stock Analysis Pro — A股多维分析工具")
    parser.add_argument("command", choices=["analyze", "market", "analyze-all", "add", "rm", "list", "concept", "review", "options", "portfolio"])
    parser.add_argument("symbol", nargs="?", help="Stock code")
    parser.add_argument("--date", help="Date YYYYMMDD")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--brief", action="store_true", help="Brief output")
    parser.add_argument("--summary", action="store_true", help="Compact JSON summary for agent consumption")
    parser.add_argument("--html", action="store_true", help="Generate HTML report file (outputs file path to stdout)")
    parser.add_argument("--top", type=int, default=10, help="Top N results (options/concept)")
    parser.add_argument("--action", choices=["add", "rm", "list", "update"], help="Portfolio action")
    parser.add_argument("--name", help="Portfolio stock name")
    parser.add_argument("--cost", type=float, help="Portfolio cost")
    parser.add_argument("--shares", type=int, help="Portfolio shares")
    parser.add_argument("--note", help="Portfolio note")
    args = parser.parse_args()

    try:
        if args.command == "analyze":
            if not args.symbol:
                print("Error: stock code required", file=sys.stderr)
                sys.exit(1)
            from plans.stock_analysis import run
            data = run(args.symbol)
            if args.html:
                from core.html_renderer import render
                path = render(data, "stock_report")
                print(path)
            elif args.summary:
                print_summary(data)
            elif args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            elif args.brief:
                print_brief(data)
            else:
                print_report(data)

        elif args.command == "market":
            from plans.daily_review import run as run_market, format_report as format_market
            data = run_market(date=args.date, verbose=not args.json and not args.html)
            if args.html:
                from core.html_renderer import render
                path = render(data, "global_macro")
                print(path)
            elif args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                print(format_market(data))

        elif args.command == "analyze-all":
            wl = get_watchlist()
            if not wl:
                print("Watchlist empty", file=sys.stderr)
                sys.exit(1)
            from plans.stock_analysis import run
            for sym in wl:
                data = run(sym)
                print_report(data)
                print("=" * 60)

        elif args.command == "concept":
            from plans.concept_analysis import run as run_concept, format_report
            data = run_concept(verbose=False)
            if args.html:
                from core.html_renderer import render
                path = render(data, "concept_report")
                print(path)
            elif args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                print(format_report(data))

        elif args.command == "add":
            if not args.symbol:
                print("Error: stock code required", file=sys.stderr)
                sys.exit(1)
            wl = get_watchlist()
            if args.symbol not in wl:
                wl.append(args.symbol)
                save_watchlist(wl)
                print(f"Added {args.symbol}")

        elif args.command == "rm":
            if not args.symbol:
                print("Error: stock code required", file=sys.stderr)
                sys.exit(1)
            wl = get_watchlist()
            if args.symbol in wl:
                wl.remove(args.symbol)
                save_watchlist(wl)
                print(f"Removed {args.symbol}")

        elif args.command == "list":
            wl = get_watchlist()
            print(f"Watchlist ({len(wl)} stocks):")
            for s in wl:
                print(f"  {s}")

        elif args.command == "review":
            from plans.daily_report import run as run_review, format_report as format_review
            data = run_review(date=args.date, verbose=not args.json and not args.html)
            if args.html:
                from core.html_renderer import render
                path = render(data, "review_report")
                print(path)
            elif args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                print(format_review(data))

        elif args.command == "options":
            from plans.options_scan import run_scan as run_options, print_summary as print_options_summary
            data = run_options(underlying=args.symbol, top_n=args.top)
            if args.html:
                from core.html_renderer import render
                path = render(data, "options_report")
                print(path)
            elif args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                print_options_summary(data)

        elif args.command == "portfolio":
            from config import load_config
            import yaml
            config = load_config()
            portfolio = config.get('portfolio', [])
            action = args.action or 'list'
            
            if action == 'list':
                print(f"持仓 ({len(portfolio)}只):")
                for p in portfolio:
                    cost_str = f"成本¥{p['cost']}" if p.get('cost') else "未设成本"
                    shares_str = f"{p['shares']}股" if p.get('shares') else "未设持仓"
                    note_str = f" | {p['note']}" if p.get('note') else ""
                    print(f"  {p['name']}({p['code']}) {cost_str} {shares_str}{note_str}")
            
            elif action == 'add':
                if not args.symbol:
                    print("Error: stock code required (--symbol CODE)", file=sys.stderr)
                    sys.exit(1)
                new_item = {
                    'code': args.symbol,
                    'name': args.name or args.symbol,
                    'cost': args.cost or 0,
                    'shares': args.shares or 0,
                    'note': args.note or '',
                }
                portfolio.append(new_item)
                cfg_path = os.path.join(BASE_DIR, 'config', 'config.yaml')
                config['portfolio'] = portfolio
                with open(cfg_path, 'w') as f:
                    yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
                print(f"Added {new_item['name']}({new_item['code']})")
            
            elif action == 'rm':
                if not args.symbol:
                    print("Error: stock code required", file=sys.stderr)
                    sys.exit(1)
                portfolio = [p for p in portfolio if p['code'] != args.symbol]
                cfg_path = os.path.join(BASE_DIR, 'config', 'config.yaml')
                config['portfolio'] = portfolio
                with open(cfg_path, 'w') as f:
                    yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
                print(f"Removed {args.symbol}")
            
            elif action == 'update':
                if not args.symbol:
                    print("Error: stock code required", file=sys.stderr)
                    sys.exit(1)
                for p in portfolio:
                    if p['code'] == args.symbol:
                        if args.cost is not None:
                            p['cost'] = args.cost
                        if args.shares is not None:
                            p['shares'] = args.shares
                        if args.note is not None:
                            p['note'] = args.note
                        if args.name:
                            p['name'] = args.name
                        cfg_path = os.path.join(BASE_DIR, 'config', 'config.yaml')
                        config['portfolio'] = portfolio
                        with open(cfg_path, 'w') as f:
                            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
                        print(f"Updated {p['name']}({p['code']})")
                        break
                else:
                    print(f"Error: {args.symbol} not found in portfolio", file=sys.stderr)
                    sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _safe(d, *keys, default="N/A"):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d if d is not None else default


def print_report(data):
    company = data.get("company", {})
    basic = data.get("basic", {})
    tech = data.get("technicals", {})
    fund = data.get("fundamentals", {})
    cap = data.get("capital", {})
    sent = data.get("sentiment", {})
    score = data.get("score", {})

    lines = []
    sep = "=" * 50

    name = basic.get("name", "?")
    code = data.get("symbol", "?")
    price = basic.get("price", 0)
    chg = basic.get("change_pct", 0)
    industry = company.get("industry", "")
    listing = company.get("listing_date", "")[:4] if company.get("listing_date") else ""

    lines.append(sep)
    lines.append(f"  {name} ({code})  ¥{price}  {chg:+.2f}%")
    lines.append(f"  {industry} | {listing}年上市" if listing else f"  {industry}")
    lines.append(sep)

    # 大盘环境 (Item 9)
    market = data.get("market", {})
    indices = market.get("indices", {})
    rs = market.get("relative_strength", 0)
    if indices:
        idx_parts = []
        for name in ["上证指数", "深证成指", "创业板指"]:
            idx = indices.get(name, {})
            if idx:
                idx_parts.append(f"{name} {idx['price']:.0f}({idx['change_pct']:+.2f}%)")
        lines.append(f"📊 大盘: {' | '.join(idx_parts)}")
        stronger = "强于大盘" if rs > 0 else "弱于大盘"
        lines.append(f"   相对强度: {rs:+.2f}% ({stronger})")

    # 公司概况
    main_biz = company.get("main_business", "")
    products = company.get("product_type", "")
    summary = company.get("summary", "")
    controller = company.get("controller", "")
    legal_rep = company.get("legal_rep", "")
    registered_capital = company.get("registered_capital", "")
    employees = company.get("employees", "")
    
    if main_biz or products or summary or controller:
        lines.append(f"\n【公司概况】")
        if controller:
            lines.append(f"  实控人：{controller}")
        if main_biz:
            lines.append(f"  主营业务：{main_biz}")
        if products:
            prods = [p.strip() for p in products.split("、") if p.strip()]
            if prods:
                lines.append(f"  产品类型：{' | '.join(prods[:4])}")
        if summary:
            # 提取下游应用关键词
            apps = []
            for kw in ["汽车电子", "机器视觉", "工业控制", "智能家居", "消费电子", "物联网", "AIoT", "安防", "教育", "医疗"]:
                if kw in summary:
                    apps.append(kw)
            if apps:
                lines.append(f"  下游应用：{'、'.join(apps)}")
            # 公司简介（截断）
            summary_short = summary.strip()[:150]
            if len(summary.strip()) > 150:
                summary_short += "..."
            lines.append(f"  公司简介：{summary_short}")
        if legal_rep or registered_capital or employees:
            extra_info = []
            if legal_rep: extra_info.append(f"法人：{legal_rep}")
            if registered_capital: extra_info.append(f"注册资本：{registered_capital}")
            if employees: extra_info.append(f"员工：{employees}人")
            if extra_info:
                lines.append(f"  {'  '.join(extra_info)}")

    # 综合评分
    rating = score.get("rating", "N/A")
    total = score.get("total_score", 0)
    lines.append(f"\n【综合评分】{rating} ({total:+d}分)")
    lines.append(f"  技术={score.get('technical', 0):+d}  基本={score.get('fundamental', 0):+d}  资金={score.get('capital', 0):+d}  舆情={score.get('sentiment', 0):+d}")
    
    sigs = score.get("signals", [])
    if sigs:
        lines.append(f"  ✅ {' | '.join(sigs[:6])}")
    warns = score.get("warnings", [])
    if warns:
        lines.append(f"  ⚠️ {' | '.join(warns[:6])}")
    
    # 历史对比 (Item 12)
    comp = data.get("comparison", {})
    if comp:
        lines.append(f"\n【历史对比】vs {comp.get('prev_date', '?')}")
        if comp.get("price_change") is not None:
            lines.append(f"  价格: {comp.get('prev_price')} → {price} ({comp['price_change']:+.2f}, {comp['price_change_pct']:+.2f}%)")
        if comp.get("score_change") is not None:
            lines.append(f"  评分: {comp.get('prev_score')} → {total} ({comp['score_change']:+d})")
        if comp.get("rating_change"):
            lines.append(f"  评级: {comp['rating_change']}")

    # 估值
    pe = basic.get("pe", 0)
    pb = basic.get("pb", 0)
    mv = basic.get("total_mv", 0)
    tr = basic.get("turnover_rate", 0)
    lines.append(f"\n【估值】PE={pe}  PB={pb}  总市值={mv}亿  换手率={tr}%")

    # 技术面
    lines.append(f"\n【技术面】")
    
    # 均线
    ma_lines = []
    for p in [5, 10, 20, 60, 120, 250]:
        ma_val = tech.get(f"ma{p}")
        if ma_val:
            sig = tech.get(f"ma{p}_signal", "")
            arrow = "↑" if sig == "above" else "↓"
            ma_lines.append(f"MA{p}={ma_val}{arrow}")
    if ma_lines:
        lines.append(f"  均线：{'  '.join(ma_lines)}")
    
    # MACD
    macd = tech.get("macd", {})
    if macd:
        gc = "金叉" if macd.get("golden_cross") else ""
        dc = "死叉" if macd.get("dead_cross") else ""
        cross = f" {gc}{dc}".strip()
        lines.append(f"  MACD：DIF={macd.get('dif',0)}  DEA={macd.get('dea',0)}  柱={macd.get('histogram',0)}{cross}")
    
    # KDJ
    kdj = tech.get("kdj", {})
    if kdj:
        lines.append(f"  KDJ：K={kdj.get('k',0)}  D={kdj.get('d',0)}  J={kdj.get('j',0)}")
    
    # RSI
    rsi_parts = []
    for p in [6, 12, 24]:
        rsi_val = tech.get(f"rsi{p}")
        if rsi_val:
            rsi_parts.append(f"RSI{p}={rsi_val}")
    if rsi_parts:
        lines.append(f"  RSI：{'  '.join(rsi_parts)}")
    
    # BOLL
    boll = tech.get("boll", {})
    if boll:
        lines.append(f"  BOLL：上轨={boll.get('upper',0)}  中轨={boll.get('middle',0)}  下轨={boll.get('lower',0)}")
    
    # 量比 + 分位 + 支撑压力
    vol_ratio = tech.get("volume_ratio", 0)
    tr_level = tech.get("turnover_level", "")
    tr = tech.get("turnover_rate", 0)
    extra_parts = [f"量比={vol_ratio}"]
    if tr:
        extra_parts.append(f"换手率={tr}%({tr_level})")
    
    p60 = tech.get("percentile_60d", {})
    p250 = tech.get("percentile_250d", {})
    if p60.get("value"):
        extra_parts.append(f"60日分位={p60['value']}%")
    if p250.get("value"):
        extra_parts.append(f"250日分位={p250['value']}%")
    
    support = tech.get("support")
    resistance = tech.get("resistance")
    if support and resistance:
        extra_parts.append(f"支撑={support}  压力={resistance}")
    
    lines.append(f"  {'  '.join(extra_parts)}")

    # 基本面
    roe = fund.get("profitability", {}).get("roe", {}).get("value", 0)
    gm = fund.get("profitability", {}).get("gross_margin", {}).get("value", 0)
    debt = fund.get("health", {}).get("debt_ratio", {}).get("value", 0)
    rev_g = fund.get("growth", {}).get("revenue_growth", {}).get("value", 0)
    np_g = fund.get("growth", {}).get("net_profit_growth", {}).get("value", 0)
    eps = fund.get("eps", 0)
    nav = fund.get("nav_per_share", 0)
    ocf = fund.get("ocf_per_share", 0)
    lines.append(f"\n【基本面】")
    lines.append(f"  ROE={roe}%  毛利率={gm}%  负债率={debt}%")
    lines.append(f"  营收增速={rev_g}%  净利增速={np_g}%")
    if eps:
        lines.append(f"  每股数据：EPS={eps}元 | 每股净资产={nav}元 | 经营现金流={ocf}元")
    
    # 一致预期 (机构盈利预测)
    forecast = fund.get("forecast", [])
    if forecast:
        fc_parts = []
        for f in forecast:
            fc_parts.append(f"{f['year']}年EPS预{f['mean_eps']}元({f['count']}家)")
        lines.append(f"  一致预期：{' | '.join(fc_parts)}")
    
    # 分红历史
    divs = fund.get("dividend", {}).get("history", [])
    if divs:
        div_strs = []
        for d in divs[:3]:
            div_val = d.get("dividend", 0)
            ex = d.get("ex_date", "")[:10]
            status = d.get("status", "")
            if ex:
                div_strs.append(f"{ex}: 每10股派{div_val}元({status})")
            else:
                div_strs.append(f"{d.get('date', '')}: 每10股派{div_val}元({status})")
        lines.append(f"  分红历史：{' | '.join(div_strs)}")

    # 资金面
    vol_stats = cap.get("volume_stats", {})
    lines.append(f"\n【资金面】")
    if "stats" in vol_stats:
        latest = vol_stats.get("latest", {}).get("amount_yi", 0)
        s = vol_stats["stats"]
        lines.append(f"  当日成交额：{latest}亿")
        lines.append(f"  近{vol_stats.get('period_days', 20)}日：高{s['high']}亿 / 低{s['low']}亿 / 中位{s['median']}亿 / 量比{s['volume_ratio']}")
    
    nb = cap.get("northbound", {})
    if "summary" in nb:
        s = nb["summary"]
        ratio = s.get("ratio", {})
        shares = s.get("shares", {})
        trend = nb.get("trend", {})
        lines.append(f"  北向持股({s['period']}，{s['trading_days']}日): {ratio.get('current')}% (高{ratio['high']}% / 低{ratio['low']}%)")
        lines.append(f"  持股量: {shares.get('current', 0):,}股 | 趋势: {trend.get('signal', '')}")
    
    # 主力资金 (东财push2被封，暂不可用)
    lines.append(f"  主力资金流：数据源封锁，待解锁")
    
    # 融资融券 (接口挂起)
    lines.append(f"  融资融券：接口不稳定，暂跳过")
    
    # 股东变动 (Item 11)
    sh_changes = cap.get("shareholder_changes", {})
    if sh_changes.get("changes"):
        sig = sh_changes.get("signal", "neutral")
        sig_label = {"increase": "增持为主", "decrease": "减持为主", "neutral": "增减持平"}.get(sig, sig)
        lines.append(f"  大股东变动: {sig_label} (近5条: 增{sh_changes.get('recent_increase',0)}/减{sh_changes.get('recent_decrease',0)})")
        for ch in sh_changes["changes"][:3]:
            lines.append(f"    [{ch['date']}] {ch['shareholder']}: {ch['change']} ({ch['method']})")

    # 舆情
    sent_sig = sent.get("signal", "")
    sent_label = sent.get("label", "")
    sent_posts = sent.get("post_count", 0)
    sent_news = sent.get("news_count", 0)
    lines.append(f"\n【舆情】{sent_sig} ({sent_label})  热帖={sent_posts}条  新闻={sent_news}条")
    for p in sent.get("raw_posts", [])[:3]:
        lines.append(f"  💬 {p.get('title', '')[:40]}")
    for n in sent.get("news", [])[:3]:
        date = n.get("date", "")
        media = n.get("media", "")
        title = n.get("title", "")[:40]
        lines.append(f"  📰 [{date}] {media}: {title}")

    # 分析师评级
    ratings = sent.get("analyst_ratings", {})
    summary = ratings.get("summary", {})
    if summary.get("total", 0) > 0:
        consensus = summary.get("consensus", "")
        buy = summary.get("buy", 0)
        overweight = summary.get("overweight", 0)
        hold = summary.get("hold", 0)
        sell = summary.get("sell", 0)
        lines.append(f"\n【分析师评级】{consensus} ({summary['total']}份研报)")
        lines.append(f"  买入={buy} 增持={overweight} 持有={hold} 减持/卖出={sell}")
        eps_this = summary.get("avg_eps_this_year")
        eps_next = summary.get("avg_eps_next_year")
        if eps_this or eps_next:
            eps_parts = []
            if eps_this:
                eps_parts.append(f"今年EPS={eps_this}元")
            if eps_next:
                eps_parts.append(f"明年EPS={eps_next}元")
            lines.append(f"  一致预期: {' | '.join(eps_parts)}")
        for r in ratings.get("reports", [])[:3]:
            lines.append(f"  📊 [{r['date']}] {r['org']}({r['rating']}): {r['title'][:35]}")

    lines.append("")
    print("\n".join(lines))


def print_brief(data):
    b = data.get("basic", {})
    out = {
        "symbol": data.get("symbol"),
        "name": b.get("name"),
        "price": b.get("price"),
        "change": b.get("change_pct"),
        "pe": b.get("pe"),
    }
    print(json.dumps(out, ensure_ascii=False))


def print_concept_report(data: dict):
    """打印概念板块分析报告"""
    if "error" in data:
        print(data["error"])
        return
    
    print(f"\\n{'='*50}")
    print(f"  🔥 概念板块扫描 Top 10 (来源: {data.get('source', 'Sina')})")
    print(f"{'='*50}")
    
    for i, c in enumerate(data.get("concepts", []), 1):
        pct = c.get("pct", 0)
        pct_str = f"+{pct:.2f}%" if pct > 0 else f"{pct:.2f}%"
        status = c.get("trend", {}).get("status", "neutral")
        leader = c.get("leader", "")
        
        print(f"\\n{i}. {c['name']} ({pct_str})")
        print(f"   领涨股：{leader}")
        print(f"   状态：{status} | {c.get('trend', {}).get('reason', '')}")
        
    print(f"\\n{'='*50}")


if __name__ == "__main__":
    main()
