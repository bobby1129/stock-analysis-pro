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
- 个股全市场资金流用新浪。
- 涨跌家数(collectors/breadth.py fetch_breadth): 新浪Market_Center.getHQNodeData全量翻页(hs_a~56页,约15秒)优先——2026-09-30与同花顺APP对照验证一致(涨2566/跌2824/平181 vs APP 2567/2824/170)；东财push2兜底(同日返回2393/2730与APP偏差大,口径存疑,且时好时坏)；腾讯getBoardRankList弃用(aStock板块仅4606只覆盖不全)。涨跌停用akshare涨停池(fetch_limit_stats)。同花顺无直接家数接口(zdfb页chameleon反爬,iwencai本机DNS不通)。plans/daily_report.py的fetch_market_breadth已委托collector,勿再重复实现。
- 同花顺/东财字段映射必须打印验证，不可假设。
- 服务器为 ARM(aarch64)，akshare 同花顺接口依赖 py_mini_racer 软链修复（venv 重装后需重建软链）。

## 报告要求

- 行业筛选报告必须包含: 催化新闻(带日期) + 行情回顾时间线 + 有价值环节分梯队；目标是可操作(入场时机)。
- 行业分析模块放每个行业卡片之后(循环内 if 匹配)，不集中到报告末尾；排名总览只列 top15，其余归"其它"；每个 top5 行业都要分析。
- 行业分类到二级(主营业务)，不用概念板块。
- 新闻搜索: Google News RSS (curl --proxy http://127.0.0.1:10809) 最稳定；百度易触发验证码；Bing国际版 curl 无法解析需浏览器。
- cron 复盘报告输出: `cache/review_report_YYYYMMDD_HHMM.html`。

## 抖音内容 (daily_content)

- 竖屏 1080×1920，大字号(40px+)，金色高级感风格。
- **左右安全边距 ≥130px（强制，2026-09-30教训）**: 9:16视频在更窄长的手机屏(19.5:9~21:9)上，抖音"填满屏幕"会按高度撑满、左右对称裁切(每侧裁97~128px)。卡片/内容容器 left/right 必须 ≥130px(内容区≤820px宽)，60~70px 边距会导致卡片两侧被切。上下被抖音UI遮挡可接受(用户确认无所谓)，顶部仍留白 200px+。
- 新进TOP50分页规则: ≤10 单页大字；11-15 单页小字；>15 分页每页10只大字。
- UI迭代原则: 小改动优先，保留内容元素，一张图一张图改。
- 中文文字渲染只能靠 HTML→截图，AI生图不可靠。
- 可视化必须有信息价值，拒绝"为了好看而好看"（全市场5000只热力图、无红绿对抗的热力图为反例）。
- 文本歧义: 写"约10亿"不写"~10亿"。
- ffmpeg: 系统 /usr/bin/ffmpeg 无 libx264（仅rkmpp硬编，init失败）；用静态版 `scripts/daily_content/ffmpeg_static`（imageio-ffmpeg，阿里云镜像 uv 安装；pip/uv 默认源和 johnvansickle.com 下载均超时）。
- 动画视频已下线（v3.18，2026-09-27）。若日后重做：弃用 Playwright 实时录屏（帧率/时序不可控），改用帧精确管线——HTML内暴露 `window.__render(t)` 同步渲染 → 逐帧截图(30fps) → ffmpeg_static 合成 mp4。
- **点火雷达（2026-10-07，替代异常信号3张）**: 全市场放量股概览 + LLM行业聚类事件卡片。脚本 `generate_ignition.py`/`llm_industry.py`，设计文档 `IGNITION_RADAR_DESIGN.md`。LLM归类用 qwen3.6-flash（3.8-max批量超时），批20只，缓存 `data/llm_industry_cache.json`（数据文件，git不提交）。

## 概念成分股数据源风控备忘（2026-10-07实测，反向索引方案弃用原因）

- 东财 push2 HTTP直连: 时好时坏(当日全断, Empty reply)；Playwright链路拉成分股触发滑块(需人工)。
- 同花顺 q.10jqka.com.cn/gn/detail 成分股页: 非ajax完整页+v cookie(py_mini_racer ths.js)可用, 但约20次请求后403, IP封锁>25min, 全量375概念爬不动; ajax接口直接被chameleon拦。
- **basic.10jqka.com.cn (F10主营业务) 不受上述风控影响**, industry_screener链路正常。
- 结论: 个股→行业归类不要再走"全量成分股反向索引", 用LLM多标签归类(点火雷达方案)或F10逐票查询(量小时)。
