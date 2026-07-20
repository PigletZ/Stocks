#!/usr/bin/env python3
"""一次性全量导入亮点榜股票池的三大报表（只跑一次）。

- 股票池：策略统一过滤条件 + 排除银行股（见 docs/financial-analysis.md §10.4）
- 每股 3 次 Tushare 调用（利润表/资产负债表/现金流量表，公告日 2024-01-01 起）
- 断点续跑：FinIncome 已有数据的股票自动跳过（重跑安全）
- 建议夜间执行：约 4000+ 只 × 3 次调用，预计 1 小时左右

用法：
    cd /kimi/projects/Stocks/backend
    venv/bin/python scripts/import_fin_all.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

from app.database import engine
from app.models import FinIncome
from app.services.financial_service import FinancialService


def main():
    service = FinancialService()
    with Session(engine) as session:
        pool = service.get_highlight_pool(session)
        done = set(
            r[0] for r in session.exec(select(FinIncome.stock_code).distinct()).all()
        )
        todo = [c for c in pool if c not in done]
        print(f"股票池 {len(pool)} 只，已导入 {len(done & set(pool))} 只，待导入 {len(todo)} 只", flush=True)

        fail = 0
        for i, code in enumerate(todo, 1):
            try:
                service.refresh_stock(code, session)
            except Exception as e:
                fail += 1
                print(f"[{i}/{len(todo)}] {code} 导入失败: {e}", flush=True)
            if i % 100 == 0:
                print(f"[{i}/{len(todo)}] 进度 {i * 100 // len(todo)}%，失败 {fail}", flush=True)
            time.sleep(0.1)
        print(f"完成：导入 {len(todo) - fail} 只，失败 {fail} 只", flush=True)


if __name__ == "__main__":
    main()
