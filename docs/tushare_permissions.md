# Tushare 接口权限清单

> 2026-07-17 逐项实测归档（31 个接口）。验证脚本：`/tmp/hp_check.py`（改 token 可复跑）。

## 结论

- 全站统一使用 `[tushare]` 普通 token（`/etc/kimi/stocks/base.conf`）。
- 原 `[high_privilege_tushare]` 已废弃：实测其权限（18/31）被普通 token（27/31）全面覆盖，没有任何一项是普通 token 没有的，已从配置和代码中移除。

## 普通 token 有权限的接口（27/31）

| 分类 | 数据 | 接口 |
|---|---|---|
| 基础数据 | 股票列表 | `stock_basic` |
| | ETF 列表 | `fund_basic` |
| | 期权列表 | `opt_basic` |
| 行情 | 日线 / 周线 / 月线 | `daily` / `weekly` / `monthly` |
| | ETF 日线 | `fund_daily` |
| 财务 | 利润表、财务指标 | `income`、`fina_indicator` |
| 宏观 | GDP / CPI | `cn_gdp`、`cn_cpi` |
| 沪深港通 | 标的列表 | `hs_const` |
| 参考数据 | 股权质押 | `pledge_stat` |
| | 限售解禁 | `share_float` |
| | 回购 | `repurchase` |
| | 增减持 | `stk_holdertrade` |
| | 龙虎榜 | `top_list` |
| | 融资融券 | `margin_detail` |
| 特色/打板专题 | 同花顺板块及成分 | `ths_index`、`ths_member`、`ths_daily` |
| | 涨停榜单 | `limit_list_d` |
| | 开盘啦涨停 | `kpl_list` |
| | 资金流向 | `moneyflow` |
| | 券商金股 | `broker_recommend` |
| | 筹码分布 | `cyq_chips`、`cyq_perf` |
| | 量化因子 | `stk_factor` |
| | 盈利预测 | `report_rc` |
| | 机构调研 | `stk_surv` |
| | 游资名录 | `hm_list` |

## 普通 token 也没有的接口（需更高积分）

| 数据 | 接口 |
|---|---|
| 游资每日明细 | `hm_detail` |
| 连板天梯 | `limit_step` |
| 同花顺热榜（个股/行业/概念） | `ths_hot` |
| 东方财富热榜 | `dc_hot` |

如需以上数据，需提升 Tushare 账号积分后重试。

## 注意事项

- **ST 股票列表**：无专门接口（`st_list` 不存在），用 `namechange`（曾用名）变通识别。
- **沪深港通标的**：用 `hs_const`（`hsgt_list` 不存在）。
- **周线/月线**：`trade_date` 必须传周五 / 月末交易日，否则返回空表（不是权限问题）。

## 接口参数约束（2026-07-21 实测补充）

- **三大报表与财务指标必须逐股拉取**：`income` / `balancesheet` / `cashflow` / `fina_indicator` 的 `ts_code` 为必填，`pro.query` 通用接口同样校验。即不存在"按 period 整批拉全市场"的调用方式，全市场财报只能逐股回源（每股 1 次调用可带回全部报告期）。
- **业绩预告 `forecast`**：`ann_date` 和 `ts_code` 至少传一个。
- **业绩快报 `express`**：支持仅按 `period` 整批拉取，但覆盖稀疏（如 2026Q1 仅 19 家），不能作为全市场数据源。

## 2026-11-27 游资动向实测补充

- `top_inst` 当前可用，2026-11-26 返回 880 条原始记录，含可转债；模块只保留 A 股。
- `hm_list` 当前可用，返回 121 条名录，关联营业部实际为 JSON 字符串列表，使用简称。
- `hm_detail` 当前仍无权限。游资动向采用 `top_list` + `top_inst` + `hm_list`，关联名录和原始席位分别保留，不将简称关联当作实名归属证明。
- 真实源记录存在席位金额缺失/异常以及个别个股总额不对齐；保留原始值，受影响的单笔金额显示未知，不补零，不影响其他有效单据。
## 2026-11-27 宽基资金观察实测

- `etf_share_size` 无权限；`fund_share`、`fund_nav`、`fund_adj`、`fund_daily`、`fund_basic` 均可用，宽基模块采用普通接口。
- `fund_share` 支持多代码逗号查询，份额单位为万份；`fund_daily.amount` 为千元，分别转换一次。`fund_nav` 提供独立的净值日和公告日，不用成交价替代。
- 固定10只基金最近45个真实交易日通过解析与接口验证；缺失或因子变化时估算保留未知，不能由份额变化识别资金主体。