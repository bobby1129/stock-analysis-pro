"""交易日检查（周末 + 节假日）

原理：周末直接否；工作日对比新浪上证指数行情日期与今天。
节假日休市时新浪返回的仍是上一交易日日期 → 判定非交易日。
行情接口异常时保守放行（宁可生成旧数据也不误杀正常交易日），并打印警告。

与 scripts/daily_content/run_all.py 中 is_trading_day() 逻辑一致（该脚本已验证可用）。
"""
import requests
from datetime import datetime


def is_trading_day():
    """返回 (ok: bool, reason: str)"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False, '周末休市'
    try:
        r = requests.get('https://hq.sinajs.cn/list=sh000001',
                         headers={'User-Agent': 'Mozilla/5.0',
                                  'Referer': 'https://finance.sina.com.cn'},
                         timeout=10)
        r.encoding = 'gbk'
        # 格式: var hq_str_sh000001="上证指数,开盘,昨收,现价,最高,最低,...,日期,时间,...";
        parts = r.text.split('"')[1].split(',')
        quote_date = parts[30]  # YYYY-MM-DD
        today = now.strftime('%Y-%m-%d')
        if quote_date == today:
            return True, f'交易日（行情日期 {quote_date}）'
        return False, f'非交易日：行情日期为 {quote_date}，今天是 {today}（节假日休市）'
    except Exception as e:
        return True, f'⚠ 行情接口异常({e})，保守放行按交易日处理'
