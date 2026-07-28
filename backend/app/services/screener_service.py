"""通用选股器：行情/技术指标条件 AND 组合筛选。

条件字段（field）：
- 快照字段（stockdailyquote）：change_pct 涨跌幅%、turnover_rate 换手率%、
  amount 成交额(亿)、float_mv 流通市值(亿)、total_mv 总市值(亿)、pe_ttm、pb
- K线派生（bar）：ma_bull 均线多头(值=1)、high_n_days N日新高(值=N)、volume_ratio 量比
- 涨停明细（limit_up_daily）：limit_times 连板数

操作符（op）：>= / <= / > / < / =
金额类字段条件值单位统一为"亿元"（库内为元，查询时换算）。
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from sqlmodel import Session, select

from ..models import Bar, LimitUpDaily, ScreenPreset, Stock, StockDailyQuote
from ..strategies.base import StockPick
from ..strategies.filters import apply_base_filters


logger = logging.getLogger(__name__)

QUOTE_FIELDS = {"change_pct", "turnover_rate", "amount", "float_mv", "total_mv", "pe_ttm", "pb"}
BAR_FIELDS = {"ma_bull", "high_n_days", "volume_ratio"}
VALID_FIELDS = QUOTE_FIELDS | BAR_FIELDS | {"limit_times"}
VALID_OPS = {">=", "<=", ">", "<", "="}
# 金额类字段：库内单位元，条件值单位亿元
YI = 1e8

# 条件中文名（生成 reason 用）
FIELD_LABELS = {
    "change_pct": "涨跌幅",
    "turnover_rate": "换手率",
    "amount": "成交额",
    "float_mv": "流通市值",
    "total_mv": "总市值",
    "pe_ttm": "PE",
    "pb": "PB",
    "limit_times": "连板数",
    "ma_bull": "均线多头",
    "high_n_days": "日新高",
    "volume_ratio": "量比",
}


class ScreenerService:
    """通用选股器服务"""

    # ==================== 预设 ====================

    def list_presets(self, session: Session) -> List[dict]:
        presets = session.exec(select(ScreenPreset).order_by(ScreenPreset.created_at)).all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "conditions": json.loads(p.conditions_json),
            }
            for p in presets
        ]

    def create_preset(self, name: str, conditions: List[dict], session: Session) -> dict:
        name = name.strip()
        if not name:
            raise ValueError("预设名称不能为空")
        self._validate_conditions(conditions)
        existing = session.exec(select(ScreenPreset).where(ScreenPreset.name == name)).first()
        if existing:
            raise ValueError("预设名称已存在")
        preset = ScreenPreset(name=name, conditions_json=json.dumps(conditions, ensure_ascii=False))
        session.add(preset)
        session.commit()
        session.refresh(preset)
        return {"id": preset.id, "name": preset.name, "conditions": conditions}

    def delete_preset(self, preset_id: int, session: Session) -> bool:
        preset = session.get(ScreenPreset, preset_id)
        if not preset:
            return False
        session.delete(preset)
        session.commit()
        return True

    def get_preset(self, preset_id: int, session: Session) -> Optional[ScreenPreset]:
        return session.get(ScreenPreset, preset_id)

    # ==================== 执行筛选 ====================

    @staticmethod
    def _validate_conditions(conditions: List[dict]):
        for c in conditions:
            if c.get("field") not in VALID_FIELDS:
                raise ValueError(f"未知条件字段: {c.get('field')}")
            if c.get("op") not in VALID_OPS:
                raise ValueError(f"未知操作符: {c.get('op')}")
            if not isinstance(c.get("value"), (int, float)):
                raise ValueError(f"条件值必须是数字: {c}")

    @staticmethod
    def _match(value: Optional[float], op: str, target: float) -> bool:
        if value is None:
            return False
        if op == ">=":
            return value >= target
        if op == "<=":
            return value <= target
        if op == ">":
            return value > target
        if op == "<":
            return value < target
        return value == target

    def run(
        self,
        conditions: List[dict],
        trade_date: Optional[date],
        session: Session,
        apply_filters: bool = True,
    ) -> dict:
        """执行筛选，返回 {trade_date, total, items}。"""
        self._validate_conditions(conditions)

        d = trade_date or session.exec(
            select(StockDailyQuote.trade_date).order_by(StockDailyQuote.trade_date.desc()).limit(1)
        ).first()
        if d is None:
            return {"trade_date": None, "total": 0, "items": []}

        # 1. 快照字段过滤
        quotes = session.exec(
            select(StockDailyQuote).where(StockDailyQuote.trade_date == d)
        ).all()
        candidates: Dict[str, StockDailyQuote] = {}
        for q in quotes:
            ok = True
            for c in conditions:
                f = c["field"]
                if f not in QUOTE_FIELDS:
                    continue
                v = getattr(q, f)
                if f in ("amount", "float_mv", "total_mv") and v is not None:
                    v = v / YI
                if not self._match(v, c["op"], c["value"]):
                    ok = False
                    break
            if ok:
                candidates[q.stock_code] = q

        # 2. 公共过滤（ST/科创/创业/北交/次新，与策略选股一致）
        codes = list(candidates.keys())
        if apply_filters and codes:
            codes = apply_base_filters(codes, d, session)
            candidates = {c: candidates[c] for c in codes if c in candidates}

        # 3. 连板数过滤与标注
        limit_map = self._limit_times_map(d, list(candidates.keys()), session)
        for f_c in [c for c in conditions if c["field"] == "limit_times"]:
            candidates = {
                code: q for code, q in candidates.items()
                if self._match(limit_map.get(code, 0), f_c["op"], f_c["value"])
            }

        # 4. K线派生条件（量比/均线/新高天数始终计算，用于结果展示）
        bar_conditions = [c for c in conditions if c["field"] in BAR_FIELDS]
        computed: Dict[str, dict] = {}
        if candidates:
            computed = self._compute_bar_metrics(d, list(candidates.keys()), session)
            for c in bar_conditions:
                f = c["field"]
                if f == "ma_bull":
                    candidates = {
                        code: q for code, q in candidates.items()
                        if self._match(1.0 if computed.get(code, {}).get("ma_bull") else 0.0, c["op"], c["value"])
                    }
                elif f == "high_n_days":
                    n = int(c["value"])
                    candidates = {
                        code: q for code, q in candidates.items()
                        if computed.get(code, {}).get("high_days", 0) >= n
                    }
                elif f == "volume_ratio":
                    candidates = {
                        code: q for code, q in candidates.items()
                        if self._match(computed.get(code, {}).get("volume_ratio"), c["op"], c["value"])
                    }

        # 5. 组装输出
        names = self._stock_names(session, set(candidates.keys()))
        items = []
        for code, q in candidates.items():
            m = computed.get(code, {})
            items.append({
                "code": code,
                "name": names.get(code, ""),
                "close": q.close,
                "change_pct": q.change_pct,
                "turnover_rate": q.turnover_rate,
                "amount": round(q.amount / YI, 2) if q.amount is not None else None,
                "float_mv": round(q.float_mv / YI, 1) if q.float_mv is not None else None,
                "total_mv": round(q.total_mv / YI, 1) if q.total_mv is not None else None,
                "pe_ttm": q.pe_ttm,
                "pb": q.pb,
                "limit_times": limit_map.get(code, 0),
                "volume_ratio": m.get("volume_ratio"),
                "ma_bull": m.get("ma_bull", False),
                "high_days": m.get("high_days", 0),
            })
        items.sort(key=lambda x: -(x["amount"] or 0))
        return {"trade_date": d.isoformat(), "total": len(items), "items": items}

    def run_as_picks(
        self,
        conditions: List[dict],
        trade_date: date,
        session: Session,
    ) -> List[StockPick]:
        """以策略形式执行（预设接入策略选股页用），结果映射为 StockPick。"""
        result = self.run(conditions, trade_date, session)
        cond_text = "、".join(
            f"{FIELD_LABELS.get(c['field'], c['field'])}{c['op']}{c['value']}" for c in conditions
        )
        picks = []
        for item in result["items"]:
            picks.append(StockPick(
                code=item["code"],
                name=item["name"],
                score=0.0,
                buy_price=item["close"] or 0.0,
                reason=f"满足条件：{cond_text}",
                raw_data=item,
            ))
        return picks

    # ==================== 内部计算 ====================

    @staticmethod
    def _limit_times_map(d: date, codes: List[str], session: Session) -> Dict[str, int]:
        if not codes:
            return {}
        rows = session.exec(
            select(LimitUpDaily).where(
                LimitUpDaily.trade_date == d,
                LimitUpDaily.limit_type == "U",
                LimitUpDaily.stock_code.in_(codes),
            )
        ).all()
        return {r.stock_code: (r.limit_times or 1) for r in rows}

    def _compute_bar_metrics(self, d: date, codes: List[str], session: Session) -> Dict[str, dict]:
        """计算每只候选股的：均线多头、连续新高天数、量比（基于本地 bar，最多回看 60 天）。"""
        if not codes:
            return {}
        since = datetime.combine(d - timedelta(days=120), datetime.min.time())
        end_ts = datetime.combine(d, datetime.max.time())
        bars = session.exec(
            select(Bar).where(
                Bar.interval == "1d",
                Bar.stock_code.in_(codes),
                Bar.timestamp >= since,
                Bar.timestamp <= end_ts,
            ).order_by(Bar.stock_code, Bar.timestamp)
        ).all()

        by_code: Dict[str, List[Bar]] = {}
        for b in bars:
            by_code.setdefault(b.stock_code, []).append(b)

        result = {}
        for code, blist in by_code.items():
            if len(blist) < 2:
                continue
            closes = [b.close for b in blist]
            last = blist[-1]
            # 均线多头：MA5 > MA10 > MA20
            ma_bull = False
            if len(closes) >= 20:
                ma5 = sum(closes[-5:]) / 5
                ma10 = sum(closes[-10:]) / 10
                ma20 = sum(closes[-20:]) / 20
                ma_bull = ma5 > ma10 > ma20
            # 连续新高天数：最新收盘是最近 N 根 K 线最高收盘价的最大 N
            high_days = 0
            running_max = 0.0
            for i in range(len(blist) - 1, -1, -1):
                running_max = max(running_max, closes[i])
                if last.close >= running_max:
                    high_days += 1
                else:
                    break
            # 量比：当日成交量 / 前 5 日均量
            volume_ratio = None
            if len(blist) >= 6:
                prev5 = [b.volume for b in blist[-6:-1]]
                avg5 = sum(prev5) / 5
                if avg5 > 0:
                    volume_ratio = round(last.volume / avg5, 2)
            result[code] = {
                "ma_bull": ma_bull,
                "high_days": high_days,
                "volume_ratio": volume_ratio,
            }
        return result

    @staticmethod
    def _stock_names(session: Session, codes) -> Dict[str, str]:
        if not codes:
            return {}
        stocks = session.exec(select(Stock).where(Stock.code.in_(list(codes)))).all()
        return {s.code: s.name for s in stocks}
