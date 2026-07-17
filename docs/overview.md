# 概览页

## 简介

概览页以 Tab 页形式展示每日复盘数据，共 5 个 Tab：**日概览、涨停、跌停、龙虎榜、涨幅榜**。

页面数据优先从本地数据库读取；数据在每个交易日收盘后由系统定时任务（16:00 起）自动同步入库，页面同时保留手动同步入口。

## Tab 页功能

### 日概览

- 支持按日期回看（交易日历选择器），默认展示最近一个有数据的交易日；当天未开盘或非交易日时回落到上一交易日
- 主要指数板块
    - 上证指数、深证成指、创业板指、科创50、北证50
    - 鼠标悬浮时显示该指数最近 30 日 K 线图
- 市场统计板块（卡片）
    - 涨跌家数、平盘家数、涨停、跌停、炸板、总成交额
- 市场情绪趋势
    - 折线图，可切换：涨跌家数 / 涨停数 / 跌停数
    - 支持近一周、近一个月、近三月及自定义起止时间
- 板块排行（同花顺行业 / 概念板块）
    - 各取涨幅前 50
    - 支持按涨跌幅、成交量排序（Tushare `ths_daily` 无成交额字段，以成交量替代）
    - 数据落库（`sectordaily` 表）后展示；并发写入使用 `INSERT ... ON CONFLICT DO UPDATE` 原子 upsert
- 数据同步
    - 支持手动同步当天数据（`POST /api/overview/sync-daily`、`POST /api/overview/sync-sectors`）
- 数据来源
    - 采集：交易日下午 16:00 定时任务统计入库
    - 页面展示默认读库；库中缺失时回源 Tushare 拉取并入库

### 涨停

- 支持选择日期，默认展示当天涨停个股
- 个股信息：
    - 股票代码、名称
    - 最新价、涨跌幅、成交额
    - 封单比、换手率
    - 流通值、总市值
    - 首封时间、封住时间、开板次数
    - 几天几板
    - 涨停分析
- 操作：复盘跳转、加入自选
- 数据入库，后续查询默认查库

### 跌停

- 支持选择日期，默认展示当天跌停个股
- 个股信息：
    - 股票代码、名称
    - 最新价、涨跌幅、成交额
    - 封单比、换手率
    - 流通值、总市值
    - 首封时间、封住时间、开板次数
    - 跌停分析
- 数据入库，后续查询默认查库

### 龙虎榜

- 支持按日期筛选
- 分组展示：游资 / 机构
    - 代码、名称、上榜日、收盘价、涨跌幅、龙虎榜净买额、上榜原因
- 过滤本地 `Stock` 表中不存在的代码（如可转债、B 股等）
- 操作：复盘跳转、加入自选

### 涨幅榜

- 区间涨幅排行：**五日涨幅榜、十日涨幅榜、二十日涨幅榜**
- 列表字段：排名、代码、名称、最新价、区间涨幅、成交额、换手率、所属行业
- 操作：复盘跳转、加入自选

## 相关接口

- `GET /api/overview/daily-overview?date=`：日概览
- `GET /api/overview/market-history?start=&end=`：市场情绪趋势
- `GET /api/overview/index-bars/{code}?start=&end=`：指数 K 线
- `GET /api/overview/sectors-daily?date=&type=&sort_by=&limit=`：板块排行
- `GET /api/overview/limit-up?date=` / `limit-down?date=`：涨停 / 跌停
- `GET /api/overview/dragon-tiger?date=`：龙虎榜
- `GET /api/overview/top-gainers?date=`：区间涨幅榜
- `GET /api/overview/trade-dates?start=&end=`：交易日历
- `POST /api/overview/sync-daily` / `POST /api/overview/sync-sectors`：手动同步
