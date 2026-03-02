"""지정학 리스크 분석 API 엔드포인트."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.services.geopolitical_service import get_geopolitical_analysis
from backend.utils.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("")
async def get_geopolitical():
    """지정학 리스크 실시간 분석 API.

    글로벌 뉴스에서 이벤트를 자동 감지하고,
    섹터별 영향도와 리스크 인덱스를 계산합니다.
    결과는 15분간 캐시됩니다.
    """
    try:
        return await get_geopolitical_analysis()
    except Exception:
        logger.exception("지정학 분석 실패")
        raise HTTPException(
            status_code=500,
            detail="지정학 리스크 분석 중 오류가 발생했습니다",
        )
