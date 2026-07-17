
## ✅ v3.2 期权卖方框架完善 — 已完成 (2026-07-17)

### 代码改动
| 改动 | 说明 |
|------|------|
| `collectors/options.py` | 标的列表从6只扩充到9只(补500ETF深/科创板50ETF/深证100ETF) |
| `plans/options_scan.py` | 收益率计算修复: 统一每张口径(premium×10000 vs 保证金) |
| `templates/options_report.html` | 按D/R/S框架重构报告模板 |

### 文档修复
| 文件 | 修改内容 |
|------|----------|
| DESIGN.md | 核心能力从5项精简为4项; options_scan描述改为D/R/S框架; 新增第8节ETF期权分析框架(标的/数据源/D/R/S公式/波动率全景/报告结构) |

### 验证结果
- ✅ 9只ETF全部采集成功, 共1110个合约
- ✅ 过滤后306个虚值期权参与排序
- ✅ 收益率计算验证: 权利金893元/张, 保证金4800元, 直接收益18.6% ✓
- ✅ HTML报告生成成功

---

## ✅ v3.3 期权买方策略实现 — 已完成 (2026-07-17)

### 核心逻辑
**买方机会 = 卖方不合适的合约**

卖方不愿意卖的合约特征：
- D值小（距离近，不安全）
- R值高（时间长，风险大）
- S值低（单位风险收益低）

买方角度看：
- 距离近 = 行权价接近现价，容易获利
- 时间长 = 等待波动的窗口充裕
- 成本低 = 权利金便宜（50~300元/张）

### 过滤条件
| 条件 | 公式 | 目的 |
|------|------|------|
| 虚值幅度 | \|现价-行权价\|/现价 > 3% | 排除近平值期权 |
| 直接收益率 | 权利金每张/保证金 < 20% | 不给卖方提供20%以上收益 |
| 天数范围 | 10~90天 | 时间窗口适中 |
| 权利金下限 | ≥ 0.005（每张≥50元） | 保证流动性 |
| 排序方式 | S值升序 | S值最低 = 卖方最不愿意卖 |

### 代码改动
| 文件 | 改动 |
|------|------|
| `plans/options_scan.py` | 新增买方过滤逻辑和排序，输出`buyer_top`字段 |
| `templates/options_report.html` | 新增第三部分买方Top10表格，展示虚值幅度/权利金/直接收益 |

### 验证结果
- ✅ 买方Top10权利金50~300元/张
- ✅ 直接收益均<20%（最高4.47%）
- ✅ 天数40~68天
- ✅ 虚值幅度均>3%
- ✅ 以深度虚值认购为主（500ETF、300ETF购）

### 文档更新
| 文件 | 修改内容 |
|------|----------|
| DESIGN.md | 新增8.4节买方策略框架（逻辑/过滤条件/设计意图），更新8.6报告结构（新增第三部分） |
| PROGRESS.md | 新增v3.3版本记录 |

## ✅ v3.1 文档与代码一致性修复 — 已完成 (2026-07-17)

### 代码修复
| 改动 | 说明 |
|------|------|
| `options_report.html` 模板 | 修复2处 `data.` 前缀遗漏 (seller_top\|length, buyer_top\|length) |

### 文档修复
| 文件 | 修改内容 |
|------|----------|
| DESIGN.md | 架构图: 补充daily_report.py/options_scan.py/breadth.py/options.py; CLI补充review/options命令; Plans表补充2个模块; 概念采集v6→v7; 关键经验重写; macro数据源改为akshare+新浪; Playwright用途限定 |
| README.md | Plans补充daily_report.py/options_scan.py; Collectors补充options.py/breadth.py; macro.py数据源; 期权Greeks描述修正; HTML主题说明; 数据源补充新浪期权 |
| USAGE.md | 复盘功能补充宏观环境/持仓详情; 数据源Playwright→HTTP API; 期权Greeks→Delta+IV/HV; 期权数据源修正; HTML主题说明 |

## ✅ v3.0 三项目合并 — 已完成 (2026-07-16)

将 `stock_review`、`stock-analysis-pro`、`etf-options-analyzer` 合并为统一仓库。

### 合并内容
| 模块 | 来源 | 状态 |
|------|------|------|
| `collectors/breadth.py` | stock_review | ✅ 涨跌家数+涨跌停 |
| `collectors/options.py` | etf-options | ✅ 期权数据采集 |
| `collectors/etf_kline.py` | etf-options | ✅ ETF K线 |
| `collectors/greeks.py` | etf-options | ✅ Greeks数据 |
| `plans/daily_report.py` | stock_review | ✅ 每日复盘编排 |
| `plans/options_scan.py` | etf-options | ✅ 期权全合约扫描 |
| `analysis/hv.py` | etf-options | ✅ 历史波动率(HV60) |
| `analysis/seller.py` | etf-options | ✅ 卖方机会排名 |
| `analysis/buyer.py` | etf-options | ✅ 买方机会排名 |
| `analysis/smile.py` | etf-options | ✅ 微笑曲线 |
| `templates/review_report.html` | stock_review | ✅ Jinja2复盘模板 |
| `templates/options_report.html` | etf-options | ✅ 期权报告模板 |
| `data/portfolio.json` | stock_review | ✅ 持仓数据 |
| CLI: review/options/portfolio | 新增 | ✅ 统一入口 |
| config.yaml 持仓管理 | stock_review | ✅ 合并配置 |
| Cron Job 更新 | 6c7b513b6407 | ✅ 指向新路径 |

### CLI 新增命令
```bash
python3 core/cli.py review [--html]    # 每日复盘
python3 core/cli.py options [--top 10]  # 期权扫描
python3 core/cli.py portfolio [--action list/add/rm/update]  # 持仓管理
```

### 验证结果
- ✅ 语法检查: 全部 .py 通过 py_compile
- ✅ 导入链: collectors.breadth, plans.daily_report, plans.options_scan 均可导入
- ✅ CLI dry-run: portfolio list 正常输出
- ✅ Jinja2 模板: review_report.html 渲染成功 (9517 bytes)
- ✅ 凭证脱敏: 无硬编码 Cookie/UT
- ✅ Cron Job: 已更新指向新路径


# stock-analysis-pro 项目进度

**最后更新**: 2026-07-14

---

## ✅ Req1 个股分析 — 已完成 (2026-06-13 凌晨)

完整度：7/9 核心维度已跑通，用户已验证通过（瑞芯微 603893 测试）

### 已实现
| 维度 | 状态 | 关键内容 |
|------|------|---------|
| 公司概况 | ✅ | 实控人/上市日期/注册资本/主营业务/产品类型/下游应用 |
| 综合评分 | ✅ | 四维打分(技术/基本/资金/舆情) + 信号/警告 |
| 估值 | ✅ | PE/PB/总市值/流通市值/换手率 |
| 技术面 | ✅ | MA5/10/20/60/120/250, MACD, KDJ, RSI, BOLL, 量比, 换手率分级, 60d/250d分位, 支撑压力 |
| 基本面 | ✅ | ROE/毛利率/负债率/营收增速/净利增速, 一致预期, 每股数据, 分红历史 |
| 资金面 | ✅ | 成交额/近N日高低中位/量比, 北向持股(有则显示) |
| 舆情 | ✅ | 股吧热帖/情绪评分/东财新闻/分析师评级/互动易问答 |

### 遗留项
| 维度 | 状态 | 原因 |
|------|------|------|
| 估值分位+同业对比 | ⏸️ P1 | 需补充接口 |
| 主力资金流 | ❌ 阻塞 | 东财push2封锁中 |
| 融资融券 | ❌ 阻塞 | 接口不稳定 |
| 行业对比/风险排查/事件催化/筹码分布/机构持仓 | ⏸️ 待开发 | 下一批次 |

---

## ✅ Req2 概念板块分析 — 已完成 (2026-06-13 晚，06-14 修复2个BUG)

### 需求逻辑（用户确认）
1. **全景扫描** → 全市场概念 Top10，过滤宽泛概念（两融/昨日/次新等）
2. **趋势定性** → 判断刚启动 vs 主升浪 vs 尾声，锁定刚开始动的和最强的
3. **归因分析** → 概念相关新闻搜集 + 简要总结 + 资金分析（如有）
4. **机会挖掘** → 成分股统计 + 领涨龙头 + 技术突破 + 资金共振

### 已实现
| 模块 | 状态 | 说明 |
|------|------|------|
| 概念排行 | ✅ | 新浪备选源，按成交额排序 Top10，智能过滤+龙头去重 |
| 趋势定性 | ✅ | 龙头股60日K线代理(MA金叉/多头排列/涨幅定性) |
| 成分股统计 | ✅ | 涨跌分布(全量100只) + 领涨Top5(涨跌幅/换手/成交额) |
| 新闻归因 | ✅ | 东财搜索API，按概念名关键词搜索，带日期/媒体/摘要 |

### 06-14 修复的BUG
| BUG | 原因 | 修复 |
|-----|------|------|
| leader_pct 读到的是龙头股价而非涨跌幅 | `parts[10]`(股价) 应为 `parts[9]`(涨跌幅) | 修正索引，数据验证通过 |
| 成分股只取80只导致涨跌分布失真 | `num=80` 遗漏20只股票 | 改为 `num=100` |

### 数据源
| 数据 | 来源 | 备注 |
|------|------|------|
| 概念排行 | 新浪 newFLJK | 稳定可用 |
| 概念成分股 | 新浪 getHQNodeData | 稳定可用 |
| 龙头K线 | 新浪 getKLineData | 60日K线代理概念趋势 |
| 新闻归因 | 东财搜索API | search-api-web.eastmoney.com，JSONP格式 |

### 运行方式
```bash
# CLI
python3 core/cli.py concept

# 直接运行
python3 plans/concept_analysis.py --count 10

# JSON输出
python3 core/cli.py concept --json
```

### 代码结构
```
/tmp/stock-analysis-pro/
├── core/cli.py              # CLI入口，stock/concept子命令
├── collectors/              # 数据采集层
│   ├── quote.py             # 行情(东财+新浪兜底)
│   ├── finance.py           # 财务数据
│   ├── flow.py              # 资金流
│   ├── info.py              # 公司信息
│   ├── sentiment.py         # 舆情
│   ├── concept.py           # 概念排行+成分股+龙头K线+新闻
│   └── cache.py             # 缓存
├── analysis/                # 分析层
│   ├── technical.py         # 技术面(完整)
│   ├── fundamental.py       # 基本面
│   ├── valuation.py         # 估值
│   ├── capital.py           # 资金面
│   ├── sentiment.py         # 舆情
│   ├── scorer.py            # 评分
│   ├── company.py           # 公司概况
│   └── concept.py           # 概念趋势定性+机会挖掘
├── plans/
│   ├── stock_analysis.py    # Req1 个股分析入口
│   └── concept_analysis.py  # Req2 概念分析入口(完整)
└── micro_old/ fetchers_old/ macro_old/  # 旧版参考
```

---

## 关键经验
1. **东财push2/push2his对服务器IP全面TCP封锁**，包括代理IP
2. **新浪可用作行情+概念备选**，概念排行/成分股/个股K线均可用
3. **概念K线无直接接口**，用龙头股60日K线代理趋势定性
4. **akshare的stock_board_concept_*系列** 在服务器上也被封锁(RemoteDisconnected)
5. **涨跌停数据用akshare**(stock_zt_pool_em)，不依赖东财push2
6. **每次个股分析必须输出完整报告**，不得遗漏维度
7. **先确认需求再写代码**，不要上来就实现
8. **东财搜索API(search-api-web)可用**，JSONP格式需去掉jQuery()包装，支持概念关键词搜索新闻

---

## 📝 文档完善 — 2026-06-14

### DESIGN.md (v1.0)
- 完整重写，反映新三层架构 (collectors → analysis → plans)
- 包含: 模块清单(行数/数据源/状态), 数据源路由策略, 评分体系, 概念趋势定性逻辑
- **旧代码迁移对照表**: 逐模块标注迁移状态(✅/⚠️/🔴/🟡)
- **待完成清单**: P0(宏观层迁移) / P1(功能补全) / P2(工程质量)

### SKILL.md (v1.0.0)
- 完整重写为 Hermes Agent skill 文档
- 包含: 全部CLI命令示例, 三层架构说明, 6大分析维度, 数据源一览表, 服务器环境
- **常见陷阱**: akshare代理, JSONP解析, 新浪字段映射, 概念K线代理, push2封禁
- 评级阈值已修正为代码实际值 (60/30/10)

---

## ✅ P0 宏观层 — 已完成 (2026-06-14)

### 新增模块
| 模块 | 行数 | 功能 |
|------|------|------|
| `collectors/macro.py` | ~270 | global_macro(美债/利率/金银油) + domestic_macro(CPI/PMI/M2/LPR) + zt_pool(涨停复盘) |
| `analysis/macro.py` | ~230 | analyze_global(环境定性) + analyze_domestic(经济周期/流动性) + analyze_event(市场情绪) + synthesize(综合研判) |
| `plans/daily_review.py` | ~150 | 编排: 国际→国内→事件→综合, 含 format_report 文本输出 |

### 数据验证 (2026-06-14 实测)
- 美债10Y: 4.48% ✅ | 美联储利率: 4.5% ✅ | 黄金/白银/原油: 实时价格 ✅
- CPI: 0.4% ✅ | PMI: 49.4 ✅ | M2: 8.8% ✅ | LPR: 1Y=3.0%, 5Y=3.5% ✅
- 涨停89只 ✅ | 最高4连板 ✅ | 热门方向: 工业金属(11只) ✅
- 综合研判: 偏多(+2分) ✅

### 旧代码处置
- `macro_old/fetchers/global_macro.py` → 已迁移到 `collectors/macro.py`, 增加了 `_safe_latest` 列名自适应和 change_pct 计算
- `macro_old/fetchers/domestic_macro.py` → 已迁移到 `collectors/macro.py`, 同样使用自适应列名
- `macro_old/fetchers/event.py` → 已迁移到 `collectors/macro.py`, 增加了连板分布统计
- `macro_old/fetchers/sector.py` → 旧版本就是TODO stub, 暂未迁移(行业板块数据源待确认)
- `macro_old/analyzers/*` → 旧版本全部TODO stub, 全新设计了 `analysis/macro.py`

---

## 📋 剩余待完成清单

### ✅ P1 — 功能补全 (已完成 2026-06-14)
| # | 任务 | 状态 |
|---|------|------|
| 1 | 舆情补全: 集成东财新闻搜索 | ✅ 已完成 |
| 2 | 新浪新闻搜索评估 | ✅ 已测试，无补充价值，放弃 |
| 3 | 主力资金流替代方案 | ⏸️ 无可用数据源，暂不实现 |
| 4 | 概念资金流替代方案 | ⏸️ 无可用数据源，暂不实现 |
| 5 | 融资融券数据源 | ⏸️ 无可用数据源，暂不实现 |
| 6 | 行业板块数据 | ⏸️ 无可用数据源，暂不实现 |
| 7 | **互动易/上证e互动**（⚠️ 重要） | ⏸️ 投资者问答是舆情核心，巨潮/上证e互动/akshare 均不可用(SPA无JSON)。待找到数据源后优先实现 |

**说明**: 3-7项因服务器IP限制或接口不可用，暂无数据源。文档保留标记为"未完成"，不删除相关设计。

### ✅ P2 — 工程质量 (已完成 2026-06-14)
| # | 任务 | 状态 |
|---|------|------|
| 1 | config/default.yaml 修正 | ✅ 权重改为4维度(各0.25) |
| 2 | __pycache__ 清理 | ✅ git中无缓存文件 |
| 3 | 旧代码清理 | ✅ 删除 micro_old/macro_old/fetchers_old/analyzers_old (1592行) |
| 4 | 单元测试 | ⏸️ 暂不实施 |

---

### ✅ P3 — 优化与分析增强 (已完成 2026-06-14)

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| 1 | 北向时间窗口修复 | ✅ | 换用 `stock_hsgt_individual_em`，加过期标注(港交所2024-08停止披露) |
| 2 | 权重配置一致性 | ✅ | `scorer.py` 读取 `config/default.yaml`，支持动态权重缩放 |
| 3 | 量价关系分析 | ✅ | 放量突破(+4)/缩量回调(+2)/天量天价(-5) 三种信号 |
| 4 | 多头/空头排列判断 | ✅ | MA5>10>20>60 多头(+5), MA5<10<20<60 空头(-5) |
| 5 | 多维共振评分 | ✅ | 3维同向+8分, 4维同向+12分 |
| 6 | 概念分析缓存 | ✅ | 10分钟TTL文件缓存(`cache/`) |
| 7 | JSON summary模式 | ✅ | `--summary` 输出~200 token紧凑JSON |
| 8 | 估值水平评估 | ✅ | PE/PB绝对值区间评分(行业均值API被封) |
| 9 | 大盘指数环境 | ✅ | 上证/深证/创业板实时 + 个股相对强度 |
| 10 | 大宗交易数据 | ⏸️ | 新浪接口返回空数组，暂无可用数据源 |
| 11 | 股东变动数据 | ✅ | 同花顺大股东增减持(akshare) |
|| 12 | 历史对比 | ✅ | 快照缓存+价格/评分/评级变化对比 |

---

## 📋 2026-06-15 更新

### HTML 报告系统 (新增)
| # | 任务 | 状态 |
|---|------|------|
| 1 | `templates/base.html` 暗色主题 + CSS 变量 + 移动端适配 | ✅ |
| 2 | 6 个可复用组件 (metric_grid / signal_badge / score_gauge / progress_bar / data_table / collapsible) | ✅ |
| 3 | `stock_report.html` 个股分析报告模板 (8 模块) | ✅ |
| 4 | `concept_report.html` / `market_report.html` 占位模板 | ✅ |
| 5 | `core/html_renderer.py` 通用 Jinja2 渲染器 | ✅ |
| 6 | CLI `--html` 参数 (analyze / concept / market) | ✅ |

### 互动易问答数据源 (新增)
| # | 任务 | 状态 |
|---|------|------|
| 1 | `collectors/sentiment.py:interactive_qa()` — 东财互动易采集器 | ✅ |
| 2 | `analysis/sentiment.py` 集成互动易数据 | ✅ |
| 3 | HTML 模板新增互动易折叠面板 | ✅ |
| 4 | 数据源: `guba.eastmoney.com/qa/qa_search.aspx` (Direct, 无需代理) | ✅ |

### Bug 修复
| Bug | 修复 |
|-----|------|
| `change_pct` 读到涨跌额而非涨跌幅 | 腾讯 API `d[31]` → `d[32]` |

---

## 📋 2026-06-17 更新

### 概念"刚启动"判定优化

**问题**: 旧逻辑仅用"首日上涨 (consecutive_days==1)"判定刚启动，但之前可能已经涨过一波，不算真正底部启动。

**改进**: 新增近一月低点对比过滤

| # | 改动 | 说明 |
|---|------|------|
| 1 | `_get_limit_up_pct(symbol)` | 按代码前缀区分涨停幅度：主板10%、创业板/科创板20%、北交所30% |
| 2 | `_is_just_started(klines, symbol)` | 双重条件：①首日上涨 ②当前价相对近20日低点涨幅 ≤ 涨停×1.2 |
| 3 | 动量分类重构 | `just_started` 从 `days==1 and pct>0` 改为调用 `_is_just_started()` |
| 4 | breakout_stocks 筛选 | 改用 `rise_from_low < threshold` 替代 `consecutive_days<=1` |
| 5 | 输出增强 | 突破股显示"距月低+X%"，直观展示启动位置 |

**阈值设计**:
- 主板: 涨停10% × 1.2 = **12%** (首次涨停不被排除)
- 创业板/科创板: 涨停20% × 1.2 = **24%**
- 北交所: 涨停30% × 1.2 = **36%**

**修改文件**: `analysis/concept.py`, `plans/concept_analysis.py`

### 概念数据源重构 — 东财push2直连 (v4)

**问题**: 
- 新浪概念列表过时 (175个，无芯片/半导体/AI等热门概念)
- 手动维护热门概念成分股不准确 (如存储芯片票被错误归入HBM)
- 与stock_review项目耦合，Cookie管理混乱

**方案**: 东财push2直连 + 离线增量缓存 + 独立Cookie管理

| # | 改动 | 说明 |
|---|------|------|
| 1 | `collectors/em_concept.py` | 东财push2采集器 (独立Cookie, 离线缓存, 增量合并) |
| 2 | `analysis/concept_rank.py` | 重写: 资金流入排序, top_n个概念, 离线兜底 |
| 3 | `plans/concept_analysis.py` | 适配新接口, 删除load_concept_mapping调用 |
| 4 | `data/em_cookie.txt` | 独立Cookie存储 (不再读取stock_review) |
| 5 | `data/concept_cache.json` | 离线概念缓存 (增量更新, 逐次积累) |
| 6 | 删除 `data/concept_mapping.json` | 新浪映射表已废弃 |
| 7 | 删除 `data/hot_concepts_manual.json` | 手动维护概念已废弃 |

**核心逻辑**:
1. **排序**: 按资金流入(f62)排序概念, 过滤非行业概念, 保留top_n个
2. **成分股**: 按涨幅(f3)获取前100只, 合并到离线缓存 (增量: 新增股票追加)
3. **兜底**: 在线失败时从离线缓存读取 (离线缓存会越来越完整)
4. **Cookie**: 独立存储, 过期时向用户索要, 不与stock_review混用

**数据验证** (2026-06-18):
- 概念列表: 10个有效概念 (资金流入排序, 过滤非行业) ✅
- 半导体概念(BK0917): 100只成分股, 均涨+9.12%, 资金流+170亿 ✅
- 离线缓存: 10个概念, 916只成分股 (首次运行即建立) ✅

**修改文件**: 新增 `collectors/em_concept.py`, `data/em_cookie.txt`, `data/concept_cache.json`; 重写 `analysis/concept_rank.py`; 修改 `plans/concept_analysis.py`

---

## 📝 2026-06-18 配置管理重构

### Cookie配置统一管理

**问题**: 
- Cookie分散在多个位置 (`data/em_cookie.txt`, 硬编码等)
- 没有配置模板，用户不知道需要哪些配置
- 本地开发时需要手动复制文件

**方案**: 统一配置文件管理

| # | 改动 | 说明 |
|---|------|------|
| 1 | `config/config.example.yaml` | 配置模板，提交git，用户参考 |
| 2 | `config/config.yaml` | 实际配置，不提交git，本地使用 |
| 3 | `collectors/em_concept.py` | 从 `config.yaml` 读取Cookie |
| 4 | `.gitignore` | 添加 `config/config.yaml` |
| 5 | 删除 `data/em_cookie.txt` | 已废弃 |

**配置项**:
```yaml
eastmoney:
  cookie: "your_cookie_here"  # 浏览器F12获取
  ut: "8dec03ba335b81bf4ebdf7b29ec27d15"  # 固定参数
```

**使用流程**:
```bash
# 1. 复制模板
cp config/config.example.yaml config/config.yaml

# 2. 填入实际Cookie
vim config/config.yaml

# 3. 运行程序
python3 plans/concept_analysis.py
```

**本地开发**: 直接从 `config.yaml` 读取，无需额外操作

**用户部署**: 
1. 复制 `config.example.yaml` 为 `config.yaml`
2. 填入自己的东方财富Cookie
3. 运行程序

**Cookie有效期**: 通常1-7天，过期时需要重新获取

**修改文件**: 新增 `config/config.example.yaml`, `config/config.yaml`; 修改 `collectors/em_concept.py`, `.gitignore`; 删除 `data/em_cookie.txt`

---

## 📋 2026-06-20 Bug修复

### 持续性分布口径矛盾修复

| Bug | 原因 | 修复 |
|-----|------|------|
| 持续性分布"下跌"包含平盘/微涨 | 用`consecutive_down_days`判断，但实际跌幅可能≥0 | 改为真实跌幅<0判定"下跌"，新增"震荡/平盘"类别 |
| `breakout_stocks`过滤与`just_started`计数不一致 | breakout用`consecutive_days<=1`，just_started用双重条件 | 统一加`consecutive_days<=1`条件，与just_started口径一致 |

**修改文件**: `analysis/concept.py`, `plans/concept_analysis.py`

---

## 📋 2026-06-21 概念采集重构 v5→v6 (Playwright)

### 核心改动: 东财push2直连 → Playwright页面导航拦截

**问题**: 东财push2直连在服务器IP上频繁限流(ERR_EMPTY_RESPONSE)，Cookie无法根治。

**方案**: 用Playwright真实浏览器访问东财行情页，拦截XHR响应获取数据。

| # | Commit | 改动 |
|---|--------|------|
| 1 | `5e5b736` | 概念选股只对过滤后的top10拉成分股，其余60个用API涨跌家数填充 |
| 2 | `eb5b9e6` | 合并为单次Playwright会话，去掉auto模式 |
| 3 | `ee053aa` | 成分股获取改为页面导航拦截，避免反爬 |
| 4 | `6b039e3` | 兼容东财新版dataapi域名，更新拦截规则 |
| 5 | `d5dd5bc` | 成分股获取改为详情页滚动触发懒加载 |
| 6 | `2c5f531` | 开放为Hermes Skill，支持其他用户部署使用 |

**新增模块**:
| 模块 | 行数 | 功能 |
|------|------|------|
| `collectors/em_browser.py` | 376 | 共享Playwright浏览器会话 (F10/股吧/搜索/研报) |
| `collectors/em_concept.py` | 770 | 概念采集v6 — Playwright页面导航拦截 (替代push2直连) |
| `config/__init__.py` | 59 | 统一配置管理 (Cookie + 代理 + get_proxy()) |

**修改模块**:
| 模块 | 改动 |
|------|------|
| `analysis/concept.py` | 418行，适配新数据源接口 |
| `analysis/concept_rank.py` | 259行，概念排名引擎重写 |
| `plans/concept_analysis.py` | 332行，适配Playwright采集器 |
| `collectors/sentiment.py` | 280行，新增互动易+新闻搜索+分析师评级 |

---

## 📋 当前代码结构 (2026-06-21)

```
/tmp/stock-analysis-pro/
├── core/
│   ├── cli.py              # 489行 CLI入口 (analyze/concept/market/add/rm/list)
│   └── html_renderer.py    # 81行  Jinja2通用渲染器
├── collectors/
│   ├── quote.py            # 190行 行情(腾讯+新浪)
│   ├── finance.py          # 105行 财务数据(akshare)
│   ├── flow.py             # 156行 资金流(腾讯+akshare)
│   ├── info.py             # 56行  公司信息(东财F10+同花顺)
│   ├── sentiment.py        # 280行 舆情(股吧+互动易+新闻+分析师评级)
│   ├── em_concept.py       # 770行 概念采集v6(Playwright页面导航拦截)
│   ├── em_browser.py       # 376行 共享Playwright会话(F10/股吧/搜索/研报)
│   ├── concept.py          # 215行 旧版概念采集(新浪,已废弃)
│   ├── macro.py            # 354行 宏观数据(全球+国内+涨停复盘)
│   ├── cache.py            # 40行  TTL缓存
│   └── __init__.py
├── analysis/
│   ├── technical.py        # 265行 技术面
│   ├── fundamental.py      # 74行  基本面
│   ├── valuation.py        # 44行  估值
│   ├── capital.py          # 17行  资金面
│   ├── sentiment.py        # 80行  舆情
│   ├── company.py          # 82行  公司概况
│   ├── scorer.py           # 404行 综合评分(4维±25)
│   ├── concept.py          # 418行 概念趋势定性+机会挖掘
│   ├── concept_rank.py     # 259行 概念排名引擎
│   └── macro.py            # 351行 宏观分析
├── plans/
│   ├── stock_analysis.py   # 152行 个股分析编排
│   ├── concept_analysis.py # 332行 概念分析编排
│   └── daily_review.py     # 191行 宏观概览编排
├── templates/
│   ├── base.html           # 197行 暗色主题+CSS变量+移动端
│   ├── stock_report.html   # 440行 个股报告模板(8模块)
│   ├── concept_report.html # 245行 概念报告模板
│   ├── market_report.html  # 244行 市场报告模板
│   └── components/         # 6个可复用组件
│       ├── metric_grid.html
│       ├── signal_badge.html
│       ├── score_gauge.html
│       ├── progress_bar.html
│       ├── data_table.html
│       └── collapsible.html
├── config/
│   ├── __init__.py         # 59行  配置管理(Cookie+代理+get_proxy)
│   ├── config.yaml         # 实际配置(不提交git)
│   └── config.example.yaml # 配置模板(提交git)
├── scripts/
│   └── check_concept_mapping.py  # 166行 概念映射季度检查
└── data/
    ├── concept_cache.json  # 离线概念缓存(增量更新)
    └── watchlist.json      # 自选股列表
```

---

## 📋 当前待完成清单

### ⏸️ 暂不实施（无可用数据源）
- 主力资金流替代方案
- 概念资金流替代方案
- 融资融券数据源
- 行业板块数据
- 大宗交易数据
- 行业估值对比

### 🔮 未来优化方向
- 概念过滤优化（品牌/政策/指数/重叠概念分类）
- 单元测试
- 报告模板个性化定制
- 更多数据源接入（同花顺/雪球）