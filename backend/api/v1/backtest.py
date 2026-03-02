"""백테스팅 API 엔드포인트."""

from fastapi import APIRouter, Depends, Query

from backend.services.backtest_service import backtest_engine
from backend.utils.auth import verify_api_key
from backend.utils.validators import validate_stock_code

router = APIRouter(dependencies=[Depends(verify_api_key)])


@router.get("/{code}")
async def run_backtest(
    code: str,
    start_date: str = Query(default="2024-01-01", description="시작일 (YYYY-MM-DD)"),
    end_date: str = Query(default="2025-12-31", description="종료일 (YYYY-MM-DD)"),
):
    """종목 백테스트 실행."""
    validate_stock_code(code)
    result = await backtest_engine.run_backtest(code, start_date, end_date)
    return result


@router.get("/{code}/sensitivity")
async def sensitivity_analysis(
    code: str,
    start_date: str = Query(default="2024-01-01"),
    end_date: str = Query(default="2025-12-31"),
):
    """파라미터 민감도 분석."""
    validate_stock_code(code)
    result = await backtest_engine.sensitivity_analysis(code, start_date, end_date)
    return result


@router.get("/{code}/attribution")
async def attribution_analysis(
    code: str,
    start_date: str = Query(default="2024-01-01"),
    end_date: str = Query(default="2025-12-31"),
):
    """팩터 기여도 분석."""
    validate_stock_code(code)
    result = await backtest_engine.attribution_analysis(code, start_date, end_date)
    return result
