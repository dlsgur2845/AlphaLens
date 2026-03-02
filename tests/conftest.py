"""AlphaLens 테스트 공통 fixture."""
import pandas as pd
import pytest


# ── 기존 데이터 fixture (단위 테스트용) ──


@pytest.fixture
def sample_closes():
    """200일 샘플 종가 데이터."""
    import numpy as np
    np.random.seed(42)
    base = 50000
    returns = np.random.normal(0.001, 0.02, 200)
    prices = [base]
    for r in returns:
        prices.append(prices[-1] * (1 + r))
    return pd.Series(prices[1:], dtype=float)


@pytest.fixture
def sample_volumes():
    """200일 샘플 거래량 데이터."""
    import numpy as np
    np.random.seed(42)
    return pd.Series(np.random.randint(100000, 1000000, 200), dtype=float)


@pytest.fixture
def bull_closes():
    """상승 추세 종가 데이터."""
    import numpy as np
    base = 50000
    prices = [base * (1 + 0.003 * i + np.random.normal(0, 0.005)) for i in range(200)]
    return pd.Series(prices, dtype=float)


@pytest.fixture
def bear_closes():
    """하락 추세 종가 데이터."""
    import numpy as np
    base = 50000
    prices = [base * (1 - 0.003 * i + np.random.normal(0, 0.005)) for i in range(200)]
    return pd.Series(prices, dtype=float)


# ── API 통합 테스트용 fixture ──


@pytest.fixture
def client():
    """FastAPI TestClient - 외부 의존성 없이 API 테스트용 앱 구성."""
    from contextlib import asynccontextmanager

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from starlette.responses import PlainTextResponse

    from backend.api.v1 import news, related, scoring, stocks
    from backend.main import RateLimitMiddleware, SecurityHeadersMiddleware, _metrics

    @asynccontextmanager
    async def _noop_lifespan(app):
        yield

    test_app = FastAPI(lifespan=_noop_lifespan)

    # 미들웨어 등록 (프로덕션과 동일 순서)
    test_app.add_middleware(SecurityHeadersMiddleware)
    test_app.add_middleware(RateLimitMiddleware, max_requests=60)

    # 헬스/메트릭 엔드포인트
    @test_app.get("/api/v1/health")
    async def health_check():
        return {"status": "ok"}

    @test_app.get("/api/v1/metrics")
    async def metrics():
        lines = []
        lines.append("# HELP alphalens_requests_total Total HTTP requests")
        lines.append("# TYPE alphalens_requests_total counter")
        for path, count in _metrics["requests_total"].items():
            lines.append(f'alphalens_requests_total{{path="{path}"}} {count}')
        lines.append("# HELP alphalens_errors_total Total HTTP errors")
        lines.append("# TYPE alphalens_errors_total counter")
        for path, count in _metrics["errors_total"].items():
            lines.append(f'alphalens_errors_total{{path="{path}"}} {count}')
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain")

    # 라우터 등록 (인증 dependency는 라우터에 포함됨 - dev 모드에서 스킵)
    test_app.include_router(stocks.router, prefix="/api/v1/stocks")
    test_app.include_router(news.router, prefix="/api/v1/news")
    test_app.include_router(scoring.router, prefix="/api/v1/scoring")
    test_app.include_router(related.router, prefix="/api/v1/related")

    with TestClient(test_app) as c:
        yield c


@pytest.fixture
def mock_stock_service():
    """stock_service 주요 함수 모킹."""
    from unittest.mock import AsyncMock, patch

    from backend.models.schemas import StockDetail, StockSearchResult

    mock_search = AsyncMock(return_value=[
        StockSearchResult(code="005930", name="삼성전자", market="KOSPI"),
    ])
    mock_detail = AsyncMock(return_value=StockDetail(
        code="005930", name="삼성전자", market="KOSPI",
        price=70000, change=1000, change_pct=1.45, volume=15000000,
        market_cap=400000000000000, per=12.5, pbr=1.2, roe=15.0,
        sector="반도체",
    ))
    mock_history = AsyncMock(return_value=None)
    mock_name = AsyncMock(return_value="삼성전자")

    with patch("backend.services.stock_service.search_stocks", mock_search), \
         patch("backend.services.stock_service.get_stock_detail", mock_detail), \
         patch("backend.services.stock_service.get_price_history", mock_history), \
         patch("backend.services.stock_service.get_stock_name", mock_name), \
         patch("backend.api.v1.related.get_stock_name", mock_name):
        yield {
            "search": mock_search,
            "detail": mock_detail,
            "history": mock_history,
            "name": mock_name,
        }


@pytest.fixture
def mock_news_service():
    """news_service 모킹."""
    from unittest.mock import AsyncMock, patch

    from backend.models.schemas import NewsResult

    mock_news = AsyncMock(return_value=NewsResult(
        code="005930", name="삼성전자",
        articles=[], overall_sentiment=0.1,
        overall_label="중립",
        positive_count=2, negative_count=1, neutral_count=3,
    ))

    with patch("backend.services.news_service.get_stock_news", mock_news):
        yield {"get_stock_news": mock_news}


@pytest.fixture
def mock_scoring_service():
    """scoring_service 모킹."""
    from unittest.mock import AsyncMock, patch

    from backend.models.schemas import ScoreBreakdown, ScoringResult

    mock_score = AsyncMock(return_value=ScoringResult(
        code="005930", name="삼성전자",
        total_score=72.5, signal="매수",
        breakdown=ScoreBreakdown(
            technical=75.0, news_sentiment=60.0,
            fundamental=70.0, related_momentum=55.0,
            macro=65.0, signal=80.0, risk=60.0,
        ),
        details={"technical": {}, "fundamental": {}},
        updated_at="2026-03-02T12:00:00",
        action_label="매수", risk_grade="B", macro_score=65.0,
    ))

    with patch("backend.services.scoring_service.calculate_score", mock_score):
        yield {"calculate_score": mock_score}


@pytest.fixture
def mock_related_service():
    """related_company_service 모킹."""
    from unittest.mock import AsyncMock, patch

    from backend.models.schemas import RelatedCompany

    mock_related = AsyncMock(return_value=[
        RelatedCompany(
            code="000660", name="SK하이닉스", market="KOSPI",
            relation_type="동일업종", depth=1, change_pct=2.3,
        ),
    ])

    with patch(
        "backend.services.related_company_service.find_related_companies",
        mock_related,
    ):
        yield {"find_related_companies": mock_related}
