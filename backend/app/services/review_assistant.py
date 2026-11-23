"""本地证据与确定性提醒。打开页面不访问行情源或模型服务。"""
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import select

from ..models import (MarketDailyStat, ReviewAudit, ReviewCondition, ReviewObservation,
                      ReviewReminderState, ReviewVerification, StockDailyQuote)
from .etf_service import EtfService
from .review_workbench import today_shanghai

PROMPT_VERSION = 1
STATE_LABELS = {"not_configured": "未设置量化条件", "pending": "仍在观察期",
                "met": "量化条件已满足", "not_met": "量化条件未满足", "unknown": "数据不足，暂不判断"}


class ConditionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    effective_date: date
    kind: Literal["end_change", "hold_change"]
    operator: Literal["ge", "le"]
    threshold_pct: Decimal = Field(ge=-100, le=1000, max_digits=8, decimal_places=4)
    note: str = Field(min_length=1, max_length=500)

    @field_validator("note")
    @classmethod
    def meaningful_note(cls, value):
        if not value.strip():
            raise ValueError("请说明该规则对应的原始条件或本次调整原因")
        return value.strip()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def iso_time(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def usable_price(value):
    return value is not None and math.isfinite(value) and value > 0


def condition_view(rule):
    if rule is None:
        return None
    wording = "期限日收盘" if rule.kind == "end_change" else "关注后至期限内每个交易日收盘"
    comparison = "不低于" if rule.operator == "ge" else "不高于"
    return {"id": rule.id, "effective_date": rule.effective_date.isoformat(), "kind": rule.kind,
            "operator": rule.operator, "threshold_pct": rule.threshold_pct, "note": rule.note,
            "created_at": iso_time(rule.created_at),
            "description": f"{wording}较关注日收盘涨跌幅{comparison} {rule.threshold_pct}%"}


def save_condition(session, observation, body):
    if not observation.observation_date <= body.effective_date <= today_shanghai():
        raise ValueError("规则所属日期必须在关注日期与今天之间")
    if (observation.deadline - observation.observation_date).days > 366:
        raise ValueError("自动价格核对暂支持一年内的验证期限")
    if observation.deadline <= observation.observation_date:
        raise ValueError("自动价格核对需要至少一个关注日之后的交易日，请使用有后续期限的关注记录")
    rule = ReviewCondition(observation_id=observation.id, effective_date=body.effective_date,
                           kind=body.kind, operator=body.operator, threshold_pct=str(body.threshold_pct), note=body.note)
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return condition_view(rule)


class ReviewAssistant:
    def __init__(self, calendar=None):
        self.calendar = calendar or EtfService().cached_trade_dates

    def context(self, session, observation, as_of, rule=None, verification=None):
        if not observation.observation_date <= as_of <= today_shanghai():
            raise ValueError("审阅日期必须在关注日期与今天之间")
        if rule is None:
            rule = session.exec(select(ReviewCondition).where(ReviewCondition.observation_id == observation.id,
                ReviewCondition.effective_date <= as_of).order_by(ReviewCondition.effective_date.desc(), ReviewCondition.id.desc())).first()
        if verification is None:
            verification = session.exec(select(ReviewVerification).where(ReviewVerification.observation_id == observation.id,
                ReviewVerification.review_date <= as_of).order_by(ReviewVerification.review_date.desc(), ReviewVerification.id.desc())).first()
        # 仅使用截至所选日且不超过原始期限的报价；远期价格不能改变原条件的结果。
        end = min(as_of, observation.deadline)
        quotes = session.exec(select(StockDailyQuote).where(StockDailyQuote.stock_code == observation.stock_code,
            StockDailyQuote.trade_date >= observation.observation_date, StockDailyQuote.trade_date <= end)
            .order_by(StockDailyQuote.trade_date)).all()
        prices = {r.trade_date: r.close for r in quotes if usable_price(r.close)}
        calendar = self.calendar(observation.observation_date, end)
        days = sorted(d for d in calendar[0] if observation.observation_date < d <= end) if calendar else []
        missing = [d.isoformat() for d in days if d not in prices]
        base = prices.get(observation.observation_date)
        evaluation = {"status": "not_configured", "label": STATE_LABELS["not_configured"],
                      "expected_samples": len(days) if calendar else None,
                      "valid_samples": sum(d in prices for d in days) if calendar else None,
                      "missing_dates": missing, "first_violation": None, "end_date": days[-1].isoformat() if days else None,
                      "end_change_pct": None, "message": "自由文本不会自动转换为已确认规则。"}
        if days and base and days[-1] in prices:
            evaluation["end_change_pct"] = float((Decimal(str(prices[days[-1]]))/Decimal(str(base))-1)*100)
        if rule:
            status, message = "unknown", "缺少完整官方日历或关注日有效收盘价；不能用缺失数据判定条件。"
            if calendar and base and observation.observation_date in calendar[0]:
                threshold = Decimal(rule.threshold_pct)
                def matches(day):
                    change = (Decimal(str(prices[day])) / Decimal(str(base)) - 1) * 100
                    return change >= threshold if rule.operator == "ge" else change <= threshold
                failures = [d for d in days if d in prices and not matches(d)]
                if rule.kind == "hold_change" and failures:
                    status, message = "not_met", "已发现不满足已确认条件的收盘记录；其他缺失报价不改变这条事实。"
                    evaluation["first_violation"] = failures[0].isoformat()
                elif rule.kind == "hold_change" and missing:
                    message = "期间规则存在缺失报价，暂不能核验；不把缺失日期当作满足条件。"
                elif as_of < observation.deadline:
                    status, message = "pending", "观察期限尚未结束；当前结果不能提前当作最终通过。"
                elif not days or (missing if rule.kind == "hold_change" else days[-1] not in prices):
                    message = "期限内存在缺失报价或没有后续交易日，暂不能核验；不回退到其他日期。"
                else:
                    passed = matches(days[-1]) if rule.kind == "end_change" else not failures
                    status = "met" if passed else "not_met"
                    message = "按已确认的价格条件核对；价格未复权，分红拆分可能影响结果，不代表收益或判断整体正确。"
                    if not passed:
                        evaluation["first_violation"] = days[-1].isoformat()
            evaluation.update(status=status, label=STATE_LABELS[status], message=message)
        facts = [{"id": "observation", "label": "原始关注（含实际录入时间）", "value": {
            "code": observation.stock_code, "date": observation.observation_date.isoformat(),
            "reason": observation.reason, "criterion": observation.criterion,
            "deadline": observation.deadline.isoformat(), "recorded_at": iso_time(observation.created_at)}},
            {"id": "coverage", "label": "数据覆盖与确定性核对", "value": evaluation}]
        if rule:
            facts.append({"id": "rule", "label": "人工确认的规则版本（可为事后补充）", "value": condition_view(rule)})
        if verification:
            facts.append({"id": "verification", "label": "人工验证，独立于自动核对", "value": {
                "date": verification.review_date.isoformat(), "verdict": verification.verdict,
                "explanation": verification.explanation, "recorded_at": iso_time(verification.updated_at)}})
        # 给模型的报价有明确日期；保留基准、首次反例和最近 20 条，避免无界输入。
        selected_days = set(sorted(prices)[-20:]) | {observation.observation_date}
        if evaluation["first_violation"]:
            selected_days.add(date.fromisoformat(evaluation["first_violation"]))
        for day in sorted(selected_days):
            if day in prices:
                facts.append({"id": f"quote-{day}", "label": f"{day} 未复权收盘价", "value": str(prices[day])})
        market = session.exec(select(MarketDailyStat).where(MarketDailyStat.stat_date == as_of)).first()
        if market:
            facts.append({"id": "market", "label": "所选日市场背景（不用于证明个股因果）", "value": {
                "date": as_of.isoformat(), "up": market.up, "down": market.down, "limit_up": market.limit_up,
                "limit_down": market.limit_down, "turnover": market.total_turnover}})
        context = {"as_of": as_of.isoformat(), "facts": facts}
        return {"rule": condition_view(rule), "evaluation": evaluation, "context": context,
                "context_hash": digest(context), "verdict": verification.verdict if verification else "待验证"}

    def dashboard(self, session, as_of):
        observations = session.exec(select(ReviewObservation).where(ReviewObservation.observation_date <= as_of)
            .order_by(ReviewObservation.observation_date.desc(), ReviewObservation.id.desc()).limit(500)).all()
        states = session.exec(select(ReviewReminderState).where(ReviewReminderState.effective_date <= as_of)
            .order_by(ReviewReminderState.id)).all()
        state_map = {r.reminder_key: r for r in states}
        reminders, entries = [], []
        for observation in observations:
            current = self.context(session, observation, as_of)
            evaluation, rule = current["evaluation"], current["rule"]
            entry = {"observation_id": observation.id, "code": observation.stock_code,
                     "rule": rule, "evaluation": evaluation}
            audit = session.exec(select(ReviewAudit).where(ReviewAudit.observation_id == observation.id,
                ReviewAudit.review_date == as_of).order_by(ReviewAudit.id.desc())).first()
            entry["audit"] = audit_view(audit, current["context_hash"]) if audit else None
            entries.append(entry)
            pending = current["verdict"] in ("待验证", "继续观察")
            signals = []
            if evaluation["status"] == "not_met" and current["verdict"] == "符合预期":
                signals.append(("conflict", "warning", "人工结论与量化条件有冲突", "请核对原始条件与反例；保留原判断，由你决定是否补充验证。", evaluation["first_violation"]))
            elif evaluation["status"] == "not_met" and pending:
                signals.append(("condition", "warning", "已确认的价格条件未满足", evaluation["message"], evaluation["first_violation"]))
            if pending and observation.deadline <= as_of:
                signals.append(("due", "attention", "关注已到验证期限", f"原定期限 {observation.deadline}，请记录验证或继续观察的依据。", str(observation.deadline)))
            if pending and not rule:
                signals.append(("criterion", "info", "待确认可计算条件", "原始文字已保留；选择价格条件并确认后，系统才会自动核对。", ""))
            elif pending and evaluation["status"] == "unknown":
                signals.append(("data", "info", "验证数据不足", evaluation["message"], str(evaluation["missing_dates"])))
            for kind, level, title, message, event in signals:
                key = digest([observation.id, kind, rule["id"] if rule else None, event])
                state = state_map.get(key)
                hidden = bool(state and (state.snooze_until is None or as_of < state.snooze_until))
                reminders.append({"key": key, "kind": kind, "level": level, "title": title, "message": message,
                    "observation_id": observation.id, "code": observation.stock_code, "deadline": str(observation.deadline),
                    "hidden": hidden, "snooze_until": str(state.snooze_until) if state and state.snooze_until else None})
        order = {"warning": 0, "attention": 1, "info": 2}
        reminders.sort(key=lambda r: (r["hidden"], order[r["level"]], r["deadline"], r["observation_id"]))
        from .review_ai import ai_status
        return {"date": as_of.isoformat(), "ai": ai_status(), "entries": entries, "reminders": reminders,
                "active_count": sum(not r["hidden"] for r in reminders), "scope_count": len(observations)}


def audit_view(audit, context_hash):
    return {"id": audit.id, "date": str(audit.review_date), "created_at": iso_time(audit.created_at),
            "model": audit.model, "stale": audit.context_hash != context_hash or audit.prompt_version != PROMPT_VERSION,
            "result": json.loads(audit.result_json), "facts": json.loads(audit.context_json)["facts"]}
