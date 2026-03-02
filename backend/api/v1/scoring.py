"""스코어링 API 엔드포인트."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.models.schemas import ScoringResult
from backend.services import scoring_service
from backend.utils.auth import verify_api_key
from backend.utils.validators import validate_stock_code

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/{code}", response_model=ScoringResult)
async def get_scoring(code: str):
    """종목 종합 스코어링 API."""
    validate_stock_code(code)
    try:
        return await scoring_service.calculate_score(code)
    except Exception as e:
        logger.exception("스코어링 계산 실패: %s", code)
        raise HTTPException(status_code=500, detail="스코어링 계산 중 오류가 발생했습니다")
