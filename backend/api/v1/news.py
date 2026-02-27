"""뉴스 조회 API 엔드포인트."""

from fastapi import APIRouter, Query

from backend.models.schemas import NewsResult
from backend.services import news_service

router = APIRouter()


@router.get("/{code}", response_model=NewsResult)
async def get_stock_news(
    code: str,
    max_articles: int = Query(20, ge=1, le=50, description="최대 기사 수"),
):
    """종목 관련 뉴스 + 감성분석 API."""
    return await news_service.get_stock_news(code, max_articles=max_articles)
