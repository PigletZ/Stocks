#!/usr/bin/env python3
"""每日财报增量同步 + 重算亮点 Top100 榜。

- 对股票池每股做 1 次 income 轻量校验，有新公告才三表回源（复用财务分析模块机制）
- 全部校验完成后重算当日亮点榜（纯本地计算）
- 建议 crontab 每交易日 19:00 执行（收盘数据与涨跌停榜单发布之后）

用法：
    cd /kimi/projects/Stocks/backend
    venv/bin/python scripts/sync_fin_daily.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session

from app.database import engine
from app.services.financial_service import FinancialService


def main():
    service = FinancialService()
    with Session(engine) as session:
        pool = service.get_highlight_pool(session)
        print(f"股票池 {len(pool)} 只，开始轻量校验...", flush=True)
        refreshed = 0
        for i, code in enumerate(pool, 1):
            try:
                result = service.ensure_fresh([code], session)
                refreshed += len(result)
            except Exception as e:
                print(f"[{i}/{len(pool)}] {code} 校验失败: {e}", flush=True)
            if i % 200 == 0:
                print(f"[{i}/{len(pool)}] 进度 {i * 100 // len(pool)}%，已刷新 {refreshed}", flush=True)
            time.sleep(0.1)

        print(f"校验完成，{refreshed} 只有新财报。开始算榜...", flush=True)
        n = service.compute_highlight_rank(session)
        print(f"完成：亮点榜 Top{n} 已更新", flush=True)


if __name__ == "__main__":
    main()
