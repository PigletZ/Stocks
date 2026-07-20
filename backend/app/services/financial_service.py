# -*- coding: utf-8 -*-
"""财务分析服务：三大报表拉取入库、派生指标计算、亮点/风险标签、雷达归一化。

设计文档：docs/financial-analysis.md
- 公告日 2024-01-01 起拉取（覆盖 2023 年报起的报告期，供同比/期初计算）
- 展示范围：2025-01-01 起的报告期（今年 + 去年）
- 轻量校验：每次分析每股 1 次 income 查询，有新公告才三表全量回源
"""
import json
import logging
import time
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import tushare as ts
from sqlmodel import Session, select

from ..config import settings
from ..models import FinBalance, FinCashflow, FinIncome, Stock
from .financial_fields import FIELD_MAPS

logger = logging.getLogger(__name__)

# 公告日拉取起点：覆盖 2023 年报起的报告期（同比与平均余额需要上一年数据）
FETCH_START_ANN = "20240101"
# 展示起点：今年和去年
DISPLAY_START = date(2025, 1, 1)

# 模型字段 ← Tushare 字段 的差异映射（其余同名字段直接取）
FIELD_ALIAS = {
    "income": {"operate_cost": "oper_cost"},
    "balance": {},
    "cashflow": {},
}

# 各表需要建列的字段（data_json 之外的列）
COLUMN_FIELDS = {
    "income": ["total_revenue", "revenue", "operate_cost", "n_income_attr_p", "basic_eps"],
    "balance": [
        "total_assets", "total_liab", "total_hldr_eqy_inc_min_int",
        "total_hldr_eqy_exc_min_int", "total_cur_assets", "total_cur_liab",
        "money_cap", "inventories", "accounts_receiv", "goodwill",
    ],
    "cashflow": ["n_cashflow_act", "n_cashflow_inv_act", "n_cash_flows_fnc_act", "free_cashflow"],
}

MODELS = {"income": FinIncome, "balance": FinBalance, "cashflow": FinCashflow}
APIS = {"income": "income", "balance": "balancesheet", "cashflow": "cashflow"}


class FinancialService:
    """财务分析数据服务"""

    def __init__(self):
        self._tushare_pro = None

    def _get_tushare_pro(self):
        """使用 Tushare token 初始化 Pro 接口（懒加载）"""
        if self._tushare_pro is None:
            token = settings.tushare_token
            if not token:
                raise RuntimeError("Tushare token 未配置，请检查 /etc/kimi/stocks/base.conf 中的 [tushare]")
            self._tushare_pro = ts.pro_api(token)
        return self._tushare_pro

    @staticmethod
    def _code_to_ts_code(code: str) -> Optional[str]:
        """将纯数字代码转换为 Tushare ts_code"""
        if code.startswith(("6", "90")):
            return f"{code}.SH"
        if code.startswith(("0", "2", "3")):
            return f"{code}.SZ"
        if code.startswith(("4", "8", "920")):
            return f"{code}.BJ"
        return None

    @staticmethod
    def _to_date(value) -> Optional[date]:
        if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
            return None
        s = str(value).strip()
        if not s:
            return None
        try:
            return datetime.strptime(s[:8], "%Y%m%d").date()
        except Exception:
            return None

    @staticmethod
    def _to_float(value) -> Optional[float]:
        if value is None or pd.isna(value):
            return None
        try:
            return float(value)
        except Exception:
            return None

    # ---------- 数据拉取与入库 ----------

    def _fetch_statement(self, ts_code: str, stmt_type: str) -> pd.DataFrame:
        """按公告日区间拉取单只股票某张报表"""
        pro = self._get_tushare_pro()
        today = date.today().strftime("%Y%m%d")
        df = getattr(pro, APIS[stmt_type])(
            ts_code=ts_code, start_date=FETCH_START_ANN, end_date=today
        )
        time.sleep(0.15)
        return df if df is not None else pd.DataFrame()

    def _dedupe(self, df: pd.DataFrame) -> List[dict]:
        """同一报告期多行时去重：优先合并报表(report_type=1)，再取最新公告日。

        返回 [{end_date, f_ann_date, fields: {原始字段: 值}}]，按报告期升序。
        """
        if df.empty:
            return []
        df = df.copy()
        df["_end"] = df["end_date"].apply(self._to_date)
        df["_fann"] = df["f_ann_date"].apply(self._to_date) if "f_ann_date" in df else None
        df = df[df["_end"].notna()]
        result = []
        for end, grp in df.groupby("_end"):
            cand = grp
            if "report_type" in grp.columns:
                merged = grp[grp["report_type"].astype(str) == "1"]
                if not merged.empty:
                    cand = merged
            if "_fann" in cand.columns and cand["_fann"].notna().any():
                cand = cand.sort_values("_fann")
            row = cand.iloc[-1]
            fields = {}
            for col in df.columns:
                if col.startswith("_"):
                    continue
                v = row[col]
                if pd.isna(v):
                    continue
                if isinstance(v, (int, float)):
                    fields[col] = float(v)
                else:
                    fields[col] = str(v)
            result.append({
                "end_date": end,
                "f_ann_date": self._to_date(row.get("f_ann_date")),
                "fields": fields,
            })
        result.sort(key=lambda x: x["end_date"])
        return result

    def _upsert_rows(self, stmt_type: str, code: str, rows: List[dict], session: Session) -> int:
        """原子 upsert（ON CONFLICT DO UPDATE），避免并发/重复写入撞唯一约束"""
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        model = MODELS[stmt_type]
        alias = FIELD_ALIAS[stmt_type]
        now = datetime.utcnow()
        values = []
        for item in rows:
            f = item["fields"]
            record = {
                "stock_code": code,
                "end_date": item["end_date"],
                "f_ann_date": item["f_ann_date"],
                "data_json": json.dumps(f, ensure_ascii=False),
                "updated_at": now,
            }
            for col in COLUMN_FIELDS[stmt_type]:
                src = alias.get(col, col)
                record[col] = self._to_float(f.get(src))
            values.append(record)
        if not values:
            return 0
        stmt = sqlite_insert(model).values(values)
        update_cols = {
            c: getattr(stmt.excluded, c)
            for c in ["f_ann_date", "data_json", "updated_at"] + COLUMN_FIELDS[stmt_type]
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_code", "end_date"], set_=update_cols
        )
        session.execute(stmt)
        session.commit()
        return len(values)

    def refresh_stock(self, code: str, session: Session) -> Dict[str, int]:
        """三表全量回源并入库，返回各表写入条数"""
        ts_code = self._code_to_ts_code(code)
        if not ts_code:
            return {}
        counts = {}
        for stmt_type in ("income", "balance", "cashflow"):
            try:
                df = self._fetch_statement(ts_code, stmt_type)
                rows = self._dedupe(df)
                counts[stmt_type] = self._upsert_rows(stmt_type, code, rows, session)
            except Exception:
                logger.exception("财务报表拉取失败: %s %s", code, stmt_type)
                counts[stmt_type] = 0
        return counts

    # ---------- 轻量校验 ----------

    def ensure_fresh(self, codes: List[str], session: Session) -> Dict[str, Dict[str, int]]:
        """每股 1 次 income 轻量查询；有新公告则三表全量回源。返回实际刷新的股票及条数。"""
        refreshed = {}
        pro = self._get_tushare_pro()
        for code in codes:
            ts_code = self._code_to_ts_code(code)
            if not ts_code:
                continue
            try:
                df = pro.income(ts_code=ts_code)
                time.sleep(0.15)
            except Exception:
                logger.exception("轻量校验失败，使用本地缓存: %s", code)
                continue
            remote = self._dedupe(df if df is not None else pd.DataFrame())
            if not remote:
                continue
            latest = remote[-1]
            db_latest = session.exec(
                select(FinIncome)
                .where(FinIncome.stock_code == code)
                .order_by(FinIncome.end_date.desc())
                .limit(1)
            ).first()
            need_refresh = (
                db_latest is None
                or latest["end_date"] > db_latest.end_date
                or (
                    latest["end_date"] == db_latest.end_date
                    and latest["f_ann_date"]
                    and db_latest.f_ann_date
                    and latest["f_ann_date"] > db_latest.f_ann_date
                )
            )
            if need_refresh:
                refreshed[code] = self.refresh_stock(code, session)
        return refreshed

    # ---------- 派生指标 ----------

    @staticmethod
    def _load_rows(session: Session, model, code: str) -> Dict[date, object]:
        """读取某股票某表全部缓存行，{报告期: 行}"""
        rows = session.exec(
            select(model).where(model.stock_code == code).order_by(model.end_date)
        ).all()
        return {r.end_date: r for r in rows}

    @staticmethod
    def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
        if a is None or b is None or b == 0:
            return None
        return a / b

    @staticmethod
    def _yoy(cur: Optional[float], base: Optional[float]) -> Optional[float]:
        """同比（小数），base<=0 时不可比（如亏损转盈），返回 None"""
        if cur is None or base is None or base <= 0:
            return None
        return cur / base - 1

    @staticmethod
    def _prev_year_end(end: date) -> Optional[date]:
        """上一年度期末（用于平均余额的期初取值）"""
        try:
            return date(end.year - 1, 12, 31)
        except Exception:
            return None

    @staticmethod
    def _annualize_factor(end: date) -> float:
        """累计值年化系数：Q1×4，中报×2，Q3×4/3，年报×1"""
        return {3: 4.0, 6: 2.0, 9: 4.0 / 3.0, 12: 1.0}.get(end.month, 1.0)

    def _build_metrics(
        self,
        income: Dict[date, FinIncome],
        balance: Dict[date, FinBalance],
        cashflow: Dict[date, FinCashflow],
        display_periods: List[date],
    ) -> Dict[str, dict]:
        """按展示期计算派生指标，{报告期字符串: 指标dict}"""
        result = {}
        for end in display_periods:
            inc = income.get(end)
            bal = balance.get(end)
            cf = cashflow.get(end)
            if inc is None and bal is None and cf is None:
                continue
            ly_end = date(end.year - 1, end.month, end.day)
            inc_ly = income.get(ly_end)
            bal_ly = balance.get(ly_end)
            bal_py = balance.get(self._prev_year_end(end))  # 上年期末（期初）

            revenue = inc.revenue if inc else None
            total_revenue = inc.total_revenue if inc else None
            operate_cost = inc.operate_cost if inc else None
            net_profit = inc.n_income_attr_p if inc else None
            equity = bal.total_hldr_eqy_exc_min_int if bal else None
            ncf = cf.n_cashflow_act if cf else None

            gross_margin = self._safe_div(
                (revenue - operate_cost) if revenue is not None and operate_cost is not None else None,
                revenue,
            )
            net_margin = self._safe_div(net_profit, total_revenue)
            roe = self._safe_div(net_profit, equity)
            factor = self._annualize_factor(end)
            roe_ann = roe * factor if roe is not None else None
            debt_ratio = self._safe_div(bal.total_liab, bal.total_assets) if bal else None
            current_ratio = (
                self._safe_div(bal.total_cur_assets, bal.total_cur_liab) if bal else None
            )
            ncf_ratio = self._safe_div(ncf, net_profit) if ncf is not None and net_profit else None

            def _avg(cur_v, py_v):
                if cur_v is None:
                    return None
                return (cur_v + py_v) / 2 if py_v is not None else cur_v

            inv_avg = _avg(bal.inventories if bal else None, bal_py.inventories if bal_py else None)
            ar_avg = _avg(
                bal.accounts_receiv if bal else None, bal_py.accounts_receiv if bal_py else None
            )
            ta_avg = _avg(bal.total_assets if bal else None, bal_py.total_assets if bal_py else None)

            gm_ly = None
            if inc_ly and inc_ly.revenue and inc_ly.operate_cost is not None:
                gm_ly = self._safe_div(inc_ly.revenue - inc_ly.operate_cost, inc_ly.revenue)

            result[end.isoformat()] = {
                "revenue": total_revenue,
                "revenue_yoy": self._yoy(total_revenue, inc_ly.total_revenue if inc_ly else None),
                "net_profit": net_profit,
                "net_profit_yoy": self._yoy(net_profit, inc_ly.n_income_attr_p if inc_ly else None),
                "gross_margin": gross_margin,
                "gross_margin_ly": gm_ly,
                "net_margin": net_margin,
                "roe": roe,
                "roe_annualized": roe_ann,
                "debt_ratio": debt_ratio,
                "current_ratio": current_ratio,
                "ncf": ncf,
                "ncf_ratio": ncf_ratio,
                "inv_turnover": self._safe_div(operate_cost, inv_avg),
                "ar_turnover": self._safe_div(revenue, ar_avg),
                "asset_turnover": self._safe_div(total_revenue, ta_avg),
                "goodwill_ratio": self._safe_div(
                    bal.goodwill if bal else None, equity
                ) if bal and bal.goodwill else None,
            }
        return result

    # ---------- 亮点 / 风险标签 ----------

    @staticmethod
    def _build_tags(metrics: Dict[str, dict], display_periods: List[date]) -> List[dict]:
        """按最新展示期指标生成亮点/风险标签（docs/financial-analysis.md §5.3）"""
        if not display_periods:
            return []
        latest_key = display_periods[-1].isoformat()
        m = metrics.get(latest_key)
        if not m:
            return []
        tags = []

        def good(label):
            tags.append({"type": "good", "label": label})

        def risk(label):
            tags.append({"type": "risk", "label": label})

        rev_yoy, np_yoy = m.get("revenue_yoy"), m.get("net_profit_yoy")
        roe_ann, dr = m.get("roe_annualized"), m.get("debt_ratio")
        ncf, ncf_ratio = m.get("ncf"), m.get("ncf_ratio")
        gm, gm_ly = m.get("gross_margin"), m.get("gross_margin_ly")
        gw = m.get("goodwill_ratio")

        if rev_yoy is not None and np_yoy is not None:
            if rev_yoy > 0 and np_yoy > 0:
                good("营收净利双增")
            if rev_yoy > 0 and np_yoy <= 0:
                risk("增收不增利")
            if rev_yoy < 0 or np_yoy < 0:
                risk("业绩下滑")
        if (rev_yoy is not None and rev_yoy > 0.15) or (np_yoy is not None and np_yoy > 0.15):
            good("高增长")
        if roe_ann is not None and roe_ann > 0.15:
            # 连续两期高 ROE 标注"连续"
            prev_high = False
            if len(display_periods) >= 2:
                prev = metrics.get(display_periods[-2].isoformat())
                prev_high = bool(prev and prev.get("roe_annualized") and prev["roe_annualized"] > 0.15)
            good("连续高ROE" if prev_high else "高ROE")
        if ncf is not None:
            if ncf > 0 and ncf_ratio is not None and ncf_ratio >= 0.8:
                good("现金流充沛")
            if ncf < 0:
                risk("经营现金流为负")
        if ncf_ratio is not None and m.get("net_profit") and m["net_profit"] > 0 and ncf_ratio < 0.5:
            risk("利润含金量低")
        if dr is not None:
            if dr < 0.40:
                good("低负债")
            if dr > 0.70:
                risk("高负债")
        if gw is not None and gw > 0.30:
            risk("高商誉")
        if gm is not None and gm_ly is not None and gm < gm_ly:
            risk("毛利率下滑")
        return tags

    # ---------- 雷达图归一化 ----------

    @staticmethod
    def _build_radar(stocks_metrics: List[Tuple[str, str, dict]]) -> dict:
        """跨股 Min-Max 归一化（0~100），输入 [(code, name, 最新期指标)]"""
        groups = {
            "盈利能力": ["gross_margin", "net_margin", "roe_annualized"],
            "成长能力": ["revenue_yoy", "net_profit_yoy"],
            "偿债能力": ["debt_ratio", "current_ratio"],
            "现金流质量": ["ncf", "ncf_ratio"],
            "运营效率": ["inv_turnover", "ar_turnover", "asset_turnover"],
        }
        n = len(stocks_metrics)
        # 逐指标跨股归一化
        norm = {}  # {metric: [per-stock value]}
        metrics_used = {m for ms in groups.values() for m in ms}
        for metric in metrics_used:
            vals = [s[2].get(metric) for s in stocks_metrics]
            valid = [v for v in vals if v is not None]
            if not valid:
                norm[metric] = [None] * n
                continue
            lo, hi = min(valid), max(valid)
            col = []
            for v in vals:
                if v is None:
                    col.append(None)
                elif hi == lo:
                    col.append(50.0)
                else:
                    col.append((v - lo) / (hi - lo) * 100)
            norm[metric] = col
        # 偿债维度中资产负债率为反向指标（越低越好），取 100 - x
        if norm.get("debt_ratio"):
            norm["debt_ratio"] = [None if v is None else 100 - v for v in norm["debt_ratio"]]

        series = []
        for i, (code, name, _) in enumerate(stocks_metrics):
            values = []
            for dim, ms in groups.items():
                dim_vals = [norm[m][i] for m in ms if norm.get(m) and norm[m][i] is not None]
                values.append(round(sum(dim_vals) / len(dim_vals), 1) if dim_vals else 0.0)
            series.append({"name": f"{name}({code})", "values": values})
        return {"dims": list(groups.keys()), "series": series}

    # ---------- 对外主接口 ----------

    def get_compare(self, codes: List[str], session: Session) -> dict:
        """对比主接口：轻量校验 + 派生指标 + 标签 + 雷达数据"""
        self.ensure_fresh(codes, session)
        stocks_out = []
        radar_input = []
        for code in codes:
            stock = session.exec(select(Stock).where(Stock.code == code)).first()
            income = self._load_rows(session, FinIncome, code)
            balance = self._load_rows(session, FinBalance, code)
            cashflow = self._load_rows(session, FinCashflow, code)
            all_periods = sorted(set(income) | set(balance) | set(cashflow))
            display_periods = [p for p in all_periods if p >= DISPLAY_START]
            metrics = self._build_metrics(income, balance, cashflow, display_periods)
            tags = self._build_tags(metrics, display_periods)
            latest_key = display_periods[-1].isoformat() if display_periods else None
            card = {"period": latest_key, **(metrics.get(latest_key) or {})}
            stocks_out.append({
                "code": code,
                "name": stock.name if stock else code,
                "industry": stock.industry if stock else None,
                "periods": [p.isoformat() for p in display_periods],
                "metrics": metrics,
                "card": card,
                "tags": tags,
            })
            if latest_key and metrics.get(latest_key):
                radar_input.append((code, stock.name if stock else code, metrics[latest_key]))
        return {"stocks": stocks_out, "radar": self._build_radar(radar_input)}

    def get_statements(self, code: str, stmt_type: str, session: Session) -> dict:
        """单股报表原文：全科目 × 展示期，附带同比。

        periods 只含展示期（2025+2026）；同比用上一年同期缓存数据计算。
        """
        model = MODELS[stmt_type]
        field_map = FIELD_MAPS[stmt_type]
        rows = self._load_rows(session, model, code)
        display = sorted(p for p in rows if p >= DISPLAY_START)
        if not display:
            return {"periods": [], "items": []}

        # 解析各期 data_json
        data: Dict[date, dict] = {}
        for p, row in rows.items():
            try:
                data[p] = json.loads(row.data_json) if row.data_json else {}
            except Exception:
                data[p] = {}

        # 收集展示期内出现过的全部字段：映射表内的按映射顺序，其余按名称排后
        used = set()
        for p in display:
            used.update(data[p].keys())
        skip = {"ts_code", "ann_date", "end_date", "f_ann_date", "report_type", "comp_type", "end_type", "update_flag"}
        ordered = [f for f in field_map if f in used and f not in skip]
        ordered += sorted(f for f in used if f not in field_map and f not in skip)

        items = []
        for f in ordered:
            values = []
            yoy = []
            has_value = False
            for p in display:
                v = self._to_float(data[p].get(f))
                values.append(v)
                if v is not None:
                    has_value = True
                ly = date(p.year - 1, p.month, p.day)
                base = self._to_float(data.get(ly, {}).get(f))
                if v is not None and base is not None and base != 0:
                    yoy.append(v / base - 1)
                else:
                    yoy.append(None)
            if not has_value:
                continue  # 全部为空(null)的科目不展示
            items.append({
                "field": f,
                "name": field_map.get(f, f),
                "values": values,
                "yoy": yoy,
            })
        return {"periods": [p.isoformat() for p in display], "items": items}

    # ---------- 亮点 Top100 榜 ----------

    # 最新报告期距今超过该天数视为数据陈旧，不入榜
    STALE_DAYS = 120

    @staticmethod
    def get_highlight_pool(session: Session) -> List[str]:
        """亮点榜股票池：策略统一过滤条件（ST/退市/科创/创业/北交/次新）+ 银行股。"""
        from ..strategies.filters import apply_base_filters

        all_codes = [s.code for s in session.exec(select(Stock)).all()]
        codes = set(apply_base_filters(all_codes, date.today(), session))
        if not codes:
            return []
        rows = session.exec(select(Stock).where(Stock.code.in_(codes))).all()
        return sorted(
            s.code for s in rows if not (s.industry and "银行" in s.industry)
        )

    def compute_highlight_rank(
        self, session: Session, stat_date: Optional[date] = None, top_n: int = 300
    ) -> int:
        """对股票池批量计算亮点榜并落库（当日整体覆盖），返回入榜数量。

        排序口径（docs/financial-analysis.md §10.5）：
        亮点数降序 → 风险数升序 → ROE(年化)降序 → 营收同比降序。
        落库前 top_n 名（默认 300），前端可选展示前 100/200/300。
        """
        from ..models import FinHighlight

        stat_date = stat_date or date.today()
        pool = self.get_highlight_pool(session)
        scored = []
        for code in pool:
            income = self._load_rows(session, FinIncome, code)
            if not income:
                continue  # 财报尚未入库
            balance = self._load_rows(session, FinBalance, code)
            cashflow = self._load_rows(session, FinCashflow, code)
            all_periods = sorted(set(income) | set(balance) | set(cashflow))
            display_periods = [p for p in all_periods if p >= DISPLAY_START]
            if not display_periods:
                continue
            if (stat_date - display_periods[-1]).days > self.STALE_DAYS:
                continue  # 数据陈旧（长期停牌/异常）
            metrics = self._build_metrics(income, balance, cashflow, display_periods)
            latest = metrics.get(display_periods[-1].isoformat())
            if not latest:
                continue
            tags = self._build_tags(metrics, display_periods)
            scored.append({
                "code": code,
                "tags": tags,
                "good_count": sum(1 for t in tags if t["type"] == "good"),
                "risk_count": sum(1 for t in tags if t["type"] == "risk"),
                "roe": latest.get("roe_annualized"),
                "rev_yoy": latest.get("revenue_yoy"),
                "metrics": latest,
            })

        def _key(item):
            # None 排最后
            roe = item["roe"] if item["roe"] is not None else -1e9
            rev = item["rev_yoy"] if item["rev_yoy"] is not None else -1e9
            return (-item["good_count"], item["risk_count"], -roe, -rev)

        scored.sort(key=_key)
        top = scored[:top_n]

        # 当日旧榜整体删除后重写（算榜是全量重算，非增量）。
        # 必须用 Core DELETE 立即执行：ORM 的 session.delete() 在 flush 时
        # 可能排在 insert 之后，导致撞 (stat_date, code) 唯一约束
        from sqlalchemy import delete as sql_delete

        session.exec(
            sql_delete(FinHighlight).where(FinHighlight.stat_date == stat_date)
        )
        for i, item in enumerate(top, 1):
            session.add(FinHighlight(
                stat_date=stat_date,
                code=item["code"],
                rank=i,
                good_count=item["good_count"],
                risk_count=item["risk_count"],
                tags_json=json.dumps(item["tags"], ensure_ascii=False),
                metrics_json=json.dumps(item["metrics"], ensure_ascii=False),
            ))
        session.commit()
        return len(top)
