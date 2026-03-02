"""뉴스 API 통합 테스트."""
import pytest
from unittest.mock import AsyncMock, patch

from backend.models.schemas import NewsArticle, NewsResult


class TestNewsAPI:
    """GET /api/v1/news/{code} 테스트."""

    def test_invalid_code_returns_400(self, client):
        resp = client.get("/api/v1/news/abc")
        assert resp.status_code == 400

    def test_short_code_returns_400(self, client):
        resp = client.get("/api/v1/news/123")
        assert resp.status_code == 400

    def test_valid_code_returns_news(self, client, mock_news_service):
        resp = client.get("/api/v1/news/005930")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "005930"
        assert "articles" in data
        assert "overall_sentiment" in data

    def test_news_response_fields(self, client, mock_news_service):
        resp = client.get("/api/v1/news/005930")
        data = resp.json()
        required = ["code", "name", "articles", "overall_sentiment",
                     "overall_label", "positive_count", "negative_count", "neutral_count"]
        for field in required:
            assert field in data, f"Missing field: {field}"

    def test_news_with_max_articles(self, client, mock_news_service):
        resp = client.get("/api/v1/news/005930?max_articles=5")
        assert resp.status_code == 200

    def test_max_articles_too_large(self, client):
        resp = client.get("/api/v1/news/005930?max_articles=100")
        # max_articles le=50 → 422
        assert resp.status_code == 422

    def test_max_articles_zero(self, client):
        resp = client.get("/api/v1/news/005930?max_articles=0")
        # max_articles ge=1 → 422
        assert resp.status_code == 422

    def test_news_with_articles(self, client):
        mock_result = NewsResult(
            code="005930", name="삼성전자",
            articles=[
                NewsArticle(
                    title="삼성전자 실적 호조",
                    link="https://example.com/1",
                    source="뉴스A",
                    date="2026-03-01",
                    summary="실적이 좋습니다",
                    sentiment_score=0.8,
                    sentiment_label="긍정",
                ),
            ],
            overall_sentiment=0.8,
            overall_label="긍정",
            positive_count=1, negative_count=0, neutral_count=0,
        )
        with patch(
            "backend.services.news_service.get_stock_news",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = client.get("/api/v1/news/005930")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["articles"]) == 1
            assert data["articles"][0]["sentiment_label"] == "긍정"

    def test_news_service_called_with_params(self, client, mock_news_service):
        client.get("/api/v1/news/005930?max_articles=10")
        mock_news_service["get_stock_news"].assert_called_once_with(
            "005930", max_articles=10,
        )
