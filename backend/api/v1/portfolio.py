"""포트폴리오 관리 API."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services.portfolio_service import analyze_portfolio

router = APIRouter()


class HoldingInput(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    quantity: int = Field(..., gt=0)
    avg_price: int = Field(..., gt=0)


class PortfolioRequest(BaseModel):
    holdings: list[HoldingInput] = Field(..., max_length=30)


@router.post("/analyze")
async def portfolio_analyze(req: PortfolioRequest):
    """포트폴리오 종합 분석 - 보유종목별 매수/보유/매도 전략 + 포트폴리오 전체 전략."""
    holdings = [h.model_dump() for h in req.holdings]
    result = await analyze_portfolio(holdings)
    return result
