# Stock Analysis Pro — 设计文档

> v3.6 | 2026-07-20
> Repo: https://github.com/bobby1129/stock-analysis-pro

---

## 1. 项目定位

**Stock Analysis Pro** 是一个完整的 A 股多维分析 + ETF 期权分析工具，作为 Hermes Agent 的 skill 使用。

四大核心能力：
1. **个股全维度分析** — 技术面/基本面/估值面/资金面/舆情面 → 综合评分
2. **概念板块扫描** — 热板排行/趋势定性/新闻归因/机会筛选
3. **宏观市场概览** — 国际宏观/国内宏观/事件驱动/综合研判
4. **ETF 期权扫描** — 标的波动率全景 + 卖方风险收益排序（D/R/S 框架）

---

## 2. 架构

```
┌─────────────────────────────────────────────────────────┐
│                    CLI (core/cli.py)                     │
│     analyze | concept | market | review | options        │
├─────────────────────────────────────────────────────────┤
│                  Plans (编排层)                           │
│  stock_analysis.py | concept_analysis.py | daily_report.py | options_scan.py │
├────────────────────────┬────────────────────────────────┤
│   Analysis (维度层)     │   Collectors (采集层)           │
│   technical.py         │   quote.py (行情/K线)           │
│   fundamental.py       │   finance.py (财务/分红/预测)   │
│   valuation.py         │   flow.py (成交额/北向)         │
│   capital.py           │   info.py (公司F10)             │
│   sentiment.py         │   sentiment.py (股吧+互动易+新闻+评级) │
│   company.py           │   em_concept.py (概念采集v7)    │
│   scorer.py (综合评分)  │   em_browser.py (共享Playwright) │
│   concept.py (概念分析)  │   concept.py (概念排行+K线+新闻) │
│   concept_rank.py       │   macro.py (宏观数据)          │
│   macro.py             │   options.py (期权数据)        │
│   breadth.py           │   breadth.py (涨跌家数)        │
│   scorer.py (综合评分)  │   cache.py (缓存)              │
├────────────────────────┼────────────────────────────────┤
│   Templates (HTML报告)  │   Config (配置管理)            │
│   base.html            │   config/__init__.py           │
│   stock_report.html    │   config/config.yaml           │
│   concept_report.html  │   config/config.example.yaml   │
│   market_report.html   │                                │
│   review_report.html   │                                │
│   options_report.html  │                                │
└────────────────────────┴────────────────────────────────┘
```

### 数据流

```
CLI command
  → Plan (编排: 按顺序调用多个 Analysis)
    → Analysis (维度计算: 调用 Collector 获取原始数据, 计算指标/信号)
      → Collector (数据采集: HTTP/Playwright 获取数据, 返回结构化数据)
```

---

## 3. 模块清单

### 3.1 Collectors (采集层)

| 模块 | 行数 | 数据源 | 功能 | 状态 |
|------|------|--------|------|------|
| `quote.py` | 190 | 腾讯(qt.gtimg.cn) + 新浪(money.finance) | 实时行情(价格/PE/PB/市值/换手率) + 历史K线(250日OHLCV) | ✅ |
| `finance.py` | 105 | akshare (THS财务摘要) | ROE/毛利率/净利率/负债率/营收增速/净利增速/EPS/每股净资产/经营现金流/分红历史/机构盈利预测 | ✅ |
| `flow.py` | 156 | 腾讯行情(推算) + akshare(北向) | 成交额统计(当日/20日高低中位/量比) + 北向持股(持股比例/趋势) | ✅ |
| `info.py` | 56 | 东财F10 + 同花顺(akshare) | 公司全称/行业/实控人/法人/主营业务/产品类型/公司简介 | ✅ |
| `sentiment.py` | 280 | 东财股吧+互动易+新闻搜索+分析师评级 | 股吧热帖 + 互动易问答 + 东财新闻 + 分析师评级(reportapi) | ✅ |
| `em_concept.py` | 770 | 东财push2+Cookie+JSONP | 概念列表(按资金流入排序) + 成分股(按涨幅,前100只) + 离线增量缓存 | ✅ |
| `em_browser.py` | 376 | Playwright Chromium | 共享浏览器会话(F10/股吧/搜索/研报)，避免重复启动浏览器 | ✅ |
| `concept.py` | 215 | 东财push2 HTTP API | 概念排行 + 成分股(100只) + 新闻 | ✅ |
| `macro.py` | 354 | akshare + 新浪 | global_macro(美债/利率) + 新浪(金银油) + domestic_macro(CPI/PMI/M2/LPR) + zt_pool(涨停复盘) | ✅ |
| `options.py` | ~495 | 新浪(hq.sinajs.cn) + 腾讯(qt.gtimg.cn) | 期权合约列表 + 实时行情(权利金) + 标的K线 + HV60计算 + D/R/S风险指标 + BS胜率(hv60_std) | ✅ |
| `cache.py` | 40 | 本地JSON文件 | TTL缓存(默认1小时)，减少重复请求 | ✅ |

**em_concept.py 核心逻辑 (v7)**:
- **采集方式**: HTTP API + Cookie + JSONP — 直接请求push2.eastmoney.com，无需浏览器
- **概念排序**: 按资金流入(f62)排序，过滤非行业概念（风格/市值/地域类），保留top_n个
- **成分股获取**: HTTP API请求，按涨幅(f3)排序获取前100只，间隔1秒避免限流
- **离线兜底**: 在线失败时从`data/concept_cache.json`读取，离线缓存随使用逐次积累
- **性能优化**: 只对过滤后的top10概念拉成分股，K线通过线程池并发拉取(10线程)

**sentiment.py 数据源**:
- **股吧热帖**: `guba.eastmoney.com` HTML解析
- **互动易问答**: `guba.eastmoney.com/qa/qa_search.aspx` Direct请求
- **新闻搜索**: `search-api-web.eastmoney.com` JSONP格式
- **分析师评级**: `reportapi.eastmoney.com` JSON格式

### 3.2 Analysis (维度层)

| 模块 | 行数 | 输入 | 输出 | 状态 |
|------|------|------|------|------|
| `technical.py` | 265 | K线数据 + 实时行情 | MA(5/10/20/60/120/250), MACD(金叉/死叉), KDJ, RSI(6/12/24), BOLL, 量比, 换手率分级, 价格分位(60d/250d), 支撑/压力位, 信号/警告列表 | ✅ |
| `fundamental.py` | 74 | 财务指标 + 分红 + 预测 | 盈利能力/财务健康/成长性/分红/一致预期, 信号/警告列表 | ✅ |
| `valuation.py` | 44 | 实时行情 | PE/PB/市值/换手率, 估值信号(低估/高估/高换手) | ✅ |
| `capital.py` | 17 | flow.py | 成交额统计 + 北向持股 (thin wrapper) | ✅ |
| `sentiment.py` | 80 | 股吧+互动易+新闻+评级 | 关键词情绪评分 → bullish/bearish/neutral + 帖子计数 + 互动易Q&A + 评级统计 | ✅ |
| `company.py` | 82 | info.py | 公司概况(行业/主营/产品/简介/实控人/法人/注册资本/员工数) | ✅ |
| `scorer.py` | 404 | 技术/基本面/资金/舆情/行情/估值 | 四维评分(各±25), 总分±100, 7级评级(强看多→强看空), 综合信号/警告 | ✅ |
| `concept.py` | 418 | 概念排行 + 成分股(100只) + 新闻 | 趋势定性(breakout/strong/rising/falling/neutral), 涨跌分布, 领涨股, 新闻归因, 综合评分(100分制) | ✅ |
| `stock_picker.py` | ~400 | 成分股+K线+deep_analysis | 双轨评分: 轨道A板块强度(100分) + 轨道B选股决策(100分) + 精选标的(入场信号分类+entry_score) + 跨概念共振 | ✅ |
| `concept_rank.py` | 259 | em_concept.py | 概念排名(资金流入排序+过滤非行业+top_n), 离线兜底 | ✅ |
| `macro.py` | 351 | macro.py (collectors) | analyze_global(环境定性) + analyze_domestic(经济周期/流动性) + analyze_event(市场情绪) + synthesize(综合研判) | ✅ |

### 3.3 Plans (编排层)

| 模块 | 行数 | 编排流程 | 状态 |
|------|------|----------|------|
| `stock_analysis.py` | 152 | 行情→公司概况→技术面→基本面→资金面→舆情面→估值→综合评分 | ✅ |
| `concept_analysis.py` | 340 | 概念排行→趋势定性(100只成分股,剔除北交所)→新闻归因→机会筛选(涨跌分布+综合评分), 含地域过滤+龙头去重 | ✅ |
| `daily_report.py` | 619 | 每日复盘: 指数行情→涨跌家数→概念资金流→宏观数据→持仓分析→自选股→格式化输出 | ✅ |
| `options_scan.py` | ~270 | ETF期权全市场扫描: 合约数据→HV计算→D/R/S风险收益排序→卖方Top10→买方Top10(BS胜率) | ✅ |

### 3.4 CLI (core/cli.py)

| 命令 | 功能 | 状态 |
|------|------|------|
| `analyze <code>` | 个股全维度分析 | ✅ |
| `analyze <code> --json` | JSON输出 | ✅ |
| `analyze <code> --brief` | 简要输出 | ✅ |
| `analyze <code> --html` | HTML报告输出 | ✅ |
| `concept` | 概念板块扫描 | ✅ |
| `concept --json` | JSON输出 | ✅ |
| `concept --html` | HTML报告输出 | ✅ |
| `market` | 宏观市场概览 | ✅ |
| `market --html` | HTML报告输出 | ✅ |
| `review` | 每日复盘 | ✅ |
| `review --html` | HTML报告输出 | ✅ |
| `options` | ETF期权扫描 | ✅ |
| `options --html` | HTML报告输出 | ✅ |
| `analyze-all` | 自选批量分析 | ✅ (简单循环) |
| `add <code>` | 加入自选 | ✅ |
| `rm <code>` | 移除自选 | ✅ |
| `list` | 查看自选 | ✅ |

---

## 3.5 HTML报告系统

### 模板架构

```
templates/
├── base.html              # 197行 基础模板 (暗色主题 + CSS变量 + 移动端适配)
├── stock_report.html      # 440行 个股分析报告 (8模块)
├── concept_report.html    # 245行 概念分析报告
├── market_report.html     # 244行 市场概览报告
└── components/            # 6个可复用组件
    ├── metric_grid.html   # 指标网格
    ├── signal_badge.html  # 信号标签
    ├── score_gauge.html   # 评分仪表盘
    ├── progress_bar.html  # 进度条
    ├── data_table.html    # 数据表格
    └── collapsible.html   # 折叠面板
```

### 渲染器

`core/html_renderer.py` (81行) — 通用Jinja2渲染器，支持`--html`参数输出完整HTML报告。

**使用方式**:
```bash
# 个股分析HTML
python3 core/cli.py analyze 600519 --html

# 概念扫描HTML
python3 core/cli.py concept --html

# 市场概览HTML
python3 core/cli.py market --html
```

---

## 3.6 配置管理

### 配置文件结构

```
config/
├── __init__.py         # 59行 配置管理(Cookie + 代理 + get_proxy())
├── config.yaml         # 实际配置 (不提交git, 本地使用)
└── config.example.yaml # 配置模板 (提交git, 用户参考)
```

### 配置项说明

| 字段 | 类型 | 说明 | 获取方式 |
|------|------|------|----------|
| `eastmoney.cookie` | string | 东方财富Cookie | 浏览器F12 → Network → 任意请求的Cookie头 |
| `eastmoney.ut` | string | 固定参数 | 无需修改 |
| `proxy.https` | string | HTTPS代理地址 | 可选，默认读环境变量`HTTPS_PROXY` |

**Cookie获取步骤**:
1. 打开 https://quote.eastmoney.com/bk/
2. F12 → Network → 刷新页面
3. 找到 `push2.eastmoney.com` 请求
4. 复制 Request Headers 中的 Cookie 值

**Cookie有效期**: 通常1-7天，过期时需要重新获取

### 本地开发

```bash
# 复制模板
cp config/config.example.yaml config/config.yaml

# 编辑配置文件，填入实际Cookie
vim config/config.yaml
```

**注意**: `config/config.yaml` 已在 `.gitignore` 中，不会被提交。

---

## 4. 数据源 & 路由策略

### 4.1 直连 (国内CDN, 无需代理)

| API | 域名 | 用途 | 备注 |
|-----|------|------|------|
| 腾讯行情 | `qt.gtimg.cn` | 实时行情(价格/PE/PB/市值) | GBK编码 |
| 新浪K线 | `money.finance.sina.com.cn` | 历史日K线(250日) | JSON(非标准, 需正则修复) |
| 东财F10 | `emweb.securities.eastmoney.com` | 公司基本信息 | JSON (Playwright拦截) |
| 东财股吧 | `guba.eastmoney.com` | 股吧热帖 | HTML解析 |
| 东财互动易 | `guba.eastmoney.com/qa/` | 投资者问答 | Direct请求 |
| 东财搜索 | `search-api-web.eastmoney.com` | 概念新闻搜索 | JSONP格式, 需剥离 `jQuery()` 包装 |
| 东财分析师评级 | `reportapi.eastmoney.com` | 机构评级数据 | JSON格式 |
| 东财push2 | `push2.eastmoney.com` | 概念列表+成分股 | HTTP API + Cookie + JSONP |

### 4.2 Playwright (浏览器自动化)

| 模块 | 功能 | 备注 |
|------|------|------|
| `em_browser.py` | 共享浏览器会话 | 避免重复启动Chromium |
| `em_concept.py` | 概念列表+成分股采集 | HTTP API + Cookie + JSONP |
| `info.py` (F10) | 公司详细信息 | 页面导航拦截 |
| `sentiment.py` (股吧) | 股吧热帖+互动易 | HTML解析 |

### 4.3 代理 (需要 Xray @ 127.0.0.1:10809)

| API | 包/域名 | 用途 | 备注 |
|-----|---------|------|------|
| akshare THS | `stock_financial_abstract_ths` | 财务摘要(ROE/成长等) | 需 `HTTPS_PROXY` |
| akshare 分红 | `stock_history_dividend_detail` | 分红历史 | 需 `HTTPS_PROXY` |
| akshare 预测 | `stock_profit_forecast_ths` | 机构盈利预测 | 需 `HTTPS_PROXY` |
| akshare 北向 | `stock_hsgt_individual_detail_em` | 北向持股数据 | 需 `HTTPS_PROXY` |
| akshare 涨停池 | `stock_zt_pool_em` | 涨跌停统计 | 需 `HTTPS_PROXY` |

### 4.4 封锁 (服务器IP限制, 不可用)

| API | 域名 | 影响 | 替代方案 |
|-----|------|------|----------|
| 东财push2直连 | `push2.eastmoney.com` | 频繁限流ERR_EMPTY_RESPONSE | Playwright页面导航拦截 |
| 东财push2his | `push2his.eastmoney.com` | 个股主力资金流缺失 | 用成交额统计+北向替代 |
| akshare概念 | `stock_board_concept_*` | 概念板块详细数据不可用 | Playwright拦截替代 |

---

## 5. 评分体系

### 5.1 四维评分 (各 ±25 分, 总分 ±100)

| 维度 | 权重 | 评分依据 |
|------|------|----------|
| 技术面 | ±25 | MA排列, MACD金叉/死叉, KDJ超买超卖, RSI, 价格分位, 量比 |
| 基本面 | ±25 | ROE, 毛利率, 负债率, 营收/净利增速, 分红, 一致预期 |
| 资金面 | ±25 | 成交额量比, 北向持股趋势 |
| 舆情面 | ±25 | 股吧情绪(bullish/bearish/neutral), 帖子数量, 互动易问答, 分析师评级 |

### 5.2 评级映射

| 总分 | 评级 |
|------|------|
| ≥ 60 | 强看多 |
| ≥ 30 | 看多 |
| ≥ 10 | 偏多 |
| ≥ -10 | 中性 |
| ≥ -30 | 偏空 |
| ≥ -60 | 看空 |
| < -60 | 强看空 |

---

## 6. 概念板块分析

### 6.1 趋势定性

基于**100只成分股**的涨幅分布+持续性分布+放量信号综合判断板块状态。

| 状态 | 条件 |
|------|------|
| `breakout` (金叉启动) | 刚启动占比 > 25% 且 上涨面 > 60% |
| `strong` (主升浪) | 连涨3天+占比 > 35% 且 上涨面 > 65% 且 涨停 ≥ 2只 |
| `rising` (上升期) | (连涨3天+>15% 或 连涨2天>10%) 且 上涨面 > 55% |
| `weak_rise` (弱上升) | 上涨面 > 50% 且 强势股 < 10% |
| `falling` (走弱) | 下跌面 > 50% |
| `weak` (震荡) | 其他 |

### 6.2 "刚启动"判定逻辑

**双重条件** (`_is_just_started`):
1. **首日上涨**: 今日收盘 > 昨日收盘
2. **低点距离过滤**: 当前价相对近20日最低价涨幅 ≤ 涨停幅度 × 1.2

| 板块 | 涨停幅度 | 刚启动阈值 |
|------|---------|-----------|
| 主板 (60xxxx) | 10% | 12% |
| 创业板 (300xxx) | 20% | 24% |
| 科创板 (688xxx) | 20% | 24% |
| 北交所 (8xxxxx) | 30% | 36% |

**设计意图**: 首次涨停的股票不会被误杀（主板涨停10% < 阈值12%），但已涨一波的反弹股会被正确排除。

### 6.3 双轨评分体系 (stock_picker.py)

概念选股采用双轨评分，分别回答不同问题：

**轨道A：板块强度 (100分) — "今天谁最热"**

| 维度 | 满分 | 公式 |
|------|------|------|
| A1 赚钱效应 | 30 | `min(30, >7%占比×100 + 3~7%占比×50)` |
| A2 资金强度 | 25 | 条件1(上限15)：按流通市值≥500亿成分股数分档，净流入×系数(3/2/1分/亿)；条件2(上限10)：放量股占比×15 |
| A3 板块宽度 | 25 | 上涨比例×25(上限20) + 涨停数×1(上限5) |
| A4 持续性 | 20 | 连涨3天+×3 + 连涨2天×2 + 刚启动×1，封顶20 |

A2 资金强度分档：流通市值≥500亿成分股 ≤5个→3分/亿，5~15个→2分/亿，>15个→1分/亿。

| 总分 | 阶段 |
|------|------|
| ≥ 70 | 🚀 加速期 |
| ≥ 50 | ⚡ 启动期 |
| ≥ 30 | 📊 震荡期 |
| < 30 | ⚠️ 衰退期 |

**轨道B：选股决策 (100分) — "现在该买什么"**

| 维度 | 满分 | 评分依据 |
|------|------|----------|
| B1 可买标的数 | 30 | 精选标的(非追高)数量×6，5只以上满分 |
| B2 标的质量 | 25 | 精选标的entry_score平均分×0.25 |
| B3 追高风险 | 25 | 连涨3天+占比×50（越高扣分越多） |
| B4 新鲜度 | 20 | 刚启动占比×30（越高越好） |

| 总分 | 阶段 |
|------|------|
| ≥ 70 | ✅ 积极 |
| ≥ 50 | 👀 关注 |
| ≥ 30 | ⚡ 观望 |
| < 30 | ⚠️ 回避 |

**精选标的入场信号分类 (entry_score)**:

| 类型 | 条件 | 分数范围 |
|------|------|----------|
| 🚀 突破启动 | 涨>5% 且 距月低<10% 且 连涨≤1天 | 80~100 |
| 📉 回踩确认 | 涨2~5% 且 距月高回撤10~20% | 70~90 |
| 💪 趋势加仓 | 涨>0% 且 连涨≥2天 | 60~85 |
| ⚡ 底部异动 | 涨>2% 且 距月低<5% 且 下跌趋势 | 65~85 |
| ⚠️ 追高 | 以上都不满足 | 10 |

**排序规则**: 按资金流入倒序，展示列：资金流入、板块涨幅、强度分、选股分。

**数据采集**: Playwright请求字段包含f21(流通市值)，用于A2资金强度的分档计算。

### 6.3b 概念综合评分 (100分制，已废弃)

> 注：以下单轨评分已被双轨评分替代，保留供历史参考。

| 维度 | 满分 | 评分依据 |
|------|------|----------|
| 赚钱效应 | 30 | >7%占比 + 上涨比例 |
| 介入时机 | 25 | 刚启动占比高加分, 连涨3天+过多减分 |
| 资金强度 | 25 | 放量股占比 + 涨停数 |
| 板块宽度 | 20 | 上涨家数占比 |

### 6.4 数据源架构 — Playwright页面导航拦截 (v6)

**背景**: 东财push2直连在服务器IP上频繁限流(ERR_EMPTY_RESPONSE)，Cookie无法根治。

**方案**: Playwright真实浏览器访问东财行情页，拦截XHR响应获取数据。

```
Playwright Chromium
  → 访问 quote.eastmoney.com/bk/ (概念列表页)
    → 拦截 push2.eastmoney.com/api/data/v1/get XHR响应
      → 解析JSON获取概念列表(资金流入排序)
  → 对每个top_n概念，访问详情页
    → 滚动触发懒加载
    → 拦截 dataapi.eastmoney.com XHR响应
      → 解析JSON获取成分股(按涨幅排序,前100只)
  → 增量合并到离线缓存 (data/concept_cache.json)
```

**排名引擎** (`collectors/em_concept.py` + `analysis/concept_rank.py`):
1. HTTP API请求概念列表页，解析JSONP获取概念列表
2. 按资金流入(f62)排序，过滤非行业概念，保留top_n个
3. 对每个概念，HTTP API请求成分股列表，间隔1秒避免限流
4. 增量合并到离线缓存 (`data/concept_cache.json`)
5. 在线失败时使用离线缓存兜底

**Cookie管理**:
- 存储在 `config/config.yaml` 的 `eastmoney.cookie` 字段
- 有效期通常1-7天，过期时需重新获取
- 过期时有清晰的错误提示引导用户操作

### 6.5 过滤规则

- 地域概念过滤：排除 "成渝特区"、"福建自贸区" 等地域性概念
- 龙头去重：同一龙头股只保留涨幅最高的概念

---

## 7. 服务器环境

- **OS**: Linux (6.1.84)
- **Python**: 3.11
- **Proxy**: Xray @ 127.0.0.1:10809 (HTTP, 用户态 systemd, whitelist 路由)
- **Playwright**: Chromium (仅用于F10/股吧/搜索/研报，概念/涨跌家数/期权均用HTTP API)
- **Dependencies**: `akshare>=1.10.0`, `requests>=2.28.0`, `pyyaml>=6.0`, `jinja2>=3.1.0`, `playwright>=1.40.0`
- **Working Dir**: `/tmp/stock-analysis-pro/`
- **Config**: `config/config.yaml` (Cookie在此管理, 不提交git)
- **Cache**: `./cache/` (JSON, TTL 1h)
- **Watchlist**: `./data/watchlist.json`

---

## 8. ETF 期权分析框架 (v3.1)

### 8.1 标的覆盖

9只可交易期权的ETF：

| 代码 | 名称 | 交易所 |
|------|------|--------|
| 510050 | 上证50ETF | 上交所 |
| 510300 | 沪深300ETF(沪) | 上交所 |
| 159919 | 沪深300ETF(深) | 深交所 |
| 510500 | 中证500ETF(沪) | 上交所 |
| 159612 | 中证500ETF(深) | 深交所 |
| 159915 | 创业板ETF | 深交所 |
| 588000 | 科创50ETF | 上交所 |
| 588080 | 科创板50ETF | 上交所 |
| 159901 | 深证100ETF | 深交所 |

### 8.2 数据源

| 数据 | 来源 | 说明 |
|------|------|------|
| 期权合约列表 | 新浪 `hq.sinajs.cn` | OP_UP/OP_DOWN |
| 期权行情(权利金) | 新浪 | 实时 |
| 标的实时价 | 腾讯 `qt.gtimg.cn` | 实时 |
| 标的60日K线 | 新浪 `money.finance` | 历史日K |
| Greeks/IV | 新浪 | 合约级数据 |

### 8.3 卖方风险收益框架 (D/R/S)

**核心参数**：
- 合约乘数 = 10000
- 保证金比例 = 12% (通用)
- 保证金 = 行权价 × 10000 × 12%
- 权利金(每张) = 权利金(每份) × 10000

**三个指标**：

| 指标 | 公式 | 含义 | 方向 |
|------|------|------|------|
| **D (距离)** | `|现价-行权价| / 60日振幅` | 标的到达行权价的"安全距离" | 越大越安全 |
| **R (风险)** | `(天数/365) / D` | 时间归一化后的距离风险 | 越小越好 |
| **S (收益比)** | `年化收益 / R` | 单位风险的收益 | 越大越好 |

**年化收益** = `(权利金每张 / 保证金) × 365 / 天数`

**过滤条件**：仅虚值、距到期≥7天、权利金≥0.005、Call/Put分开排序

### 8.4 买方策略框架

**逻辑**：卖方不合适的合约 = 买方机会

**排序**：S值升序（S值最低 = 卖方不愿意卖 = 距离近或时间长）

**胜率计算**：Black-Scholes d2公式估算到期达实值概率
- `d2 = (ln(S/K) + (r - σ²/2)×T) / (σ√T)`
- 认购: P = Φ(d2)；认沽: P = Φ(-d2)
- σ = HV60年化标准差（对数收益率 std × √252）

**过滤条件**：
- 虚值幅度 > 3%：`|现价-行权价|/现价 > 0.03`
- 直接收益率 < 20%：`权利金每张/保证金 < 0.20`
- 天数 10~90天
- 权利金 ≥ 0.005（每张≥50元）
- 胜率 ≥ 10%（BS d2概率）
- 仅虚值

**收益率计算（每张口径）**：
- 每张权利金 = 每份价格 × 10000
- 保证金 = 行权价 × 10000 × 12%
- 直接收益 = 每张权利金 / 保证金

**设计意图**：
- 低权利金：控制成本（50~300元/张）
- 低直接收益：不给卖方提供20%以上收益
- 虚值幅度>3%：排除近平值期权
- 时间窗口：10~90天，既不太短也不太长
- BS胜率≥10%：排除极低概率合约

### 8.5 波动率全景

| 指标 | 公式 | 说明 |
|------|------|------|
| V_ratio | HV60 / 250日均HV | 当前波动率相对历史位置 |
| 阈值 | >1.2 🔴高波, <0.8 🟢低波 | 判断当前环境 |

### 8.6 报告结构

1. **第一部分：波动率全景** — 9只标的V_ratio/P分位/状态，表格展示
2. **第二部分：卖方Top10** — S值排序，含D/R/S/年化收益/权利金/保证金
3. **第三部分：买方Top10** — S值升序，含虚值幅度/权利金/直接收益
4. **字段说明** — 底部D/R/S含义和过滤规则说明

---

## 9. 关键经验

1. **东财push2方案** — HTTP API + Cookie，概念/涨跌家数均走此路，间隔1秒防限流
2. **Playwright仅用于F10/股吧** — `em_browser.py`共享会话，概念/涨跌家数不走Playwright
3. **K线用新浪** — `hq.sinajs.cn`无限流，可线程池并发拉取
4. **akshare的stock_board_concept_*系列** — 在服务器上被封(RemoteDisconnected)
5. **涨跌停数据用akshare** — `stock_zt_pool_em`，不依赖东财push2
6. **东财搜索API可用** — JSONP格式需去掉jQuery()包装，支持概念关键词搜索新闻
7. **北向数据过时** — 港交所2024-08停止披露个股级数据，评分自动降权

---

## 9. 待完成清单

### ✅ 期权买方策略（v3.4已完成）
- ~~买方机会扫描（IV/HV价差 + σ归一化安全边际）~~ → 用BS d2胜率替代
- ~~买方风险收益排序框架~~ → S值升序 + 胜率≥10%过滤

### ⏸️ 暂不实施（无可用数据源）
- 主力资金流替代方案
- 融资融券数据源
- 行业板块数据
- 大宗交易数据
- 行业估值对比

### 🔮 未来优化方向
- 概念过滤优化（品牌/政策/指数/重叠概念分类）
- 单元测试
- 报告模板个性化定制
- 更多数据源接入（同花顺/雪球）
