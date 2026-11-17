# 新机会扫描 (Opportunity Scan) 设计文档

状态: **已确认, 实现中** (2026-11-18)
定位: 每日复盘报告新板块 —— 以短期信号为导火索，梳理个股逻辑，最终筛选长期值得投资的票。**短期信号 + 长期价值** 双维度。

## 一、目标

现有复盘报告只对**持仓票**做LLM逻辑验证(thesis校验, llm_interpret.py)。本模块对**未持仓的机会票**做反向工作: 从每日两类异动信号中入池，梳理"为什么放量/进榜"，并叠加长期价值评估，输出可操作建议(进自选/观察/放弃)。

## 二、入池规则 (每日上限15只)

### A. 新进TOP50 (优先, 最多10只)
- 口径沿用 generate_new_top50.py: 当日成交额TOP50 且 **近5个交易日都没进过榜** (取近5个缓存日top50并集对比, cache_dates.py 日期指针)。
- 不做硬剔除(2026-11-18决议): 金融权重票(如东方财富)也收进池, 交给LLM判skip, 避免关键词误杀。
- 不足10只按实际数量, 不补位到B类。

### B. 点火首放低位股 (补满至15只)
- 数据源: 当日 `output/daily_content/ignition_data_YYYYMMDD.json` (点火雷达已落盘)。
- 条件: `vol_tag == '首放'` 且 `p60 <= 50` (60日价格分位, 低位定义; 阈值待确认30/50)。
- 顺序: 按事件卡片排名 **top1事件往前取**, 同事件内按 p60 升序。
- 与A类去重(同票只保留A类身份)。

### 量级实测 (2026-11-17)
- 新进TOP50: 4只 (剔东方财富后3只)
- 点火TOP5事件内首放且p60≤50: 4只
- 合计约 **7只/天**, 远低于15上限; 极端行情日会顶到上限, 由优先级规则截断。

## 三、数据富化

| 字段 | A类(新进TOP50) | B类(点火首放) | 来源 |
|---|---|---|---|
| 名称/代码/成交额 | ✅缓存已有 | ✅已有 | stock_amount_cache / ignition_data |
| 涨幅/PE/PB/市值/换手 | 需补 | 部分需补 | 腾讯 tencent_detail (qt.gtimg.cn, 批量1请求) |
| p60/p250位置分位 | 需补 | ✅已有 | tencent_kline 250日 + calc_price_percentile |
| 主营/概念标签 | 需补 | ✅已有 | data/stock_business_map.json (TTL 180天缓存, 缺失走F10) |
| 公告/新闻标题 | 需抓 | 需抓 | 东财 np-anotice-stock 接口 + Google News RSS (proxy) |

**红线**: 成交额只走腾讯实时 index37 或缓存, 严禁 tencent_kline/sina_kline 的 volume 冒充; K线备源只吃 close/volume (AGENTS.md 勿扩散红线)。

## 四、LLM 判定 (轻量版起步)

复用 `llm_interpret.py` 基建: `_call_llm_json` / qwen3.6-flash / temperature=0 / config读key / scheme拼接 / 当日缓存。

每只票一次调用 (不抓正文, 只用标题级信息):
- 输入: 行情快照(涨幅/量比/换手/p60/PE/PB/市值) + 主营(F10) + 概念标签 + 所属点火事件名(如有) + 公告/新闻标题(≤8条)
- 输出 JSON:
  - `catalyst`: 催化归因 (announcement/news/none=纯资金) + 一句话摘要
  - `signal_quality`: 短期信号质量 (strong/medium/weak) —— 放量位置、是否一字板买不进、连板高度
  - `value_rating`: 长期价值评级 (high/medium/low/unclear) —— 行业空间、主营竞争地位、估值合理性
  - `value_logic`: 长期逻辑一句话 (value_rating=high/medium 必填)
  - `action`: **watchlist(进自选) / observe(观察) / skip(放弃)** + 理由一句话
  - action规则: signal_quality≥medium 且 value_rating≥medium → watchlist; 单边好 → observe; 双弱 → skip
- 失败降级: 单票LLM失败输出纯数据行, 不阻塞整体 (同 llm_interpret 模式)。

### Token 估算
每只约 1.5~2k input + 300 output → 15只/天 ≈ **25~35k tokens/天** (flash级, 每天<1分钱)。

### 二期 (暂不做)
action=watchlist 的票二次深挖: 抓公告PDF/新闻正文, 输出深度逻辑报告。每天仅2~4次调用。等一期跑稳后再上。

## 五、工程挂载

- 新文件 `analysis/opportunity_scan.py`:
  - `collect_candidates(date)` → 入池列表(A+B, 含富化数据)
  - `scan(date, verbose)` → LLM判定 + 缓存 `cache/review_history/opportunity_cache_YYYYMMDD.json` (输入hash不变0调用, 同llm_interpret模式)
- `plans/daily_report.py` run() 新增 **7f步** (7e极端行情后、8落盘前), 失败降级不阻塞。
- 落盘: review_history JSON 新增 `opportunity_scan` 字段 (候选+判定), 同日重跑保留已填非空。
- 模板: 新增 **🔭 新机会扫描** 板块, 位置在持仓/自选之后、指引之前; 按 action 分组排序 (watchlist 置顶红色高亮, skip 折叠); 每票一行: 名称(代码) | 信号来源标签(新进TOP50/点火首放) | 催化 | 价值评级 | 建议。
- 依赖顺序: 需在点火雷达(15:35 cron)与 stock_amount 缓存生成之后跑 —— 复盘cron 18:30 满足; 手动补跑若当日点火数据缺失, B类降级为空, 只出A类。

## 六、已确认决议 (2026-11-18)

1. 低位阈值: **p60 ≤ 50** (宽口径, 位置好坏交给LLM在signal_quality里评)。
2. 金融权重票: **不硬剔**, 收进池交给LLM判skip (避免关键词误杀)。
3. watchlist 票: **只提示, 不自动写入**自选股文件, 报告里标注人工加。
