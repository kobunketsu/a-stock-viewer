from fastapi import APIRouter, Depends

from ...core.intraday_service import IntradayService, get_intraday_service

router = APIRouter(prefix="/intraday", tags=["intraday"])


@router.get("/{code}")
def get_intraday(
    code: str,
    service: IntradayService = Depends(get_intraday_service),
) -> list[dict]:
    """返回分时数据（示例使用模拟数据）。"""

    return service.get_intraday_series(code)

