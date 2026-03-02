from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class StockSearchResult(BaseModel):
    code: str
    name: str
    market: str  # KOSPI | KOSDAQ


class OverMarketPrice(BaseModel):
    """시간외/대체거래소(NXT) 가격 정보."""
    session_type: str  # AFTER_MARKET | PRE_MARKET
    status: str  # OPEN | CLOSE
    price: int
    change: int
    change_pct: float
    traded_at: str  # ISO datetime


class StockDetail(BaseModel):
    code: str
    name: str
    market: str
    price: int
    change: int
    change_pct: float
    volume: int
    market_cap: int | None = None
    per: float | None = None
    pbr: float | None = None
    roe: float | None = None
    sector: str | None = None
    market_status: str | None = None  # OPEN | CLOSE | PRE_MARKET_OPEN 등
    traded_at: str | None = None  # KRX 최종 거래 시각
    over_market: OverMarketPrice | None = None  # 시간외/NXT 가격


class PricePoint(BaseModel):
    date: str
    open: int
    high: int
    low: int
    close: int
    volume: int


class PriceHistory(BaseModel):
    code: str
    name: str
    prices: list[PricePoint]


class RelatedCompany(BaseModel):
    code: str
    name: str
    market: str
    relation_type: str  # 계열사, 동일업종, 주요주주 등
    depth: int
    change_pct: float | None = None


class RelatedCompanyResult(BaseModel):
    source_code: str
    source_name: str
    companies: list[RelatedCompany]
    total: int


class NewsArticle(BaseModel):
    title: str
    link: str
    source: str
    date: str
    summary: str
    sentiment_score: float  # -1.0 ~ 1.0
    sentiment_label: str  # 긍정, 부정, 중립
    finbert_score: Optional[float] = None  # KR-FinBERT 감성점수 (-1~1)
    finbert_confidence: Optional[float] = None  # KR-FinBERT 신뢰도 (0~1)


class NewsResult(BaseModel):
    code: str
    name: str
    articles: list[NewsArticle]
    overall_sentiment: float
    overall_label: str
    positive_count: int
    negative_count: int
    neutral_count: int


# ── 매크로 스코어 ──

class MacroBreakdown(BaseModel):
    us_market: float = 0.0
    fx: float = 0.0
    rates: float = 0.0
    rate_spread: float = 0.0
    commodities: float = 0.0
    china: float = 0.0
    event_risk: float = 0.0


class MacroScore(BaseModel):
    score: float = 50.0
    breakdown: MacroBreakdown = MacroBreakdown()
    details: dict = {}
    events: list[dict] = []
    updated_at: str = ""


# ── 시그널 스코어 ──

class SignalBreakdown(BaseModel):
    momentum: float = 0.0
    mean_reversion: float = 0.0
    breakout: float = 0.0
    regime: str = "UNKNOWN"
    regime_score: float = 0.0


class SignalScore(BaseModel):
    score: float = 50.0
    action_label: str = "중립"
    breakdown: SignalBreakdown = SignalBreakdown()
    buy_signals: list[str] = []
    sell_signals: list[str] = []


# ── 리스크 스코어 ──

class RiskBreakdown(BaseModel):
    volatility: float = 0.0
    mdd: float = 0.0
    var_cvar: float = 0.0
    liquidity: float = 0.0


class RiskScore(BaseModel):
    score: float = 50.0
    grade: str = "C"
    breakdown: RiskBreakdown = RiskBreakdown()
    position_size_pct: float = 0.0
    atr: float | None = None


# ── 종합 스코어링 ──

class ScoreBreakdown(BaseModel):
    technical: float  # 0~100
    news_sentiment: float
    fundamental: float
    related_momentum: float
    macro: float = 50.0
    signal: float = 50.0
    risk: float = 50.0


class ScoringResult(BaseModel):
    code: str
    name: str
    total_score: float  # 0~100
    signal: str  # 강력매수, 매수, 중립, 매도, 강력매도, 관망, 강한상승(하위호환)
    breakdown: ScoreBreakdown
    details: dict
    updated_at: str
    action_label: str = "중립"  # 7단계 라벨
    risk_grade: str = "C"  # A-E
    macro_score: float = 50.0
