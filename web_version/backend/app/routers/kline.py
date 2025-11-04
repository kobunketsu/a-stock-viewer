from fastapi import APIRouter, Depends

from ...core.kline_service import KLineService, get_kline_service
from ...core.models import KLineResponse

router = APIRouter(prefix="/kline", tags=["kline"])


@router.get("/{code}", response_model=KLineResponse)
def get_kline(
    code: str,
    service: KLineService = Depends(get_kline_service),
) -> KLineResponse:
    """获取指定股票的日 K 及附加数据。"""

    return service.get_daily_kline(code)

