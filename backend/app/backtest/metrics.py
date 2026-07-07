"""回测指标计算。"""

from datetime import date
from typing import Any, Dict, List

from .piglet_backtest import EquitySnapshot


def compute_backtest_metrics(
    equity_curve: List[EquitySnapshot],
    trades: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """根据权益曲线与交易记录计算常用回测指标。"""
    if not equity_curve:
        return _empty_metrics()

    initial_value = equity_curve[0].total_value
    final_value = equity_curve[-1].total_value
    total_return = (final_value - initial_value) / initial_value if initial_value else 0.0

    # 年化收益：按实际交易日天数 / 252
    days = (equity_curve[-1].date - equity_curve[0].date).days
    years = days / 365.0 if days > 0 else 0.0
    cagr = (final_value / initial_value) ** (1 / years) - 1 if years > 0 and initial_value > 0 else 0.0

    # 最大回撤
    max_drawdown = 0.0
    peak = initial_value
    for s in equity_curve:
        if s.total_value > peak:
            peak = s.total_value
        dd = (peak - s.total_value) / peak if peak else 0.0
        if dd > max_drawdown:
            max_drawdown = dd

    # 日收益率序列（用于夏普）
    daily_returns: List[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1].total_value
        curr = equity_curve[i].total_value
        if prev > 0:
            daily_returns.append((curr - prev) / prev)

    sharpe_ratio = _sharpe(daily_returns)

    # 交易统计
    sell_trades = [t for t in trades if t.get("direction") == "sell"]
    buy_trades = [t for t in trades if t.get("direction") == "buy"]
    num_trades = len(sell_trades)

    wins = [t for t in sell_trades if (t.get("pnl") or 0) > 0]
    losses = [t for t in sell_trades if (t.get("pnl") or 0) <= 0]
    win_rate = len(wins) / num_trades if num_trades > 0 else 0.0

    total_pnl = sum(t.get("pnl") or 0 for t in sell_trades)
    avg_trade_pnl = total_pnl / num_trades if num_trades > 0 else 0.0
    avg_win = sum(t.get("pnl") or 0 for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t.get("pnl") or 0 for t in losses) / len(losses) if losses else 0.0

    total_win = sum(t.get("pnl") or 0 for t in wins)
    total_loss = abs(sum(t.get("pnl") or 0 for t in losses))
    profit_factor = total_win / total_loss if total_loss > 0 else (float("inf") if total_win > 0 else 0.0)

    avg_hold_days = (
        sum(t.get("hold_days") or 0 for t in sell_trades) / num_trades
        if num_trades > 0
        else 0.0
    )

    return {
        "initial_capital": initial_value,
        "final_value": final_value,
        "total_return": round(total_return, 6),
        "total_return_pct": round(total_return * 100, 2),
        "cagr": round(cagr, 6),
        "cagr_pct": round(cagr * 100, 2),
        "max_drawdown": round(max_drawdown, 6),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "sharpe_ratio": round(sharpe_ratio, 4),
        "num_buy_trades": len(buy_trades),
        "num_sell_trades": num_trades,
        "win_rate": round(win_rate, 4),
        "win_rate_pct": round(win_rate * 100, 2),
        "profit_factor": round(profit_factor, 4),
        "avg_trade_pnl": round(avg_trade_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "avg_hold_days": round(avg_hold_days, 2),
    }


def _empty_metrics() -> Dict[str, Any]:
    return {
        "initial_capital": 0.0,
        "final_value": 0.0,
        "total_return": 0.0,
        "total_return_pct": 0.0,
        "cagr": 0.0,
        "cagr_pct": 0.0,
        "max_drawdown": 0.0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "num_buy_trades": 0,
        "num_sell_trades": 0,
        "win_rate": 0.0,
        "win_rate_pct": 0.0,
        "profit_factor": 0.0,
        "avg_trade_pnl": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "avg_hold_days": 0.0,
    }


def _sharpe(daily_returns: List[float], risk_free_rate: float = 0.0) -> float:
    """日收益年化夏普。"""
    if not daily_returns:
        return 0.0
    n = len(daily_returns)
    mean = sum(daily_returns) / n
    variance = sum((r - mean) ** 2 for r in daily_returns) / n
    std = variance ** 0.5
    if std == 0:
        return 0.0
    # 年化：均值 * 252，标准差 * sqrt(252)
    return (mean - risk_free_rate / 252) / std * (252 ** 0.5)


def equity_curve_to_dicts(equity_curve: List[EquitySnapshot]) -> List[Dict[str, Any]]:
    """将权益曲线对象列表转为可序列化字典。"""
    return [
        {
            "date": s.date.isoformat(),
            "cash": round(s.cash, 2),
            "market_value": round(s.market_value, 2),
            "total_value": round(s.total_value, 2),
        }
        for s in equity_curve
    ]
