from __future__ import annotations

from typing import Iterable, List, Optional

from .data_provider import MarketDataProvider, get_market_data_provider
from .models import QuoteDetail, WatchlistMeta, WatchlistSymbol
from .watchlist_repository import SYSTEM_LISTS, WatchlistRepository, get_watchlist_repository


class WatchlistService:
    """封装 watchlist 的业务逻辑（持久化 + 行情融合）。"""

    def __init__(
        self,
        repository: WatchlistRepository | None = None,
        data_provider: MarketDataProvider | None = None,
    ) -> None:
        self._repository = repository or get_watchlist_repository()
        self._data_provider = data_provider or get_market_data_provider()

    # ------------------------------------------------------------------ Watchlists
    def list_watchlists(self) -> List[WatchlistMeta]:
        records = self._repository.list_watchlists()
        result: List[WatchlistMeta] = []
        for record in records:
            result.append(
                WatchlistMeta(
                    name=record.name,
                    type=record.type,  # type: ignore[arg-type]
                    symbol_count=len(record.symbols),
                    description=record.description,
                    metadata=record.metadata,
                )
            )
        return result

    def create_watchlist(self, name: str, description: Optional[str] = None, metadata: Optional[dict] = None) -> WatchlistMeta:
        record = self._repository.create_watchlist(name=name, description=description, metadata=metadata)
        return WatchlistMeta(
            name=record.name,
            type=record.type,  # type: ignore[arg-type]
            symbol_count=len(record.symbols),
            description=record.description,
            metadata=record.metadata,
        )

    def update_watchlist(self, name: str, new_name: Optional[str] = None, description: Optional[str] = None, metadata: Optional[dict] = None) -> WatchlistMeta:
        record = self._repository.update_watchlist(name=name, new_name=new_name, description=description, metadata=metadata)
        return WatchlistMeta(
            name=record.name,
            type=record.type,  # type: ignore[arg-type]
            symbol_count=len(record.symbols),
            description=record.description,
            metadata=record.metadata,
        )

    def delete_watchlist(self, name: str) -> None:
        self._repository.delete_watchlist(name)

    # ------------------------------------------------------------------ Symbols
    def get_watchlist_symbols(self, watchlist: str, with_quotes: bool = True) -> List[WatchlistSymbol]:
        if watchlist in SYSTEM_LISTS:
            # 系统列表暂由专用 API 提供，这里返回空
            return []

        codes = self._repository.list_symbols(watchlist)
        symbols = []
        if not codes:
            return []

        quotes = self._data_provider.get_watchlist_quotes(codes) if with_quotes else {}

        for code in codes:
            entry = self._repository.get_symbol_entry(code)
            name = entry.get("name") or code
            lists = entry.get("lists", [watchlist])
            tags = entry.get("tags", [])
            notes = entry.get("notes")

            quote_payload = quotes.get(code) if with_quotes else None
            quote_detail = self._build_quote_detail(quote_payload) if quote_payload else None

            symbols.append(
                WatchlistSymbol(
                    code=code,
                    name=name,
                    lists=lists,
                    tags=tags,
                    notes=notes,
                    quote=quote_detail,
                )
            )
        return symbols

    def add_symbol(self, watchlist: str, code: str, name: Optional[str] = None) -> None:
        self._repository.add_symbol(watchlist, code, name)

    def remove_symbol(self, watchlist: str, code: str) -> None:
        self._repository.remove_symbol(watchlist, code)

    def update_symbol_meta(self, code: str, **fields: object) -> None:
        self._repository.update_symbol_meta(code, **fields)

    # ------------------------------------------------------------------ Quotes & search
    def get_quotes(self, codes: Iterable[str]) -> dict:
        return self._data_provider.get_watchlist_quotes(list(codes))

    def search_symbols(self, query: str) -> List[WatchlistSymbol]:
        query = query.strip()
        if not query:
            return []

        matches: List[WatchlistSymbol] = []
        if query.isdigit() and len(query) in (6, 5):
            code = query.zfill(6)
            entry = self._repository.get_symbol_entry(code)
            if entry:
                matches.append(
                    WatchlistSymbol(
                        code=code,
                        name=entry.get("name") or code,
                        lists=entry.get("lists", []),
                        tags=entry.get("tags", []),
                        notes=entry.get("notes"),
                    )
                )
            else:
                quote = self._data_provider.get_watchlist_quotes([code]).get(code)
                name = self._data_provider.lookup_symbol_name(code)
                if quote or name:
                    matches.append(
                        WatchlistSymbol(
                            code=code,
                            name=name or quote.get("name") if quote else name or code,
                            lists=[],
                            quote=self._build_quote_detail(quote) if quote else None,
                        )
                    )
            return matches

        # 名称模糊匹配（遍历已记录 symbol）
        seen = set()
        for symbol_code, info in self._repository.iter_symbols():
            name = info.get("name", "")
            if query.lower() in name.lower():
                if symbol_code in seen:
                    continue
                seen.add(symbol_code)
                matches.append(
                    WatchlistSymbol(
                        code=symbol_code,
                        name=name or symbol_code,
                        lists=info.get("lists", []),
                        tags=info.get("tags", []),
                        notes=info.get("notes"),
                    )
                )

        # 如果本地匹配不足，使用数据提供者搜索
        provider_matches = self._data_provider.search_symbols(query, limit=10)
        for item in provider_matches:
            code = item.get("code")
            name = item.get("name") or code
            if not code or not name:
                continue
            if any(existing.code == code for existing in matches):
                continue
            quote = self._data_provider.get_watchlist_quotes([code]).get(code, {})
            matches.append(
                WatchlistSymbol(
                    code=code,
                    name=name,
                    lists=[],
                    quote=self._build_quote_detail(quote) if quote else None,
                )
            )
        return matches

    # ------------------------------------------------------------------
    @staticmethod
    def _build_quote_detail(payload: dict) -> QuoteDetail:
        return QuoteDetail(
            last_price=_safe_float(payload.get("last_price")),
            change_percent=_safe_float(payload.get("change_percent")),
            industry=payload.get("industry"),
            cost_change=_safe_float(payload.get("cost_change")),
            ma5_deviation=_safe_float(payload.get("ma5_deviation")),
            next_day_limit_up_ma5_deviation=_safe_float(payload.get("next_day_limit_up_ma5_deviation")),
            intraday_trend=payload.get("intraday_trend"),
            day_trend=payload.get("day_trend"),
            week_trend=payload.get("week_trend"),
            month_trend=payload.get("month_trend"),
            holders_change=_safe_float(payload.get("holders_change")),
            capita_change=_safe_float(payload.get("capita_change")),
            message=payload.get("message"),
            signal_level=payload.get("signal"),
        )


def _safe_float(value: object) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def get_watchlist_service() -> WatchlistService:
    return WatchlistService()
