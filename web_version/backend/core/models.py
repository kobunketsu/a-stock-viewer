from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class WatchlistEntry(BaseModel):
    """自选列表条目的基本模型。"""

    code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    tags: List[str] = Field(default_factory=list, description="标签/分组信息")
    last_price: Optional[float] = Field(None, description="最新价（可选）")
    change_percent: Optional[float] = Field(None, description="涨跌幅（%）")
    signal: Optional[str] = Field(None, description="信号或提示信息")


class QuoteDetail(BaseModel):
    last_price: Optional[float] = None
    change_percent: Optional[float] = None
    industry: Optional[str] = None
    cost_change: Optional[float] = None
    ma5_deviation: Optional[float] = None
    next_day_limit_up_ma5_deviation: Optional[float] = None
    intraday_trend: Optional[str] = None
    day_trend: Optional[str] = None
    week_trend: Optional[str] = None
    month_trend: Optional[str] = None
    holders_change: Optional[float] = None
    capita_change: Optional[float] = None
    message: Optional[str] = None
    signal_level: Optional[str] = None


class WatchlistSymbol(BaseModel):
    code: str
    name: str
    lists: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    last_refreshed: Optional[datetime] = None
    quote: Optional[QuoteDetail] = None


class WatchlistMeta(BaseModel):
    name: str
    type: Literal["custom", "system"]
    symbol_count: int = 0
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KLinePoint(BaseModel):
    """单个 K 线数据点。"""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class KLineResponse(BaseModel):
    """日 K 接口返回体。"""

    code: str
    name: str
    kline: List[KLinePoint]
    indicators: dict = Field(default_factory=dict, description="附加技术指标")
    chip_distribution: dict = Field(
        default_factory=dict,
        description="筹码相关数据，需包含 70%/90% 集中度曲线",
    )


class HealthStatus(BaseModel):
    """健康检查响应。"""

    status: Literal["ok", "degraded", "unhealthy"]
    detail: str = ""
