# Stocks - 股票复盘软件

个人股票复盘工具：A 股 / ETF 行情复盘与财务分析。浏览器访问，数据源自 Tushare。

## 功能

- **概览**：日概览（指数/市场统计/情绪趋势/板块排行）、涨停、跌停、龙虎榜、涨幅榜，支持按交易日回看
- **A 股**：全市场股票列表（搜索/筛选/排序）、自选股分组管理、股票详情（K 线 + 复盘回放模拟交易）
- **财务分析**：1~10 只股票三大报表对比（体检卡/指标对比/五维雷达/全科目报表，不支持银行股）
- **ETF**：全 ETF 列表（品类筛选/排序）、ETF 涨幅榜

详细功能文档见 [docs/](docs/)：

| 文档 | 内容 |
|---|---|
| [docs/overview.md](docs/overview.md) | 概览页 |
| [docs/A_stocks.md](docs/A_stocks.md) | A 股（列表/自选/详情/回放） |
| [docs/policy.md](docs/policy.md) | 已下线模块的历史设计，待重新讨论 |
| [docs/financial-analysis.md](docs/financial-analysis.md) | 财务分析模块 |
| [docs/etf.md](docs/etf.md) | ETF 模块 |
| [docs/tushare_permissions.md](docs/tushare_permissions.md) | Tushare 接口权限归档 |
| [docs/frontend-style-guide.md](docs/frontend-style-guide.md) | 前端样式规范 |

## 技术栈

- 前端：Vue 3 + TypeScript + Vite + Pinia + Vue Router
- 图表：TradingView Lightweight Charts + ECharts
- 后端：Python FastAPI + SQLModel + pandas + numpy
- 数据库：SQLite
- 数据源：Tushare（统一使用普通 token）
- 通信：HTTP REST API（单账号登录鉴权）

## 目录结构

```
backend/    Python FastAPI 后端
  app/        应用代码（routers / services / strategies / models）
  scripts/    数据同步与迁移脚本
frontend/   Vue 3 前端
docs/       功能与设计文档
```

## 快速开始

### 后端

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev        # 开发
```

### 生产部署

```bash
cd frontend && npm run build       # 构建前端（由后端托管静态文件）
cd ../backend && source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问：`http://<服务器IP>:8000`

服务器上后端以 systemd 服务常驻（服务名 `stocks`）：

```bash
systemctl restart stocks     # 改代码后重启
journalctl -u stocks -f      # 查看日志（同时输出到 backend/logs/server.log）
```

## 配置

| 配置项 | 位置 | 说明 |
|---|---|---|
| Tushare token | `/etc/kimi/stocks/base.conf` 的 `[tushare]` 节 | 全站唯一数据源 token（高权限 token 已废弃） |
| 公网 IP / 域名 | `backend/.env` 的 `PUBLIC_HOST` | CORS 白名单 |
| 登录账号/密钥 | `backend/.env` 的 `AUTH_USERNAME` / `AUTH_PASSWORD` / `AUTH_SECRET` | 单账号登录 |

首次启动前复制 `backend/.env.example` 为 `backend/.env` 并填写登录配置。
登录账号和密码不得为空，签名密钥至少 32 字符，建议使用 `python -c "import secrets; print(secrets.token_hex(32))"` 生成。
缺少配置时后端拒绝启动；配置文件按绝对项目路径加载，不依赖启动目录。真实凭据只保存在服务器环境或被 Git 忽略的 `.env` 中。
修改登录账号、密码或签名密钥后需重启服务，已有 token 随即失效。本次鉴权升级也会使升级前的登录态失效，需要重新登录。

核心回归验证（在已安装后端依赖的环境执行，不访问 Tushare、不写业务数据库）：

```bash
cd backend
python -m unittest discover -s tests -v
```

## 数据同步

系统 crontab 在每个交易日收盘后自动同步数据：

- 16:00 日概览/每日行情入库（`scripts/import_daily.py`）
- 16:20 策略行情快照（`scripts/sync_strategy_data.py --quote-days 5 --skip-bars`）
- 16:40 K 线数据（`scripts/sync_strategy_data.py --quote-days 1 --bar-days 10`）
- 19:00 财报增量校验 + 亮点 Top100 算榜（`scripts/sync_fin_daily.py`，每天）

页面同时保留手动同步入口。

## 开发约定

- 所有时间统一使用 UTC 存储，前端按用户时区显示
- 数据库 Schema 变更使用迁移脚本管理（`backend/scripts/`）
- 数据源只用 Tushare；如需其他数据源请先确认
- 不开源，仅个人使用
