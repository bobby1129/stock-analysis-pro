# -*- coding: utf-8 -*-
"""缓存层 — 同日内数据不重复请求"""

import os
import json
import time
from typing import Any, Optional

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def get(key: str, ttl: int = 3600) -> Optional[Any]:
    """读取缓存，ttl 秒内有效"""
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if not os.path.exists(path):
        return None
    
    with open(path, "r") as f:
        data = json.load(f)
    
    if time.time() - data.get("_ts", 0) > ttl:
        return None
    
    return data.get("_val")


def set(key: str, val: Any, ttl: int = 3600) -> None:
    """写入缓存"""
    path = os.path.join(CACHE_DIR, f"{key}.json")
    with open(path, "w") as f:
        json.dump({"_val": val, "_ts": time.time()}, f)


def clear() -> None:
    """清空所有缓存"""
    for f in os.listdir(CACHE_DIR):
        if f.endswith(".json"):
            os.remove(os.path.join(CACHE_DIR, f))
