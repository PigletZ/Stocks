# A股

## 全市场股票

### 功能
- 手动同步 A 股股票基础信息（Tushare `stock_basic`）
- 手动同步每日行情数据（Tushare `daily` + `daily_basic`）
- 支持搜索（代码/名称模糊匹配）
- 支持行业筛选
- 支持分页（默认 50 条/页）
- 支持列排序（代码、名称、最新价、涨跌幅、成交额、换手率、流通市值、总市值、PE、PB、上市日期）
- 点击股票可进入详情页

### 列表字段
- 代码、名称
- 最新价、涨跌幅
- 成交额、换手率
- 流通市值、总市值
- PE、PB
- 行业
- 上市日期

### 数据来源
- 股票基础信息：Tushare `stock_basic`
- 行情数据：Tushare `daily` + `daily_basic`
- 同步时机：
  - 系统定时任务在每个交易日收盘后自动同步（见 crontab `import_daily.py` / `sync_strategy_data.py`）
  - 页面保留手动同步入口
- 全市场模糊搜索经优化为毫秒级响应

### 技术实现
- 后端：
  - `Stock` 模型扩展 `industry`、`list_date`、`updated_at` 字段
  - 新增 `StockDailyQuote` 模型缓存日线数据
  - `GET /api/stocks` 返回带分页、搜索、筛选、排序的股票列表
  - `GET /api/stocks/industries` 返回行业列表
  - `GET /api/stocks/{code}` 返回股票基本信息 + 最新行情
  - `POST /api/stocks/sync` 同步股票基础信息
  - `POST /api/stocks/quotes/sync` 同步每日行情
- 前端：`StockListView.vue` 表格展示，分页排序由后端处理

## 自选股票

### 功能
- 支持分组管理（创建、重命名、删除分组）
- 支持添加/移除股票到自选
- 支持移动股票到不同分组
- 展示自选股票最新行情（同全市场股票字段）

### 技术实现
- 后端：
  - 新增 `WatchlistGroup` 表
  - `WatchlistItem` 改用 `group_id` 外键关联分组
  - `GET /api/watchlist/groups` 返回分组及组内股票（含行情）
  - `POST /api/watchlist/groups` 创建分组
  - `PUT /api/watchlist/groups/{id}` 重命名分组
  - `DELETE /api/watchlist/groups/{id}` 删除分组
  - `POST /api/watchlist/{code}` 加自选
  - `PUT /api/watchlist/{code}/group` 移动分组
  - `DELETE /api/watchlist/{code}` 移除自选
- 前端：`WatchlistView.vue` 分组卡片布局，支持分组 CRUD

## 股票详情

### 功能
- K 线图（日线 only，Tushare `daily`）
- 股票基本信息展示（名称、代码、行业、上市日期、交易所、最新价、涨跌幅、成交额、换手率、总市值、PE、PB）
- 复盘回放面板
    - 初始化回放会话（设定初始资金）
    - 回放控制（逐根 K 线推进）
    - 模拟买入 / 卖出，查看持仓与交易记录
- 无分钟级 K 线（无 Tushare 权限）

### 技术实现
- 后端：
  - `GET /api/bars/{code}?interval=1d` 使用 Tushare `daily` 接口
  - 回放会话与模拟交易：`POST /api/trades/session/{session_id}/init`、`GET/POST /api/trades/session/{session_id}`、`GET /api/trades/session/{session_id}/position`
- 前端：`StockDetailView.vue` 使用 `ChartPanel` 组件（TradingView Lightweight Charts）展示日线，侧边栏为回放面板（`stores/replay`）

## 数据源

- 仅使用 Tushare，已移除 AKShare 依赖
- 相关服务：`backend/app/services/tushare_stock_service.py`

## 数据库迁移

涉及迁移脚本（位于 `backend/scripts/`）：
- `migrate_add_stock_fields.py`：为 `stock` 表添加扩展字段
- `migrate_create_stock_daily_quote.py`：创建 `stockdailyquote` 表
- `migrate_watchlist_groups.py`：创建 `watchlistgroup` 表并迁移 `watchlistitem.group_name` 到 `group_id`

执行顺序：
1. 停止后端
2. 依次运行上述迁移脚本
3. 重启后端

## 单位说明

- 价格/涨跌幅：元 / %
- 成交额：元
- 市值：元
- 成交量（K 线）：股（Tushare `daily.vol` 为手，已乘 100 转换）
- 换手率：%
