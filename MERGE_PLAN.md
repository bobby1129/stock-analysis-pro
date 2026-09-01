# 三项目合并执行计划

> 创建时间: 2026-07-16
> 目标: 将 stock_review + etf-options-analyzer 合并进 stock-analysis-pro

## 一、合并前状态

### 项目A: stock-analysis-pro (主项目，合并目标)
- 路径: `/home/cat/stock-analysis-pro/`
- Git: `bobby1129/stock-analysis-pro` (main分支, clean)
- CLI命令: `analyze`, `market`, `concept`, `analyze-all`, `add`, `rm`, `list`
- 模板: `stock_report.html`, `concept_report.html`, `market_report.html`
- 依赖: `akshare, requests, pyyaml, jinja2, playwright`

### 项目B: stock_review (每日复盘，被合并)
- 路径: `/home/cat/stock_review/`
- 文件清单(7个py + config + data):
  - `run_review.py` (35行) — 入口，调fetch_all→generate_html
  - `fetch_data.py` (499行) — 核心: 指数行情+涨跌停(akshare)+持仓+自选股+宏观(美债/汇率/商品)
  - `fetch_concept_fundflow.py` (68行) — 概念资金流push2直连(硬编码Cookie)
  - `fetch_market_breadth.py` (62行) — Playwright从DOM抓涨跌家数
  - `fetch_market_data.py` (92行) — Playwright统一抓涨跌家数+概念资金流
  - `generate_html.py` (408行) — 手写HTML拼接(非Jinja2)
  - `manage_portfolio.py` (160行) — 持仓CRUD
  - `config.json` — portfolio(5只: 603893/600887/689009/000876/603501) + indices(4个)
  - `data/latest.json` — 缓存数据
  - `output/` — 历史HTML报告(20260609~20260715)
- Cron: `6c7b513b6407`, 每工作日17:00, `cd /home/cat/stock_review && python3 run_review.py`
- 硬编码Cookie: fetch_data.py和fetch_concept_fundflow.py各自有一份(相同值)

### 项目C: etf-options-analyzer (期权分析，被合并)
- 路径: `/tmp/etf-options-analyzer/`
- 文件清单(13个py):
  - `collectors/options.py` — 新浪期权51字段行情(UNDERLYINGS常量)
  - `collectors/etf_kline.py` — 新浪ETF日K线
  - `collectors/greeks.py` — akshare Greeks(T-1)
  - `analysis/hv.py` — HV20/HV60计算
  - `analysis/seller.py` — 卖方指标排名
  - `analysis/buyer.py` — 买方指标排名
  - `analysis/smile.py` — 微笑曲线+SVG坐标预算
  - `analysis/scanner.py` — 编排器(采集→计算→过滤→排名)
  - `core/cli.py` (95行) — CLI入口(scan/hv命令)
  - `core/html_renderer.py` (69行) — Jinja2渲染+平值IV计算
  - `templates/report.html` — 期权报告模板
  - `requirements.txt` — requests, akshare, jinja2, pyyaml
- 无配置文件(无Cookie需求)

---

## 二、合并后目标架构

```
stock-analysis-pro/
├── collectors/               # 采集层
│   ├── quote.py              # [已有] 腾讯/新浪行情
│   ├── finance.py            # [已有] 财务数据
│   ├── flow.py               # [已有] 资金流
│   ├── info.py               # [已有] 公司信息
│   ├── sentiment.py          # [已有] 舆情
│   ├── em_concept.py         # [已有] 东财概念push2+Cookie
│   ├── em_browser.py         # [已有] Playwright东财
│   ├── macro.py              # [已有] 宏观数据
│   ├── cache.py              # [已有] 统一缓存
│   ├── concept.py            # [已有] 概念相关
│   ├── options.py            # [新增] ← etf-options/collectors/options.py
│   ├── etf_kline.py          # [新增] ← etf-options/collectors/etf_kline.py
│   ├── greeks.py             # [新增] ← etf-options/collectors/greeks.py
│   └── breadth.py            # [新增] ← stock_review涨跌家数(Playwright)
│
├── analysis/                 # 维度层(单指标计算)
│   ├── technical.py          # [已有]
│   ├── fundamental.py        # [已有]
│   ├── valuation.py          # [已有]
│   ├── capital.py            # [已有]
│   ├── sentiment.py          # [已有]
│   ├── company.py            # [已有]
│   ├── scorer.py             # [已有]
│   ├── concept.py            # [已有]
│   ├── concept_rank.py       # [已有]
│   ├── macro.py              # [已有]
│   ├── hv.py                 # [新增] ← etf-options/analysis/hv.py
│   ├── seller.py             # [新增] ← etf-options/analysis/seller.py
│   ├── buyer.py              # [新增] ← etf-options/analysis/buyer.py
│   └── smile.py              # [新增] ← etf-options/analysis/smile.py
│
├── plans/                    # 编排层(完整策略流程)
│   ├── stock_analysis.py     # [已有] 个股分析
│   ├── concept_analysis.py   # [已有] 概念分析
│   ├── daily_review.py       # [已有] 宏观概览
│   ├── daily_report.py       # [新增] 每日复盘 ← 吸收stock_review全部逻辑
│   └── options_scan.py       # [新增] ← etf-options/analysis/scanner.py
│
├── core/
│   ├── cli.py                # [修改] 新增review/options/portfolio子命令
│   └── html_renderer.py      # [已有] 统一渲染
│
├── templates/
│   ├── base.html             # [已有]
│   ├── stock_report.html     # [已有]
│   ├── concept_report.html   # [已有]
│   ├── market_report.html    # [已有]
│   ├── review_report.html    # [新增] 每日复盘模板(Jinja2重写)
│   ├── options_report.html   # [新增] ← etf-options/templates/report.html
│   └── components/           # [已有] 共享组件
│
├── config/
│   ├── __init__.py           # [已有] load_config()
│   ├── config.yaml           # [修改] 新增portfolio+indices字段
│   └── config.example.yaml   # [修改] 新增portfolio+indices模板
│
├── data/
│   ├── watchlist.json        # [已有]
│   ├── concept_cache.json    # [已有]
│   └── portfolio.json        # [已移除] 持仓统一在 config.yaml
│
├── output/                   # [新增] 统一输出目录(原stock_review/output/迁移)
│
├── MERGE_PLAN.md             # 本文档
├── PROGRESS.md               # [修改] 记录合并进度
├── DESIGN.md                 # [修改] 更新架构图
└── requirements.txt          # [不变] 已包含所有依赖
```

---

## 三、执行步骤

### 步骤1: 复制etf-options文件到主项目
```bash
# collectors (3个文件)
cp /tmp/etf-options-analyzer/collectors/options.py /home/cat/stock-analysis-pro/collectors/options.py
cp /tmp/etf-options-analyzer/collectors/etf_kline.py /home/cat/stock-analysis-pro/collectors/etf_kline.py
cp /tmp/etf-options-analyzer/collectors/greeks.py /home/cat/stock-analysis-pro/collectors/greeks.py

# analysis (4个文件)
cp /tmp/etf-options-analyzer/analysis/hv.py /home/cat/stock-analysis-pro/analysis/hv.py
cp /tmp/etf-options-analyzer/analysis/seller.py /home/cat/stock-analysis-pro/analysis/seller.py
cp /tmp/etf-options-analyzer/analysis/buyer.py /home/cat/stock-analysis-pro/analysis/buyer.py
cp /tmp/etf-options-analyzer/analysis/smile.py /home/cat/stock-analysis-pro/analysis/smile.py

# plan (1个文件，重命名)
cp /tmp/etf-options-analyzer/analysis/scanner.py /home/cat/stock-analysis-pro/plans/options_scan.py

# template (1个文件)
cp /tmp/etf-options-analyzer/templates/report.html /home/cat/stock-analysis-pro/templates/options_report.html

# html_renderer辅助函数(平值IV计算) → 合并到core/html_renderer.py
# (手动合并calc_atm_ivs函数)
```

### 步骤2: 修改迁入文件的import路径
etf-options原文件使用 `from collectors.xxx import ...` 和 `from analysis.xxx import ...`
迁入后目录结构一致，import无需修改。但需验证:
- `options_scan.py`(原scanner.py)的import路径是否正确
- 各analysis文件的内部import是否交叉引用

### 步骤3: 创建collectors/breadth.py
从stock_review的`fetch_market_breadth.py`和`fetch_market_data.py`提取:
- Playwright加载东财中心页面
- 拦截`ulist.np/get`响应获取涨跌家数(f104~f108字段)
- 输出: `{up, down, flat, limit_up, limit_down}`

### 步骤4: 创建plans/daily_report.py
吸收stock_review全部逻辑:
```
def run(verbose=True) -> dict:
    1. collectors/quote.py → 批量获取指数行情(上证/深证/创业板/科创50)
    2. collectors/breadth.py → 涨跌家数
    3. collectors/em_concept.py → 概念资金流Top10
    4. collectors/quote.py → 持仓股行情
    5. collectors/quote.py → 自选股行情
    6. collectors/macro.py → 宏观快照(美债/汇率/商品)
    7. 汇总输出dict

def format_report(data) -> str:
    文本格式化
```

数据来源映射:
| stock_review原实现 | 合并后调用 |
|---|---|
| fetch_data.py → 指数行情(腾讯) | collectors/quote.py → batch_quotes() |
| fetch_data.py → 涨跌停(akshare) | collectors/breadth.py(Playwright) |
| fetch_data.py → 持仓行情(腾讯) | collectors/quote.py → batch_quotes() |
| fetch_data.py → 宏观(akshare) | collectors/macro.py → global_macro() |
| fetch_concept_fundflow.py → push2 | collectors/em_concept.py(已有) |
| fetch_market_breadth.py → Playwright | collectors/breadth.py(新建) |
| generate_html.py → 手写HTML | templates/review_report.html(Jinja2) |

### 步骤5: 创建templates/review_report.html
将generate_html.py的手写HTML改为Jinja2模板:
- 暗色主题(与stock_report/concept_report统一)
- 移动端优先
- 区块: 指数概览 + 市场宽度 + 概念资金流 + 持仓明细 + 宏观快照

### 步骤6: 持仓管理迁移
- 从stock_review/config.json提取portfolio → data/portfolio.json
- config.yaml新增portfolio和indices字段
- CLI新增`portfolio add/rm/list/update`子命令(吸收manage_portfolio.py逻辑)

### 步骤7: 修改core/cli.py
新增子命令:
```
review              → plans/daily_report.py → 每日复盘HTML
options scan        → plans/options_scan.py → 期权扫描
options hv          → 查看各品种HV
portfolio add/rm/list → 持仓管理
```

### 步骤8: 统一输出目录
- 创建 `output/` 目录
- review报告输出到 `output/review_YYYYMMDD.html`
- 其他报告也从cache/改到output/(可选，后续处理)

### 步骤9: 更新Cron Job
Cron `6c7b513b6407` 的prompt改为:
```
cd /home/cat/stock-analysis-pro && python3 core/cli.py review --html
然后读取输出的HTML路径，发送给用户。
```

### 步骤10: 更新文档
- DESIGN.md: 更新架构图，新增collectors/options/breadth和plans/daily_report/options_scan
- PROGRESS.md: 记录合并操作
- config.example.yaml: 新增portfolio/indices模板
- SKILL.md: 新增review/options/portfolio命令说明

### 步骤11: 提交推送
```bash
cd /home/cat/stock-analysis-pro
git add -A
git commit -m "feat: 合并stock_review + etf-options-analyzer到主项目"
https_proxy=http://127.0.0.1:10809 git push origin main
```

### 步骤12: 迁移历史报告
```bash
cp /home/cat/stock_review/output/*.html /home/cat/stock-analysis-pro/output/
```

### 步骤13: Skill瘦身(后续单独做)
- 主SKILL.md精简到~300行
- API详情移到references/
- 合并etf-options skill内容

---

## 四、配置合并方案

### config.yaml新增字段
```yaml
eastmoney:
  cookie: "..."
  ut: "8dec03ba335b81bf4ebdf7b29ec27d15"

# proxy:
#   https: "http://127.0.0.1:10809"

# 持仓管理 (从stock_review/config.json迁移)
portfolio:
  - code: "603893"
    name: "瑞芯微"
    cost: 0
    shares: 0
    note: "SoC芯片设计"
  - code: "600887"
    name: "伊利股份"
    cost: 0
    shares: 0
    note: "乳制品"
  - code: "689009"
    name: "九号公司"
    cost: 0
    shares: 0
    note: "智能短交通"
  - code: "000876"
    name: "新 希 望"
    cost: 0
    shares: 0
    note: "农牧食品"
  - code: "603501"
    name: "韦尔股份"
    cost: 0
    shares: 0
    note: "豪威集团"

# 复盘跟踪的指数
indices:
  - code: "sh000001"
    name: "上证指数"
  - code: "sz399001"
    name: "深证成指"
  - code: "sz399006"
    name: "创业板指"
  - code: "sh000688"
    name: "科创50"
```

---

## 五、合并后Cron运行机制

### 每日复盘 (每工作日17:00)
```
Cron触发 → Agent执行:
  cd /home/cat/stock-analysis-pro && python3 core/cli.py review --html
    ↓
  plans/daily_report.py::run()
    1. collectors/quote.py → 4个指数行情
    2. collectors/breadth.py → 涨跌家数(Playwright)
    3. collectors/em_concept.py → 概念资金流Top10(push2+Cookie)
    4. collectors/quote.py → 5只持仓股行情
    5. collectors/quote.py → 自选股行情
    6. collectors/macro.py → 宏观快照
    ↓
  core/html_renderer.py → templates/review_report.html → Jinja2渲染
    ↓
  输出: output/review_YYYYMMDD.html
    ↓
  Agent通过微信发送 MEDIA:/home/cat/stock-analysis-pro/output/review_YYYYMMDD.html
```

### 概念映射季度检查 (不变)
```
Cron fc5b765ff023: 每季度17日10:00
  cd /home/cat/stock-analysis-pro && python3 scripts/check_concept_mapping.py
```

---

## 六、风险与回退

1. **Playwright冲突**: stock_review和stock-analysis-pro都启动Playwright，合并后共享。如果daily_report和concept_analysis在同一次cron中运行，需确保浏览器实例不冲突(各自独立launch+close即可)。
2. **Cookie过期**: 合并后只维护一份Cookie(config.yaml)，比之前更好管理。
3. **回退方案**: stock_review目录暂不删除，保留作为回退。确认合并后稳定运行1周再清理。
