# 系统监控

## 功能入口

- 系统监控页：`/system`

## 接口

- `GET /api/system/status`：数据库体积、缓存表新鲜度、定时任务日志健康度（只读）

## 监控内容

### 数据缓存（8 张表）
市场统计 / 指数日线 / 板块日线 / 个股行情快照 / 涨停明细 / 龙虎榜 / 财务亮点榜 / K线（主板）
- 每张表显示最新数据日期、行数；最新日期超过容差天数标记"滞后"

### 定时任务（对应系统 crontab 4 个任务）
- 状态判定：日志 mtime 超过预期窗口 → 滞后；日志尾部出现 Traceback/ERROR/失败 → 异常（并展示错误行 + 最后 5 行日志）
- 任务清单硬编码在 `app/services/system_service.py` 的 `CRON_JOBS`，crontab 变更时需同步

## 本模块上线时顺带修复的问题

1. `sync_strategy_data.py` 循环内异常未 `session.rollback()`，一次失败导致后续全部失败（监控页首次运行即发现）
2. `overview_service._fetch_sector_daily_from_tushare` 用 `or 0` 兜底 NaN（NaN 是 truthy），导致板块写入撞 NOT NULL 约束
3. `import_daily.py` 增加"近日补漏"：涨停明细/龙虎榜/板块/市场统计对最近 3 个交易日检查缺失并补同步（解决 limit_list_d、ths_daily 发布晚于 16:00 cron 导致的漏天）
