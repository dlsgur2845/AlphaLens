"""주식 API 통합 테스트."""
import pytest
from unittest.mock import AsyncMock, patch

from backend.models.schemas import PriceHistory, PricePoint, StockSearchResult


class TestSearchStocks:
    """GET /api/v1/stocks/search 테스트."""

    def test_search_returns_results(self, client, mock_stock_service):
        resp = client.get("/api/v1/stocks/search?q=삼성")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["code"] == "005930"
        assert data[0]["name"] == "삼성전자"
        mock_stock_service["search"].assert_called_once()

    def test_search_with_limit(self, client, mock_stock_service):
        resp = client.get("/api/v1/stocks/search?q=삼성&limit=5")
        assert resp.status_code == 200
        # limit 파라미터가 전달되는지 확인
        args, kwargs = mock_stock_service["search"].call_args
        assert kwargs.get("limit", args[1] if len(args) > 1 else None) == 5

    def test_search_empty_query_rejected(self, client):
        resp = client.get("/api/v1/stocks/search?q=")
        # FastAPI Query(min_length=1) → 422 Validation Error
        assert resp.status_code == 422

    def test_search_missing_query(self, client):
        resp = client.get("/api/v1/stocks/search")
        # q는 필수 파라미터 → 422
        assert resp.status_code == 422

    def test_search_limit_too_large(self, client):
        resp = client.get("/api/v1/stocks/search?q=삼성&limit=100")
        # limit max=50 → 422
        assert resp.status_code == 422

    def test_search_limit_zero(self, client):
        resp = client.get("/api/v1/stocks/search?q=삼성&limit=0")
        # limit ge=1 → 422
        assert resp.status_code == 422

    def test_search_returns_list_schema(self, client, mock_stock_service):
        resp = client.get("/api/v1/stocks/search?q=삼성")
        data = resp.json()
        for item in data:
            assert "code" in item
            assert "name" in item
            assert "market" in item


class TestStockDetail:
    """GET /api/v1/stocks/{code} 테스트."""

    def test_valid_code_returns_detail(self, client, mock_stock_service):
        resp = client.get("/api/v1/stocks/005930")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "005930"
        assert data["name"] == "삼성전자"
        assert data["price"] == 70000

    def test_invalid_code_format_alpha(self, client):
        resp = client.get("/api/v1/stocks/abcdef")
        assert resp.status_code == 400

    def test_invalid_code_too_short(self, client):
        resp = client.get("/api/v1/stocks/12345")
        assert resp.status_code == 400

    def test_invalid_code_too_long(self, client):
        resp = client.get("/api/v1/stocks/1234567")
        assert resp.status_code == 400

    def test_not_found_stock(self, client):
        with patch(
            "backend.services.stock_service.get_stock_detail",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get("/api/v1/stocks/999999")
            assert resp.status_code == 404

    def test_detail_response_fields(self, client, mock_stock_service):
        resp = client.get("/api/v1/stocks/005930")
        data = resp.json()
        required_fields = ["code", "name", "market", "price", "change", "change_pct", "volume"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


class TestPriceHistory:
    """GET /api/v1/stocks/{code}/price 테스트."""

    def test_valid_code_returns_prices(self, client):
        mock_result = PriceHistory(
            code="005930", name="삼성전자",
            prices=[
                PricePoint(date="2026-03-01", open=69000, high=71000, low=68500, close=70000, volume=10000000),
                PricePoint(date="2026-02-28", open=68000, high=70000, low=67500, close=69000, volume=9000000),
            ],
        )
        with patch(
            "backend.services.stock_service.get_price_history",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = client.get("/api/v1/stocks/005930/price")
            assert resp.status_code == 200
            data = resp.json()
            assert data["code"] == "005930"
            assert len(data["prices"]) == 2

    def test_invalid_code_format(self, client):
        resp = client.get("/api/v1/stocks/abc/price")
        assert resp.status_code == 400

    def test_custom_days_param(self, client):
        with patch(
            "backend.services.stock_service.get_price_history",
            new_callable=AsyncMock,
            return_value=PriceHistory(code="005930", name="삼성전자", prices=[]),
        ):
            resp = client.get("/api/v1/stocks/005930/price?days=30")
            assert resp.status_code == 200

    def test_days_too_small(self, client):
        resp = client.get("/api/v1/stocks/005930/price?days=1")
        # days ge=7 → 422
        assert resp.status_code == 422

    def test_days_too_large(self, client):
        resp = client.get("/api/v1/stocks/005930/price?days=1000")
        # days le=365 → 422
        assert resp.status_code == 422

    def test_price_not_found(self, client):
        with patch(
            "backend.services.stock_service.get_price_history",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get("/api/v1/stocks/005930/price")
            assert resp.status_code == 404
