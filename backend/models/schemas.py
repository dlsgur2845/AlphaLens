from __future__ import annotations

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


class NewsResult(BaseModel):
    code: str
    name: str
    articles: list[NewsArticle]
    overall_sentiment: float
    overall_label: str
    positive_count: int
    negative_count: int
    neutral_count: int


class ScoreBreakdown(BaseModel):
    technical: float  # 0~100
    news_sentiment: float
    fundamental: float
    related_momentum: float


class ScoringResult(BaseModel):
    code: str
    name: str
    total_score: float  # 0~100
    signal: str  # 강한상승, 상승, 중립, 하락, 강한하락
    breakdown: ScoreBreakdown
    details: dict
    updated_at: str
