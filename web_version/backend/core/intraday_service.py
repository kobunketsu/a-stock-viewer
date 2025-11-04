from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from .data_provider import MarketDataProvider, get_market_data_provider


@dataclass
class IntradayService:
    data_provider: MarketDataProvider | None = None

    def __post_init__(self) -> None:
        if self.data_provider is None:
            self.data_provider = get_market_data_provider()

    def get_intraday_series(self, code: str, minutes: int = 120) -> List[dict]:
        assert self.data_provider is not None
        df = self.data_provider.get_intraday_series(code, minutes=minutes)
        if df.empty:
            df = self._generate_sample(minutes)

        def _format_ts(value: pd.Timestamp | str) -> str:
            if isinstance(value, pd.Timestamp):
                return value.to_pydatetime().isoformat()
            return str(value)

        return [
            {
                "timestamp": _format_ts(row["timestamp"]),
                "price": float(row["price"]),
                "volume": float(row["volume"]),
                "rsi": float(row["rsi"]),
                "ma5": float(row["ma5"]),
            }
            for _, row in df.iterrows()
        ]

    @staticmethod
    def _generate_sample(minutes: int) -> pd.DataFrame:
        now = pd.Timestamp.utcnow()
        records: List[dict] = []
        price = 100.0
        for idx in range(minutes):
            ts = now - pd.Timedelta(minutes=minutes - idx)
            price = max(0.1, price * (1 + ((idx % 10) - 5) * 0.0008))
            volume = 10_000 * (1 + (idx % 5))
            records.append(
                {
                    "timestamp": ts,
                    "price": round(price, 2),
                    "volume": volume,
                    "rsi": 50 + (idx % 20 - 10) * 1.2,
                    "ma5": round(price * 0.99, 2),
                }
            )
        return pd.DataFrame(records)


def get_intraday_service() -> IntradayService:
    return IntradayService()
