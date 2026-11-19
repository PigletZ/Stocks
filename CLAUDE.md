# Stocks - 股票复盘软件

个人本地股票复盘软件

## 技术方案

- 前端：Vue 3 + TypeScript + Vite + Pinia + Vue Router
- 运行形态：本地 Web 应用（浏览器访问），前端与 Python 后端通过 HTTP API 通信
- 后端：Python FastAPI + SQLModel + pandas + numpy
- 图表：TradingView Lightweight Charts + ECharts
- 数据源：只使用Tushare
- 数据库：SQLite
- 通信：HTTP REST API
- 开源：暂不开放源代码，作为个人工具使用

## 页面导航栏结构
- 策略选股、选股器、策略回测已下线，相关历史文档仅供后续重做参考。保留历史数据库表与共享行情同步脚本，不向网页暴露入口或接口。
- 概览：主要包含日概览、涨停、跌停、龙虎榜、涨幅榜等，详情可参看：docs/overview.md
- 复盘：连板梯队（昨日涨停今日表现）、情绪周期曲线、复盘日志（笔记+交易台账），详情可参看：docs/review.md
- A股：主要包含所有股票信息以及自选股信息，详情可参看：docs/A_stocks.md
- 策略选股：详情可参看：docs/policy.md
- 选股器：通用条件组合筛选（可保存预设并接入策略选股），详情可参看：docs/policy.md 通用选股器一节
- 策略回测：详情可参看：docs/policy.md 回测模块一节
- 财务分析：1~10 只股票三大报表对比分析（不支持银行股），详情可参看：docs/financial-analysis.md
- ETF：全 ETF 列表与 ETF 涨幅榜，详情可参看：docs/etf.md
- 系统管理：数据完整度、接口诊断、任务结果、常用配置与备份状态，详情可参看：docs/system.md
- Tushare 接口权限归档：docs/tushare_permissions.md

## 目录结构
- backend：Python FastAPI 后端
- frontend：Vue 3 前端
- docs: 方案、设计文档等存放处
- CLAUDE.md：claude文档
- README.md： git readme 文档

## Build && Run && Test
- git地址：git@github.com:PigletZ/Stocks.git

-  backend
    - 执行命令
        - cd backend && python -m venv venv && source venv/bin/activate
        - pip install -r requirements.txt
        - uvicorn app.main:app --reload --port 8000

- frontend
    - 执行命令
        - cd frontend && npm install && npm install

- 配置公网 IP
    - 配置文件在backend/.env的PUBLIC_HOST

- Run
    - 执行命令
        - cd frontend && npm run build
        - cd ../backend && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000

- 访问页面
    - 浏览地址：http://你的公网IP:8000


## 开发约定
- 所有时间统一使用 UTC 存储，前端按用户时区显示。
- 价格统一使用 `Decimal` 或整数“分”存储，避免浮点误差。
- 数据库 Schema 变更使用迁移脚本管理。
- 图表渲染优先使用 Canvas/WebGL，保证大数据量流畅。
- 核心回放引擎与 UI 解耦，便于后续接入回测与策略。
- 数据源只用Tushare，如果Tushare没有需和我确认是否使用其他数据源


