"""Indicator calculation helpers for the daily K line service."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

__all__ = [
    "compute_moving_averages",
    "compute_bollinger_bands",
    "compute_rsi",
    "compute_cost_change",
    "compute_ma5_deviation",
    "compute_smart_money_lines",
    "fetch_chip_data",
    "fetch_fund_flow_series",
    "should_draw_volume_prediction",
    "get_current_time_ratio",
    "predict_final_volume",
    "series_to_list",
]


def series_to_list(series: pd.Series, digits: int = 4) -> List[Optional[float]]:
    """Convert a Pandas series to a list with ``None`` for missing values."""

    return [None if pd.isna(value) else round(float(value), digits) for value in series]


def compute_moving_averages(
    close: pd.Series, periods: Iterable[int]
) -> Dict[str, List[Optional[float]]]:
    """Compute moving averages for the provided periods."""

    result: Dict[str, List[Optional[float]]] = {}
    close = close.astype(float)
    for period in periods:
        ma = close.rolling(window=period, min_periods=1).mean()
        result[f"ma{period}"] = series_to_list(ma, digits=3)
    return result


def compute_bollinger_bands(close: pd.Series, window: int = 20) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """Return Bollinger upper/middle/lower bands."""

    close = close.astype(float)
    middle = close.rolling(window=window, min_periods=1).mean()
    std = close.rolling(window=window, min_periods=1).std(ddof=0).fillna(0)
    upper = middle + 2 * std
    lower = middle - 2 * std
    return (
        series_to_list(upper, digits=3),
        series_to_list(middle, digits=3),
        series_to_list(lower, digits=3),
    )


def compute_rsi(close: pd.Series, periods: Iterable[int] = (6, 12, 24)) -> Dict[str, List[Optional[float]]]:
    """Calculate RSI values for the given periods."""

    temp = close.astype(float).copy()
    price_change = temp.diff()
    result: Dict[str, List[Optional[float]]] = {}

    for period in periods:
        gains = price_change.where(price_change > 0, 0)
        losses = -price_change.where(price_change < 0, 0)
        alpha = 1.0 / period
        avg_gains = gains.ewm(alpha=alpha, adjust=False).mean()
        avg_losses = losses.ewm(alpha=alpha, adjust=False).mean()
        rs = avg_gains / avg_losses.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.replace([np.inf, -np.inf], np.nan).fillna(50).clip(0, 100)
        result[f"rsi{period}"] = series_to_list(rsi, digits=2)
    return result


def compute_cost_change(avg_cost: pd.Series) -> Tuple[List[Optional[float]], List[Optional[float]]]:
    """Compute daily cost change percentage and cumulative positive change."""

    if avg_cost.isna().all():
        zeros = [0.0 for _ in avg_cost]
        return zeros, zeros

    pct_change = avg_cost.astype(float).pct_change() * 100
    pct_change = pct_change.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
    cumulative = pct_change.copy()
    cumulative[cumulative < 1.1] = 0
    cumulative = cumulative.cumsum()
    return series_to_list(pct_change, digits=2), series_to_list(cumulative, digits=2)


def compute_ma5_deviation(df: pd.DataFrame) -> Tuple[List[Optional[float]], List[Optional[float]]]:
    """Calculate MA5 upper and lower deviation percentages."""

    ma5 = df["close"].astype(float).rolling(window=5, min_periods=5).mean()
    ma5_safe = ma5.replace(0, np.nan)

    up = ((df["high"] - ma5_safe) / ma5_safe * 100).where(df["high"] > ma5_safe, 0)
    down = ((df["low"] - ma5_safe) / ma5_safe * 100).where(df["low"] < ma5_safe, 0)

    up = up.replace([np.inf, -np.inf], 0).fillna(0)
    down = down.replace([np.inf, -np.inf], 0).fillna(0)
    return series_to_list(up, digits=2), series_to_list(down, digits=2)


def compute_smart_money_lines(df: pd.DataFrame) -> Tuple[List[Optional[float]], List[Optional[float]]]:
    """Return three-day entity change ("dumb line") and smart profit ("smart line")."""

    open_price = df["open"].astype(float)
    close_price = df["close"].astype(float)

    # Entity change (dumb line)
    current_entity_low = np.minimum(open_price, close_price)
    entity_high_3d_ago = np.maximum(open_price.shift(3), close_price.shift(3))
    entity_change = (current_entity_low - entity_high_3d_ago) / entity_high_3d_ago
    entity_change = entity_change.replace([np.inf, -np.inf], 0).fillna(0)

    # Smart profit line
    current_entity_high = np.maximum(open_price, close_price)
    entity_low_3d_ago = np.minimum(open_price.shift(3), close_price.shift(3))
    smart_profit = (current_entity_high - entity_low_3d_ago) / entity_low_3d_ago
    smart_profit = smart_profit.replace([np.inf, -np.inf], 0).fillna(0)

    return series_to_list(entity_change, digits=3), series_to_list(smart_profit, digits=3)


def fetch_chip_data(
    code: str, index: pd.DatetimeIndex, fallback_close: pd.Series
) -> Tuple[Dict[str, List[Optional[float]]], pd.Series]:
    """Fetch chip distribution and aligned average cost data."""

    try:
        import akshare as ak  # type: ignore
    except Exception:
        empty = pd.Series([np.nan] * len(index), index=index)
        return (
            {
                "concentration_70": [None] * len(index),
                "concentration_90": [None] * len(index),
                "cost_70_low": [None] * len(index),
                "cost_70_high": [None] * len(index),
                "cost_90_low": [None] * len(index),
                "cost_90_high": [None] * len(index),
            },
            empty,
        )

    try:
        cyq = ak.stock_cyq_em(symbol=str(code), adjust="qfq")
    except Exception:
        cyq = pd.DataFrame()

    if cyq is None or cyq.empty:
        avg_cost = fallback_close.rolling(window=20, min_periods=1).mean()
        return (
            {
                "concentration_70": [None] * len(index),
                "concentration_90": [None] * len(index),
                "cost_70_low": [None] * len(index),
                "cost_70_high": [None] * len(index),
                "cost_90_low": [None] * len(index),
                "cost_90_high": [None] * len(index),
            },
            avg_cost,
        )

    cyq = cyq.copy()
    if "日期" in cyq.columns:
        cyq["日期"] = pd.to_datetime(cyq["日期"])
        cyq = cyq.set_index("日期")
    column_mapping = {
        "90%低": "cost_90_low",
        "90%高": "cost_90_high",
        "70%低": "cost_70_low",
        "70%高": "cost_70_high",
        "90%集中度": "concentration_90",
        "70%集中度": "concentration_70",
        "平均成本": "average_cost",
    }
    cyq = cyq.rename(columns=column_mapping)

    aligned = cyq.reindex(index, method="ffill")

    avg_cost = aligned.get("average_cost")
    if avg_cost is None:
        avg_cost = fallback_close.rolling(window=20, min_periods=1).mean()

    result = {}
    for key in (
        "concentration_70",
        "concentration_90",
        "cost_70_low",
        "cost_70_high",
        "cost_90_low",
        "cost_90_high",
    ):
        series = aligned.get(key, pd.Series([np.nan] * len(index), index=index))
        result[key] = series_to_list(series)

    return result, avg_cost


def fetch_fund_flow_series(
    code: str, index: pd.DatetimeIndex
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]], str]:
    """Fetch fund flow series grouped by trader type using LHB details.

    The function aggregates net amounts (in yuan) for institution, hot money and retail
    categories. When remote data is unavailable, zero series are returned.
    """

    try:
        import akshare as ak  # type: ignore
    except Exception:
        zeros = [0.0 for _ in index]
        return zeros, zeros, zeros, "amount"

    institution = pd.Series(0.0, index=index)
    hot_money = pd.Series(0.0, index=index)
    retail = pd.Series(0.0, index=index)

    for date in index:
        date_str = date.strftime("%Y%m%d")
        try:
            buy_df = ak.stock_lhb_stock_detail_em(symbol=str(code), date=date_str, flag="买入")
            sell_df = ak.stock_lhb_stock_detail_em(symbol=str(code), date=date_str, flag="卖出")
        except Exception:
            continue

        combined = []
        if isinstance(buy_df, pd.DataFrame) and not buy_df.empty:
            combined.append(buy_df)
        if isinstance(sell_df, pd.DataFrame) and not sell_df.empty:
            combined.append(sell_df)
        if not combined:
            continue

        df = pd.concat(combined, ignore_index=True)
        if "类型" not in df.columns or "净额" not in df.columns:
            continue

        grouped = df.groupby("类型")["净额"].sum(min_count=1)
        for trader_type, value in grouped.items():
            if pd.isna(value):
                continue
            if "机构" in trader_type:
                institution.at[date] += float(value)
            elif "营业部" in trader_type or "券商" in trader_type or "游资" in trader_type:
                hot_money.at[date] += float(value)
            else:
                retail.at[date] += float(value)

    return (
        series_to_list(institution, digits=0),
        series_to_list(hot_money, digits=0),
        series_to_list(retail, digits=0),
        "amount",
    )


def should_draw_volume_prediction(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    morning_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
    morning_end = now.replace(hour=11, minute=30, second=0, microsecond=0)
    afternoon_start = now.replace(hour=13, minute=0, second=0, microsecond=0)
    afternoon_end = now.replace(hour=15, minute=0, second=0, microsecond=0)
    if morning_start <= now <= morning_end:
        return True
    if afternoon_start <= now <= afternoon_end:
        return True
    if morning_end < now < afternoon_start:
        return True
    return False


def get_current_time_ratio(now: Optional[datetime] = None) -> float:
    now = now or datetime.now()
    morning_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
    morning_end = now.replace(hour=11, minute=30, second=0, microsecond=0)
    afternoon_start = now.replace(hour=13, minute=0, second=0, microsecond=0)
    afternoon_end = now.replace(hour=15, minute=0, second=0, microsecond=0)

    if morning_start <= now <= morning_end:
        elapsed = (now - morning_start).total_seconds() / 60
        return min(elapsed / 120, 0.5)
    if morning_end < now < afternoon_start:
        return 0.5
    if afternoon_start <= now <= afternoon_end:
        elapsed = (now - afternoon_start).total_seconds() / 60
        return 0.5 + (elapsed / 120) * 0.5
    return 0.0


def predict_final_volume(current_volume: float, time_percent: float) -> float:
    """Predict the final trading volume based on intraday progress."""

    if time_percent <= 0:
        return float(current_volume)
    alpha = 0.65
    beta = 0.015
    total_minutes = 240
    traded_min = total_minutes * time_percent
    remaining_ratio = max(0.0, 1 - time_percent)
    predicted = current_volume / max(time_percent, 1e-6)
    predicted *= (alpha + beta * remaining_ratio * (total_minutes - traded_min) / total_minutes)
    return float(max(predicted, current_volume))
