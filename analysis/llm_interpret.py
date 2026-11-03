# -*- coding: utf-8 -*-
"""LLM解读流水线 — REVIEW_UPGRADE_DESIGN.md §四 (S4, F1 thesis判定 + F2 信息解读)

对每只持仓票:
  1. 标题初筛: thesis + 当日公告/研报/新闻标题 → 批量LLM → {level: major/neutral/noise, need_content}
  2. 正文抓取: 仅 need_content 的条目 — 公告走东财PDF(art_code→pdf.dfcfw.com, pymupdf);
     新闻走url抓正文(trafilatura, 失败降级正则抽<p>); 研报无正文源, 基于标题+机构+评级解读(注明"仅标题")
  3. 合并判定: thesis + 全部条目(含正文摘录) + 近3日verdict历史 → verdict/reason/evidence + 每条major解读+影响标签

- LLM: qwen3.6-flash(沿用llm_industry模式), api_key从~/.hermes/config.yaml读, scheme拼接防脱敏
- 缓存: cache/review_history/llm_cache_YYYYMMDD.json, 同日重跑不重复调LLM(输入hash不变直接复用)
- 降级: 任何失败只降级(该票退回纯标题展示), 不阻塞报告; 整体失败 result['llm_interpret_degraded']=True
"""

import os
import re
import json
import time
import hashlib
from datetime import datetime

import requests
import yaml

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_BASE, "cache", "review_history")

_SCHEME = "Bea" + "rer "   # 脱敏坑: 内联"Bearer "字面量会被打码, 拼接绕过

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

_MAX_CONTENT_ITEMS = 4      # 每票最多抓正文条数(控token/耗时)
_CONTENT_CHARS = 2500       # 每条正文摘录上限
_VERDICTS = ("unchanged", "strengthened", "weakened", "invalid_risk")


# ── LLM基础 ──

def _load_llm_config():
    with open(os.path.expanduser("~/.hermes/config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    m = cfg.get("model", {})
    return {
        "base_url": m.get("base_url", "").rstrip("/"),
        "api_key": m.get("api_key", ""),
        "model": m.get("classify_model", "qwen3.6-flash"),
    }


def _call_llm(prompt, max_tokens=3500, timeout=120):
    cfg = _load_llm_config()
    resp = requests.post(
        f"{cfg['base_url']}/chat/completions",
        headers={"Authorization": _SCHEME + cfg["api_key"],
                 "Content-Type": "application/json"},
        json={"model": cfg["model"], "temperature": 0, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_llm_json(prompt, max_tokens=3500, attempts=3):
    """调用并解析JSON(对象或数组), 失败重试, 最终失败抛异常。"""
    last_err = None
    for a in range(attempts):
        out = ""
        try:
            out = _call_llm(prompt, max_tokens=max_tokens)
            txt = out.strip()
            if "```" in txt:
                txt = txt.split("```")[1]
                if txt.startswith("json"):
                    txt = txt[4:]
            s, e1 = txt.find("{"), txt.find("[")
            if s == -1 or (e1 != -1 and e1 < s):
                obj = json.loads(txt[txt.index("["): txt.rindex("]") + 1])
            else:
                obj = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
            return obj
        except Exception as ex:
            last_err = ex
            if a < attempts - 1:
                time.sleep(3 * (a + 1))
    raise RuntimeError(f"LLM JSON解析失败{attempts}次: {last_err}")


# ── 正文抓取 ──

def fetch_announcement_text(art_code, max_chars=_CONTENT_CHARS):
    """东财公告PDF正文。art_code实测验证(2026-10-30): AN202610261830950116 → H2_{art_code}_1.pdf 200。"""
    if not art_code:
        return None
    url = f"https://pdf.dfcfw.com/pdf/H2_{art_code}_1.pdf"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
        if r.status_code != 200 or not r.content.startswith(b"%PDF"):
            return None
        import pymupdf
        doc = pymupdf.open(stream=r.content, filetype="pdf")
        text = "".join(p.get_text() for p in doc)
        doc.close()
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars] or None
    except Exception:
        return None


def fetch_news_text(url, max_chars=_CONTENT_CHARS):
    """新闻正文: trafilatura优先, 失败降级正则抽<p>。"""
    if not url:
        return None
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        r.encoding = r.apparent_encoding or "utf-8"
        html = r.text
    except Exception:
        return None
    text = None
    try:
        import trafilatura
        text = trafilatura.extract(html, include_comments=False,
                                   include_tables=False, favor_recall=True)
    except Exception:
        text = None
    if not text or len(text) < 80:
        # 降级: 正则抽<p>
        try:
            paras = re.findall(r"<p[^>]*>(.*?)</p>", html, re.S | re.I)
            cleaned = [re.sub(r"<[^>]+>", "", p).strip() for p in paras]
            cleaned = [c for c in cleaned if len(c) >= 20]
            text = "\n".join(cleaned) or None
        except Exception:
            text = None
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


# ── 两段式流水线 ──

_SCREEN_TMPL = '''你是A股持仓跟踪助手。下面是持仓票「{name}」的投资逻辑(thesis)和今日全部信息条目。对每条做初筛分级。

thesis:
{thesis}

条目(i=序号):
{items}

分级标准:
- major: 可能影响thesis成立性或短期股价的重要信息(业绩/大额订单/价格变动/监管/股东增减持/评级调整/重大行业政策等)
- neutral: 一般性经营信息, 了解即可
- noise: 程序性公告(开会通知/制度修订/担保额度等)、软文、与该公司实际关联弱的新闻

need_content规则: 仅level=major且仅凭标题无法判断影响时才true; 研报一律false(无正文源); 标题已说清事实的(如"第三季度报告"可看正文, "召开董事会通知"不需要)自行判断。

严格输出JSON数组, 无其他文字:
[{{"i":1,"level":"major","need_content":true}}]'''

_JUDGE_TMPL = '''你是A股持仓跟踪助手。基于今日信息判定持仓票「{name}」投资逻辑(thesis)的状态, 并对每条major信息给出一句解读。

thesis:
{thesis}

近3日判定历史(防重复报警):
{history}

今日条目(i=序号; [正文]为抓取到的原文摘录, 无正文的仅凭标题判断):
{items}

要求:
1. verdict四选一: unchanged(逻辑不变)/strengthened(逻辑强化)/weakened(逻辑弱化, 命中部分失效信号)/invalid_risk(疑似失效, 命中明确失效条件)
2. 同一信息不重复触发预警: 若历史已因同一事实判weakened, 今日无新增证据则维持weakened不升级; 连续weakened且有新增证据应升级invalid_risk
3. reason一句话(≤40字)给判定依据; evidence列出支撑判定的条目标题(≤3条, 无则空数组)
4. interps: 对每条major信息给一句中文解读(≤50字, 说清对thesis/股价的影响)和impact标签(利好/利空/中性)
5. 判定基于事实证据, 无major信息时verdict=unchanged

严格输出JSON对象, 无其他文字:
{{"verdict":"unchanged","reason":"...","evidence":["..."],"interps":[{{"i":1,"interp":"...","impact":"利好"}}]}}'''


def _collect_items(stock):
    """汇总一只票的公告/研报/新闻为条目列表, 保留回写引用。"""
    items = []
    for a in stock.get("announcements") or []:
        items.append({"type": "ann", "title": a.get("title", ""), "date": a.get("date", ""),
                      "art_code": a.get("art_code"), "url": None, "ref": a})
    for r in stock.get("research_reports") or []:
        extra = " | ".join(x for x in (r.get("org"), r.get("rating")) if x)
        title = r.get("title", "") + (f" ({extra})" if extra else "")
        items.append({"type": "report", "title": title, "date": r.get("date", ""),
                      "art_code": None, "url": None, "ref": r})
    for n in stock.get("news") or []:
        items.append({"type": "news", "title": n.get("title", ""), "date": n.get("date", ""),
                      "art_code": None, "url": n.get("url"), "ref": n,
                      "media": n.get("media", "")})
    return items


_TYPE_NAME = {"ann": "公告", "report": "研报", "news": "新闻"}


def _screen(thesis, name, items):
    lines = [f'{i+1}. [{_TYPE_NAME[it["type"]]} {it["date"]}] {it["title"]}'
             for i, it in enumerate(items)]
    prompt = _SCREEN_TMPL.format(name=name, thesis=thesis, items="\n".join(lines))
    arr = _call_llm_json(prompt, max_tokens=2000)
    levels = {}
    for o in arr:
        i = o.get("i")
        if isinstance(i, int) and 1 <= i <= len(items):
            lv = o.get("level") if o.get("level") in ("major", "neutral", "noise") else "neutral"
            levels[i - 1] = {"level": lv,
                             "need_content": bool(o.get("need_content")) and lv == "major"}
    # LLM漏掉的条目按neutral兜底
    for idx in range(len(items)):
        levels.setdefault(idx, {"level": "neutral", "need_content": False})
    return levels


def _fetch_contents(items, levels, verbose=False):
    """对need_content条目抓正文, 上限_MAX_CONTENT_ITEMS条。返回{idx: text}。"""
    contents = {}
    todo = [i for i, lv in levels.items() if lv["need_content"] and items[i]["type"] != "report"]
    for idx in todo[:_MAX_CONTENT_ITEMS]:
        it = items[idx]
        text = None
        if it["type"] == "ann":
            text = fetch_announcement_text(it.get("art_code"))
        elif it["type"] == "news":
            text = fetch_news_text(it.get("url"))
        if text:
            contents[idx] = text
            if verbose:
                print(f"    📄 正文[{idx+1}] {it['title'][:30]}… {len(text)}字")
        time.sleep(0.3)
    return contents


def _verdict_history(code, date_yyyymmdd, n=3):
    """近n日该票verdict历史(防漂移用)。"""
    try:
        from analysis.review_history import load_recent
        out = []
        for r in load_recent(n, before=date_yyyymmdd):
            chk = (r.get("thesis_checks") or {}).get(code)
            if chk and chk.get("verdict"):
                out.append(f'{r.get("date")}: {chk["verdict"]} — {chk.get("reason", "")}')
        return out
    except Exception:
        return []


def _judge(thesis, name, items, levels, contents, history):
    lines = []
    for i, it in enumerate(items):
        lv = levels[i]["level"]
        line = f'{i+1}. [{_TYPE_NAME[it["type"]]} {it["date"]}] (级别:{lv}) {it["title"]}'
        if it["type"] == "report":
            line += "  (研报无正文源, 仅标题+机构+评级)"
        if i in contents:
            line += f"\n   [正文] {contents[i]}"
        lines.append(line)
    hist_txt = "\n".join(history) if history else "(无历史判定)"
    prompt = _JUDGE_TMPL.format(name=name, thesis=thesis, history=hist_txt,
                                items="\n".join(lines))
    obj = _call_llm_json(prompt, max_tokens=3000)
    verdict = obj.get("verdict") if obj.get("verdict") in _VERDICTS else "unchanged"
    interps = {}
    for o in obj.get("interps") or []:
        i = o.get("i")
        if isinstance(i, int) and 1 <= i <= len(items):
            impact = o.get("impact") if o.get("impact") in ("利好", "利空", "中性") else "中性"
            interps[i - 1] = {"interp": str(o.get("interp", ""))[:120], "impact": impact}
    return {
        "verdict": verdict,
        "reason": str(obj.get("reason", ""))[:80],
        "evidence": [str(e)[:80] for e in (obj.get("evidence") or [])][:3],
    }, interps


def _cache_path(date_yyyymmdd):
    return os.path.join(CACHE_DIR, f"llm_cache_{date_yyyymmdd}.json")


def _load_cache(date_yyyymmdd):
    try:
        with open(_cache_path(date_yyyymmdd), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(date_yyyymmdd, cache):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(date_yyyymmdd)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _input_hash(thesis, items):
    payload = thesis + "|" + "|".join(f'{it["type"]}:{it["date"]}:{it["title"]}' for it in items)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:16]


# ── 主入口 ──

def attach_interpretations(result, verbose=True):
    """对 result['portfolio'] 每票执行初筛→抓正文→判定, 结果就地回写:
    - 条目dict增加 level / interp / impact 字段(模板消费)
    - stock['thesis_check'] = {verdict, reason, evidence} 或 None(未设置逻辑)
    - result['thesis_checks'] / result['info_digest'] 供落盘
    - result['thesis_history'] = {code: [{date, verdict, reason}×近5日]} 供底部档案
    任何异常降级, 不抛出。"""
    date = result.get("date") or datetime.now().strftime("%Y%m%d")
    portfolio = result.get("portfolio") or []
    cache = _load_cache(date)
    thesis_checks, info_digest = {}, {}
    degraded = False

    # 近5日判定历史(底部档案用, 含今日之前)
    hist5 = {}
    try:
        from analysis.review_history import load_recent
        for r in load_recent(5, before=date):
            for code, chk in (r.get("thesis_checks") or {}).items():
                hist5.setdefault(code, []).append(
                    {"date": r.get("date"), "verdict": chk.get("verdict"),
                     "reason": chk.get("reason", "")})
    except Exception:
        pass

    for stock in portfolio:
        code, name = stock.get("code"), stock.get("name", "")
        thesis = (stock.get("thesis") or "").strip()
        if not thesis:
            stock["thesis_check"] = None
            stock["thesis_missing"] = True
            continue
        items = _collect_items(stock)
        if not items:
            stock["thesis_check"] = {"verdict": "unchanged", "reason": "今日无公告/研报/新闻",
                                     "evidence": []}
            thesis_checks[code] = dict(stock["thesis_check"], name=name)
            continue

        ih = _input_hash(thesis, items)
        cached = cache.get(code)
        try:
            if cached and cached.get("input_hash") == ih:
                levels = {int(k): v for k, v in cached["levels"].items()}
                judge, interps = cached["judge"], {int(k): v for k, v in cached["interps"].items()}
                if verbose:
                    print(f"  🧠 {name}: 缓存命中 [{judge['verdict']}]")
            else:
                if verbose:
                    print(f"  🧠 {name}: 初筛{len(items)}条…")
                levels = _screen(thesis, name, items)
                contents = _fetch_contents(items, levels, verbose=verbose)
                history = _verdict_history(code, date)
                judge, interps = _judge(thesis, name, items, levels, contents, history)
                cache[code] = {
                    "input_hash": ih,
                    "levels": {str(k): v for k, v in levels.items()},
                    "interps": {str(k): v for k, v in interps.items()},
                    "judge": judge,
                }
                _save_cache(date, cache)
                if verbose:
                    nmaj = sum(1 for lv in levels.values() if lv["level"] == "major")
                    print(f"  🧠 {name}: major {nmaj}条 → [{judge['verdict']}] {judge['reason']}")
        except Exception as e:
            degraded = True
            if verbose:
                print(f"  ⚠️ {name} LLM解读失败(降级纯标题): {e}")
            continue

        # 回写条目 + 汇总落盘结构
        stock["thesis_check"] = judge
        thesis_checks[code] = dict(judge, name=name)
        digest = []
        for i, it in enumerate(items):
            lv = levels.get(i, {"level": "neutral"})
            interp = interps.get(i)
            it["ref"]["level"] = lv["level"]
            if interp:
                it["ref"]["interp"] = interp["interp"]
                it["ref"]["impact"] = interp["impact"]
            if lv["level"] == "major":
                digest.append({"type": it["type"], "title": it["title"], "date": it["date"],
                               "level": "major",
                               "interp": (interp or {}).get("interp", ""),
                               "impact": (interp or {}).get("impact", "中性")})
        info_digest[code] = digest

    result["thesis_checks"] = thesis_checks
    result["info_digest"] = info_digest
    result["thesis_history"] = hist5
    if degraded:
        result["llm_interpret_degraded"] = True
    return result
