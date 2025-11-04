from fastapi.testclient import TestClient

from backend.app.main import app


def test_intraday_websocket():
    client = TestClient(app)
    with client.websocket_connect("/ws/intraday/600519") as websocket:
        websocket.send_text("ping")
        data = websocket.receive_json()
        assert data["code"] == "600519"
        assert isinstance(data["data"], list)
        assert data["data"]
