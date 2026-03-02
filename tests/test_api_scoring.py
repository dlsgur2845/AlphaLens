"""스코어링 API 통합 테스트."""
import pytest
from unittest.mock import AsyncMock, patch


class TestScoringAPI:
    """GET /api/v1/scoring/{code} 테스트."""

    def test_invalid_code_returns_400(self, client):
        resp = client.get("/api/v1/scoring/invalid")
        assert resp.status_code == 400

    def test_short_code_returns_400(self, client):
        resp = client.get("/api/v1/scoring/123")
        assert resp.status_code == 400

    def test_alpha_code_returns_400(self, client):
        resp = client.get("/api/v1/scoring/abcdef")
        assert resp.status_code == 400

    def test_valid_code_returns_scoring(self, client, mock_scoring_service):
        resp = client.get("/api/v1/scoring/005930")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "005930"
        assert data["name"] == "삼성전자"
        assert "total_score" in data
        assert "breakdown" in data
        assert "action_label" in data

    def test_scoring_response_breakdown(self, client, mock_scoring_service):
        resp = client.get("/api/v1/scoring/005930")
        data = resp.json()
        breakdown = data["breakdown"]
        expected_keys = ["technical", "news_sentiment", "fundamental",
                         "related_momentum", "macro", "signal", "risk"]
        for key in expected_keys:
            assert key in breakdown, f"Missing breakdown key: {key}"

    def test_scoring_service_called(self, client, mock_scoring_service):
        client.get("/api/v1/scoring/005930")
        mock_scoring_service["calculate_score"].assert_called_once_with("005930")

    def test_scoring_internal_error(self, client):
        with patch(
            "backend.services.scoring_service.calculate_score",
            new_callable=AsyncMock,
            side_effect=Exception("서비스 오류"),
        ):
            resp = client.get("/api/v1/scoring/005930")
            assert resp.status_code == 500

    def test_scoring_score_range(self, client, mock_scoring_service):
        resp = client.get("/api/v1/scoring/005930")
        data = resp.json()
        assert 0 <= data["total_score"] <= 100

    def test_scoring_has_updated_at(self, client, mock_scoring_service):
        resp = client.get("/api/v1/scoring/005930")
        data = resp.json()
        assert "updated_at" in data
        assert data["updated_at"] != ""

    def test_scoring_risk_grade(self, client, mock_scoring_service):
        resp = client.get("/api/v1/scoring/005930")
        data = resp.json()
        assert data["risk_grade"] in ("A", "B", "C", "D", "E")
