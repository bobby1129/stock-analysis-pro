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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 全局请求会话 ──
SESSION = requests.Session()
from requests.adapters import HTTPAdapter
_adapter = HTTPAdapter(max_retries=3, pool_connections=10, pool_maxsize=10)
SESSION.mount("https://", _adapter)
SESSION.mount("http://", _adapter)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


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
        print("\n[4/4] 获取前5大行业的详细指标...")
    
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
