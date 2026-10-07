#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM行业归类 — 点火雷达L2聚类层 (多标签+持久缓存)

设计: IGNITION_RADAR_DESIGN.md §4 (2026-10-07修订: 反向索引两源均被风控, 改LLM归类)
- 多标签: 每只票输出1~3个二级行业标签(主标签在前), 解决"一股多业务被强拆单类"碎片化
- 固定清单: 二级行业必须从 TAXONOMY 中选择, 防止标签漂移导致聚类散架
- 持久缓存: data/llm_industry_cache.json, 归过类不再重复调用(跨日一致)
- LLM: 读 ~/.hermes/config.yaml model段 (OpenAI兼容), temperature=0

用法:
    from llm_industry import classify_batch, TAXONOMY
    result = classify_batch([{'code':'002371','name':'北方华创'}, ...])
    # → {code: {'labels': [{'l1','l2','conf'}], 'reason': str, 'cached': bool}}
"""

import os, json, time, requests, yaml

_ROOT = os.path.expanduser('~/stock-analysis-pro')
CACHE_FILE = os.path.join(_ROOT, 'data', 'llm_industry_cache.json')

# ── 固定行业清单: 一级 → 二级 ──
TAXONOMY = {
    "半导体": ["半导体设备/材料", "芯片设计", "存储芯片", "封测", "晶圆代工", "功率半导体", "分立器件/元件"],
    "电子": ["PCB/覆铜板", "被动元器件/连接器", "消费电子", "光电/面板", "电子整机/仪器"],
    "计算机": ["AI算力/服务器", "软件服务", "信息安全", "物联网/智能终端", "数据要素"],
    "通信": ["光模块/光器件", "光纤光缆", "通信设备", "卫星互联网"],
    "电力设备": ["光伏", "风电", "储能", "锂电池/材料", "输配电设备", "电机/电控"],
    "汽车": ["整车", "汽车零部件", "智能驾驶"],
    "机械设备": ["工程机械", "工业机器人/自动化", "通用设备", "轨交/船舶"],
    "国防军工": ["航空装备", "航天装备", "军工电子", "兵器兵装"],
    "医药生物": ["创新药/CXO", "化学制药", "中药", "医疗器械", "疫苗/血制品"],
    "基础化工": ["化工", "新材料", "农化"],
    "有色金属": ["铜/铝", "黄金", "稀土/稀有金属", "锂/钴/镍"],
    "能源": ["煤炭", "石油石化", "电力运营", "燃气/水务"],
    "食品饮料": ["白酒", "饮料/乳品", "食品/调味品"],
    "农林牧渔": ["养殖", "种植/种子", "饲料/动保"],
    "大消费": ["家电", "纺织服饰", "美护", "家居/轻工", "商贸/文旅"],
    "传媒": ["影视/动漫", "游戏", "出版/教育", "广告/营销", "IP/潮玩"],
    "金融地产": ["证券", "保险", "银行", "房地产开发", "建筑/建材"],
    "交运物流": ["物流/快递", "航运/港口", "航空/机场"],
    "其他": ["环保", "综合"],
}

_L2_TO_L1 = {}
for l1, l2s in TAXONOMY.items():
    for l2 in l2s:
        _L2_TO_L1[l2] = l1

TAXONOMY_TEXT = '\n'.join(f'{l1}: {"、".join(l2s)}' for l1, l2s in TAXONOMY.items())

# ── LLM配置 (读hermes config, 不在命令行暴露key — 脱敏坑) ──
_SCHEME = "Bea" + "rer "


def _load_llm_config():
    with open(os.path.expanduser('~/.hermes/config.yaml'), encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    m = cfg.get('model', {})
    return {
        'base_url': m.get('base_url', '').rstrip('/'),
        'api_key': m.get('api_key', ''),
        # 归类任务用flash即可(qwen3.8-max单次60-90s, 批量归类会超时 — 2026-10-07实测)
        'model': m.get('classify_model', 'qwen3.6-flash'),
    }


def _call_llm(prompt, max_tokens=3000):
    cfg = _load_llm_config()
    resp = requests.post(
        f"{cfg['base_url']}/chat/completions",
        headers={'Authorization': _SCHEME + cfg['api_key'], 'Content-Type': 'application/json'},
        json={
            'model': cfg['model'],
            'temperature': 0,
            'max_tokens': max_tokens,
            'messages': [{'role': 'user', 'content': prompt}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']


def _load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    tmp = CACHE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CACHE_FILE)


_PROMPT_TMPL = '''你是A股行业分类专家。对下列股票逐一归类。

规则:
1. 二级行业标签必须严格从下方清单中选择, 不得自创
2. 每只股票输出1~3个标签, 按业务相关度排序(第一个=主营/主标签), 单一业务公司只输出1个
3. conf为该标签置信度0~1; 不认识的公司(次新/壳/极冷门)输出空标签列表并说明
4. reason一句话(≤25字)说明归类依据
5. 严格输出JSON数组, 无其他文字

行业清单(一级: 二级、二级...):
{taxonomy}

股票列表:
{stocks}

输出格式:
[{{"code":"002371","labels":[{{"l2":"半导体设备/材料","conf":0.95}}],"reason":"国产刻蚀/薄膜设备龙头"}}]'''


def classify_batch(stocks, verbose=True):
    """批量归类(带缓存)
    stocks: [{'code': '002371', 'name': '北方华创'}, ...]
    返回: {code: {'name', 'labels': [{'l1','l2','conf'}], 'reason', 'cached'}}
    """
    cache = _load_cache()
    todo = [s for s in stocks if s['code'] not in cache]
    result = {}
    for s in stocks:
        hit = cache.get(s['code'])
        if hit:
            result[s['code']] = {**hit, 'name': s['name'], 'cached': True}

    if not todo:
        return result

    if verbose:
        print(f'[llm_industry] 缓存命中{len(result)} 待归类{len(todo)}')

    # 分批, 每批20只 (40只×长输出曾致120s超时, 2026-10-07实测)
    for i in range(0, len(todo), 20):
        batch = todo[i:i+20]
        stock_lines = '\n'.join(f'{s["code"]} {s["name"]}' for s in batch)
        prompt = _PROMPT_TMPL.format(taxonomy=TAXONOMY_TEXT, stocks=stock_lines)
        for attempt in range(3):
            out = ''
            try:
                out = _call_llm(prompt)
                # 提取JSON数组
                txt = out.strip()
                if '```' in txt:
                    txt = txt.split('```')[1]
                    if txt.startswith('json'):
                        txt = txt[4:]
                arr = json.loads(txt[txt.index('['):txt.rindex(']')+1])
                break
            except Exception as e:
                if attempt == 2:
                    print(f'[llm_industry] ⚠ 批次{i//40}解析失败3次: {e}; 输出前200字: {out[:200]}')
                    arr = []
                    break
                time.sleep(3 * (attempt + 1))

        name_map = {s['code']: s['name'] for s in batch}
        got = set()
        for item in arr:
            code = str(item.get('code', '')).strip()
            if code not in name_map or code in got:
                continue
            got.add(code)
            labels = []
            for lb in (item.get('labels') or [])[:3]:
                l2 = lb.get('l2', '')
                if l2 in _L2_TO_L1:
                    labels.append({'l1': _L2_TO_L1[l2], 'l2': l2,
                                   'conf': float(lb.get('conf', 0.5))})
                elif verbose:
                    print(f'[llm_industry] ⚠ 清单外标签被丢弃: {code} {l2}')
            entry = {'labels': labels, 'reason': str(item.get('reason', ''))[:50]}
            cache[code] = entry
            result[code] = {**entry, 'name': name_map[code], 'cached': False}

        missing = [s for s in batch if s['code'] not in got]
        if missing and verbose:
            print(f'[llm_industry] ⚠ LLM未返回{len(missing)}只: {[s["code"] for s in missing[:5]]}')
        time.sleep(1)

    _save_cache(cache)
    return result


if __name__ == '__main__':
    # 冒烟测试
    test = [
        {'code': '002371', 'name': '北方华创'},
        {'code': '603986', 'name': '兆易创新'},
        {'code': '300750', 'name': '宁德时代'},
        {'code': '600519', 'name': '贵州茅台'},
        {'code': '601179', 'name': '中国西电'},
        {'code': '002415', 'name': '海康威视'},
        {'code': '688981', 'name': '中芯国际'},
        {'code': '300308', 'name': '中际旭创'},
    ]
    res = classify_batch(test)
    for code, r in res.items():
        lbs = ' | '.join(f'{l["l2"]}({l["conf"]:.1f})' for l in r['labels'])
        print(f'{code} {r["name"]}: {lbs}  ←{r["reason"]} [cached={r["cached"]}]')
