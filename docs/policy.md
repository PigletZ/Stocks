# 策略选股

策略选股模块用于按不同选股逻辑筛选当日或历史交易日的潜力标的。当前版本仅实现选股功能，回测模块后续补充。

## 功能入口

- 前端页面：`/strategies`
- 后端 API：`/api/strategies`

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
| `volume-breakout` | 放量突破 | 成交量为 20 日均量 2 倍以上且创 20 日新高 | [volume-breakout.md](policy/volume-breakout.md) |
| `momentum-leader` | 强势领涨 | 近 5 日涨幅位于市场前 10% 且当日继续放量上涨 | [momentum-leader.md](policy/momentum-leader.md) |

## 公共过滤条件

所有策略统一过滤以下标的：

- ST 股票（名称含 ST 或 *ST）
- 科创板（688 开头）
- 创业板（300/301 开头）
- 北交所（8/43/82/83/87/88/89/920 开头）
- 次新股（上市不满 365 天）

## 评分规则

每个策略内部计算原始评分，然后通过 Min-Max 归一化到 0-100，便于不同策略之间横向对比。

## 缓存机制

选股结果缓存 4 小时，命中缓存直接返回，避免重复调用 Tushare。可通过 `force_refresh=true` 强制刷新。

## 后续规划

- 增加更多选股策略
- 接入回测模块
- 支持策略组合与权重配置
