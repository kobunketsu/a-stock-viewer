from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ...core.models import WatchlistMeta, WatchlistSymbol
from ...core.watchlist_service import WatchlistService, get_watchlist_service

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


class CreateWatchlistRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = None
    metadata: Optional[dict] = None


class UpdateWatchlistRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    description: Optional[str] = None
    metadata: Optional[dict] = None


class AddSymbolRequest(BaseModel):
    code: str = Field(..., min_length=1)
    name: Optional[str] = None


@router.get("", response_model=List[WatchlistMeta])
def get_watchlists(
    service: WatchlistService = Depends(get_watchlist_service),
) -> List[WatchlistMeta]:
    return service.list_watchlists()


@router.post("", response_model=WatchlistMeta, status_code=status.HTTP_201_CREATED)
def create_watchlist(
    payload: CreateWatchlistRequest,
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistMeta:
    try:
        return service.create_watchlist(payload.name, payload.description, payload.metadata)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/{name}", response_model=WatchlistMeta)
def update_watchlist(
    name: str,
    payload: UpdateWatchlistRequest,
    service: WatchlistService = Depends(get_watchlist_service),
) -> WatchlistMeta:
    try:
        return service.update_watchlist(
            name=name,
            new_name=payload.name,
            description=payload.description,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        status_code = status.HTTP_400_BAD_REQUEST if str(exc) != "WATCHLIST_NOT_FOUND" else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist(
    name: str,
    service: WatchlistService = Depends(get_watchlist_service),
) -> None:
    try:
        service.delete_watchlist(name)
    except ValueError as exc:
        status_code = status.HTTP_400_BAD_REQUEST if str(exc) != "WATCHLIST_NOT_FOUND" else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/{name}/symbols", response_model=List[WatchlistSymbol])
def list_watchlist_symbols(
    name: str,
    with_quotes: bool = Query(True),
    service: WatchlistService = Depends(get_watchlist_service),
) -> List[WatchlistSymbol]:
    try:
        return service.get_watchlist_symbols(name, with_quotes=with_quotes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{name}/symbols", status_code=status.HTTP_201_CREATED)
def add_symbol_to_watchlist(
    name: str,
    payload: AddSymbolRequest,
    service: WatchlistService = Depends(get_watchlist_service),
) -> None:
    try:
        service.add_symbol(name, payload.code, payload.name)
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_400_BAD_REQUEST
        if detail == "WATCHLIST_NOT_FOUND":
            status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.delete("/{name}/symbols/{code}", status_code=status.HTTP_204_NO_CONTENT)
def remove_symbol_from_watchlist(
    name: str,
    code: str,
    service: WatchlistService = Depends(get_watchlist_service),
) -> None:
    try:
        service.remove_symbol(name, code)
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_400_BAD_REQUEST
        if detail in {"WATCHLIST_NOT_FOUND", "SYMBOL_NOT_IN_LIST"}:
            status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=detail) from exc
