# stock-analysis-pro Agent备忘

项目核心文档。Agent 动本项目前先读此文件；改动代码必须同步更新此文档。
相关文档: DESIGN.md(设计)、USAGE.md(用法)、DAILY_CONTENT.md / DAILY_CONTENT_PROJECT.md(抖音内容)、IGNITION_RADAR_DESIGN.md(点火雷达)、PROGRESS.md。

## 数据源与接口

- industry_screener.py: 新浪行情 + 同花顺F10主营业务；剔除北交所；成交额 /10000 转亿。
- 概念资金流(两套口径, 2026-09-30主力口径上线):
  - **主力口径**(默认): 同花顺官方 `stockpage.10jqka.com.cn/stock_page/api/v1/stockpage/funds/?code=<885码>&marketId=48` = 超大单/大单/中单/小单四档，与同花顺APP"主力资金"同口径(用户对照APP验证一致)。主力净额=超大单+大单。四单净额之和恒为0(按委托单大小双侧记账)。封装在 `collectors/ths_mainforce.py`，无需hexin-v，375概念约70秒，当日缓存 `cache/ths_mainforce_YYYYMMDD.json`(仅15:05后生成的缓存有效)。
  - **全口径**(gnzjl): akshare `stock_fund_flow_concept("即时")` = 全量387概念，净额=主动买-主动卖(主动口径)。网页版只返回涨幅TOP50有采样偏差(弃用)。资金榜需过滤宽基桶(融资融券/股通/国企改革等)，但"国家大基金持股"是真题材不可误杀。
  - **两口径不可相加**：主力=按委托单大小分档("谁在买")，主动=按成交方向("买方急不急")。背离信号: 主力流出≥0.5亿+主动流入≥2亿=⚠派发嫌疑；反向=吸筹嫌疑。
  - 概念名→885码映射: `data/ths_concept_885_mapping.json`，由 `scripts/build_ths_885_mapping.py` 生成(概念详情页隐藏域clid，375概念约4分钟)，季度刷新(挂concept-mapping-check cron)。
- 概念板块日K历史(collectors/ths_board_hist.py): 直连 `d.10jqka.com.cn/v4/line/bk_<885码>/01/<year>.js`(hexin-v cookie, 与akshare同法生成), **不碰被风控的q.10jqka详情页**, 375概念全量约2分钟零封禁(2026-10-12实测)。缓存 `cache/concept_amount_history.json`(近70交易日成交额, git不提交), generate_matrix 前置 ensure_history_fresh 幂等刷新。用途: 板块量比=今日K线额/自身20日均额(时序自比, 免疫成分股数量/天生活跃度截面偏置)。口径坑: gnzjl流入+流出≈0.65×真实成交额, 与K线额不同口径, 量比统一用K线口径; gnzjl总额仅作离群校验(K线今日额<gnzjl总额×0.4→数据异常降级NaN)。
- 一级行业板块日K(同collector): 881码日K同一接口可拉(`bk_881xxx`), 90行业约20秒。映射 `data/ths_industry_881_mapping.json`(akshare `stock_board_industry_name_ths()` 直接返回881码, 无需爬详情页; scripts/build_ths_industry_mapping.py 生成, 季度刷新), 缓存 `cache/industry_amount_history.json`。用途: 点火雷达事件卡片板块量比标签(LLM标签是行业级, 行业881优先匹配, 概念885兜底; generate_ignition内 ensure_industry_history_fresh 幂等刷新)。
- 个股全市场资金流用新浪。
- 个股日K线(tencent_kline, industry_screener.py与daily_report.py各一份): 主源腾讯 `web.ifzq.gtimg.cn fqkline`(qfq前复权)，2026-10-13起备源新浪 `quotes.sina.cn CN_MarketDataService.getKLineData`，腾讯WAF拦截(返回501/HTML)时自动切换。备源口径对齐: ①复权——新浪K线原始为不复权, 用因子接口 `finance.sina.com.cn/realstock/company/{symbol}/qfq.js` 做 raw/f 前复权还原(茅台500根对照东财qfq: 不复权误差3.71%→还原后0.38%; 因子失败退回不复权并打警告); ②volume——新浪单位为股, /100换手对齐腾讯(实测比值恰100)。验证脚本 `scripts/verify_kline_fallback.py`。**⚠勿扩散红线: 新浪K线只有volume(成交量)、没有成交额(元)**——历史上"成交量趋势"曾误把volume当成交额酿成单位错误。所有需成交额的地方(TOP10/TOP50/板块总额等)严禁调用tencent_kline/sina_kline_fallback，成交额一律走腾讯实时qt.gtimg.cn index37(万)或同花顺K线。当前备源合法消费方: 点火雷达L3(分位/首放/形态)、fetch_stock_indicators(连涨/分位)、daily_report(calc_multi_day_change/技术指标)——全部只吃close/volume。
- 涨跌家数(collectors/breadth.py fetch_breadth): 新浪Market_Center.getHQNodeData全量翻页(hs_a~56页,约15秒)优先——2026-09-30与同花顺APP对照验证一致(涨2566/跌2824/平181 vs APP 2567/2824/170)；东财push2兜底(同日返回2393/2730与APP偏差大,口径存疑,且时好时坏)；腾讯getBoardRankList弃用(aStock板块仅4606只覆盖不全)。涨跌停用akshare涨停池(fetch_limit_stats)。同花顺无直接家数接口(zdfb页chameleon反爬,iwencai本机DNS不通)。plans/daily_report.py的fetch_market_breadth已委托collector,勿再重复实现。
- 同花顺/东财字段映射必须打印验证，不可假设。
- 服务器为 ARM(aarch64)，akshare 同花顺接口依赖 py_mini_racer 软链修复（venv 重装后需重建软链）。

## 报告要求

- 行业筛选报告必须包含: 催化新闻(带日期) + 行情回顾时间线 + 有价值环节分梯队；目标是可操作(入场时机)。
- 行业分析模块放每个行业卡片之后(循环内 if 匹配)，不集中到报告末尾；排名总览只列 top15，其余归"其它"；每个 top5 行业都要分析。
- 行业分类到二级(主营业务)，不用概念板块。
- 新闻搜索: Google News RSS (curl --proxy http://127.0.0.1:10809) 最稳定；百度易触发验证码；Bing国际版 curl 无法解析需浏览器。
- cron 复盘报告输出: `cache/review_report_YYYYMMDD_HHMM.html`。
- 复盘落盘层(2026-10-30, S2): `analysis/review_history.py` — daily_report.run()末尾自动落盘 `cache/review_history/YYYYMMDD.json`(情绪快照/指引/个股提示, 预留thesis_checks/info_digest/assertions/extreme)，供情绪时序(S3)/研判验证(S5)/极端对照(S6)消费。同日重跑覆盖但保留已填非空字段；写入原子化(.tmp+rename)；读取全部容错(缺失/损坏跳过不崩)。max_lianban取自akshare涨停池lianban字段。设计详见 REVIEW_UPGRADE_DESIGN.md §三。
- 情绪周期定位(2026-10-30, S3): `analysis/sentiment_cycle.py` — 规则引擎热度打分(上涨家数30+涨停25+连板20+成交额偏离25=100)五档定位(冰点/修复/发酵/高潮/退潮), 硬覆盖up<800→冰点, 趋势<−8→退潮; 纯字符串内嵌SVG三联图(上涨家数柱/涨跌停折线/成交额+MA20)。daily_report.run()中先算周期(7b)后落盘(8), cycle_phase入JSON。阈值用10-29真实大跌日校准(初版普跌日打分不够冷, 见PROGRESS.md)。模板消费result.sentiment_cycle/sentiment_ts_svg, 无数据整块不渲染。⚠SVG小样本坑(2026-10-30修): 柱宽plot_w/n与端点式柱心i/(n-1)叠加, n=2时柱子负坐标越界侵入邻联——n≤4改槽位居中(i+0.5)/n+柱宽上限40px+clamp面板内。
- LLM解读流水线(2026-10-30, S4/F1+F2): `analysis/llm_interpret.py` — 持仓票两段式: 标题初筛(major/neutral/noise)→抓正文(公告=东财PDF `pdf.dfcfw.com/pdf/H2_{art_code}_1.pdf`+pymupdf, art_code来自np-anotice-stock接口已打印验证; 新闻=trafilatura降级正则; 研报仅标题)→合并判定(verdict四档+reason+evidence+每条major解读/影响标签, 附近3日verdict历史防重复报警)。qwen3.6-flash/temp=0/config读key/scheme拼接。缓存`cache/review_history/llm_cache_YYYYMMDD.json`(输入hash不变0次调用)。持仓条目3→8条(fetch_single_stock max_info), 自选保持3。run()7c步挂载, 失败降级纯标题不阻塞。落盘thesis_checks/info_digest。模板: 顶部警示区(仅weakened/invalid_risk)+卡片🧠逻辑状态行+条目解读标签(利好红/利空绿)+底部📖档案(details折叠, 警示票自动open排前)。trafilatura装在hermes venv(python3 -m pip, uv --system会被PEP668拒)。⚠盘前(0点后)手动补跑run()须显式传date=前一交易日, 否则落盘标错日期(cron 18:30不受影响)。
- 研判验证(2026-10-30, S5/F4): `analysis/verify_guidance.py` — generate_assertions(当日规则指引+市场数据→LLM改写3-5条次日可验证断言→落盘guidance.assertions) + verify_previous(读前一交易日assertions+stock_tips, 对照今日实际数据LLM逐条判hit/miss/unclear; 提示判定: 偏多涨hit/偏空跌hit/中性±1%内hit、±1~3%unclear、超±3%miss; 命中率近5/20日滚动, unclear不计分母)。共用llm_interpret的_call_llm_json; 缓存verify_cache_YYYYMMDD.json; run()7d步挂载(7c后、8落盘前), 失败降级不阻塞。落盘新增verification字段, 同日重跑不覆盖非空。模板: ✅昨日研判验证板块(指引前, ✓红✗绿A股配色)+📌今日断言盒(指引末尾)。
- 极端行情专区(2026-10-30, S6/F5): `analysis/extreme_mode.py` — check_triggers纯规则触发(上证/创业板≥±2%、上涨家数<1000或>4000、跌停>30或涨停>150、成交额较20日均偏离>±30%[现算与落盘同口径]); 触发才执行: RSS归因(Google News三组关键词走proxy→LLM 2-3句"今天为什么") + 结构拆解(涨跌停/权重vs题材分化[创业板-上证≥1pct]/领涨TOP5+领跌BOTTOM5[daily_report新增concepts_decline]) + 历史对照(情绪库相似日≥2条附其后1/5日上证表现; 不足走上证日K兜底±1pct相似日统计, **只用close严禁volume**) + 持仓应对LLM(thesis+行情→overall+per_stock, 固定免责)。缓存extreme_cache_YYYYMMDD.json; run()7e步挂载(7d后、8落盘前); 落盘extreme字段(同日重跑保留已触发); 各子项独立降级不阻塞。模板🌪专区(暖橙警示)插宏观后情绪前, 触发才渲染。

## 抖音内容 (daily_content)

- 竖屏 1080×1920，大字号(40px+)，金色高级感风格。
- **左右安全边距 ≥130px（强制，2026-09-30教训）**: 9:16视频在更窄长的手机屏(19.5:9~21:9)上，抖音"填满屏幕"会按高度撑满、左右对称裁切(每侧裁97~128px)。卡片/内容容器 left/right 必须 ≥130px(内容区≤820px宽)，60~70px 边距会导致卡片两侧被切。上下被抖音UI遮挡可接受(用户确认无所谓)，顶部仍留白 200px+。
- 新进TOP50分页规则: ≤10 单页大字；11-15 单页小字；>15 分页每页10只大字。
- **昨日成交额缓存定位用日期指针，不用天数回溯**（2026-10-08改造）: 旧方案 `range(1,5)` 只回溯4天，国庆休市8天后 top10/top50 对比数据全空（新进榜误报"50只全新进"）。现方案 `scripts/daily_content/cache_dates.py` 维护指针 `cache/daily_content/amount_cache_dates.json`（save_amount_cache 写入时登记），读取时取"今天之前最近的缓存日期"；指针缺失/损坏自动扫描目录重建。generate_stock_amount.py 三处 fetch_yesterday_* 与 generate_new_top50.py 均已接入，长假（春节/国庆）后无需干预。
- UI迭代原则: 小改动优先，保留内容元素，一张图一张图改。
- 中文文字渲染只能靠 HTML→截图，AI生图不可靠。
- 可视化必须有信息价值，拒绝"为了好看而好看"（全市场5000只热力图、无红绿对抗的热力图为反例）。
- 文本歧义: 写"约10亿"不写"~10亿"。
- ffmpeg: 系统 /usr/bin/ffmpeg 无 libx264（仅rkmpp硬编，init失败）；用静态版 `scripts/daily_content/ffmpeg_static`（imageio-ffmpeg，阿里云镜像 uv 安装；pip/uv 默认源和 johnvansickle.com 下载均超时）。
- **周末/节假日补跑方法（2026-10-17实操验证）**: run_all.py 周末直接拒跑且日期取now()，补跑须绕过入口分脚本跑。**⚠ faketime 与 hexin-v 互斥**——libfaketime 伪装时间后同花顺 hexin-v cookie 签名因时间戳校验失败被拒（gnzjl/板块日K 返回拦截页, `page_info` None 崩），所以：①依赖 hexin-v 的 generate_matrix.py 必须**真实时间**跑（其 trading_date() 周六自动回退上一交易日，标签正确）；②日期敏感但不碰 hexin-v 的脚本用 faketime（`LD_PRELOAD=/tmp/faketime-venv/.../libfaketime.so.1 FAKETIME="YYYY-MM-DD 15:35:00" DONT_FAKE_MONOTONIC=1`）：generate_new_top50.py、generate_anomaly.py（也可 --date 显式传）、generate_stock_amount.py（新浪/腾讯不校验签名）；③generate_ignition.py 的 date_str 走 detect_quote_date()（行情日期）天然正确，但其连板数据 fetch_limit_stats() 默认 date=今天，周末须 faketime 跑否则涨停池查错日期返回空；gnzjl成分家数子项在 faketime 下失败但已有 try/except 降级，不影响整体。HTML→PNG 截图用 run_all.html_to_png() 单独补。
- **cron定时必须≥15:30启动**（2026-10-13教训）: generate_matrix.py 的 trading_date() 以15:30为交易日阈值——15:30前运行会把当日数据标成前一日标签（且与真文件同名互相覆盖）。cron现为15:35，调整时间不得早于15:30。全流程约8-12分钟（v3.22加板块量比后），cron提示词必须要求后台运行+等待完成，前台600秒会杀进程。
- 动画视频已下线（v3.18，2026-09-27）。若日后重做：弃用 Playwright 实时录屏（帧率/时序不可控），改用帧精确管线——HTML内暴露 `window.__render(t)` 同步渲染 → 逐帧截图(30fps) → ffmpeg_static 合成 mp4。
- **点火雷达（2026-10-07，替代异常信号3张）**: 全市场放量股概览 + LLM行业聚类事件卡片。脚本 `generate_ignition.py`/`llm_industry.py`，设计文档 `IGNITION_RADAR_DESIGN.md`。LLM归类用 qwen3.6-flash（3.8-max批量超时），批20只，缓存 `data/llm_industry_cache.json`（数据文件，git不提交）。催化层（2026-10-07升级）：事件名+主属前5只个股名双层RSS检索 → LLM汇集排序（个股直接催化>行业政策>泛观点），≤3条摘要，失败降级原始标题，原始数据存 ignition_data_*.json。
- **点火雷达v6标签净化（2026-10-13）**: 聚合前LLM按F10主营业务剔擦边概念标签（只筛不造，`llm_label_filter.py`；主营缓存 `data/stock_business_map.json` TTL 180天防新增业务误剔，净化缓存 `data/llm_label_filter_cache.json`，均git不提交）；排序改绝对触发家数（tiebreaker=板块量比>首放占比，v5渗透率加权退役但score仍落盘回测）。属性直通标签（专精特新/一带一路/自贸区/指数持仓类等，`ATTRIBUTE_CONCEPTS`名单）不交LLM判、不参与聚合排名——否则霸屏且去重误并（验证教训）。详见设计文档§12。

## 概念成分股数据源风控备忘（2026-10-07实测，反向索引方案弃用原因）

- 东财 push2 HTTP直连: 时好时坏(当日全断, Empty reply)；Playwright链路拉成分股触发滑块(需人工)。
- 同花顺 q.10jqka.com.cn/gn/detail 成分股页: 非ajax完整页+v cookie(py_mini_racer ths.js)可用, 但约20次请求后403, IP封锁>25min, 全量375概念爬不动; ajax接口直接被chameleon拦。
- **basic.10jqka.com.cn (F10主营业务) 不受上述风控影响**, industry_screener链路正常。
- 结论: 个股→行业归类不要再走"全量成分股反向索引", 用LLM多标签归类(点火雷达方案)或F10逐票查询(量小时)。
