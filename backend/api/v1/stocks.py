"""주식 검색/상세 API 엔드포인트."""

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.models.schemas import PriceHistory, StockDetail, StockSearchResult
from backend.services import stock_service
from backend.services.stock_service import _fetch_krx_stock_list
from backend.utils.auth import verify_api_key
from backend.utils.validators import validate_stock_code

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/search", response_model=list[StockSearchResult])
async def search_stocks(
    q: str = Query(..., min_length=1, description="검색어 (종목명 또는 코드)"),
    limit: int = Query(20, ge=1, le=50),
):
    """종목 검색 API."""
    return await stock_service.search_stocks(q, limit)


@router.get("/screener", response_model=list[StockSearchResult])
async def screener(
    market: str = Query("", description="시장 필터 (KOSPI, KOSDAQ, 빈값=전체)"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """간이 종목 스크리너 - 시장별 종목 목록."""
    stocks = await _fetch_krx_stock_list()
    if market:
        stocks = [s for s in stocks if s["market"] == market.upper()]
    total = len(stocks)
    page = stocks[offset:offset + limit]
    return [
        StockSearchResult(code=s["code"], name=s["name"], market=s["market"])
        for s in page
    ]


@router.get("/{code}", response_model=StockDetail)
async def get_stock_detail(code: str):
    """종목 상세정보 조회 API."""
    validate_stock_code(code)
    result = await stock_service.get_stock_detail(code)
    if not result:
        raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")
    return result


@router.get("/{code}/price", response_model=PriceHistory)
async def get_price_history(
    code: str,
    days: int = Query(90, ge=7, le=365),
):
    """가격 히스토리 조회 API."""
    validate_stock_code(code)
    result = await stock_service.get_price_history(code, days)
    if not result:
        raise HTTPException(status_code=404, detail="가격 데이터를 찾을 수 없습니다")
    return result
