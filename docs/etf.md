# ETF

ETF 模块包含两个页面：**全 ETF 列表** 与 **ETF 涨幅榜**，在侧边栏以独立分组展示。

## 全 ETF 列表（`/etfs`）

### 功能
- 展示全部场内 ETF（约 2800+ 只）
- 支持按品类筛选（宽基、行业、主题、债券、商品、跨境等，按名称/业绩基准关键词规则归类）
- 支持列排序（最新价、涨跌幅、成交额等）
- 支持分页

### 列表字段
- 代码、名称
- 基金公司、基金类型
- 品类（自动归类）
- 最新价、涨跌幅、成交额

## ETF 涨幅榜（`/etfs/gainers`）

### 功能
- 按交易日展示 ETF 涨幅排行，包含 2 日 / 5 日 / 10 日 / 20 日四个窗口
  - 2 日榜定位"异动预警"，响应快但噪音大，默认过滤当日成交额 < 1000 万的 ETF（可用 `min_amount` 参数调整）
  - 5/10/20 日榜定位"趋势确认"，不过滤成交额
- 支持日期选择回看；所选日期无数据时自动回落到最近一个有数据的交易日
- 支持按品类筛选

## 数据来源

- ETF 基础列表：Tushare `fund_basic(market='E')`，内存缓存 1 小时
- ETF 日线行情：Tushare `fund_daily(trade_date=...)`，按交易日拉取
- 数据不入库，均为实时拉取 + 进程内缓存
- token：与全站统一，使用 `[tushare]` 普通 token（高权限 token 已废弃，见 [tushare_permissions.md](tushare_permissions.md)）

## 相关接口

- `GET /api/etfs/list?sort_by=&order=&offset=&limit=&category=`：ETF 列表（含最新行情）
- `GET /api/etfs/categories`：品类列表
- `GET /api/etfs/gainers?date=&category=&min_amount=`：涨幅榜（`min_amount` 为 2 日榜最低成交额，单位万元，默认 1000）

## 技术实现

- 后端：`backend/app/services/etf_service.py`（`EtfService`）、`backend/app/routers/etf.py`
- 前端：`EtfListView.vue`、`EtfGainersView.vue`
