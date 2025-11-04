from pathlib import Path

import pytest

from backend.core.watchlist_repository import WatchlistRepository
from backend.core.watchlist_service import WatchlistService


def make_service(tmp_path: Path) -> WatchlistService:
    repo_path = tmp_path / "config" / "watchlists.json"
    repo = WatchlistRepository(data_path=repo_path)
    return WatchlistService(repository=repo)


def test_list_watchlists_contains_default(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    watchlists = service.list_watchlists()
    names = {wl.name for wl in watchlists}
    assert "默认" in names
    # 系统列表也应该存在
    assert {"买入信号", "卖出信号", "超跌", "退市", "龙虎榜"}.issubset(names)


def test_add_and_fetch_symbols(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.create_watchlist("测试A")
    service.add_symbol("测试A", "600000", "浦发银行")
    service.add_symbol("测试A", "000001", "平安银行")

    symbols = service.get_watchlist_symbols("测试A", with_quotes=False)
    assert [item.code for item in symbols] == ["600000", "000001"]
    assert symbols[0].name == "浦发银行"


def test_remove_symbol(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.create_watchlist("测试B")
    service.add_symbol("测试B", "600519", "贵州茅台")
    service.remove_symbol("测试B", "600519")
    symbols = service.get_watchlist_symbols("测试B", with_quotes=False)
    assert symbols == []


def test_search_symbol_by_code(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.create_watchlist("测试C")
    service.add_symbol("测试C", "300750", "宁德时代")

    results = service.search_symbols("300750")
    assert results and results[0].name == "宁德时代"


@pytest.mark.parametrize("code", ["600519", "000001", "510300"])
def test_kline_service_mock(code: str) -> None:
    from backend.core.kline_service import KLineService

    service = KLineService()
    response = service.get_daily_kline(code)
    assert response.code == code
    assert len(response.kline) >= 60
    assert "concentration_70" in response.chip_distribution


def test_intraday_service_mock() -> None:
    from backend.core.intraday_service import IntradayService

    service = IntradayService()
    data = service.get_intraday_series("600519")
    assert len(data) == 120
    assert {"timestamp", "price", "volume", "rsi", "ma5"}.issubset(data[0].keys())
