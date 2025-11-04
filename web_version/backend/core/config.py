from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Settings:
    """轻量级配置管理，避免对特定库的强依赖。"""

    env: str = "development"
    data_dir: Path = Path(__file__).resolve().parent.parent / "data"
    enable_cache: bool = True
    cache_ttl_seconds: int = 300
    request_timeout_seconds: int = 10
    akshare_primary_source: str = "eastmoney"
    akshare_proxy_pool: Optional[str] = None
    akshare_rate_limit_per_minute: int = 60


_BOOL_TRUE_VALUES = {"1", "true", "yes", "on"}


def _parse_bool(value: str, default: bool) -> bool:
    return value.lower() in _BOOL_TRUE_VALUES if value is not None else default


@lru_cache()
def get_settings() -> Settings:
    """从环境变量加载设置，提供简单的覆盖能力。"""

    base = Settings()
    data_dir_env = os.getenv("WEBTK_DATA_DIR")
    cache_env = os.getenv("WEBTK_ENABLE_CACHE")

    return Settings(
        env=os.getenv("WEBTK_ENV", base.env),
        data_dir=Path(data_dir_env) if data_dir_env else base.data_dir,
        enable_cache=_parse_bool(cache_env, base.enable_cache),
        cache_ttl_seconds=int(os.getenv("WEBTK_CACHE_TTL", base.cache_ttl_seconds)),
        request_timeout_seconds=int(
            os.getenv("WEBTK_REQUEST_TIMEOUT", base.request_timeout_seconds)
        ),
        akshare_primary_source=os.getenv(
            "WEBTK_AKSHARE_PRIMARY", base.akshare_primary_source
        ),
        akshare_proxy_pool=os.getenv(
            "WEBTK_AKSHARE_PROXY_POOL", base.akshare_proxy_pool
        ),
        akshare_rate_limit_per_minute=int(
            os.getenv("WEBTK_AKSHARE_RATE_LIMIT", base.akshare_rate_limit_per_minute)
        ),
    )
