# AlphaLens

한국 주식 AI 멀티팩터 스코어링 플랫폼

캐피탈사(투자법인)를 위한 중/장기 투자 분석 도구로, 7개 팩터 기반 종합 스코어링과 정확한 매수/매도 타이밍 포착을 목표로 합니다.

## 주요 기능

- **7-팩터 종합 스코어링**: 기술적(23%) + 펀더멘탈(19%) + 시그널(19%) + 리스크(15%) + 매크로(14%) + 관련기업(5%) + 뉴스(5%)
- **KR-FinBERT 감성분석**: 한국어 금융 특화 AI 모델 기반 뉴스 감성 분석 (키워드 30% + FinBERT 70% 앙상블)
- **지정학 리스크 분석**: 9개 카테고리(전쟁, 한반도, 관세, 통화정책 등) 이벤트 감지 및 섹터 영향 매핑
- **백테스팅**: 매매 시뮬레이션, 가중치 민감도 분석, 팩터 기여도 분석
- **실시간 스트리밍**: WebSocket 기반 실시간 스코어링 업데이트
- **7단계 액션 라벨**: 강력매수 / 매수 / 관망(매수우위) / 중립 / 관망(매도우위) / 매도 / 강력매도

## 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | FastAPI, Python 3.12, httpx (비동기), SQLAlchemy + asyncpg |
| Frontend | Vanilla JS, Chart.js, 다크 테마 |
| AI/ML | KR-FinBERT (snunlp/KR-FinBert-SC), PyTorch CPU |
| LLM | Docker Model Runner (Qwen3.5-35B), OpenAI-compatible API |
| Database | PostgreSQL 16 (가격 히스토리, 스코어링 스냅샷) |
| Infra | Docker Compose, Nginx 리버스 프록시 |
| 인증 | JWT + API Key 이중 인증, CORS 화이트리스트, Rate Limit |

## 빠른 시작

### 사전 요구사항

- Docker & Docker Compose
- Git

### 개발 환경 실행

```bash
# 저장소 클론
git clone https://github.com/dlsgur2845/AlphaLens.git
cd AlphaLens

# 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 필요한 값 수정

# 실행
docker compose up -d --build

# 접속: http://localhost:8000
```

### 프로덕션 환경 실행

```bash
docker compose -f docker-compose.prod.yml up -d --build

# 접속: http://localhost (Nginx 리버스 프록시)
```

## 프로젝트 구조

```
AlphaLens/
├── backend/
│   ├── api/v1/              # API 엔드포인트
│   │   ├── stocks.py        # 종목 검색/상세
│   │   ├── scoring.py       # 7-팩터 스코어링
│   │   ├── news.py          # 뉴스 감성분석
│   │   ├── recommendations.py  # 매수/매도 추천
│   │   ├── geopolitical.py  # 지정학 리스크
│   │   ├── backtest.py      # 백테스팅
│   │   ├── related.py       # 관련기업 분석
│   │   └── ws.py            # WebSocket 스트리밍
│   ├── services/            # 비즈니스 로직
│   │   ├── scoring_service.py      # 종합 스코어링 엔진
│   │   ├── signal_service.py       # 매매 시그널 (모멘텀, 평균회귀, 브레이크아웃)
│   │   ├── risk_service.py         # 리스크 평가 (변동성, MDD, VaR/CVaR)
│   │   ├── macro_service.py        # 글로벌 매크로 지표
│   │   ├── finbert_service.py      # KR-FinBERT 감성분석
│   │   ├── geopolitical_service.py # 지정학 리스크 분석
│   │   ├── llm_service.py          # LLM 클라이언트 (Docker Model Runner)
│   │   ├── backtest_service.py     # 백테스팅 엔진
│   │   ├── stock_service.py        # 주식 데이터 (KRX, 네이버)
│   │   ├── news_service.py         # 뉴스 수집
│   │   ├── recommendation_logic.py # 추천 로직
│   │   └── ...
│   ├── utils/
│   │   ├── technical.py     # 기술적 분석 (MA, RSI, MACD, BB, OBV, ATR, ADX)
│   │   ├── sentiment.py     # 감성분석 (FinBERT + 키워드 앙상블)
│   │   ├── auth.py          # JWT/API Key 인증
│   │   └── validators.py    # 입력 검증
│   ├── models/schemas.py    # Pydantic 모델
│   ├── config.py            # 설정 (pydantic-settings)
│   └── main.py              # FastAPI 앱 진입점
├── frontend/
│   ├── index.html           # SPA 메인 페이지
│   ├── css/style.css        # 다크 테마 스타일
│   └── js/
│       ├── app.js           # 메인 앱 로직
│       ├── chart.js         # Chart.js 차트
│       ├── score.js         # 스코어 렌더링
│       ├── api.js           # API 클라이언트
│       ├── search.js        # 종목 검색
│       ├── stream.js        # WebSocket 스트리밍
│       └── storage.js       # 로컬 스토리지 (즐겨찾기, 최근 종목)
├── docs/
│   └── AI_LLM_ROADMAP.md   # AI/LLM 도입 로드맵
├── docker-compose.yml       # 개발 환경
├── docker-compose.prod.yml  # 프로덕션 환경 (PostgreSQL + Nginx + Qwen LLM)
├── Dockerfile               # 멀티스테이지 빌드 (KR-FinBERT 프리로드)
├── requirements.txt
└── .env.example
```

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/v1/stocks/search?q=` | 종목 검색 |
| GET | `/api/v1/stocks/{code}` | 종목 상세 정보 |
| GET | `/api/v1/stocks/{code}/price?days=` | 가격 히스토리 |
| GET | `/api/v1/scoring/{code}` | 7-팩터 종합 스코어링 |
| GET | `/api/v1/news/{code}` | 뉴스 및 감성분석 |
| GET | `/api/v1/related/{code}` | 관련기업 분석 |
| GET | `/api/v1/geopolitical` | 지정학 리스크 |
| GET | `/api/v1/recommendations` | 매수/매도 추천 |
| GET | `/api/v1/backtest/{code}` | 백테스트 시뮬레이션 |
| GET | `/api/v1/backtest/{code}/sensitivity` | 가중치 민감도 분석 |
| GET | `/api/v1/backtest/{code}/attribution` | 팩터 기여도 분석 |
| WS | `/api/v1/ws/{code}` | 실시간 스코어링 스트리밍 |
| GET | `/api/v1/health` | 헬스체크 |
| GET | `/metrics` | 시스템 메트릭 |

## 7-팩터 스코어링 모델

```
종합 점수 = Tech(23%) + Fund(19%) + Signal(19%) + Risk(15%) + Macro(14%) + Related(5%) + News(5%)
```

- **Technical (23%)**: MA(5/20/60/120/200), RSI, MACD, OBV, 볼린저밴드, 거래량, ATR, ADX
- **Fundamental (19%)**: PER(13개 섹터별 기준), PBR, ROE
- **Signal (19%)**: 모멘텀(5/20/60일), 평균회귀(BB %B), 브레이크아웃, 매도 시그널; 레짐 감지; 다중공선성 할인 15%
- **Risk (15%)**: 변동성(10/20/60일 다중 윈도우), MDD(Rolling 60일), VaR/CVaR, 유동성; A~E 등급; 비토 룰(25점 미만 시 총점 45점 캡)
- **Macro (14%)**: 미국 시장, 환율(USD/KRW, DXY), 금리(US10Y, 금리 스프레드), 원자재(Cu, Au, WTI), 중국; 섹터 베타 계수
- **Related (5%)**: 관련기업 모멘텀, 민감도 x0.5, +-3 캡
- **News (5%)**: KR-FinBERT + 키워드 앙상블 (0.7:0.3)

## 환경 변수

`.env.example` 참조. 주요 설정:

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `API_KEY` | API 인증 키 (비어있으면 인증 비활성화) | - |
| `JWT_SECRET` | JWT 시크릿 키 | - |
| `DATABASE_URL` | PostgreSQL 연결 URL (비어있으면 인메모리 캐시) | - |
| `CORS_ORIGINS` | 허용 오리진 | `http://localhost:8000` |
| `RATE_LIMIT_PER_MINUTE` | 분당 요청 제한 | `60` |
| `DEBUG` | 디버그 모드 | `true` |

## 테스트

```bash
# 전체 테스트 실행 (409 tests)
pytest

# 커버리지 포함
pytest --cov=backend
```

## AI/LLM 로드맵

> "정량은 규칙, 정성은 LLM"

- **Phase 1** (완료): KR-FinBERT 감성분석
- **Phase 2a** (계획): 지정학 LLM 보강 (GPT-4o/Claude API)
- **Phase 2b** (계획): 애널리스트 리포트 RAG (LangChain + Vector DB)
- **Phase 3** (계획): 자연어 질의 인터페이스 + 자동 리포트 생성

자세한 내용은 [`docs/AI_LLM_ROADMAP.md`](docs/AI_LLM_ROADMAP.md)를 참조하세요.

## 라이선스

Private Repository - All Rights Reserved
