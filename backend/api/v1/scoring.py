"""스코어링 API 엔드포인트."""

from fastapi import APIRouter, HTTPException

from backend.models.schemas import ScoringResult
from backend.services import scoring_service

router = APIRouter()


@router.get("/{code}", response_model=ScoringResult)
async def get_scoring(code: str):
    """종목 종합 스코어링 API."""
    try:
        return await scoring_service.calculate_score(code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"스코어링 계산 실패: {str(e)}")
