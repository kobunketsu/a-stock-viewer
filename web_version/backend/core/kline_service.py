from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd

from .data_provider import MarketDataProvider, get_market_data_provider
from .indicator_calculator import (
    compute_bollinger_bands,
    compute_cost_change,
    compute_ma5_deviation,
    compute_moving_averages,
    compute_rsi,
    compute_smart_money_lines,
    fetch_chip_data,
    fetch_fund_flow_series,
    get_current_time_ratio,
    predict_final_volume,
    series_to_list,
    should_draw_volume_prediction,
)
from .models import (
    BollingerBands,
    ChipDistribution,
    CostChangeSeries,
    FundFlowSeries,
    KLineIndicators,
    KLinePoint,
    KLineResponse,
    MA5DeviationSeries,
    RSIIndicators,
    SmartMoneySeries,
    VolumeIndicators,
)


@dataclass
class KLineService:
    data_provider: MarketDataProvider | None = None

    def __post_init__(self) -> None:
        if self.data_provider is None:
            self.data_provider = get_market_data_provider()

    def get_daily_kline(self, code: str, days: int = 120) -> KLineResponse:
        assert self.data_provider is not None  # for type checker
        request_days = max(days, 260)  # ensure enough history for long MAs
        df = self.data_provider.get_daily_kline(code, days=request_days)
        if df.empty:
            df = self._generate_sample_series(request_days)

        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)
        indexed_full = df.set_index("timestamp")
        count = min(days, len(indexed_full))
        indexed = indexed_full.iloc[-count:]

        ma_periods = (5, 10, 20, 250)
        ma_full = compute_moving_averages(indexed_full["close"], ma_periods)

        def tail(values: List[Optional[float]]) -> List[Optional[float]]:
            if count == 0:
                return []
            if len(values) >= count:
                return values[-count:]
            # pad with None when upstream data shorter than expected
            return [None] * (count - len(values)) + values

        ma_series = {key: tail(values) for key, values in ma_full.items()}

        boll_upper_full, boll_middle_full, boll_lower_full = compute_bollinger_bands(indexed_full["close"])
        boll_upper = tail(boll_upper_full)
        boll_middle = tail(boll_middle_full)
        boll_lower = tail(boll_lower_full)

        rsi_full = compute_rsi(indexed_full["close"])
        rsi_values = {key: tail(values) for key, values in rsi_full.items()}

        chip_raw_full, average_cost_series_full = fetch_chip_data(
            code, indexed_full.index, indexed_full["close"]
        )
        chip_raw = {key: tail(values) for key, values in chip_raw_full.items()}
        average_cost_series = average_cost_series_full.reindex(indexed.index, method="ffill")

        cost_daily, cost_cumulative = compute_cost_change(average_cost_series)
        ma5_up, ma5_down = compute_ma5_deviation(indexed)
        entity_change, smart_profit = compute_smart_money_lines(indexed)
        inst_flow, hot_flow, retail_flow, flow_unit = fetch_fund_flow_series(code, indexed.index)

        predicted_volume: float | None = None
        if len(indexed) > 0 and should_draw_volume_prediction():
            time_ratio = get_current_time_ratio()
            if time_ratio > 0:
                predicted_volume = predict_final_volume(float(indexed["volume"].iloc[-1]), time_ratio)

        kline_points = [
            KLinePoint(
                timestamp=ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            for ts, row in indexed.iterrows()
        ]

        indicators = KLineIndicators(
            ma=ma_series,
            bollinger=BollingerBands(upper=boll_upper, middle=boll_middle, lower=boll_lower),
            rsi=RSIIndicators(
                rsi6=rsi_values.get("rsi6", [None] * len(indexed)),
                rsi12=rsi_values.get("rsi12", [None] * len(indexed)),
                rsi24=rsi_values.get("rsi24", [None] * len(indexed)),
            ),
            average_cost=series_to_list(average_cost_series, digits=3),
            cost_change=CostChangeSeries(daily_change=cost_daily, cumulative_positive=cost_cumulative),
            ma5_deviation=MA5DeviationSeries(up=ma5_up, down=ma5_down),
            smart_money=SmartMoneySeries(entity_change_3d=entity_change, smart_profit_3d=smart_profit),
            volume=VolumeIndicators(predicted=predicted_volume),
            fund_flow=FundFlowSeries(
                institution=inst_flow,
                hot_money=hot_flow,
                retail=retail_flow,
                unit=flow_unit,
            ),
        )

        chip_distribution = ChipDistribution(**chip_raw)

        quotes = self.data_provider.get_watchlist_quotes([code])
        name = quotes.get(code, {}).get("name", self._fallback_name(code))

        return KLineResponse(
            code=code,
            name=name,
            kline=kline_points,
            indicators=indicators,
            chip_distribution=chip_distribution,
        )

    @staticmethod
    def _fallback_name(code: str) -> str:
        if code.startswith("60"):
            return "上证股票"
        if code.startswith("00"):
            return "深证股票"
        return code

    @staticmethod
    def _generate_sample_series(days: int) -> pd.DataFrame:
        base_price = 100.0
        date = datetime.now().date() - timedelta(days=days)
        price = base_price
        records: List[dict] = []
        for idx in range(days):
            day = date + timedelta(days=idx)
            open_price = price
            close_price = max(0.1, open_price * (1 + ((idx % 5) - 2) * 0.003))
            high_price = max(open_price, close_price) * 1.01
            low_price = min(open_price, close_price) * 0.99
            volume = 1_000_000 * (1 + (idx % 7) * 0.1)
            price = close_price
            records.append(
                {
                    "timestamp": datetime.combine(day, datetime.min.time()),
                    "open": round(open_price, 2),
                    "high": round(high_price, 2),
                    "low": round(low_price, 2),
                    "close": round(close_price, 2),
                    "volume": volume,
                }
            )
        return pd.DataFrame(records)


def get_kline_service() -> KLineService:
    return KLineService()
