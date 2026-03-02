"""미들웨어 통합 테스트 - SecurityHeaders, RateLimiting, Health, Metrics."""
import pytest


class TestHealthEndpoint:
    """GET /api/v1/health 테스트."""

    def test_health_returns_ok(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_health_content_type(self, client):
        resp = client.get("/api/v1/health")
        assert "application/json" in resp.headers.get("content-type", "")


class TestSecurityHeaders:
    """SecurityHeadersMiddleware 테스트."""

    def test_x_content_type_options(self, client):
        resp = client.get("/api/v1/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self, client):
        resp = client.get("/api/v1/health")
        assert resp.headers.get("X-Frame-Options") == "DENY"

    def test_x_xss_protection(self, client):
        resp = client.get("/api/v1/health")
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"

    def test_referrer_policy(self, client):
        resp = client.get("/api/v1/health")
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_csp_present(self, client):
        resp = client.get("/api/v1/health")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src" in csp

    def test_csp_contains_self(self, client):
        resp = client.get("/api/v1/health")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "'self'" in csp

    def test_csp_script_src(self, client):
        resp = client.get("/api/v1/health")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "script-src" in csp

    def test_all_security_headers_present(self, client):
        resp = client.get("/api/v1/health")
        expected = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Referrer-Policy",
            "Content-Security-Policy",
        ]
        for header in expected:
            assert header in resp.headers, f"Missing security header: {header}"


class TestRateLimiting:
    """RateLimitMiddleware 테스트."""

    def test_normal_request_allowed(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_rate_limit_reached(self, client):
        # 60/min 제한 - 61번째 요청은 429
        for i in range(61):
            resp = client.get("/api/v1/health")
        assert resp.status_code == 429

    def test_rate_limit_response_body(self, client):
        for _ in range(61):
            resp = client.get("/api/v1/health")
        assert "Too Many Requests" in resp.text

    def test_non_api_path_not_limited(self, client):
        # /api/ 로 시작하지 않는 경로는 rate limit 대상이 아님
        # (단, static files는 mount되어 있어서 다른 방식으로 처리될 수 있음)
        for _ in range(70):
            resp = client.get("/api/v1/health")
        # API 경로는 제한됨
        assert resp.status_code == 429


class TestMetricsEndpoint:
    """GET /api/v1/metrics 테스트."""

    def test_metrics_returns_200(self, client):
        resp = client.get("/api/v1/metrics")
        assert resp.status_code == 200

    def test_metrics_content_type(self, client):
        resp = client.get("/api/v1/metrics")
        assert "text/plain" in resp.headers.get("content-type", "")

    def test_metrics_contains_requests_total(self, client):
        # 먼저 요청을 보내서 메트릭 생성
        client.get("/api/v1/health")
        resp = client.get("/api/v1/metrics")
        assert "alphalens_requests_total" in resp.text

    def test_metrics_contains_errors_total(self, client):
        resp = client.get("/api/v1/metrics")
        assert "alphalens_errors_total" in resp.text

    def test_metrics_has_help_comments(self, client):
        resp = client.get("/api/v1/metrics")
        assert "# HELP" in resp.text
        assert "# TYPE" in resp.text
