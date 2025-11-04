from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from ...core.models import QuoteDetail, WatchlistSymbol
from ...core.watchlist_service import WatchlistService, get_watchlist_service

router = APIRouter(tags=["symbols"])


@router.get("/symbols/search", response_model=List[WatchlistSymbol])
def search_symbols(
    q: str = Query(..., min_length=1, description="关键字（代码/名称/拼音）"),
    service: WatchlistService = Depends(get_watchlist_service),
) -> List[WatchlistSymbol]:
    return service.search_symbols(q)


@router.get("/quotes", response_model=Dict[str, QuoteDetail])
def get_quotes(
    codes: str = Query(..., description="逗号分隔的股票代码列表"),
    service: WatchlistService = Depends(get_watchlist_service),
) -> Dict[str, QuoteDetail]:
    code_list = [code.strip() for code in codes.split(",") if code.strip()]
    if not code_list:
        raise HTTPException(status_code=400, detail="codes must not be empty")
    quotes_raw = service.get_quotes(code_list)
    return {code: WatchlistService._build_quote_detail(payload) for code, payload in quotes_raw.items()}
