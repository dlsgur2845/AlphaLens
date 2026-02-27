"""관련기업 탐색 API 엔드포인트."""

from fastapi import APIRouter, Query

from backend.models.schemas import RelatedCompanyResult
from backend.services import related_company_service
from backend.services.stock_service import _fetch_krx_stock_list

router = APIRouter()


@router.get("/{code}", response_model=RelatedCompanyResult)
async def get_related_companies(
    code: str,
    depth: int = Query(2, ge=1, le=3, description="탐색 깊이"),
    max: int = Query(20, ge=1, le=50, description="최대 결과 수"),
):
    """관련기업 BFS 탐색 API."""
    stocks = await _fetch_krx_stock_list()
    name = code
    for s in stocks:
        if s["code"] == code:
            name = s["name"]
            break

    companies = await related_company_service.find_related_companies(
        code, max_depth=depth, max_companies=max
    )
    return RelatedCompanyResult(
        source_code=code,
        source_name=name,
        companies=companies,
        total=len(companies),
    )
