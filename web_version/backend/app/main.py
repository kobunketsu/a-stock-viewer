import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .routers import health, intraday, kline, watchlists, symbols
from .websocket_manager import WebSocketManager
from ..core.intraday_service import get_intraday_service

app = FastAPI(title="Grid Strategy Web Toolkit", version="0.1.0")

# CORS：允许本地前端（Vite 默认 5173 端口）访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(watchlists.router)
app.include_router(kline.router)
app.include_router(intraday.router)
app.include_router(symbols.router)

ws_manager = WebSocketManager()


@app.get("/")
def root() -> dict:
    return {"message": "Grid Strategy Web Toolkit backend is running."}


@app.websocket("/ws/intraday/{code}")
async def intraday_stream(websocket: WebSocket, code: str) -> None:
    service = get_intraday_service()
    try:
        await ws_manager.connect(websocket)
        while True:
            series = service.get_intraday_series(code)
            await websocket.send_json({"code": code, "data": series})
            await websocket.receive_text()
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as exc:  # pragma: no cover
        await websocket.close(code=1011, reason=str(exc))
        ws_manager.disconnect(websocket)
