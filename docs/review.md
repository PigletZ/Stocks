# 涨停复盘（连板梯队 + 情绪周期）

## 功能入口

- 连板梯队：`/review/ladder`
- 情绪周期：`/review/emotion`

## 数据落库

涨跌停/龙虎榜明细此前每次实时拉取、不落库。本模块新增两张缓存表：

| 表 | 来源接口 | 说明 |
|---|---|---|
| `limit_up_daily` | `limit_list_d` | 涨停(U)/跌停(D)/炸板(Z) 明细：连板数、涨停统计、封单额、首封/末封时间、开板次数等 |
| `dragon_tiger_daily` | `top_list` | 龙虎榜：买卖额、净买额、上榜原因（同票多条按 code 聚合），为回测本地化做准备 |

- 唯一键均为 `(stock_code, trade_date)`，当天整体覆盖式写入（delete + insert）
- 数据未就绪（空表/异常）时不触碰已有数据
- 每日 cron：`scripts/import_daily.py`（16:00）已增加两张表的同步步骤
- 历史回填：`scripts/import_limit_history.py`，已回填 2024-01-02 至今（与 marketdailystat 对齐，618 个交易日），已落库日期自动跳过可续传

## 接口

| 接口 | 说明 |
|---|---|
| `GET /api/review/limit-ladder?date=` | 连板梯队：涨停股按连板数分组（从高到低），含首封时间/开板次数 |
| `GET /api/review/limit-performance?date=` | 昨日涨停今日表现：晋级率、平均涨幅、明细（晋级/炸板/红盘/绿盘/跌停） |
| `GET /api/review/emotion?start&end` | 情绪周期时间序列：涨停/跌停/炸板数、炸板率、晋级率、最高板、成交额 |
| `POST /api/review/sync?date=` | 手动触发指定日期落库 |

## 口径说明

- **晋级**：昨日涨停（U）今日仍涨停
- **炸板率** = 炸板数 /（涨停数 + 炸板数），基于 marketdailystat
- **晋级率** = 今日涨停中昨日也涨停的家数 / 昨日涨停家数，基于 limit_up_daily
- **最高板**：当日涨停股最大连板数
- 昨日涨停的今日涨幅：优先取今日涨跌停表，其次 `stockdailyquote`，早于其覆盖范围（2026-04 之前）实时拉 `daily` 补齐（单日一次请求）

## 前端

- 连板梯队页：统计卡（昨日涨停数/晋级率/平均涨幅）+ 梯队图（按板数分列，点击个股打开 K 线明细弹窗）+ 昨日涨停今日表现明细表
- 情绪周期页：最新一日摘要卡 + 两张 ECharts（涨跌停与最高板 / 炸板率与晋级率），快捷区间 近一月~全部

# 复盘日志（笔记 + 交易台账）

## 功能入口

- 复盘日志：`/review/journal`

## 数据表

| 表 | 说明 |
|---|---|
| `review_note` | 每日复盘笔记（`note_date` 唯一，Markdown 文本 + 关联股票 codes JSON） |
| `trade_journal` | 真实交易台账（code/direction/price/quantity/fee/traded_at/note） |

## 接口（`/api/journal`）

| 接口 | 说明 |
|---|---|
| `GET/PUT/DELETE /note?date=` | 笔记查询/保存/删除 |
| `GET /note-dates?year&month` | 当月有笔记/有交易的日期（日历标记） |
| `GET/POST /trades`，`PUT/DELETE /trades/{id}` | 交易台账 CRUD；卖出数量超过该时点持仓会被拒绝 |
| `GET /positions` | 当前持仓：FIFO 成本（含买入费用摊薄）+ 最新收盘浮动盈亏 |
| `GET /stats` | 已实现盈亏、胜率（按卖出笔数）、买卖次数、累计费用 |

## 口径说明

- 持仓成本用 FIFO：卖出时从最早买入批次扣减，每股成本含买入费用摊薄
- 卖出盈亏 =（卖价 - FIFO 成本）× 数量 - 卖出费用；历史买入未录入导致的超卖部分按 0 成本计并记日志
- 页面三个 Tab：复盘笔记（日历 + 编辑器 + 当日交易）、交易台账（录入 + 明细表）、当前持仓

