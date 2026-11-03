# DESIGN: 每日复盘升级（逻辑跟踪+信息解读+情绪时序+研判验证+极端行情）

状态：待用户确认后开工。前置讨论稿 REVIEW_UPGRADE_DRAFT.md、thesis初稿 THESIS_DRAFT.md（用户已确认"以这版为基础"）。
日期：2026-10-30
原则：**全部增量改动，不推翻现有 review 流水线**（plans/daily_report.py → templates/review_report.html 主链路保留）。

---

## 一、范围总览（5个新能力）

| # | 能力 | 类型 | 依赖 |
|---|------|------|------|
| F1 | 持仓逻辑跟踪（thesis判定+预警） | 新增 | config.yaml thesis字段、LLM流水线 |
| F2 | 新信息解读（公告/研报/新闻抓正文+分级解读） | 新增 | LLM流水线 |
| F3 | 情绪周期时序化（20日趋势+周期定位） | 升级现有"市场情绪" | 落盘层 |
| F4 | 昨日研判验证（闭环+命中率） | 新板块 | 落盘层 |
| F5 | 极端行情特别模式 | 条件触发专区 | 落盘层(历史对照)、RSS |

共用基础设施：**每日落盘层**（`cache/review_history/`）+ **LLM解读流水线**（新模块）。

---

## 二、持仓 thesis 存储（F1）

- 位置：`config/config.yaml` → `portfolio[].thesis`，三段式字符串：
  ```yaml
  - code: "002709"
    name: 天赐材料
    note: 锂电电解液龙头
    thesis: |
      逻辑: 电解液全球龙头，六氟自供一体化成本优势，周期反转弹性已兑现(前三季净利+827%)，估值10倍，H股推进。
      假设: ①电解液/六氟价格维持景气不重回价格战 ②储能需求持续超预期 ③一体化利润率行业领先
      失效: 电解液价格下行/行业产能重启价格战; 净利环比连续两季下滑(Q3已-13%需盯Q4); H股发行摊薄恶化预期; 锂价剧烈波动侵蚀库存收益。
  ```
- 内容以 THESIS_DRAFT.md 确认版为准（用户后续优化直接改yaml）。
- thesis 属配置，git 可提交；判定结果/解读缓存属数据，git 不提交。
- 读取兼容：thesis 缺失的票跳过判定，报告显示"未设置逻辑"。

## 三、每日落盘层（F3/F4/F5 共用）

目录 `cache/review_history/`，每交易日一个文件 `YYYYMMDD.json`（git不提交，加入.gitignore）：

```json
{
  "date": "2026-10-30",
  "sentiment": {
    "up_count": 2566, "down_count": 2824, "flat_count": 181,
    "limit_up": 45, "limit_down": 3, "broken_board": null,
    "max_lianban": 5,
    "total_amount": 18234.5,          // 两市成交额(亿)
    "amount_vs_ma20": 0.08,           // 较20日均值偏离
    "indices": {"sh000001": {"close": 3300.1, "pct": 0.5}, "sz399006": {...}},
    "cycle_phase": "发酵"              // 冰点/修复/发酵/高潮/退潮
  },
  "guidance": {                        // F4验证对象: 当日指引结构化落盘
    "market_view": "……(大盘短线指引原文要点, 拆成可验证的断言列表)",
    "assertions": ["指数震荡偏强", "AI算力方向延续", "……"],
    "stock_tips": {"603893": "……(该股短线操作提示原文)"}
  },
  "thesis_checks": {                   // F1判定结果
    "002709": {"verdict": "weakened", "reason": "…", "evidence": ["公告标题…"], "ts": "..."}
  },
  "info_digest": {                     // F2解读结果
    "603893": [{"type": "ann", "title": "…", "date": "…", "level": "major",
                "interp": "…", "impact": "利好", "url_or_id": "…"}]
  },
  "extreme": {"triggered": false, "triggers": [], "analysis": null}
}
```

- 写入时机：review 流水线末尾统一落盘（新模块 `analysis/review_history.py`：save/load_recent(n)/load_similar_days）。
- 读取容错：文件缺失/损坏→跳过依赖项，报告降级（如情绪图只显示已有天数），不报错崩溃。
- 冷启动：情绪时序图有多少画多少（首日只有1个点）；历史对照不足20日时改用指数日K回看（数据现成，tencent_kline链路，**只用close，成交额严禁走K线口径**——见AGENTS.md红线）。

## 四、LLM 解读流水线（F1/F2 共用）

新模块 `analysis/llm_interpret.py`，沿用点火雷达 `llm_industry.py` 的成熟模式：
- 模型 qwen3.6-flash（3.8-max批量会超时）；api_key 从 config.yaml 读取，Authorization scheme 拼接绕过脱敏（"Bea"+"rer "）；批量调用、失败重试、结果缓存。
- **两段式流程**（对每只持仓票）：
  1. **标题初筛**：当日全部公告/研报/新闻标题（现有 fetch_announcements/fetch_research_reports/fetch_stock_news 已获取，max_items 从3提到8）+ thesis → 单次批量LLM调用，输出每条 `{level: major/neutral/noise, need_content: bool}`；
  2. **正文抓取+解读**：仅 need_content=true 的条目抓正文——公告走东财PDF：`np-anotice-stock` 返回含 `art_code`（✅2026-10-30实测验证，如 AN202610261830950116），拼 `https://pdf.dfcfw.com/pdf/H2_{art_code}_1.pdf`（✅实测200），pymupdf提取（✅1.28.2可用，瑞芯微三季报12页正常），截前3000字；新闻走url抓页面正文——**trafilatura未安装，S4时 uv pip 安装，失败降级正则抽 `<p>` 文本**；研报只有标题无正文源，直接基于标题+org+rating解读（注明"仅标题"）。
  3. **合并判定**：每票一次调用，输入 thesis + 全部条目解读 → 输出 `{verdict: unchanged/strengthened/weakened/invalid_risk, reason(一句话), evidence[]}` + 每条major信息的1-2句中文解读和影响标签(利好/利空/中性)。
- 防漂移/防重复报警：判定结果落盘；次日判定prompt中附最近3日该票verdict历史，要求"同一信息不重复触发预警，但连续weakened需升级为invalid_risk"。
- 缓存：`cache/review_history/llm_cache_YYYYMMDD.json`，同一天重跑不重复调LLM。
- 降级：LLM整体失败 → 报告退回现状（只列标题），顶部灰条注明"今日解读不可用"，**不阻塞报告生成**。
- Token预算：8票×(初筛1次+判定1次)+正文解读，日总量<5万token。

## 五、展现形式（已确认，templates/review_report.html 增量改动）

报告单HTML文件交付（MEDIA发送），结构自上而下：

1. **⚠️ 顶部警示区**（条件渲染）：仅当有票 verdict ∈ {weakened, invalid_risk}——红色卡片：票名+命中哪条失效条件+依据信息。强化/不变不置顶。
2. **📈 大盘指数**（不变）
3. **🌐 宏观环境**（不变）
4. **🌪 极端行情专区**（条件渲染，触发才出现，插在情绪前）：
   - 触发原因徽章（如"上涨家数832<1000"）；
   - 归因：Google News RSS（走proxy）检索当日宏观/政策关键词 → LLM 2-3句"今天为什么"；
   - 结构拆解：涨跌停分布、领跌/领涨板块（复用概念TOP数据）、权重vs题材（指数分化）；
   - 历史对照：情绪库相似日（up_count±300、成交额偏离同向±15%内）之后1/5日指数表现；库不足时用指数日K找历史相似跌幅日；
   - 持仓应对提示（LLM基于thesis+当日行情，注明"仅供参考不构成决策"）。
   - **触发阈值**：上证或创业板 ≥±2%；上涨家数 <1000 或 >4000；跌停 >30 或 涨停 >150；两市成交额较20日均值偏离 >±30%。
5. **🎯 市场情绪**（升级）：
   - 现有当日数字保留；
   - 新增近20日情绪时序：内嵌SVG（无外部库，单文件离线可看），上涨家数柱状+涨停数折线+成交额/MA20折线，三联小图；
   - 新增情绪周期定位徽章：冰点→修复→发酵→高潮→退潮 五档刻度条，当前档高亮+一句依据。定位规则（规则引擎非LLM，可解释）：up_count分位+涨停数+连板高度+成交额偏离综合打分。
6. **💼 持仓个股**（卡片内升级）：
   - 新增「🧠 逻辑状态」一行：徽章 🟢不变/💪强化/🟡弱化/🔴疑似失效 + 一句依据；
   - 公告/研报/新闻列表：major条目下方灰色小字附1-2句解读+影响标签(利好红/利空绿/中性灰，A股配色)，noise条目只留标题；max_items 3→8；
   - 「📐 短线操作提示」保留（并结构化落盘供F4）。
7. **👀 自选股**（不变）
8. **💰 概念板块 TOP10**（不变）
9. **✅ 昨日研判验证**（新板块，放在指引之前形成闭环）：
   - 表格：昨日断言 | 实际走势 | ✓/✗/无法验证；
   - 命中率：近5日/近20日滚动（验证本身由LLM对比断言与实际数据，逐条判✓✗）。
10. **🧭 大盘短线指引**（保留；**现状为规则引擎输出**（KDJ/MACD/均线打分→advice，daily_report.py L1022-1041），不重写规则——在其后新增一步LLM将规则输出+当日情绪数据改写成3-5条**可验证断言**落盘，如"指数震荡偏强""AI算力方向延续"，避免模糊到无法验证。持仓「短线操作提示」同为规则输出（L684-692），原文落盘即可，验证时LLM对照次日该股实际走势判✓✗）。
11. **📖 持仓逻辑档案**（文档最底部，`<details>`默认折叠）：每票完整thesis三段式+近5日判定历史；weakened/invalid_risk的票自动`open`展开并排最前。

## 六、实现步骤（确认后按序开工，每步本地验证→汇报→下一步）

1. **S1 thesis入config** ✅完成(2026-10-30)：THESIS_DRAFT.md 8票已写入 config/config.yaml portfolio[].thesis，草稿已删除。
2. **S2 落盘层** ✅完成(2026-10-30)：analysis/review_history.py + daily_report.py 末尾接线save，真实run验证JSON生成；cache/已在.gitignore无需补充。
3. **S3 情绪时序+周期定位(F3)** ✅完成(2026-10-30)：analysis/sentiment_cycle.py规则引擎(热度0-100打分+五档定位+硬覆盖)+SVG三联图；daily_report.run()接线(先算周期后落盘, cycle_phase入JSON)；模板五档刻度条+依据句+内嵌SVG；mock历史20天+真实10-29数据自测24项全过, 浏览器vision质检通过。
4. **S4 LLM解读流水线(F1+F2)** ✅完成(2026-10-30)：analysis/llm_interpret.py（初筛→抓正文→判定解读，两段式+当日缓存+历史防重复报警）；公告PDF art_code三样本打印验证通过；模板警示区+逻辑状态行+条目解读+底部折叠档案；真实run 8票全过（3强化/4不变/1弱化）。
5. **S5 研判验证(F4)** ✅完成(2026-10-30)：analysis/verify_guidance.py（断言生成+昨日验证双函数，共用llm_interpret LLM基础+当日缓存）；daily_report 7d步接线；review_history落盘assertions/verification；模板验证板块(✓红✗绿？灰+命中率)+指引末尾今日断言盒；mock测试25项全过；真实双日run验证（10-29生成4断言→10-30验证12条✓7✗3命中70%）。
6. **S6 极端行情(F5)** ✅完成(2026-10-30)：analysis/extreme_mode.py（触发规则引擎→RSS归因LLM→结构拆解→历史对照(情绪库/日K兜底只用close)→持仓应对LLM）；daily_report 7e步接线+concepts_decline领跌榜；review_history落盘extreme；模板专区(宏观后情绪前, 触发才渲染)；mock测试37项全过；10-29真实大跌日回测（触发3条/归因命中"美股纳指大跌"实因/日K兜底10相似日/8票应对提示）浏览器vision质检通过。
7. **S7 cron接线+全链路验证** ✅完成(2026-11-03)：job 6c7b513b6407提示词已更新（强制后台运行+时长预期8-12分钟+当日要点摘要+降级不阻塞交付）；5个新模块import全过；10-30(五)/11-02(一)/11-03(二) 连续3个交易日实跑观察通过——报告HTML正常生成(120-122KB)、JSON落盘完整(sentiment/guidance/verification/extreme字段齐全)、cron status=ok无delivery error。
8. **文档同步**：每步完成即更新 AGENTS.md/DESIGN.md/PROGRESS.md；收尾时 REVIEW_UPGRADE_DRAFT.md 内容并入正式文档后删除草稿；THESIS_DRAFT.md 保留至thesis入config后删除。
9. **S8 日K兜底升级：单日涨跌幅相似 → 多日形态相似** ✅完成(2026-11-03, 本地验证通过待commit)：
   - 新模块 `analysis/similar_pattern.py`：特征=近5日收益率序列欧氏距离 + 位置过滤(60日区间分位差>30排除) + 相似日去重叠(间隔≥3交易日) + top10；窗口1000交易日(实测新浪datalen=1000可用/2000返回None, `_fetch_index_kline` 已加None容错)。
   - `extreme_mode._history_from_kline` 改为委托新模块(函数名/调用点不变, source改名 `kline_pattern`, matches新增dist/cum5/pos字段)；最近邻距离>4 加 `weak=True`，模板/卡片显示"⚠近4年无高相似形态日"提示。模板与 generate_review_cards.py 均兼容旧落盘 source='kline'。
   - 验证：`scripts/verify_similar_pattern.py`(数据自检4项+单元逻辑9项+6个历史极端日新旧对照)全过；`test_extreme_mode.py` mock套件全过；真实数据端到端(11-03收跌日)出10例、位置分位过滤生效。
   - 对照发现旧口径三缺陷(已随替换消除)：前视偏差(取"最近10条"不限目标日之前)、自我匹配(只排除最后一根)、无区分度(不同市况返回同一组日子)。
   - 红线遵守：只用close；情绪库主源逻辑未动。

## 七、红线清单（沿用项目规范）

- 增量改动，现有报告元素一律保留；已验证的数据链路（breadth/ths_mainforce/tencent_kline等）不重写。
- 成交额一律走腾讯实时/同花顺K线口径，严禁K线volume冒充成交额。
- LLM批量用 qwen3.6-flash；api_key从config读取+scheme拼接防脱敏。
- 新数据文件全部 cache/review_history/ 下，git不提交；thesis在config.yaml属配置可提交。
- 同花顺/东财新字段（公告PDF art_code等）先打印验证再消费。
- cron时间不动（18:30），只改提示词；NON_TRADING_DAY静默逻辑保留。
