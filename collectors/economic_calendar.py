# -*- coding: utf-8 -*-
"""经济日历采集器 — 读取硬编码的日历配置，筛选未来N天事件

数据源: data/economic_calendar.json (硬编码，定期更新)
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List


def load_economic_calendar(days_ahead: int = 14) -> Dict:
    """加载经济日历，筛选未来N天内的事件
    
    Args:
        days_ahead: 向前看多少天，默认14天（2周）
    
    Returns:
        {
            "events": [...],  # 未来事件列表
            "total_count": N,
            "high_importance_count": N,
            "date_range": "YYYY-MM-DD ~ YYYY-MM-DD"
        }
    """
    calendar_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "economic_calendar.json"
    )
    
    if not os.path.exists(calendar_path):
        return {
            "events": [],
            "total_count": 0,
            "high_importance_count": 0,
            "date_range": "",
            "error": "economic_calendar.json not found"
        }
    
    try:
        with open(calendar_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {
            "events": [],
            "total_count": 0,
            "high_importance_count": 0,
            "date_range": "",
            "error": str(e)
        }
    
    all_events = data.get("events", [])
    
    # 筛选未来N天内的事件
    now = datetime.now()
    start_date = now.date()
    end_date = start_date + timedelta(days=days_ahead)
    
    filtered_events = []
    for event in all_events:
        try:
            event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
            if start_date <= event_date <= end_date:
                # 判断事件状态：已发布/待发布
                event_datetime = datetime.strptime(
                    f"{event['date']} {event.get('time', '00:00')}",
                    "%Y-%m-%d %H:%M"
                )
                if event_datetime < now:
                    status = "published"
                else:
                    status = "upcoming"
                
                # 重要性标签
                importance = event.get("importance", 1)
                if importance >= 5:
                    importance_label = "🔴"
                elif importance >= 4:
                    importance_label = "🟡"
                else:
                    importance_label = "⚪"
                
                filtered_events.append({
                    "date": event["date"],
                    "time": event.get("time", ""),
                    "country": event.get("country", ""),
                    "indicator": event.get("indicator", ""),
                    "importance": importance,
                    "importance_label": importance_label,
                    "previous": event.get("previous", ""),
                    "forecast": event.get("forecast", ""),
                    "impact": event.get("impact", ""),
                    "status": status,
                })
        except Exception as e:
            continue
    
    # 按日期+时间排序
    filtered_events.sort(key=lambda x: (x["date"], x["time"]))
    
    # 统计高重要性事件数量
    high_importance_count = sum(1 for e in filtered_events if e["importance"] >= 5)
    
    # 日期范围
    if filtered_events:
        date_range = f"{filtered_events[0]['date']} ~ {filtered_events[-1]['date']}"
    else:
        date_range = ""
    
    return {
        "events": filtered_events,
        "total_count": len(filtered_events),
        "high_importance_count": high_importance_count,
        "date_range": date_range,
        "last_updated": data.get("last_updated", ""),
    }


def format_calendar_text(calendar_data: Dict) -> str:
    """格式化日历为文本（用于日志/调试）"""
    lines = []
    lines.append(f"📅 未来经济日历 ({calendar_data.get('date_range', 'N/A')})")
    lines.append(f"  共 {calendar_data.get('total_count', 0)} 个事件，其中 {calendar_data.get('high_importance_count', 0)} 个高重要性")
    
    events = calendar_data.get("events", [])
    if not events:
        lines.append("  暂无重要事件")
        return "\n".join(lines)
    
    # 按日期分组
    current_date = None
    for event in events:
        if event["date"] != current_date:
            current_date = event["date"]
            lines.append(f"\n  [{current_date}]")
        
        status_icon = "✓" if event["status"] == "published" else "○"
        country = "🇺🇸" if event["country"] == "US" else ("🇨🇳" if event["country"] == "CN" else "")
        lines.append(f"    {status_icon} {event['importance_label']} {event['time']} {country} {event['indicator']}")
        if event.get("previous"):
            lines.append(f"       前值: {event['previous']}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # 测试
    calendar = load_economic_calendar(days_ahead=14)
    print(format_calendar_text(calendar))
