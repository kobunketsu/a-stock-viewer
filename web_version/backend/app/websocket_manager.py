from typing import List

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_json(self, websocket: WebSocket, data: dict) -> None:
        await websocket.send_json(data)

    async def broadcast(self, data: dict) -> None:
        for connection in list(self.active_connections):
            await connection.send_json(data)
