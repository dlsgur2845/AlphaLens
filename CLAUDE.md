# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AlphaLens - Korean stock AI multi-factor scoring platform for capital firms. FastAPI backend + Vanilla JS frontend (no build step). 7-factor model: Technical(23%) + Fundamental(19%) + Signal(19%) + Macro(14%) + Risk(15%) + Related(5%) + News(5%).

## Commands

### Development (Docker)
```bash
# Start dev environment (PostgreSQL + API)
docker compose up -d --build

# Production (PostgreSQL + Qwen LLM + Nginx)
docker compose -f docker-compose.prod.yml up -d --build

# Local without Docker
pip install -r requirements.txt
python run.py  # Uvicorn on :8000, 2 workers
```

### Testing
```bash
# All tests
pytest tests/ -v --tb=short

# Single test file
pytest tests/test_scoring.py -v

# Single test
pytest tests/test_scoring.py::TestScoringService::test_calculate_total_score -v

# With coverage
pytest --cov=backend tests/
```

### Linting
```bash
ruff check backend/ --select E,F,W --ignore E501
```

### Security audit
```bash
pip-audit --strict --desc
```

### QA with gstack (headless browser)
```bash
# Navigate and screenshot
gstack navigate http://localhost:8000
gstack screenshot

# Test specific UI elements
gstack click "[data-nav='recommendations']"
gstack assert-text ".stock-name" "삼성전자"
```

## Architecture

### Backend (`backend/`)
- **Entry**: `main.py` - FastAPI app with lifespan (DB init, scheduler, FinBERT warmup)
- **Config**: `config.py` - pydantic-settings, all config via `.env` (blank = feature disabled)
- **API routes**: `api/v1/` - RESTful endpoints + WebSocket (`ws.py`)
- **Services**: `services/` - Business logic layer. Optional services use `try/except ImportError` for graceful degradation (finbert, signal, macro, risk)
- **Models**: `models/schemas.py` - 100+ Pydantic models; `models/database.py` - SQLAlchemy async models
- **Auth**: `utils/auth.py` - JWT + API Key dual auth (both optional, blank = disabled)

### Frontend (`frontend/`)
- **No build step** - Vanilla JS modules loaded via `<script>` tags in `index.html`
- **Load order matters**: api → storage → chart → score → search → stream → utils → (feature modules) → router → app
- **Router**: `router.js` - Page registry pattern (`_pages` object), hash-based SPA routing. New pages register in `_pages`.
- **Cache busting**: All JS/CSS use `?v=N` query parameter (increment on changes)
- **Charts**: Chart.js 4.4.7 via CDN

### Scoring Engine (`services/scoring_service.py`)
- 7-factor weighted model with sector-specific fundamental standards (13 sectors)
- Risk veto rule: risk score < 25 caps total at 45
- Signal multicollinearity: BB %B correlation discount 15%
- News sentiment: FinBERT 70% + keyword 30% ensemble (falls back to keyword-only)
- 7 action labels: 강력매수(80+) → 강력매도(<5)

### Data Flow
- **Stock data**: Naver Finance scraping + yfinance
- **News**: Web scraping with sentiment analysis
- **Macro**: yfinance + FRED proxied data
- **LLM**: Docker Model Runner (optional, `LLM_BASE_URL` in config)
- **DB**: PostgreSQL async (optional, in-memory cache fallback)
- **Streaming**: SSE for recommendations, WebSocket for real-time updates

### Infrastructure
- **Docker**: Multi-stage build, Python 3.12, PyTorch CPU-only, KR-FinBERT pre-downloaded
- **Nginx**: Reverse proxy, rate limiting (30 req/s), security headers, WebSocket upgrade
- **Scheduler**: APScheduler - stock list refresh 6h, cache cleanup 5min
- **Middleware stack**: CORS → SecurityHeaders → RequestTimeout(45s) → RateLimit

## Key Patterns

- **Progressive rendering**: Frontend fires independent API calls with separate `.then()` handlers
- **Guard pattern**: `StockDetail` uses `_loadRequestId` to prevent stale responses
- **CircuitBreaker**: 3 failures → open state, 120s reset (backend HTTP calls)
- **Cache**: LRU 500 entries with TTL per data type
- **FinBERT**: Lazy-loaded on first request, LRU cache 1000 entries

## Testing Conventions

- `pytest-asyncio` with `asyncio_mode = auto` - no need for `@pytest.mark.asyncio`
- `conftest.py` provides: `sample_closes/volumes` (200-day random data), `bull_closes/bear_closes`, `client` (FastAPI TestClient with mocked deps)
- API tests mock service layer; service tests mock external HTTP calls
- 409 tests across 15 test files (3 skipped)

## Design System
Always read DESIGN.md before making any visual or UI decisions.
All font choices, colors, spacing, and aesthetic direction are defined there.
Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match DESIGN.md.

## Environment

- All config via `.env` (see `.env.example`). Blank values disable features (auth, DB, LLM).
- Docker volumes use `.docker-data/` (gitignored)
- Timezone: `Asia/Seoul`
