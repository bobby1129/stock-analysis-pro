# -*- coding: utf-8 -*-
"""行业异动筛选计划 — 涨幅>5%股票的行业归类与指标分析

流程:
  1. 获取涨幅>5%的股票列表 (新浪分页接口)
  2. 获取主营业务 (同花顺F10)
  3. 行业归类 (二级行业体系)
  4. 对前5大行业，获取每只股票的详细指标
  5. 生成HTML报告

指标说明:
  - 当日涨幅: 今日涨跌幅
  - 连涨天数: 从最新K线往前数，连续上涨的天数 (收盘价>前一日收盘价)
  - 量比: 今日成交量/过去5日平均成交量
  - 60日分位: 当前价格在60日价格区间的位置 (0%=最低, 100%=最高)
  - 250日分位: 当前价格在250日价格区间的位置
  - 换手率: 今日成交量/流通股本
  - 成交额: 今日成交金额(万元)
  - 振幅: (最高价-最低价)/昨收 * 100%
  - 市盈率: PE(TTM)

用法:
    from plans.industry_screener import run
    data = run()
    from core.html_renderer import render
    html_path = render(data, "industry_screener")
"""

import sys
import os
import json
import time
import re
import requests
from datetime import datetime
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 全局请求会话 ──
SESSION = requests.Session()
from requests.adapters import HTTPAdapter
_adapter = HTTPAdapter(max_retries=3, pool_connections=10, pool_maxsize=10)
SESSION.mount("https://", _adapter)
SESSION.mount("http://", _adapter)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Proxy for Google News
PROXY = {"http": "http://127.0.0.1:10809", "https": "http://127.0.0.1:10809"}


def safe_request(url, timeout=10, headers=None, max_retries=2):
    """带重试的HTTP请求"""
    if headers is None:
        headers = {"User-Agent": UA}
    for attempt in range(max_retries + 1):
        try:
            r = SESSION.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200 or r.content:
                return r.content
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2)
            continue
    return None


# ── 第一步: 获取涨幅>5%的股票 ──

def is_beijing_stock(code):
    """判断是否是北交所股票
    
    北交所代码特征: 920xxx, 8xxxxx, 430xxx
    """
    if not code:
        return False
    return (code.startswith("920") or 
            code.startswith("8") or 
            code.startswith("430"))


def fetch_stocks_gt5(limit=500):
    """获取涨幅>5%的股票列表 (新浪分页接口)
    
    返回: [{code, name, changepercent, trade, volume, amount}, ...]
    注意: 自动剔除北交所股票
    """
    headers = {"User-Agent": UA, "Referer": "https://finance.sina.com.cn/"}
    all_stocks = []
    page = 1
    num_per_page = 100
    beijing_count = 0
    
    while len(all_stocks) < limit:
        url = f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={page}&num={num_per_page}&sort=changepercent&asc=0&node=hs_a"
        try:
            raw = safe_request(url, headers=headers, timeout=10)
            if not raw:
                break
            data = json.loads(raw)
            if not data:
                break
            
            # 筛选涨幅>5%
            for s in data:
                code = s.get("code", "")
                # 剔除北交所股票
                if is_beijing_stock(code):
                    beijing_count += 1
                    continue
                if s.get("changepercent", 0) > 5:
                    all_stocks.append({
                        "code": code,
                        "symbol": s.get("symbol", ""),
                        "name": s.get("name", ""),
                        "changepercent": s.get("changepercent", 0),
                        "trade": s.get("trade", 0),
                        "volume": s.get("volume", 0),
                        "amount": s.get("amount", 0),
                    })
            
            # 如果最后一个股票的涨幅已经<5%，可以停止
            if data[-1].get("changepercent", 0) < 5:
                break
            page += 1
            if page > 10:  # 防止无限循环
                break
        except Exception as e:
            print(f"  [警告] 获取第{page}页失败: {e}")
            break
    
    if beijing_count > 0:
        print(f"  已剔除 {beijing_count} 只北交所股票")
    
    return all_stocks


# ── 第二步: 获取主营业务 ──

def fetch_main_business(code):
    """获取股票主营业务 (同花顺F10)
    
    返回: 主营业务文本 或 ""
    """
    url = f"http://basic.10jqka.com.cn/{code}/company.html"
    headers = {
        "User-Agent": UA,
        "Referer": "http://basic.10jqka.com.cn/"
    }
    try:
        raw = safe_request(url, headers=headers, timeout=10)
        if not raw:
            return ""
        try:
            html = raw.decode("gbk")
        except:
            html = raw.decode("utf-8", errors="replace")
        
        # 提取主营业务 - 在<span>标签内
        match = re.search(r"主营业务：</strong>\s*<span>([^<]+)</span>", html)
        if match:
            return match.group(1).strip()
    except Exception as e:
        pass
    return ""


def fetch_all_business(stocks):
    """批量获取主营业务"""
    results = []
    for i, s in enumerate(stocks):
        biz = fetch_main_business(s["code"])
        results.append({
            **s,
            "main_business": biz,
        })
        if (i + 1) % 20 == 0:
            print(f"  获取主营业务: {i+1}/{len(stocks)}")
        time.sleep(0.1)  # 防止请求过快
    return results


# ── 第三步: 行业归类 ──

# 两级分类体系：一级 → 二级（最终输出到二级）
INDUSTRY_HIERARCHY = {
    "电子": {
        "PCB": ["印制电路板", "PCB", "印制线路板"],
        "覆铜板/铜箔": ["覆铜板", "铜箔", "粘结片"],
        "被动元器件": ["电容器", "电容", "电阻", "瓷介电容", "薄膜电容", "阻容"],
        "连接器": ["连接器", "互连产品", "连接线", "精密结构件"],
        "电子元器件": ["电子元器件", "电子元件", "电子材料"],
    },
    "通信": {
        "光纤光缆": ["光纤", "光缆", "光纤预制棒", "光纤环"],
        "射频器件": ["射频", "同轴电缆"],
        "光模块/光器件": ["光通信", "光器件", "光磁"],
        "通信设备": ["载波通信", "网络总线", "数据电缆", "通信"],
    },
    "计算机": {
        "AI算力": ["AI芯片", "智能算力", "算力", "人工智能"],
        "物联网": ["物联网", "RFID", "智慧城市", "能源互联网"],
        "信息安全": ["信息安全", "网络可视化", "数据安全", "网络与信息安全"],
        "软件服务": ["软件开发", "系统集成", "数智", "数据应用"],
    },
    "传媒": {
        "影视": ["电影", "影视", "电视节目", "媒体广告", "IP运营"],
        "数字媒体": ["数字阅读", "数字化体验", "短剧", "版权"],
        "数字电视": ["数字电视"],
    },
    "电力设备": {
        "光伏": ["光伏", "太阳能", "光伏玻璃", "光伏组件", "光伏胶膜"],
        "风电": ["风电", "风能"],
        "储能": ["储能", "氢能", "锂电池"],
        "电力运营": ["电力", "供电", "供热", "发电", "水电", "火力发电"],
        "输配电设备": ["输配电", "电线电缆", "泵", "控制设备"],
    },
    "国防军工": {
        "航空装备": ["航空", "飞机", "刹车系统"],
        "航天装备": ["航天", "碳/碳复合材料"],
        "兵器兵装": ["武器", "坦克", "战车", "火炮", "精确制导", "特品"],
        "军工电子": ["军工电子", "光电信息装备"],
    },
    "汽车": {
        "整车": ["整车", "汽车整车"],
        "零部件": ["汽车", "底盘", "零部件", "模具", "金属结构件"],
    },
    "机械设备": {
        "工程机械": ["工程机械", "流体控制", "自动化"],
        "矿山设备": ["矿山", "矿山监控"],
        "轨道交通设备": ["铁路信号", "轨道交通"],
        "纺织设备": ["纺织机械", "拉幅定形机"],
        "检测设备": ["工业检测", "分析测量仪器"],
    },
    "医药生物": {
        "医疗器械": ["医疗器械", "内镜", "诊疗器械", "手术缝线"],
        "化学制药": ["药品", "制药", "多肽"],
        "医药包装": ["医药包装"],
    },
    "美容护理": {
        "个护用品": ["个人卫生用品", "卫生用品"],
    },
    "轻工制造": {
        "家居": ["木地板", "全屋定制", "家居", "木饰面"],
        "卫浴": ["卫浴", "水系统"],
    },
    "建筑材料": {
        "玻纤": ["玻璃纤维", "玻纤", "芳纶纸"],
        "玻璃": ["玻璃", "药用玻璃", "浮法玻璃"],
        "复合材料": ["复合材料", "高分子复合材料", "光学膜"],
    },
    "基础化工": {
        "化工": ["化工", "助剂"],
        "塑料": ["塑料", "薄膜", "塑料包装"],
        "橡胶": ["橡胶", "软管"],
        "新材料": ["新材料", "高分子", "树脂"],
    },
    "钢铁": {
        "钢管": ["焊接钢管", "钢管"],
    },
    "公用事业": {
        "水务": ["自来水", "水务", "水处理", "排水"],
        "固废处理": ["垃圾", "清扫", "收集", "运输", "处理"],
        "环保工程": ["生态", "环保"],
    },
    "交通运输": {
        "物流": ["仓储", "配送"],
        "农产品流通": ["农产品", "果蔬", "水果", "蔬菜"],
    },
    "社会服务": {
        "旅游": ["旅游", "景区"],
        "教育": ["驾驶培训", "教育"],
    },
    "商贸零售": {
        "百货": ["百货", "购物中心", "超市", "零售", "连锁"],
    },
    "家用电器": {
        "小家电": ["小家电"],
        "消费电子": ["消费电子"],
    },
    "建筑装饰": {
        "建筑工程": ["建筑装饰", "工程", "建设", "勘察设计", "工程总承包"],
    },
    "有色金属": {
        "铜": ["铜"],
        "铝": ["铝"],
        "稀有金属": ["稀有金属", "硬质合金"],
    },
    "其他": {
        "纺织": ["纺织", "芳纶"],
        "超细纤维": ["超细纤维"],
        "线缆": ["线缆"],
        "物业管理": ["物业"],
    },
}


def fetch_google_news_rss(keyword, max_items=10):
    """通过Google News RSS获取新闻
    
    返回: [{"title": str, "date": str, "source": str}, ...]
    """
    try:
        # Google News RSS URL
        encoded_kw = keyword.replace(" ", "+")
        url = f"https://news.google.com/rss/search?q={encoded_kw}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        
        r = SESSION.get(url, proxies=PROXY, timeout=10, headers={"User-Agent": UA})
        if r.status_code != 200:
            return []
        
        # 解析RSS XML
        root = ET.fromstring(r.content)
        items = root.findall(".//item")[:max_items]
        
        news = []
        for item in items:
            title = item.find("title").text if item.find("title") is not None else ""
            pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
            source = item.find("source").text if item.find("source") is not None else ""
            
            # 解析日期: "Mon, 15 Sep 2026 10:30:00 GMT" → "9月15日"
            date_short = ""
            if pub_date:
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(pub_date)
                    date_short = f"{dt.month}月{dt.day}日"
                except:
                    # 降级: 取前几个字符
                    date_short = pub_date[:10]
            
            if title:
                news.append({
                    "title": title,
                    "date": date_short,
                    "source": source
                })
        
        return news
    except Exception as e:
        print(f"  [警告] Google News搜索失败: {e}")
        return []


def fetch_industry_news(industries, verbose=True):
    """为每个行业获取相关新闻 + 生成深度分析
    
    industries: [{"l1": str, "l2": str, "stocks": [...]}, ...]
    返回: industries列表，每个行业增加 "news" / "catalyst" / "timeline" / "value_chain" 字段
    """
    if verbose:
        print("\n[5/5] 获取行业新闻与深度分析...")
    
    for i, ind in enumerate(industries):
        keyword = ind["l2"]
        if verbose:
            print(f"  {i+1}/{len(industries)}: {keyword}")
        
        news = fetch_google_news_rss(keyword, max_items=10)
        ind["news"] = news
        
        # 从新闻+股票指标生成深度分析
        ind["catalyst"] = extract_catalyst(news, ind)
        ind["timeline"] = build_timeline(news, ind)
        ind["value_chain"] = build_value_chain(ind)
        
        time.sleep(0.5)
    
    return industries


def extract_catalyst(news, ind):
    """从新闻标题中提取核心催化主题
    
    返回: [{"theme": str, "items": [{"title": str, "date": str}], "summary": str}, ...]
    """
    if not news:
        return []
    
    # 关键词聚类：按新闻标题中的高频关键词分组
    # 定义行业相关的催化关键词
    catalyst_keywords = {
        "政策": ["政策", "规划", "意见", "补贴", "扶持", "扶持", "国务院", "发改委", "工信部", "财政部", "央行", "证监会"],
        "技术突破": ["突破", "首创", "量产", "交付", "落地", "发布", "研发", "创新", "新一代"],
        "需求增长": ["需求", "订单", "增长", "扩产", "紧缺", "涨价", "供不应求", "景气"],
        "资本动作": ["投资", "融资", "收购", "并购", "上市", "增持", "回购", "分红"],
        "行业事件": ["展会", "论坛", "峰会", "大会", "签约", "合作", "战略"],
        "海外动态": ["海外", "国际", "美国", "欧洲", "日本", "韩国", "全球", "出口", "进口"],
        "供给变化": ["产能", "投产", "扩产", "减产", "停产", "检修", "开工率"],
        "价格变动": ["涨价", "降价", "价格", "成本", "毛利", "利润"],
    }
    
    # 对每条新闻分类到催化主题
    theme_items = {}  # theme_name -> [news_item, ...]
    for n in news:
        title = n.get("title", "")
        matched = False
        for theme, keywords in catalyst_keywords.items():
            for kw in keywords:
                if kw in title:
                    if theme not in theme_items:
                        theme_items[theme] = []
                    theme_items[theme].append(n)
                    matched = True
                    break
            if matched:
                break
        if not matched:
            # 未匹配的新闻归入"其他动态"
            if "其他动态" not in theme_items:
                theme_items["其他动态"] = []
            theme_items["其他动态"].append(n)
    
    # 按新闻数量排序，取top3主题
    sorted_themes = sorted(theme_items.items(), key=lambda x: len(x[1]), reverse=True)
    
    catalysts = []
    for theme, items in sorted_themes[:3]:
        if theme == "其他动态" and len(items) < 2:
            continue
        # 生成摘要
        summary_parts = []
        for item in items[:2]:
            summary_parts.append(item["title"][:40])
        summary = "；".join(summary_parts)
        
        catalysts.append({
            "theme": theme,
            "count": len(items),
            "items": [{"title": n["title"], "date": n["date"]} for n in items[:3]],
            "summary": summary,
        })
    
    return catalysts


def build_timeline(news, ind):
    """从新闻构建行情时间线
    
    返回: [{"date": str, "events": [{"title": str, "stocks": [str]}]}, ...]
    """
    if not news:
        return []
    
    # 按日期分组
    date_events = {}
    stock_names = [s.get("name", "") for s in ind.get("stocks", [])]
    
    for n in news:
        date = n.get("date", "")
        title = n.get("title", "")
        
        if date not in date_events:
            date_events[date] = []
        
        # 检查新闻中是否提到行业内股票
        mentioned_stocks = []
        for sname in stock_names:
            if sname and sname in title:
                mentioned_stocks.append(sname)
        
        date_events[date].append({
            "title": title,
            "stocks": mentioned_stocks,
        })
    
    # 按日期排序（最近的在前）
    timeline = []
    for date, events in sorted(date_events.items(), key=lambda x: x[0], reverse=True):
        timeline.append({
            "date": date,
            "events": events[:3],  # 每天最多3条
            "is_highlight": len(events) >= 2 or any(
                any(kw in e["title"] for kw in ["涨停", "暴涨", "大涨", "突破", "新高"])
                for e in events
            ),
        })
    
    return timeline[:7]  # 最多7天


def build_value_chain(ind):
    """基于股票指标构建有价值环节分析
    
    返回: {"tiers": [{"tier": int, "label": str, "color": str, "stocks": [...], "logic": str}], "watch_direction": str}
    """
    stocks = ind.get("stocks", [])
    if not stocks:
        return {"tiers": [], "watch_direction": ""}
    
    l2 = ind.get("l2", "")
    l1 = ind.get("l1", "")
    
    # 计算每只股票的综合得分
    scored = []
    for s in stocks:
        score = 0
        reasons = []
        
        # 连涨天数 (权重高)
        consec = s.get("consecutive_days", 0)
        if consec >= 3:
            score += 30
            reasons.append(f"连涨{consec}天")
        elif consec >= 2:
            score += 20
            reasons.append(f"连涨{consec}天")
        elif consec >= 1:
            score += 10
        
        # 量比 (资金强度)
        vol_ratio = s.get("volume_ratio", 0) or 0
        if vol_ratio >= 3:
            score += 25
            reasons.append(f"量比{vol_ratio:.1f}倍")
        elif vol_ratio >= 2:
            score += 15
            reasons.append(f"量比{vol_ratio:.1f}倍")
        elif vol_ratio >= 1.5:
            score += 8
        
        # 60日分位 (位置)
        pct60 = s.get("percentile_60d", 0) or 0
        if pct60 >= 80:
            score += 15
            reasons.append("60日高位")
        elif pct60 >= 60:
            score += 8
        elif pct60 <= 20:
            score += 5
            reasons.append("60日低位")
        
        # 250日分位
        pct250 = s.get("percentile_250d", 0) or 0
        if pct250 >= 80:
            score += 10
        elif pct250 <= 20:
            score += 5
            reasons.append("250日低位")
        
        # 涨幅
        pct = s.get("changepercent", 0) or 0
        if pct >= 9.5:
            score += 20
            reasons.append("涨停")
        elif pct >= 7:
            score += 15
        elif pct >= 5:
            score += 10
        
        # 换手率
        turnover = s.get("turnoverrate", 0) or 0
        if turnover >= 10:
            score += 10
            reasons.append(f"换手{turnover:.1f}%")
        
        scored.append({
            "code": s.get("code", ""),
            "name": s.get("name", ""),
            "score": score,
            "reasons": reasons,
            "changepercent": pct,
            "consecutive_days": consec,
        })
    
    # 按得分排序
    scored.sort(key=lambda x: x["score"], reverse=True)
    
    # 分梯队
    tiers = []
    
    # 第一梯队: 得分>=50 或 涨停+连涨
    tier1 = [s for s in scored if s["score"] >= 50 or (s["changepercent"] >= 9.5 and s["consecutive_days"] >= 2)]
    if tier1:
        tiers.append({
            "tier": 1,
            "label": "核心受益",
            "color": "tier-1",
            "stocks": tier1[:5],
            "logic": "资金持续流入+趋势确认，短线动能最强",
        })
    
    # 第二梯队: 得分30-50 或 放量突破
    tier2 = [s for s in scored if s not in tier1 and (s["score"] >= 30 or s.get("volume_ratio", 0) >= 2.5)]
    if tier2:
        tiers.append({
            "tier": 2,
            "label": "弹性标的",
            "color": "tier-2",
            "stocks": tier2[:5],
            "logic": "放量启动或补涨逻辑，关注确认信号",
        })
    
    # 第三梯队: 其余
    tier3 = [s for s in scored if s not in tier1 and s not in tier2]
    if tier3:
        tiers.append({
            "tier": 3,
            "label": "跟涨观察",
            "color": "tier-3",
            "stocks": tier3[:5],
            "logic": "板块联动或低位补涨，需等待催化",
        })
    
    # 观察方向
    watch_direction = _generate_watch_direction(l1, l2, stocks)
    
    return {"tiers": tiers, "watch_direction": watch_direction}


def _generate_watch_direction(l1, l2, stocks):
    """基于行业生成观察方向建议"""
    # 根据行业特征给出方向性建议
    direction_map = {
        "半导体": "关注上游设备/材料国产替代进展，以及下游AI/汽车需求拉动",
        "PCB": "关注AI服务器用板需求增量、高端HDI产能扩张节奏",
        "光伏": "关注产业链价格触底信号、海外订单恢复情况",
        "风电": "关注海风项目开工节奏、大兆瓦机型渗透率提升",
        "锂电": "关注固态电池产业化进度、储能需求放量",
        "新能源车": "关注智驾渗透率提升、出口放量节奏",
        "汽车零部件": "关注智能化(线控底盘/空悬)渗透率、海外产能布局",
        "化工": "关注原油价格传导、下游需求复苏节奏",
        "医药": "关注创新药管线进展、集采政策边际变化",
        "军工": "关注订单落地节奏、新型号批产进度",
        "消费电子": "关注AI终端渗透率、新品发布周期",
        "电力运营": "关注电力市场化改革、绿电交易溢价",
        "白酒": "关注批价走势、库存去化进度",
        "房地产": "关注政策放松力度、销售数据拐点",
        "证券": "关注市场成交量中枢、政策催化(并购重组/降佣)",
        "人工智能": "关注大模型应用落地、算力需求持续性",
        "软件": "关注信创订单节奏、AI+应用商业化进展",
        "通信": "关注5G-A/6G技术演进、算力网络建设",
        "汽车": "关注智驾渗透率、出口放量节奏",
    }
    
    # 先匹配二级行业，再匹配一级
    base = direction_map.get(l2, "")
    if not base:
        base = direction_map.get(l1, f"关注{l2}板块龙头的业绩兑现与估值切换")
    
    # 根据股票特征补充
    avg_pct = sum(s.get("changepercent", 0) for s in stocks) / max(len(stocks), 1)
    high_vol = sum(1 for s in stocks if (s.get("volume_ratio", 0) or 0) >= 2)
    
    if high_vol >= len(stocks) * 0.5:
        base += "；板块整体放量，资金关注度较高"
    if avg_pct >= 8:
        base += "；短线涨幅较大，注意追高风险"
    
    return base


def classify_stock(business_text):
    """归类股票到二级行业
    
    返回: (一级行业, 二级行业, 匹配关键词) 或 (None, None, None)
    """
    for l1, l2_dict in INDUSTRY_HIERARCHY.items():
        for l2, keywords in l2_dict.items():
            for kw in keywords:
                if kw in business_text:
                    return l1, l2, kw
    return None, None, None


def classify_all(stocks):
    """批量归类"""
    results = []
    for s in stocks:
        l1, l2, kw = classify_stock(s.get("main_business", ""))
        results.append({
            **s,
            "industry_l1": l1,
            "industry_l2": l2,
            "keyword": kw,
        })
    return results


# ── 第四步: 获取详细指标 ──

def tencent_detail(code):
    """获取腾讯详情 (PE/PB/市值/振幅/量比)"""
    prefix = "sh" if code.startswith("6") else "sz"
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    raw = safe_request(url, timeout=6)
    if not raw:
        return {}
    try:
        text = raw.decode("gbk")
    except:
        text = raw.decode("utf-8", errors="replace")
    if "~" not in text:
        return {}
    parts = text.split("~")
    if len(parts) < 50:
        return {}
    return {
        "name": parts[1],
        "code": parts[2],
        "price": float(parts[3]) if parts[3] else 0,
        "prev_close": float(parts[4]) if parts[4] else 0,
        "volume": float(parts[36]) if len(parts) > 36 and parts[36] else 0,
        "amount": float(parts[37]) if len(parts) > 37 and parts[37] else 0,  # 成交额(万)
        "pe": float(parts[52]) if len(parts) > 52 and parts[52] else None,
        "pb": float(parts[46]) if len(parts) > 46 and parts[46] else None,
        "total_mv": float(parts[45]) if len(parts) > 45 and parts[45] else None,  # 总市值(亿)
        "float_mv": float(parts[44]) if len(parts) > 44 and parts[44] else None,  # 流通市值(亿)
        "amplitude": float(parts[43]) if len(parts) > 43 and parts[43] else 0,  # 振幅%
        "volume_ratio": float(parts[49]) if len(parts) > 49 and parts[49] else 0,  # 量比
        "turnover_rate": float(parts[38]) if len(parts) > 38 and parts[38] else 0,  # 换手率%
        "change_pct": float(parts[32]) if len(parts) > 32 and parts[32] else 0,
        "high": float(parts[33]) if len(parts) > 33 and parts[33] else 0,
        "low": float(parts[34]) if len(parts) > 34 and parts[34] else 0,
    }


def tencent_kline(code, days=250):
    """获取腾讯K线数据"""
    prefix = "sh" if code.startswith("6") else "sz"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{days},qfq"
    raw = safe_request(url, timeout=6)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except:
        return []
    stock_data = data.get("data", {}).get(f"{prefix}{code}", {})
    klines = stock_data.get("qfqday", stock_data.get("day", []))
    if not klines:
        for k, v in stock_data.items():
            if isinstance(v, list) and len(v) > 0:
                klines = v
                break
    return klines


def calc_consecutive_up_days(klines):
    """计算连涨天数
    
    规则: 从最新K线往前数，连续上涨的天数 (收盘价>前一日收盘价)
    注意: 如果今天下跌，则连涨天数为0
    
    返回: 连涨天数 (int)
    """
    if not klines or len(klines) < 2:
        return 0
    
    # klines格式: [[date, open, close, high, low, volume], ...]
    # 按日期正序排列，最后一根是最新
    consecutive = 0
    for i in range(len(klines) - 1, 0, -1):
        curr_close = float(klines[i][2])
        prev_close = float(klines[i-1][2])
        if curr_close > prev_close:
            consecutive += 1
        else:
            break
    
    return consecutive


def calc_price_percentile(klines, current_price, window):
    """计算价格分位
    
    返回: 当前价格在window日价格区间的位置 (0-100)
    """
    if not klines or len(klines) < window:
        return None
    
    # 取最近window根K线的收盘价
    closes = [float(k[2]) for k in klines[-window:]]
    min_price = min(closes)
    max_price = max(closes)
    
    if max_price == min_price:
        return 50  # 如果价格没变，返回50
    
    percentile = (current_price - min_price) / (max_price - min_price) * 100
    return round(percentile, 1)


def fetch_stock_indicators(code):
    """获取单只股票的详细指标"""
    # 腾讯详情
    detail = tencent_detail(code)
    
    # K线数据
    klines = tencent_kline(code, days=260)  # 多取一些，确保有250日
    
    # 计算指标
    current_price = detail.get("price", 0)
    
    # 连涨天数
    consecutive_days = calc_consecutive_up_days(klines)
    
    # 60日分位
    percentile_60 = calc_price_percentile(klines, current_price, 60)
    
    # 250日分位
    percentile_250 = calc_price_percentile(klines, current_price, 250)
    
    return {
        "code": code,
        "name": detail.get("name", ""),
        "price": current_price,
        "change_pct": detail.get("change_pct", 0),
        "volume": detail.get("volume", 0),
        "amount": detail.get("amount", 0),  # 成交额(万)
        "pe": detail.get("pe"),
        "pb": detail.get("pb"),
        "total_mv": detail.get("total_mv"),  # 总市值(亿)
        "float_mv": detail.get("float_mv"),  # 流通市值(亿)
        "amplitude": detail.get("amplitude", 0),  # 振幅%
        "volume_ratio": detail.get("volume_ratio", 0),  # 量比
        "turnover_rate": detail.get("turnover_rate", 0),  # 换手率%
        "consecutive_days": consecutive_days,  # 连涨天数
        "percentile_60": percentile_60,  # 60日分位
        "percentile_250": percentile_250,  # 250日分位
    }


def fetch_indicators_for_industry(stocks, max_stocks=20):
    """获取行业内所有股票的指标 (最多max_stocks只)"""
    results = []
    for i, s in enumerate(stocks[:max_stocks]):
        try:
            indicators = fetch_stock_indicators(s["code"])
            results.append({
                **s,
                **indicators,
            })
            if (i + 1) % 5 == 0:
                print(f"    获取指标: {i+1}/{min(len(stocks), max_stocks)}")
            time.sleep(0.2)  # 防止请求过快
        except Exception as e:
            print(f"    [警告] {s['code']} 获取指标失败: {e}")
    return results


# ── 主流程 ──

def run(verbose=True):
    """执行行业异动筛选计划
    
    返回: {
        "date": "2024-01-01",
        "total_stocks": 100,
        "classified_stocks": 98,
        "industry_summary": [{l1, l2, count, stocks}, ...],
        "top5_industries": [{l1, l2, count, stocks: [{code, name, ...}]}, ...],
    }
    """
    if verbose:
        print("=" * 60)
        print("行业异动筛选")
        print("=" * 60)
    
    # 1. 获取涨幅>5%的股票
    if verbose:
        print("\n[1/4] 获取涨幅>5%的股票...")
    stocks = fetch_stocks_gt5(limit=500)
    if verbose:
        print(f"  共获取 {len(stocks)} 只股票")
    
    # 2. 获取主营业务
    if verbose:
        print("\n[2/4] 获取主营业务...")
    stocks = fetch_all_business(stocks)
    
    # 3. 行业归类
    if verbose:
        print("\n[3/4] 行业归类...")
    stocks = classify_all(stocks)
    
    # 统计归类情况
    from collections import defaultdict
    by_l2 = defaultdict(list)
    unclassified = []
    
    for s in stocks:
        if s["industry_l2"]:
            key = f"{s['industry_l1']} → {s['industry_l2']}"
            by_l2[key].append(s)
        else:
            unclassified.append(s)
    
    # 按数量排序 (排除"其他")
    sorted_l2 = sorted(
        [(k, v) for k, v in by_l2.items() if "其他" not in k],
        key=lambda x: -len(x[1])
    )
    
    # 行业汇总
    industry_summary = []
    for l1_l2, group in sorted_l2:
        l1, l2 = l1_l2.split(" → ")
        industry_summary.append({
            "l1": l1,
            "l2": l2,
            "count": len(group),
            "stocks": [{"code": s["code"], "name": s["name"], "changepercent": s["changepercent"]} for s in group],
        })
    
    # 4. 获取前5大行业的详细指标
    if verbose:
        print("\n[4/5] 获取前5大行业的详细指标...")
    
    top5_industries = []
    for l1_l2, group in sorted_l2[:5]:
        l1, l2 = l1_l2.split(" → ")
        if verbose:
            print(f"  {l1} → {l2} ({len(group)}只)")
        
        # 获取详细指标
        stocks_with_indicators = fetch_indicators_for_industry(group, max_stocks=20)
        
        top5_industries.append({
            "l1": l1,
            "l2": l2,
            "count": len(group),
            "stocks": stocks_with_indicators,
        })
    
    # 5. 获取top5行业的新闻动态
    top5_industries = fetch_industry_news(top5_industries, verbose=verbose)
    
    # 构建结果
    result = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_stocks": len(stocks),
        "classified_stocks": len(stocks) - len(unclassified),
        "unclassified_count": len(unclassified),
        "industry_summary": industry_summary,
        "top5_industries": top5_industries,
        "unclassified": [{"code": s["code"], "name": s["name"], "changepercent": s["changepercent"], "main_business": s["main_business"]} for s in unclassified],
    }
    
    if verbose:
        print("\n" + "=" * 60)
        print(f"完成! 共{len(stocks)}只股票, 已归类{len(stocks)-len(unclassified)}只")
        print("=" * 60)
    
    return result


if __name__ == "__main__":
    # 直接运行测试
    data = run(verbose=True)
    
    # 保存JSON
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    json_path = os.path.join(output_dir, "industry_screener.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\nJSON已保存: {json_path}")
    
    # 生成HTML
    try:
        from core.html_renderer import render
        html_path = render(data, "industry_screener")
        print(f"HTML已生成: {html_path}")
    except Exception as e:
        print(f"HTML生成失败: {e}")
