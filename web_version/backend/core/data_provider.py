from __future__ import annotations

import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import pandas as pd

from .config import Settings, get_settings

try:  # Optional依赖
    from pypinyin import NORMAL, FIRST_LETTER, pinyin as to_pinyin  # type: ignore
except Exception:  # pragma: no cover
    NORMAL = FIRST_LETTER = None
    to_pinyin = None

logger = logging.getLogger(__name__)


class RateLimiter:
    """简单的令牌桶，实现每分钟调用上限控制。"""

    def __init__(self, limit_per_minute: int) -> None:
        self.limit_per_minute = max(limit_per_minute, 1)
        self.calls: deque[float] = deque()

    def acquire(self) -> None:
        now = time.time()
        window_start = now - 60
        while self.calls and self.calls[0] < window_start:
            self.calls.popleft()
        if len(self.calls) >= self.limit_per_minute:
            sleep_time = 60 - (now - self.calls[0])
            if sleep_time > 0:
                logger.debug("RateLimiter sleeping %.2fs", sleep_time)
                time.sleep(sleep_time)
                now = time.time()
        self.calls.append(now)


@dataclass
class CacheEntry:
    payload: object
    expires_at: float


class TTLCache:
    """内存级 TTL 缓存，支持过期淘汰。"""

    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = ttl_seconds
        self._store: Dict[str, CacheEntry] = {}

    def get(self, key: str) -> Optional[object]:
        entry = self._store.get(key)
        if not entry:
            return None
        if entry.expires_at < time.time():
            self._store.pop(key, None)
            return None
        return entry.payload

    def set(self, key: str, payload: object) -> None:
        self._store[key] = CacheEntry(payload=payload, expires_at=time.time() + self.ttl)

    def clear(self) -> None:
        self._store.clear()


class MarketDataProvider:
    """市场数据多源聚合器，提供自选、日K、分时等行情。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.rate_limiter = RateLimiter(self.settings.akshare_rate_limit_per_minute)
        self.cache = TTLCache(self.settings.cache_ttl_seconds)
        self.data_dir = self.settings.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._code_meta: Dict[str, Dict[str, str]] = {}
        self._code_meta_loaded_at: float = 0.0
        self._code_meta_ttl_seconds: int = 6 * 60 * 60
        self._quote_cooldown_until: float = 0.0

    # ------------------------------------------------------------------ Quotes
    def get_watchlist_quotes(self, codes: Iterable[str]) -> Dict[str, dict]:
        """获取自选列表行情，按多数据源顺序尝试，失败时回退到样例数据。"""

        code_list = list({code.strip() for code in codes if code})
        if not code_list:
            return {}

        cache_key = f"quotes:{','.join(sorted(code_list))}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached  # type: ignore[return-value]

        providers: List[Callable[[], Dict[str, dict]]] = [
            lambda: self._fetch_quotes_from_akshare(code_list),
            lambda: self._load_quotes_from_cache_file(),
            lambda: self._generate_sample_quotes(code_list),
        ]

        for provider in providers:
            try:
                data = provider()
                if data:
                    self.cache.set(cache_key, data)
                    return data
            except Exception as exc:  # pragma: no cover - 记录异常
                logger.warning("Quote provider %s failed: %s", provider.__name__, exc)

        return {}

    def _fetch_quotes_from_akshare(self, codes: List[str]) -> Dict[str, dict]:
        try:
            import akshare as ak  # type: ignore
        except Exception as exc:
            logger.warning("AkShare 模块不可用（行情），使用缓存/样例数据: %s", exc)
            return {}

        if time.time() < self._quote_cooldown_until:
            logger.debug("quotes provider in cooldown, skip akshare call")
            return {}

        self.rate_limiter.acquire()
        df_list: List[pd.DataFrame] = []

        for fn in ("stock_zh_a_spot_em", "stock_zh_a_spot"):
            if not hasattr(ak, fn):
                continue
            try:
                df = getattr(ak, fn)()
                if df is not None and not df.empty:
                    df_list.append(df)
                    break
            except Exception as exc:  # pragma: no cover - 网络异常
                logger.warning(
                    "AkShare 实时行情接口 %s 调用失败：%s。进入 5 分钟降级，改用缓存/样例数据。",
                    fn,
                    exc,
                )
                self._quote_cooldown_until = time.time() + 300

        if not df_list:
            return {}

        df = df_list[0]
        code_column = "代码" if "代码" in df.columns else df.columns[0]
        filtered = df[df[code_column].isin(codes)]

        quotes: Dict[str, dict] = {}
        for _, row in filtered.iterrows():
            code = str(row[code_column])
            quotes[code] = {
                "code": code,
                "name": row.get("名称") or row.get("股票名称") or code,
                "last_price": float(row.get("最新价") or row.get("最新价(元)") or 0),
                "change_percent": float(row.get("涨跌幅") or row.get("涨跌幅(%)") or 0),
                "signal": None,
            }
        if quotes:
            self._quote_cooldown_until = 0.0
        return quotes

    # ------------------------------------------------------------------ Code search helpers
    def lookup_symbol_name(self, code: str) -> Optional[str]:
        meta = self._get_code_meta()
        normalized = code.strip()
        entry = meta.get(normalized) or meta.get(normalized.upper()) or meta.get(normalized.zfill(6))
        return entry.get("name") if entry else None

    def search_symbols(self, keyword: str, limit: int = 10) -> List[dict]:
        meta = self._get_code_meta()
        keyword = keyword.strip()
        if not keyword:
            return []

        lower_keyword = keyword.lower()
        results: List[dict] = []

        # 精确匹配优先
        exact = meta.get(keyword) or meta.get(keyword.upper()) or meta.get(keyword.zfill(6))
        if exact:
            results.append({"code": keyword.zfill(6) if keyword.isdigit() else keyword.upper(), "name": exact})

        for code, info in meta.items():
            if len(results) >= limit:
                break
            name = info.get("name", "")
            if {"code": code, "name": name} in results:
                continue
            if lower_keyword in code.lower() or lower_keyword in name.lower():
                results.append({"code": code, "name": name})
                continue
            # 拼音匹配
            full = info.get("pinyin_full", "")
            first = info.get("pinyin_first", "")
            if lower_keyword and (lower_keyword in full or lower_keyword in first):
                results.append({"code": code, "name": name})

        return results[:limit]

    def _load_quotes_from_cache_file(self) -> Dict[str, dict]:
        cache_file = self.data_dir / "sample_quotes.json"
        if not cache_file.exists():
            return {}
        with cache_file.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return {item["code"]: item for item in payload}

    def _generate_sample_quotes(self, codes: List[str]) -> Dict[str, dict]:
        quotes: Dict[str, dict] = {}
        base_price = 100.0
        for idx, code in enumerate(codes, start=1):
            change = ((idx % 5) - 2) * 1.23
            quotes[code] = {
                "code": code,
                "name": f"{code}示例",
                "last_price": round(base_price + idx * 1.5, 2),
                "change_percent": round(change, 2),
                "signal": "mock" if change > 0 else None,
            }
        return quotes

    # ------------------------------------------------------------------ Daily K
    def get_daily_kline(self, code: str, days: int = 120) -> pd.DataFrame:
        cache_key = f"kline:{code}:{days}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        providers: List[Callable[[], pd.DataFrame]] = [
            lambda: self._fetch_kline_from_akshare(code, days),
            lambda: self._load_kline_from_cache_file(code),
            lambda: self._generate_sample_kline(days),
        ]

        for provider in providers:
            try:
                df = provider()
                if df is not None and not df.empty:
                    df = df.sort_values("timestamp").reset_index(drop=True)
                    self.cache.set(cache_key, df)
                    return df
            except Exception as exc:  # pragma: no cover
                logger.warning("Kline provider %s failed: %s", provider.__name__, exc)

        return pd.DataFrame()

    def _fetch_kline_from_akshare(self, code: str, days: int) -> pd.DataFrame:
        try:
            import akshare as ak  # type: ignore
        except Exception as exc:
            logger.info("akshare not available for kline: %s", exc)
            return pd.DataFrame()

        self.rate_limiter.acquire()
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")

        apis = [
            ("stock_zh_a_hist", {"symbol": code, "start_date": start_date, "end_date": end_date, "adjust": ""}),
            ("stock_zh_a_daily", {"symbol": code, "adjust": ""}),
        ]
        for api_name, params in apis:
            if not hasattr(ak, api_name):
                continue
            try:
                df = getattr(ak, api_name)(**params)
            except Exception as exc:  # pragma: no cover
                logger.warning("akshare %s failed: %s", api_name, exc)
                continue
            if df is None or df.empty:
                continue
            df = df.tail(days).copy()
            df.rename(
                columns={
                    "日期": "timestamp",
                    "开盘": "open",
                    "最高": "high",
                    "最低": "low",
                    "收盘": "close",
                    "成交量": "volume",
                },
                inplace=True,
            )
            if "timestamp" not in df.columns:
                continue
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            return df[["timestamp", "open", "high", "low", "close", "volume"]]

        return pd.DataFrame()

    def _load_kline_from_cache_file(self, code: str) -> pd.DataFrame:
        cache_file = self.data_dir / f"{code}_kline.csv"
        if not cache_file.exists():
            return pd.DataFrame()
        df = pd.read_csv(cache_file, parse_dates=["timestamp"])
        return df

    def _generate_sample_kline(self, days: int) -> pd.DataFrame:
        base_price = 100.0
        records: List[dict] = []
        date = datetime.now().date() - timedelta(days=days)
        price = base_price
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

    # --------------------------------------------------------------- Intraday
    def get_intraday_series(self, code: str, minutes: int = 120) -> pd.DataFrame:
        cache_key = f"intraday:{code}:{minutes}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        providers: List[Callable[[], pd.DataFrame]] = [
            lambda: self._fetch_intraday_from_akshare(code, minutes),
            lambda: self._load_intraday_from_cache_file(code),
            lambda: self._generate_sample_intraday(minutes),
        ]

        for provider in providers:
            try:
                df = provider()
                if df is not None and not df.empty:
                    df = df.sort_values("timestamp").reset_index(drop=True)
                    self.cache.set(cache_key, df)
                    return df
            except Exception as exc:  # pragma: no cover
                logger.warning("Intraday provider %s failed: %s", provider.__name__, exc)

        return pd.DataFrame()

    def _fetch_intraday_from_akshare(self, code: str, minutes: int) -> pd.DataFrame:
        try:
            import akshare as ak  # type: ignore
        except Exception as exc:
            logger.info("akshare not available for intraday: %s", exc)
            return pd.DataFrame()

        self.rate_limiter.acquire()
        apis = [
            ("stock_zh_a_minute", {"symbol": code, "period": "1"}),  # 1-min interval
            ("stock_zh_a_tick_tx", {"symbol": code}),
        ]
        for api_name, params in apis:
            if not hasattr(ak, api_name):
                continue
            try:
                df = getattr(ak, api_name)(**params)
            except Exception as exc:  # pragma: no cover
                logger.warning("akshare %s failed: %s", api_name, exc)
                continue

            if df is None or df.empty:
                continue
            if "time" in df.columns:
                df.rename(columns={"time": "timestamp"}, inplace=True)
            elif "成交时间" in df.columns:
                df.rename(columns={"成交时间": "timestamp"}, inplace=True)

            if "timestamp" not in df.columns:
                continue

            df["timestamp"] = pd.to_datetime(df["timestamp"])
            if "price" not in df.columns and "最新价" in df.columns:
                df.rename(columns={"最新价": "price"}, inplace=True)
            if "volume" not in df.columns and "成交量" in df.columns:
                df.rename(columns={"成交量": "volume"}, inplace=True)

            df = df.tail(minutes)
            if "price" not in df.columns:
                df["price"] = df.get("close") or df.get("收盘") or df.get("最新价", 0)
            if "rsi" not in df.columns:
                df["rsi"] = self._compute_mock_rsi(df["price"])
            if "ma5" not in df.columns:
                df["ma5"] = df["price"].rolling(window=5, min_periods=1).mean()

            wanted_columns = ["timestamp", "price", "volume", "rsi", "ma5"]
            return df[wanted_columns]

        return pd.DataFrame()

    def _load_intraday_from_cache_file(self, code: str) -> pd.DataFrame:
        cache_file = self.data_dir / f"{code}_intraday.csv"
        if not cache_file.exists():
            return pd.DataFrame()
        return pd.read_csv(cache_file, parse_dates=["timestamp"])

    def _generate_sample_intraday(self, minutes: int) -> pd.DataFrame:
        now = datetime.now()
        records: List[dict] = []
        price = 100.0
        for idx in range(minutes):
            ts = now - timedelta(minutes=minutes - idx)
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

    # ----------------------------------------------------------------- Helpers
    @staticmethod
    def _compute_mock_rsi(series: Iterable[float]) -> pd.Series:
        prices = pd.Series(list(series))
        delta = prices.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        loss = -delta.clip(upper=0).ewm(alpha=1 / 14, adjust=False).mean()
        rs = gain / loss.replace(0, pd.NA)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50)

    def _get_code_meta(self) -> Dict[str, Dict[str, str]]:
        if self._code_meta and (time.time() - self._code_meta_loaded_at) < self._code_meta_ttl_seconds:
            return self._code_meta

        mapping = self._load_code_meta_from_akshare()
        if not mapping:
            mapping = self._load_code_meta_cache()
        if not mapping:
            mapping = self._sample_code_meta()

        self._code_meta = mapping
        self._code_meta_loaded_at = time.time()
        if mapping:
            self._save_code_meta_cache(mapping)
        return mapping

    def _load_code_meta_from_akshare(self) -> Dict[str, Dict[str, str]]:
        try:
            import akshare as ak  # type: ignore
        except Exception as exc:
            logger.warning("AkShare 模块不可用，使用缓存/样例数据: %s", exc)
            return {}

        self.rate_limiter.acquire()
        try:
            df = ak.stock_info_a_code_name()
        except Exception as exc:  # pragma: no cover
            logger.warning("AkShare 获取代码表失败，将使用缓存/样例数据", exc_info=True)
            return {}

        if df is None or df.empty:
            return {}

        mapping: Dict[str, Dict[str, str]] = {}
        for _, row in df.iterrows():
            code = str(row.get("code") or row.get("A股代码") or "").strip()
            name = str(row.get("name") or row.get("A股简称") or "").strip()
            if code and name:
                mapping[code] = self._build_code_meta_entry(code, name)
        return mapping

    def _code_meta_cache_path(self) -> Path:
        return self.data_dir / "code_name_cache.json"

    def _load_code_meta_cache(self) -> Dict[str, Dict[str, str]]:
        path = self._code_meta_cache_path()
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
                if isinstance(data, dict):
                    return {
                        str(code): {
                            "name": str(meta.get("name", "")),
                            "pinyin_full": str(meta.get("pinyin_full", "")),
                            "pinyin_first": str(meta.get("pinyin_first", "")),
                        }
                        for code, meta in data.items()
                    }
                if isinstance(data, list):
                    result: Dict[str, Dict[str, str]] = {}
                    for item in data:
                        code = str(item.get("code", "")).strip()
                        name = str(item.get("name", "")).strip()
                        if code and name:
                            result[code] = {
                                "name": name,
                                "pinyin_full": str(item.get("pinyin_full", "")),
                                "pinyin_first": str(item.get("pinyin_first", "")),
                            }
                    return result
        except Exception:
            logger.warning("failed to read code-name cache", exc_info=True)
        return {}

    def _save_code_meta_cache(self, mapping: Dict[str, Dict[str, str]]) -> None:
        path = self._code_meta_cache_path()
        try:
            with path.open("w", encoding="utf-8") as fp:
                json.dump(mapping, fp, ensure_ascii=False)
        except Exception:  # pragma: no cover
            logger.warning("failed to save code-name cache", exc_info=True)

    def _sample_code_meta(self) -> Dict[str, Dict[str, str]]:
        file_path = self.data_dir / "sample_codes.json"
        if file_path.exists():
            try:
                with file_path.open("r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    if isinstance(data, list):
                        return {
                            str(item.get("code")): self._build_code_meta_entry(
                                str(item.get("code")), str(item.get("name"))
                            )
                            for item in data
                            if item.get("code") and item.get("name")
                        }
                    if isinstance(data, dict):
                        return {str(k): self._build_code_meta_entry(str(k), str(v)) for k, v in data.items()}
            except Exception:
                logger.warning("failed to load sample code list", exc_info=True)
        # 兜底少量样例
        fallback = {
            "600519": "贵州茅台",
            "000001": "平安银行",
            "300750": "宁德时代",
            "600036": "招商银行",
            "601919": "中远海控",
        }
        return {code: self._build_code_meta_entry(code, name) for code, name in fallback.items()}

    def _build_code_meta_entry(self, code: str, name: str) -> Dict[str, str]:
        full = initials = ""
        if to_pinyin and NORMAL and FIRST_LETTER:
            try:
                full = ''.join(word for syllables in to_pinyin(name, style=NORMAL) for word in syllables)
                initials = ''.join(word for syllables in to_pinyin(name, style=FIRST_LETTER) for word in syllables)
            except Exception:  # pragma: no cover
                pass
        return {
            "name": name,
            "pinyin_full": full.lower(),
            "pinyin_first": initials.lower(),
        }


_provider_instance: Optional[MarketDataProvider] = None


def get_market_data_provider() -> MarketDataProvider:
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = MarketDataProvider()
    return _provider_instance
