"""데이터베이스 테이블 모델 정의."""
from sqlalchemy import BigInteger, Column, DateTime, Float, Index, Integer, String
from sqlalchemy.sql import func

from backend.services.database import Base


class PriceHistory(Base):
    """일봉 가격 히스토리."""
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(6), nullable=False, index=True)
    date = Column(DateTime, nullable=False)
    open_price = Column(Float)
    high_price = Column(Float)
    low_price = Column(Float)
    close_price = Column(Float, nullable=False)
    volume = Column(BigInteger, default=0)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_price_code_date", "stock_code", "date", unique=True),
    )


class ScoringSnapshot(Base):
    """스코어링 결과 스냅샷 (백테스팅용)."""
    __tablename__ = "scoring_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(6), nullable=False, index=True)
    scored_at = Column(DateTime, nullable=False, server_default=func.now())
    total_score = Column(Float, nullable=False)
    action_label = Column(String(20))
    tech_score = Column(Float)
    fund_score = Column(Float)
    signal_score = Column(Float)
    macro_score = Column(Float)
    risk_score = Column(Float)
    related_score = Column(Float)
    risk_grade = Column(String(1))
    regime = Column(String(10))

    __table_args__ = (
        Index("ix_scoring_code_date", "stock_code", "scored_at"),
    )
