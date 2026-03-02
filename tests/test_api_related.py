"""관련기업 API 통합 테스트."""
import pytest
from unittest.mock import AsyncMock, patch

from backend.models.schemas import RelatedCompany


class TestRelatedAPI:
    """GET /api/v1/related/{code} 테스트."""

    def test_invalid_code_returns_400(self, client):
        resp = client.get("/api/v1/related/abc")
        assert resp.status_code == 400

    def test_short_code_returns_400(self, client):
        resp = client.get("/api/v1/related/12345")
        assert resp.status_code == 400

    def test_valid_code_returns_related(self, client, mock_stock_service, mock_related_service):
        resp = client.get("/api/v1/related/005930")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_code"] == "005930"
        assert "companies" in data
        assert "total" in data

    def test_related_response_fields(self, client, mock_stock_service, mock_related_service):
        resp = client.get("/api/v1/related/005930")
        data = resp.json()
        assert data["source_name"] == "삼성전자"
        assert data["total"] == 1
        company = data["companies"][0]
        assert company["code"] == "000660"
        assert company["name"] == "SK하이닉스"
        assert company["relation_type"] == "동일업종"

    def test_related_with_depth(self, client, mock_stock_service, mock_related_service):
        resp = client.get("/api/v1/related/005930?depth=3")
        assert resp.status_code == 200

    def test_related_with_max(self, client, mock_stock_service, mock_related_service):
        resp = client.get("/api/v1/related/005930?max=10")
        assert resp.status_code == 200

    def test_depth_too_large(self, client):
        resp = client.get("/api/v1/related/005930?depth=5")
        # depth le=3 → 422
        assert resp.status_code == 422

    def test_depth_zero(self, client):
        resp = client.get("/api/v1/related/005930?depth=0")
        # depth ge=1 → 422
        assert resp.status_code == 422

    def test_max_too_large(self, client):
        resp = client.get("/api/v1/related/005930?max=100")
        # max le=50 → 422
        assert resp.status_code == 422

    def test_empty_related_companies(self, client, mock_stock_service):
        with patch(
            "backend.services.related_company_service.find_related_companies",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = client.get("/api/v1/related/005930")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 0
            assert data["companies"] == []
