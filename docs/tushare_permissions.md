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
