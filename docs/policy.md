# 策略选股

策略选股模块用于按不同选股逻辑筛选当日或历史交易日的潜力标的。当前已实现选股与回测功能。

## 功能入口

- 选股页面：`/strategies`
- 回测页面：`/backtest`
- 选股 API：`/api/strategies`
- 回测 API：`/api/backtests`

## 接口说明

### 列出所有策略

```http
GET /api/strategies
```

返回策略 ID、名称和描述。

### 执行选股

```http
GET /api/strategies/{strategy_id}/picks?trade_date=YYYY-MM-DD&force_refresh=false
```

返回 Top10 选股结果：

```json
{
  "strategy_id": "dragon-tiger",
  "trade_date": "2026-06-24",
  "count": 10,
  "items": [
    {
      "code": "000001",
      "name": "平安银行",
      "score": 92.5,
      "buy_price": 12.34,
      "reason": "龙虎榜净买占比 3.21%，主板小市值（流通市值 45.2亿）"
    }
  ]
}
```

## 当前策略列表

| 策略 ID | 名称 | 说明 | 文档 |
|---|---|---|---|
| `dragon-tiger` | 龙虎榜游资追踪 | 基于龙虎榜净买入数据，聚焦主板小市值 | [dragon-tiger.md](policy/dragon-tiger.md) |
| `piglet` | 首板不破·龙头跟踪 | 捕捉首次涨停后持续不跌破首板的强势龙头，标注游资介入 | [piglet.md](policy/piglet.md) |

## 公共过滤条件

所有策略统一过滤以下标的：

- ST 股票（名称含 ST 或 *ST）
- 退市股票（名称含"退"）
- 科创板（688 开头）
- 创业板（300/301 开头）
- 北交所（8/43/82/83/87/88/89/920 开头）
- 次新股（上市不满 365 天）

## 评分规则

每个策略内部计算原始评分，然后通过 Min-Max 归一化到 0-100，便于不同策略之间横向对比。

## 回测模块

### 入口

- 前端页面：`/backtest`
- 运行回测：`POST /api/backtests/run`
- 查询结果：`GET /api/backtests/{run_id}`
- 历史记录：`GET /api/backtests`

### 当前支持策略

- `piglet`（首板不破·龙头跟踪）

### 回测规则

- 收盘后产生信号，下一交易日开盘买入
- 持有固定交易日后开盘卖出
- 目标仓位 = 当前总权益 / 最大持仓数
- 买入数量向下取整到 100 股整数倍
- 佣金双边收取

### 可调参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `window_days` | 5 | 选股回看窗口天数 |
| `hold_days` | 5 | 买入后持有天数 |
| `max_positions` | 5 | 最大同时持仓数 |
| `max_per_day` | 2 | 每个信号日最多新增仓位 |
| `require_dragon` | false | 是否只交易有龙虎榜游资介入的股票 |
| `initial_capital` | 100000 | 初始资金 |
| `commission_rate` | 0.0003 | 佣金率（双边） |

### 数据与范围限制

- 当前回测实时从 Tushare 拉取数据，引擎内部带日期级缓存减少重复请求
- 为避免长请求超时，回测改为后台异步执行：`POST /api/backtests/run` 立即返回 `run_id`，前端轮询结果
- 实时 Tushare 模式限制最大回测区间为 **15 天**（日历日），超出会报错

## 缓存机制

策略结果缓存已禁用：每次请求都实时计算。`force_refresh` 参数保留在接口签名中，当前无实际作用。历史计算结果会持久化到本地数据库，可按交易日回看。

## 后续规划

- 增加更多选股策略
- 支持策略组合与权重配置
- 回测数据改为本地缓存后可放开 15 天区间限制
