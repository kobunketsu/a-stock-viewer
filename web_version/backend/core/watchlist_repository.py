from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .config import get_settings


SYSTEM_LISTS = {"板块", "买入信号", "卖出信号", "超跌", "退市", "龙虎榜"}


@dataclass
class WatchlistRecord:
    name: str
    type: str  # "custom" | "system"
    symbols: List[str] = field(default_factory=list)
    description: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)


class WatchlistRepository:
    """负责 watchlist 数据的持久化与基本操作。"""

    def __init__(self, data_path: Path | None = None) -> None:
        settings = get_settings()
        self._data_path = data_path or settings.data_dir.parent / "config" / "watchlists.json"
        self._data_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._data = {
            "symbols": {},  # code -> {name, lists, tags, notes}
            "lists": {"默认": []},
            "metadata": {},
        }
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self._data_path.exists():
            self._persist()
            return
        with self._data_path.open("r", encoding="utf-8") as fp:
            self._data = json.load(fp)

    def _persist(self) -> None:
        tmp_path = self._data_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fp:
            json.dump(self._data, fp, ensure_ascii=False, indent=2)
        tmp_path.replace(self._data_path)

    # ------------------------------------------------------------------
    def list_watchlists(self) -> List[WatchlistRecord]:
        with self._lock:
            result: List[WatchlistRecord] = []
            lists_data: Dict[str, List[str]] = self._data.get("lists", {})
            meta_data: Dict[str, dict] = self._data.get("metadata", {})
            for name, symbols in lists_data.items():
                wl_type = "system" if name in SYSTEM_LISTS else "custom"
                metadata = meta_data.get(name, {})
                result.append(
                    WatchlistRecord(
                        name=name,
                        type=wl_type,
                        symbols=list(symbols),
                        description=metadata.get("description"),
                        metadata={k: v for k, v in metadata.items() if k != "description"},
                    )
                )
            # 确保系统列表存在
            for system_name in SYSTEM_LISTS:
                if system_name not in lists_data:
                    result.append(
                        WatchlistRecord(
                            name=system_name,
                            type="system",
                            symbols=[],
                        )
                    )
            return sorted(result, key=lambda r: (r.type != "system", r.name))

    def create_watchlist(self, name: str, description: str | None = None, metadata: Optional[dict] = None) -> WatchlistRecord:
        with self._lock:
            lists = self._data.setdefault("lists", {})
            if name in lists or name in SYSTEM_LISTS:
                raise ValueError("WATCHLIST_ALREADY_EXISTS")
            lists[name] = []
            meta = self._data.setdefault("metadata", {})
            meta[name] = {}
            if description:
                meta[name]["description"] = description
            if metadata:
                meta[name].update(metadata)
            self._persist()
            return WatchlistRecord(name=name, type="custom", symbols=[])

    def update_watchlist(self, name: str, new_name: Optional[str] = None, description: Optional[str] = None, metadata: Optional[dict] = None) -> WatchlistRecord:
        with self._lock:
            if name in SYSTEM_LISTS:
                raise ValueError("SYSTEM_LIST_IMMUTABLE")
            lists = self._data.setdefault("lists", {})
            if name not in lists:
                raise ValueError("WATCHLIST_NOT_FOUND")
            target_name = new_name or name
            if target_name != name and (target_name in lists or target_name in SYSTEM_LISTS):
                raise ValueError("WATCHLIST_ALREADY_EXISTS")

            symbols = lists.pop(name)
            lists[target_name] = symbols

            meta = self._data.setdefault("metadata", {})
            meta[target_name] = meta.pop(name, {})
            if description is not None:
                meta[target_name]["description"] = description
            if metadata:
                meta[target_name].update(metadata)

            # 同步更新 symbols -> lists 映射
            symbols_map: Dict[str, dict] = self._data.setdefault("symbols", {})
            for info in symbols_map.values():
                lists_set = set(info.get("lists", []))
                if name in lists_set:
                    lists_set.remove(name)
                    lists_set.add(target_name)
                info["lists"] = sorted(lists_set)

            self._persist()
            return WatchlistRecord(
                name=target_name,
                type="custom",
                symbols=list(symbols),
                description=meta[target_name].get("description"),
                metadata={k: v for k, v in meta[target_name].items() if k != "description"},
            )

    def delete_watchlist(self, name: str) -> None:
        with self._lock:
            if name in SYSTEM_LISTS:
                raise ValueError("SYSTEM_LIST_IMMUTABLE")
            lists = self._data.setdefault("lists", {})
            if name not in lists:
                raise ValueError("WATCHLIST_NOT_FOUND")
            del lists[name]
            meta = self._data.setdefault("metadata", {})
            meta.pop(name, None)
            # 从 symbols 映射中移除
            symbols_map: Dict[str, dict] = self._data.setdefault("symbols", {})
            for code, info in list(symbols_map.items()):
                lists_set = set(info.get("lists", []))
                if name in lists_set:
                    lists_set.remove(name)
                    info["lists"] = sorted(lists_set)
                if not info.get("lists"):
                    symbols_map.pop(code, None)
            self._persist()

    # ------------------------------------------------------------------
    def list_symbols(self, watchlist: str) -> List[str]:
        with self._lock:
            if watchlist in SYSTEM_LISTS:
                return []
            lists = self._data.setdefault("lists", {})
            return list(lists.get(watchlist, []))

    def add_symbol(self, watchlist: str, code: str, name: Optional[str] = None) -> None:
        with self._lock:
            if watchlist in SYSTEM_LISTS:
                raise ValueError("SYSTEM_LIST_IMMUTABLE")
            lists = self._data.setdefault("lists", {})
            if watchlist not in lists:
                raise ValueError("WATCHLIST_NOT_FOUND")
            if code in lists[watchlist]:
                raise ValueError("SYMBOL_ALREADY_EXISTS")
            lists[watchlist].append(code)

            symbols_map: Dict[str, dict] = self._data.setdefault("symbols", {})
            entry = symbols_map.setdefault(code, {"name": name or "", "lists": []})
            if name:
                entry["name"] = name
            entry_lists = set(entry.get("lists", []))
            entry_lists.add(watchlist)
            entry["lists"] = sorted(entry_lists)

            self._persist()

    def remove_symbol(self, watchlist: str, code: str) -> None:
        with self._lock:
            if watchlist in SYSTEM_LISTS:
                raise ValueError("SYSTEM_LIST_IMMUTABLE")
            lists = self._data.setdefault("lists", {})
            if watchlist not in lists:
                raise ValueError("WATCHLIST_NOT_FOUND")
            if code not in lists[watchlist]:
                raise ValueError("SYMBOL_NOT_IN_LIST")
            lists[watchlist].remove(code)

            symbols_map: Dict[str, dict] = self._data.setdefault("symbols", {})
            info = symbols_map.get(code)
            if info:
                lists_set = set(info.get("lists", []))
                lists_set.discard(watchlist)
                if lists_set:
                    info["lists"] = sorted(lists_set)
                else:
                    symbols_map.pop(code, None)

            self._persist()

    def get_symbol_entry(self, code: str) -> dict:
        with self._lock:
            return self._data.setdefault("symbols", {}).get(code, {})

    def update_symbol_meta(self, code: str, **fields: object) -> None:
        with self._lock:
            symbols_map: Dict[str, dict] = self._data.setdefault("symbols", {})
            entry = symbols_map.setdefault(code, {"name": "", "lists": []})
            entry.update({k: v for k, v in fields.items() if v is not None})
            self._persist()

    def iter_symbols(self):
        with self._lock:
            symbols_map: Dict[str, dict] = self._data.setdefault("symbols", {})
            for code, info in symbols_map.items():
                yield code, dict(info)


def get_watchlist_repository() -> WatchlistRepository:
    return WatchlistRepository()
