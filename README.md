# stock-analysis-pro

A股全维度分析 + ETF 期权分析工具 — 个股深度分析、概念板块扫描、宏观市场概览、每日复盘、ETF 期权扫描。

可命令行直接执行，也可作为 [Hermes Agent](https://github.com/NousResearch/hermes-agent) skill 对话调用。

## 功能

### 每日复盘（新增 v3.0）

每日收盘后自动生成综合报告，覆盖：
- **指数概览** — 上证/深证/创业板/科创50 实时行情
- **涨跌统计** — 涨跌家数、涨停跌停数、赚钱效应分析
- **概念板块 TOP10** — 资金净流入 TOP10 + 涨幅 TOP10（同花顺数据源，无需 Cookie）
- **持仓跟踪** — 当日持仓盈亏、涨跌、风险提示
- **自选股监控** — 自选股列表及表现

支持文本和 HTML 两种输出格式，HTML 报告可在微信/浏览器查看。

### ETF 期权扫描（新增 v3.0）

全市场 ETF 期权合约扫描，寻找高胜率交易机会：
- **卖方机会** — IV > HV 的虚值期权，按时间价值衰减速度排序
- **买方机会** — IV < HV 的平值/浅虚值期权，按性价比排序
- **风险指标** — Delta归一化安全边际 + IV/HV价差

支持多标的扫描（50ETF、300ETF、500ETF 等），自动过滤流动性差的合约。

### 个股深度分析

对单只股票进行 6 大维度全方位分析，输出综合评分（-100 ~ +100）和 7 级评级：

| 维度 | 关键数据 |
|------|----------|
| 公司概况 | 主营业务、行业地位、实控人 |
| 技术面 | MA均线、MACD、KDJ、RSI、BOLL、量价关系、支撑/压力位 |
| 基本面 | ROE、毛利率、负债率、营收/净利增速、现金流质量、周转效率、研发占比、多期趋势、分红、机构预期、综合评分(100分制) |
| 估值 | PE/PB、市值、换手率 |
| 资金面 | 成交额统计、北向持股 |
| 舆情 | 股吧热帖、互动易问答、新闻、分析师评级 |

### 概念板块扫描

按**资金流入**排序概念板块，自动过滤非行业概念（风格/市值/地域类），对每个概念进行深度分析：

1. **趋势定性** — 基于成分股涨幅分布判断板块状态（刚启动/主升浪/走弱）
2. **新闻归因** — 搜索概念相关新闻，给出驱动逻辑
3. **机会挖掘** — 成分股涨跌分布、领涨龙头、刚启动信号

### 行业异动筛选（新增 v3.1）

自动扫描当日涨幅>5%的A股，按主营业务归类到细分行业，对Top5行业展示详细指标辅助判断介入时机：

- **行业归类** — 基于同花顺F10主营业务描述，映射到二级行业体系（不依赖东财概念板块）
- **多维指标** — 涨幅、连涨天数、量比、换手率、成交额、振幅、60日/250日价格分位、PE、市值
- **行业深度分析** — 对Top5行业自动生成：
  - 🔥 核心催化（3大驱动逻辑 + 海外市场规模）
  - 🌍 行业动态（最新新闻，带日期）
  - 📈 近期行情回顾（时间线形式）
  - 🎯 有价值环节分析（分梯队标的推荐）
- **自动剔除** — 北交所股票自动过滤

数据源：新浪财经（行情）+ 同花顺F10（主营业务）+ Google News（行业动态），完全独立于东方财富。

### 抖音日更内容（新增 v3.2）

自动生成适合抖音发布的竖屏数据可视化图片（1080×1920），包含11张图：

1. **个股成交额TOP10**（1张）— 全市场按成交额排序（新浪数据源），含排名变化箭头（↑↓）
2. **概念板块资金意图矩阵**（5张）— akshare同花顺全量373概念（无采样偏差），价格×资金四象限：
   - p0 资金全景图（四象限计数+资金面研判）、p1 失血榜（抽血率=净流出/成交额）、p2 对倒嫌疑榜（巨量不留钱）、p3 主攻方向榜（价涨+钱进+锁仓三共振）、p4 潜伏吸筹榜（钱进价未动）
   - 核心指标：留存率（净额/总成交，归一化可比）+ 能量（成交/公司家数）
   - "盘后情报局"栏目角标 + 每页一句💡研判 + NEW标记（对比昨日四区缓存）
3. **新进成交额TOP50**（1张或多张）— 首次进入成交额前50的股票，支持智能分页：
   - ≤15只：1页展示完
   - >15只：每页10只，分多页展示（标题显示"第X/Y页"）
4. **异常信号捕捉**（4张）— 放量滞涨/缩量新高/放量急拉 + 连板梯队（腾讯量比 + akshare涨停池）

一键生成所有图片：
```bash
python scripts/daily_content/run_all.py
```

详细文档见 [DAILY_CONTENT.md](DAILY_CONTENT.md)。

### 宏观市场概览

4 大维度实时分析市场环境：

- 国际环境（美债/利率/黄金/原油）
- 国内经济（CPI/PMI/M2/LPR）
- 事件驱动（涨停数/连板/热门方向）
- 综合研判（操作建议）

## 快速开始

### 方式一：作为 Hermes Agent Skill 安装（推荐）

```bash
# 1. 克隆到 Hermes skills 目录
git clone https://github.com/bobby1129/stock-analysis-pro.git ~/.hermes/skills/stock-analysis-pro
cd ~/.hermes/skills/stock-analysis-pro

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装 Playwright 浏览器
playwright install chromium

# 4. 复制配置模板并填入东财 Cookie
cp config/config.example.yaml config/config.yaml
vim config/config.yaml

# 5. 验证安装
python core/cli.py analyze 600519 --brief
# 成功输出：贵州茅台 实时价格 + PE/PB 即表示安装正确
```

安装完成后，Hermes Agent 会自动加载本 skill。对 Agent 说：
- `分析 600519` → 个股全维度分析
- `概念扫描` → 热门概念板块
- `市场概览` → 宏观环境

### 方式二：命令行直接使用

```bash
# 1. 克隆项目
git clone https://github.com/bobby1129/stock-analysis-pro.git
cd stock-analysis-pro

# 2. 安装依赖
pip install -r requirements.txt
playwright install chromium

# 3. 配置
cp config/config.example.yaml config/config.yaml
vim config/config.yaml

# 4. 验证
python core/cli.py analyze 600519 --brief
```

### Cookie 获取步骤

1. 浏览器打开 https://quote.eastmoney.com/bk/
2. F12 → Network → 刷新页面
3. 找到 `push2.eastmoney.com` 请求
4. 复制 Request Headers 中的 Cookie 值
5. 粘贴到 `config/config.yaml` 的 `eastmoney.cookie` 字段

> ⚠️ Cookie 有效期 1-7 天。过期后概念板块功能降级为离线缓存模式，需要重新获取。
> 过期时会显示清晰的错误提示引导操作。

### 系统要求

| 项目 | 最低要求 |
|------|---------|
| Python | 3.11+ |
| 操作系统 | Linux / macOS |
| 内存 | 2GB+ (Playwright Chromium 需要) |
| 网络 | 国内直连可用，akshare 需代理 |

### 命令参考

```bash
# 个股分析
python core/cli.py analyze 600519           # 全维度分析
python core/cli.py analyze 600519 --html    # HTML报告
python core/cli.py analyze 600519 --json    # JSON输出

# 概念板块扫描
python core/cli.py concept                  # 资金流入Top10
python core/cli.py concept --html           # HTML报告

# 宏观市场概览
python core/cli.py market                   # 文本输出
python core/cli.py market --html            # HTML报告

# 自选股
python core/cli.py add 600519              # 加入自选
python core/cli.py rm 600519               # 移除
python core/cli.py list                     # 查看列表
python core/cli.py analyze-all              # 批量分析自选股
```

## 项目结构

```
stock-analysis-pro/
├── core/
│   ├── cli.py              # CLI入口
│   └── html_renderer.py    # HTML报告渲染器 (Jinja2)
├── collectors/             # 数据采集层
│   ├── quote.py            # 实时行情+K线 (腾讯/新浪)
│   ├── finance.py          # 财务数据 (akshare/THS)
│   ├── flow.py             # 资金流 (成交额/北向)
│   ├── info.py             # 公司F10 (东财)
│   ├── sentiment.py        # 舆情 (股吧/新闻/互动易)
│   ├── em_concept.py       # 概念板块 (HTTP API主链路 + Playwright辅助F10)
│   ├── ths_concept.py      # 同花顺概念板块 (资金流向/涨幅榜, 无需Cookie)
│   ├── em_browser.py       # 共享Playwright浏览器会话
│   ├── macro.py            # 宏观数据 (akshare + 新浪)
│   ├── options.py          # 期权数据 (新浪hq.sinajs.cn)
│   ├── breadth.py          # 涨跌家数 (HTTP API + Cookie)
│   └── cache.py            # 通用缓存
├── analysis/               # 分析引擎层
│   ├── technical.py        # 技术面分析
│   ├── fundamental.py      # 基本面分析
│   ├── valuation.py        # 估值分析
│   ├── capital.py          # 资金面分析
│   ├── sentiment.py        # 舆情分析
│   ├── company.py          # 公司概况
│   ├── concept.py          # 概念深度分析
│   ├── stock_picker.py     # 双轨评分+选股
│   ├── macro.py            # 宏观分析
│   └── scorer.py           # 综合评分
├── plans/                  # 编排层
│   ├── stock_analysis.py   # 个股分析流程
│   ├── concept_analysis.py # 概念分析流程
│   ├── daily_report.py     # 每日复盘流程
│   ├── global_macro.py     # 宏观市场概览
│   ├── industry_screener.py # 行业异动筛选
│   └── options_scan.py     # 期权扫描流程
├── templates/              # HTML报告模板
├── config/
│   ├── config.example.yaml # 配置模板 (提交git)
│   └── config.yaml         # 实际配置 (不提交, 本地使用)
├── data/
│   ├── watchlist.json      # 自选股列表
│   └── concept_cache.json  # 概念离线缓存 (增量更新)
├── cache/                  # 运行时缓存 (TTL 1小时)
├── requirements.txt
└── DESIGN.md               # 详细设计文档
```

## 数据源

| 数据源 | 用途 | 访问方式 | 状态 |
|--------|------|----------|------|
| 腾讯 (qt.gtimg.cn) | 实时行情 | 直连 | ✅ |
| 新浪 (hq.sinajs.cn) | 期权/ETF行情/K线 | 直连 | ✅ |
| 新浪 (money.finance) | K线数据 | 直连 | ✅ |
| 东财 (emweb/guba) | 公司F10/股吧 | Playwright拦截 | ✅ |
| 东财 (search-api) | 概念新闻 | 直连 | ✅ |
| 东财 (push2.eastmoney.com) | 概念板块 | HTTP API + Cookie (主链路, 1s间隔) / Playwright (F10辅助) | ✅ |
| 东财 (互动易) | 投资者问答 | 直连 | ✅ |
| akshare (THS) | 财务/分红/预测 | 需代理 | ✅ |

> 概念板块主链路通过 HTTP API 直接请求 push2.eastmoney.com，带 Cookie + JSONP 回调，概念间 sleep(1s) 避免限流。Playwright 仅用于 F10/股吧/搜索/研报等动态页面。

## 代理配置

akshare 接口（财务/分红/北向/涨停池）需要通过代理访问。如果服务器在国内：

```bash
export HTTPS_PROXY=http://your-proxy:port
```

腾讯/新浪/东财直连接口无需代理。

## 输出格式

| 格式 | 参数 | 适用场景 |
|------|------|---------|
| 文本 | (默认) | 终端查看 |
| HTML | `--html` | 微信/浏览器查看，复盘浅色/其他暗色 |
| JSON | `--json` | 程序对接 |
| 摘要 | `--summary` | 快速概览 (~200 token) |

## 已知限制

| 限制 | 原因 | 影响 |
|------|------|------|
| 个股主力资金流 | 东财push2his对部分IP封禁 | 资金面评分缺少主力数据 |
| 北向持股过时 | 港交所2024-08停止披露 | 北向评分自动降权 |
| 行业估值对比 | 行业均值API不可用 | 只能看绝对估值 |

## 文档

- [DESIGN.md](DESIGN.md) — 详细设计文档（架构、模块、评分体系）
- [PROGRESS.md](PROGRESS.md) — 开发进度日志
- [USAGE.md](USAGE.md) — 使用指南（对话式用法）
- [SKILL.md](SKILL.md) — Hermes Agent skill 文档

## 故障排除

| 问题 | 原因 | 解决 |
|------|------|------|
| `playwright: command not found` | 未安装Playwright | `pip install playwright && playwright install chromium` |
| 概念板块返回空/离线缓存 | Cookie过期 | 重新获取Cookie，更新`config/config.yaml` |
| `⚠️ 疑似触发东财滑块验证` | HTTP API连续断连(RemoteDisconnected) | 浏览器打开 https://data.eastmoney.com/bkzj/gn.html 手动完成滑块验证后重试 |
| akshare报 `RemoteDisconnected` | 未配置代理 | `export HTTPS_PROXY=http://127.0.0.1:10809` 或在`config.yaml`配置`proxy.https` |
| F10/股吧采集超时 | Playwright Chromium未安装 | `playwright install chromium` |
| 概念板块数据为空且无离线缓存 | 首次运行+Cookie无效 | 先配置有效Cookie再运行 |
| `ModuleNotFoundError: jinja2` | 依赖未安装 | `pip install -r requirements.txt` |
| 个股分析缺少财务数据 | akshare代理不通 | 检查`HTTPS_PROXY`环境变量，其他维度正常输出 |

## License

MIT
