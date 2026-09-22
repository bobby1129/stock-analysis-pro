# 抖音日更内容项目文档

## 项目目标

为抖音制作每日股市数据可视化内容，生成竖屏图片（1080×1920），包含以下5个主题：

1. 个股成交额TOP10
2. 概念板块排行（涨幅+净流入）
3. 新进成交额TOP50
4. 异常信号捕捉
5. 市场情绪日报

## 当前状态（2026-09-18）

### ✅ 已完成

#### 1. 个股成交额TOP10
- **状态**：已完成
- **数据源**：新浪行情接口（全市场数据）
- **接口**：`https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData`
- **参数**：`sort=amount`（按成交额排序）
- **显示字段**：排名、股票、现价、涨幅、成交额、环比
- **环比机制**：每日运行后缓存成交额到 `cache/daily_content/stock_amount_cache_YYYYMMDD.json`，次日读取计算环比增减
- **输出文件**：`output/daily_content/stock_amount_top10_YYYYMMDD.html` → `.png`

#### 2. 概念板块表现
- **状态**：已完成
- **数据源**：同花顺概念板块资金流向
- **接口**：`https://data.10jqka.com.cn/funds/gnzjl/`
- **显示内容**：
  - 涨幅排行TOP8：排名、概念名称、涨跌幅、领涨股
  - 净流入排行TOP6：排名、概念名称、涨跌幅、净流入
  - 两个区域均带金色表头行
- **字段映射**：
  - `cols[1]`：概念名称
  - `cols[3]`：涨跌幅
  - `cols[6]`：净流入（亿元）
  - `cols[8]`：领涨股
  - `cols[9]`：领涨股涨幅
- **输出文件**：`output/daily_content/concept_YYYYMMDD.html` → `.png`

#### 3. 异常信号捕捉
- **状态**：已完成
- **数据源**：腾讯行情接口（获取量比数据）
- **接口**：`https://qt.gtimg.cn/q=`（批量获取）
- **检测信号**：
  - 放量滞涨（量比>3 且 涨幅<1%）
  - 缩量新高（量比<0.8 且 涨幅>5%）
  - 放量急拉（量比>2 且 涨幅>5%）
- **量比字段**：腾讯接口返回数据的第49个字段
- **输出文件**：`output/daily_content/anomaly_YYYYMMDD.html` → `.png`

#### 4. 市场情绪日报
- **状态**：部分完成（成交量数据有问题）
- **数据源**：
  - 涨跌家数：东方财富接口
  - 涨停数据：akshare
  - 成交量趋势：新浪K线API（**有问题**）
- **接口**：
  - 涨跌家数：`https://push2.eastmoney.com/api/qt/ulist.np/get`
  - 涨停数据：`akshare.stock_zt_pool_em()`
  - 成交量：`https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData`
- **显示内容**：
  - 涨跌家数分布
  - 涨跌停统计
  - 连板梯队
  - 全市场成交量趋势（**数据错误**）
- **输出文件**：`output/daily_content/sentiment_YYYYMMDD.html` → `.png`

### ❌ 已删除

#### 个股净流入TOP10
- **原因**：新浪行情接口没有净流入字段
- **测试发现**：新浪接口返回的字段中不包含`netamount`或类似的净流入数据
- **替代方案**：无（同花顺接口只返回50条数据，不是全市场）

## 数据源详细说明

### 新浪行情接口
- **用途**：个股成交额TOP10
- **优点**：全市场数据，可排序
- **缺点**：没有净流入字段
- **返回字段**：symbol, code, name, trade, pricechange, changepercent, volume, amount等

### 同花顺接口
- **用途**：概念板块资金流向、个股资金流向
- **优点**：有净流入数据
- **缺点**：个股数据只返回50条，不是全市场
- **返回字段**：序号、代码、名称、最新价、涨跌幅、换手率、流入资金、流出资金、净额、成交额

### 腾讯行情接口
- **用途**：获取量比数据（用于异常信号检测）
- **优点**：批量获取，包含量比字段
- **缺点**：K线数据没有成交额字段
- **返回字段**：88个字段，第49个字段是量比

### 东方财富接口
- **用途**：涨跌家数统计
- **优点**：实时数据
- **缺点**：从当前服务器访问不稳定（需要代理）
- **返回字段**：上涨家数、下跌家数、平盘家数

### akshare
- **用途**：涨停数据
- **优点**：封装好的接口，易用
- **缺点**：依赖第三方库
- **返回字段**：涨停股票列表，包含连板数

## 已知问题

### 1. 成交量数据错误（严重）
- **问题描述**：市场情绪日报中的"全市场成交量趋势"数据显示的是成交量（股数），不是成交额（元）
- **根本原因**：新浪K线API只返回`volume`字段（成交量），不返回成交额
- **当前代码**：`float(item['volume']) / 1e8`，错误地把成交量当作成交额处理
- **影响**：显示的数据单位是"亿股"，但标注为"亿元"，数据完全错误
- **测试数据**：
  - 2026-09-18：volume=48571250700，当前显示486亿（错误）
  - 实际成交额：约9942亿元（来自腾讯实时行情API字段37）

### 2. 东方财富接口访问不稳定
- **问题描述**：从当前服务器访问东方财富API需要代理，且经常超时
- **影响**：涨跌家数数据获取不稳定
- **临时方案**：使用akshare的breadth模块

### 3. 同花顺个股数据不完整
- **问题描述**：同花顺接口只返回50条个股数据，不是全市场
- **影响**：无法获取全市场的个股净流入TOP10
- **已采取措施**：删除了个股净流入TOP10功能

## 待解决问题

### 1. 修复成交量数据（优先级：高）
**解决方案选项**：

**方案A：用成交量×均价估算成交额**
```python
# 从腾讯API获取K线数据
# 数据格式：[日期, 开盘, 收盘, 最高, 最低, 成交量]
avg_price = (open + close + high + low) / 4
amount = volume * 100 * avg_price  # 成交量单位是手，1手=100股
```
- 优点：可以用现有API
- 缺点：是估算值，有误差

**方案B：寻找提供历史成交额的API**
- 东方财富API有成交额字段，但从当前服务器访问不了
- 需要找到其他数据源

**方案C：只获取当天成交额，不做历史趋势**
- 用新浪实时行情API获取当天成交额
- 放弃历史趋势图
- 优点：数据准确
- 缺点：没有趋势对比

### 2. 优化数据获取稳定性（优先级：中）
- 为东方财富接口添加重试机制
- 考虑使用备用数据源

### 3. 代码重构（优先级：低）
- 将HTML生成逻辑统一到一个文件
- 当前分散在多个临时脚本中（`/tmp/generate_*.py`）

## 文件结构

```
~/stock-analysis-pro/
├── output/daily_content/          # 生成的HTML和PNG文件
│   ├── stock_amount_top10_YYYYMMDD.html/png
│   ├── concept_YYYYMMDD.html/png
│   ├── anomaly_YYYYMMDD.html/png
│   └── sentiment_YYYYMMDD.html/png
├── collectors/                    # 数据采集模块
│   ├── breadth.py                # 涨跌家数和涨停数据
│   ├── ths_concept.py            # 同花顺概念板块
│   └── quote.py                  # 行情数据
└── DAILY_CONTENT_PROJECT.md      # 本文档
```

## 生成脚本位置

当前生成脚本都在`/tmp/`目录：
- `/tmp/generate_all.py` - 生成个股成交额TOP10和概念板块
- `/tmp/generate_anomaly_clean.py` - 生成异常信号捕捉
- `/tmp/generate_sentiment_volume.py` - 生成市场情绪日报

**建议**：将这些脚本移到`~/stock-analysis-pro/scripts/`目录，统一管理

## 下一步行动

1. **立即修复**：成交量数据问题（选择方案A/B/C）
2. **短期优化**：将生成脚本移到项目目录
3. **中期优化**：添加自动化测试，验证数据准确性
4. **长期规划**：考虑添加更多数据维度（如北向资金、融资融券等）

## 技术细节

### HTML模板
- 使用内联CSS，不依赖外部样式表
- 竖屏布局：1080×1920px
- 配色方案：深色背景（#1a1a2e），金色标题（#ffd700）

### 图片生成
- 使用Playwright将HTML转为PNG
- 脚本：`/tmp/html2png.py`
- 命令：`python /tmp/html2png.py input.html output.png`

### 数据更新频率
- 交易日15:00后更新（收盘后）
- 通过cron job自动运行（待配置）

## 联系方式

如有问题，请查看：
- 项目README：`~/stock-analysis-pro/README.md`
- 设计文档：`~/stock-analysis-pro/DESIGN.md`
- 进度记录：`~/stock-analysis-pro/PROGRESS.md`
