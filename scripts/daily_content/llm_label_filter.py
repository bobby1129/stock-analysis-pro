#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM标签净化 — 点火雷达v6 (IGNITION_RADAR_DESIGN.md §12)

问题: 同花顺概念成分表静态粘性(挂了不摘), 泛概念被擦边票撑大
  (2026-10-13实测: AIGC桶19只触发股混有水处理/染料中间体票, 最大子概念覆盖率仅53%)。
方案: 分子侧净化 — LLM按F10主营业务从个股概念标签中剔除无直接营收相关性的,
  只筛不造(输出必须是输入子集, 保持885体系, 下游量比/催化检索无缝)。

属性直通名单(ATTRIBUTE_CONCEPTS): 政策/资质/地域/持仓类标签主营业务看不出来,
  不交LLM判(防误杀), 保留在个股标签上; 但**不参与事件聚合排名**
  (人人可挂, 无资金聚集含义, 否则绝对数量榜被专精特新/一带一路霸屏 — 2026-10-13验证教训)。

缓存:
  - 主营业务 data/stock_business_map.json (collectors.ths_stock_business, TTL 180天)
  - 净化结果 data/llm_label_filter_cache.json (key=code, 标签集hash变了才重判; git不提交)

LLM: qwen3.6-flash, temperature=0, 批20 (复用 llm_industry._call_llm 链路)

用法:
    from llm_label_filter import purify_labels
    purify_labels(stocks)   # 就地写 s['concepts_clean']; s['concepts']保留原始供审计
"""
import os, json, time, hashlib

_ROOT = os.path.expanduser('~/stock-analysis-pro')
CACHE_FILE = os.path.join(_ROOT, 'data', 'llm_label_filter_cache.json')

# ── 属性直通名单 (2026-10-13 全量过375概念定稿) ──
# 政策/地域属性
ATTRIBUTE_CONCEPTS = {
    '一带一路', '西部大开发', '乡村振兴', '雄安新区', '粤港澳大湾区',
    '京津冀一体化', '长三角一体化', '新疆振兴', '数字乡村', '新型城镇化',
    '共同富裕示范区', '统一大市场', '供销社', '土地流转', '特色小镇',
    # 自贸区/新区 (地域属性)
    '上海自贸区', '天津自贸区', '广东自贸区', '福建自贸区', '海南自贸区',
    '黑龙江自贸区', '横琴新区', '中韩自贸区', '自由贸易港',
    # 资质/身份属性
    '专精特新', '中字头股票', '摘帽', '股权转让(并购重组)', 'PPP概念',
    '化债概念(AMC概念)', '独角兽概念', '超级品牌',
    # 指数/持仓/风格属性 (主营业务看不出, LLM判=必误杀)
    '同花顺中特估100', '同花顺出海50', '同花顺新质50', '同花顺漂亮100',
    '同花顺果指数', '高股息精选', '证金持股', '参股保险', '参股券商',
    '参股银行', '国家大基金持股',
    # 地缘事件属性
    '俄乌冲突概念', '海峡两岸', '中俄贸易概念',
}


def is_attribute_concept(name):
    """属性直通标签: 保留在个股标签上, 但不参与事件聚合排名"""
    return name in ATTRIBUTE_CONCEPTS


# ── 净化结果缓存 ──
def _load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    tmp = CACHE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CACHE_FILE)


def _labels_hash(names):
    return hashlib.md5('|'.join(sorted(names)).encode()).hexdigest()[:12]


_PROMPT_TMPL = '''你是A股概念板块审核专家。对下列每只股票, 根据其F10主营业务文本, 从其"候选概念标签"中筛选出与主营业务有直接营收相关性的标签。

规则:
1. 只做减法: 输出必须是候选标签的子集, 严禁新造标签、严禁改写标签名
2. 判断标准: 公司主营业务与该概念有直接的营收/产品/技术相关性才保留; 仅沾边(如"子公司小业务""曾有合作""同地域")一律剔除
3. 主营业务为空或无法判断时, 保留候选中看起来最合理的1~2个, 宁松勿严
4. reason一句话(≤20字)
5. 严格输出JSON数组, 无其他文字

正例: 凡拓数创(主营:数字创意展示、数字孪生、虚拟数字人) 候选[AIGC概念,虚拟现实,乡村振兴,IP经济(谷子经济)] → 保留[AIGC概念,虚拟现实] (数字创意与AIGC/VR直接相关, 乡村振兴无关)
反例: 华骐环保(主营:水处理材料BAF滤料) 候选[AIGC概念,人工智能,乡村振兴] → 保留[乡村振兴] (环保水务与AI无关)

股票列表:
{stocks}

输出格式:
[{{"code":"300827","keep":["AIGC概念","虚拟现实"],"reason":"数字创意直接相关"}}]'''


def _filter_batch(batch, verbose=True):
    """一批(≤20只)调LLM筛选, 返回 {code: {'keep': [...], 'reason': str}}; 失败返回{}"""
    from llm_industry import _call_llm
    lines = []
    for s in batch:
        biz = (s.get('business') or '(空)')[:120]
        cands = [c for c in s['concepts'] if not is_attribute_concept(c)]
        lines.append(f"{s['code']} {s['name']} 主营:{biz} 候选:{json.dumps(cands, ensure_ascii=False)}")
    prompt = _PROMPT_TMPL.format(stocks='\n'.join(lines))
    for attempt in range(3):
        try:
            out = _call_llm(prompt, max_tokens=4000).strip()
            if '```' in out:
                out = out.split('```')[1]
                if out.startswith('json'):
                    out = out[4:]
            arr = json.loads(out[out.index('['):out.rindex(']') + 1])
            result = {}
            for item in arr:
                code = str(item.get('code', '')).strip()
                if code:
                    result[code] = {'keep': item.get('keep') or [],
                                    'reason': str(item.get('reason', ''))[:30]}
            return result
        except Exception as e:
            if verbose:
                print(f'  [label_filter] ⚠ LLM第{attempt+1}次失败: {str(e)[:80]}')
            time.sleep(3 * (attempt + 1))
    return {}


def purify_labels(stocks, verbose=True):
    """就地净化: 为每只stock写 s['concepts_clean'](=LLM保留∩候选 + 属性直通)
    stocks: [{'code','name','concepts'(原始F10标签,已剔宽基桶)}, ...]
    带持久缓存(标签集hash不变不重判); LLM整批失败降级=保留全部非属性标签(宁松勿严)。
    返回统计 {'total','cached','llm','failed'}"""
    from collectors.ths_stock_business import get_or_fetch_business

    todo_all = [s for s in stocks if s.get('concepts')]
    if not todo_all:
        for s in stocks:
            s['concepts_clean'] = []
        return {'total': 0, 'cached': 0, 'llm': 0, 'failed': 0}

    # 主营业务 (180天TTL缓存, 只对需要LLM判的拉)
    cache = _load_cache()
    need_llm = []
    stats = {'total': len(stocks), 'cached': 0, 'llm': 0, 'failed': 0}
    for s in stocks:
        cands = [c for c in (s.get('concepts') or []) if not is_attribute_concept(c)]
        ent = cache.get(s['code'])
        if ent and ent.get('hash') == _labels_hash(cands):
            # 缓存命中: keep∩当前候选(防概念改名/摘牌后残留)
            keep = [c for c in ent.get('keep', []) if c in cands]
            s['concepts_clean'] = keep + [c for c in (s.get('concepts') or [])
                                          if is_attribute_concept(c)]
            s['filter_reason'] = ent.get('reason', '')
            stats['cached'] += 1
        else:
            s['_cands_for_llm'] = cands
            need_llm.append(s)

    if need_llm:
        biz = get_or_fetch_business([s['code'] for s in need_llm], verbose=verbose)
        for s in need_llm:
            s['business'] = biz.get(s['code'], '')
        if verbose:
            print(f'  [label_filter] 待LLM净化{len(need_llm)}只 (缓存命中{stats["cached"]})')
        for i in range(0, len(need_llm), 20):
            batch = need_llm[i:i + 20]
            res = _filter_batch(batch, verbose)
            for s in batch:
                cands = set(s['_cands_for_llm'])
                item = res.get(s['code'])
                if item:
                    keep = [c for c in item['keep'] if c in cands]   # 只筛不造强制
                    reason = item['reason']
                    stats['llm'] += 1
                else:
                    keep = sorted(cands)   # 降级: 全保留
                    reason = '(LLM失败降级)'
                    stats['failed'] += 1
                attr = [c for c in s['concepts'] if is_attribute_concept(c)]
                s['concepts_clean'] = keep + attr
                s['filter_reason'] = reason
                cache[s['code']] = {'hash': _labels_hash(sorted(cands)),
                                    'keep': keep, 'reason': reason,
                                    'updated': time.strftime('%Y%m%d')}
            s2 = None
            time.sleep(1)
        _save_cache(cache)

    for s in stocks:
        s.pop('_cands_for_llm', None)
        s.setdefault('concepts_clean', [])
    return stats
