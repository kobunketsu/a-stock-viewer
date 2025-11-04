from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

import pandas as pd

from .data_provider import MarketDataProvider, get_market_data_provider
from .models import KLinePoint, KLineResponse


@dataclass
class KLineService:
    data_provider: MarketDataProvider | None = None

    def __post_init__(self) -> None:
        if self.data_provider is None:
            self.data_provider = get_market_data_provider()

    def get_daily_kline(self, code: str, days: int = 120) -> KLineResponse:
        assert self.data_provider is not None  # for type checker
        df = self.data_provider.get_daily_kline(code, days=days)
        if df.empty:
            df = self._generate_sample_series(days)

        kline_points = [
            KLinePoint(
                timestamp=row["timestamp"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            for _, row in df.iterrows()
        ]

        close_series = df["close"].astype(float)
        indicators = {
            "ma5": close_series.rolling(window=5, min_periods=1).mean().round(2).tolist(),
            "ma10": close_series.rolling(window=10, min_periods=1).mean().round(2).tolist(),
        }

        chip_distribution = self._build_chip_distribution(close_series)

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
    def _build_chip_distribution(close_series: pd.Series) -> dict:
        normalized = (close_series - close_series.min()) / (
            (close_series.max() - close_series.min()) + 1e-6
        )
        concentration_70 = normalized.rolling(window=14, min_periods=1).mean().clip(0, 1)
        concentration_90 = normalized.rolling(window=30, min_periods=1).mean().clip(0, 1)
        return {
            "concentration_70": concentration_70.round(3).tolist(),
            "concentration_90": concentration_90.round(3).tolist(),
        }

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
