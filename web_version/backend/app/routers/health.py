from fastapi import APIRouter

from ...core.models import HealthStatus

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthStatus)
def get_health_status() -> HealthStatus:
    """基础健康检查，后续可扩展监控项。"""

    return HealthStatus(status="ok", detail="Milestone 1 skeleton ready")

