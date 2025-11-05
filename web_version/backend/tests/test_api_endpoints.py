import os

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.core.config import get_settings


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBTK_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    return TestClient(app)


def test_health_endpoint(api_client: TestClient) -> None:
    response = api_client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"


def test_watchlists_endpoint(api_client: TestClient) -> None:
    response = api_client.get("/watchlists")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data
    assert {"name", "type", "symbol_count"}.issubset(data[0].keys())


def test_create_watchlist_flow(api_client: TestClient) -> None:
    response = api_client.post("/watchlists", json={"name": "自选A"})
    assert response.status_code == 201

    add_resp = api_client.post("/watchlists/自选A/symbols", json={"code": "600519", "name": "贵州茅台"})
    assert add_resp.status_code == 201

    list_resp = api_client.get("/watchlists/自选A/symbols", params={"with_quotes": False})
    assert list_resp.status_code == 200
    symbols = list_resp.json()
    assert symbols and symbols[0]["code"] == "600519"

    search_resp = api_client.get("/symbols/search", params={"q": "600519"})
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert search_data and search_data[0]["code"] == "600519"


def test_kline_endpoint(api_client: TestClient) -> None:
    response = api_client.get("/kline/600519")
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == "600519"
    assert len(payload["kline"]) >= 60

    indicators = payload["indicators"]
    assert set(indicators["ma"].keys()) >= {"ma5", "ma10", "ma20", "ma250"}
    assert len(indicators["ma"]["ma5"]) == len(payload["kline"])

    boll = indicators["bollinger"]
    assert {"upper", "middle", "lower"}.issubset(boll.keys())

    rsi = indicators["rsi"]
    assert {"rsi6", "rsi12", "rsi24"}.issubset(rsi.keys())

    cost_change = indicators["cost_change"]
    assert {"daily_change", "cumulative_positive"}.issubset(cost_change.keys())

    ma5_dev = indicators["ma5_deviation"]
    assert {"up", "down"}.issubset(ma5_dev.keys())

    smart = indicators["smart_money"]
    assert {"entity_change_3d", "smart_profit_3d"}.issubset(smart.keys())

    fund_flow = indicators["fund_flow"]
    assert {"institution", "hot_money", "retail", "unit"}.issubset(fund_flow.keys())

    chip = payload["chip_distribution"]
    assert {
        "concentration_70",
        "concentration_90",
        "cost_70_low",
        "cost_70_high",
        "cost_90_low",
        "cost_90_high",
    }.issubset(chip.keys())


def test_intraday_endpoint(api_client: TestClient) -> None:
    response = api_client.get("/intraday/600519")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert payload
    first = payload[0]
    assert {"timestamp", "price", "volume", "rsi", "ma5"}.issubset(first.keys())
