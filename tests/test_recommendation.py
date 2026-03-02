"""추천 로직 순수함수 단위 테스트."""
import pytest

from backend.models.schemas import ScoreBreakdown, ScoringResult
from backend.services.recommendation_logic import (
    RecommendationResult,
    _check_avoid,
    _check_recommended,
    _compose_reason,
    _extract_metrics,
    _generate_negative_factors,
    _generate_positive_factors,
    _generate_risk_warnings,
    derive_key_factors,
    derive_sector_outlook,
    evaluate_recommendation,
    format_stock_item,
    generate_reason,
    macro_label,
)


# ── 헬퍼: ScoringResult 생성 ──

def _make_scoring(
    total_score: float = 60.0,
    risk_grade: str = "C",
    action_label: str = "중립",
    signal: str = "중립",
    tech: float = 55.0,
    fund: float = 55.0,
    sig: float = 55.0,
    macro: float = 50.0,
    risk: float = 50.0,
    related: float = 50.0,
    news: float = 50.0,
    rsi: float | None = 50.0,
    per: float | None = 12.0,
    pbr: float | None = 0.8,
    roe: float | None = 10.0,
    regime: str = "SIDEWAYS",
    buy_signals: list[str] | None = None,
    sell_signals: list[str] | None = None,
) -> ScoringResult:
    """테스트용 ScoringResult 생성."""
    details = {
        "technical": {"rsi": rsi, "macd": None, "bollinger_bands": None, "volume_trend": None, "obv": None},
        "fundamental": {"per": per, "pbr": pbr, "roe": roe},
        "signal": {
            "regime": regime,
            "buy_signals": buy_signals or [],
            "sell_signals": sell_signals or [],
        },
    }
    return ScoringResult(
        code="005930",
        name="삼성전자",
        total_score=total_score,
        signal=signal,
        breakdown=ScoreBreakdown(
            technical=tech,
            news_sentiment=news,
            fundamental=fund,
            related_momentum=related,
            macro=macro,
            signal=sig,
            risk=risk,
        ),
        details=details,
        updated_at="2026-03-02T12:00:00",
        action_label=action_label,
        risk_grade=risk_grade,
        macro_score=macro,
    )


# ── _extract_metrics ──

class TestExtractMetrics:
    """ScoringResult에서 지표 추출."""

    def test_basic_extraction(self):
        result = _make_scoring(total_score=70.0, rsi=55.0, per=10.0)
        m = _extract_metrics(result)
        assert m["total_score"] == 70.0
        assert m["rsi"] == 55.0
        assert m["per"] == 10.0
        assert m["risk_grade"] == "C"

    def test_none_values(self):
        result = _make_scoring(rsi=None, per=None, pbr=None, roe=None)
        m = _extract_metrics(result)
        assert m["rsi"] is None
        assert m["per"] is None
        assert m["pbr"] is None
        assert m["roe"] is None

    def test_signal_fields(self):
        result = _make_scoring(
            regime="BULL",
            buy_signals=["골든크로스"],
            sell_signals=["RSI 과매수"],
        )
        m = _extract_metrics(result)
        assert m["regime"] == "BULL"
        assert "골든크로스" in m["buy_signals"]
        assert "RSI 과매수" in m["sell_signals"]


# ── _check_recommended ──

class TestCheckRecommended:
    """추천 조건 판정."""

    def test_meets_all_criteria(self):
        """모든 조건 충족 → 추천."""
        result = _make_scoring(total_score=65, risk_grade="B", sig=60, rsi=50, pbr=0.8)
        m = _extract_metrics(result)
        is_rec, conf = _check_recommended(m)
        assert is_rec is True
        assert conf > 60

    def test_fails_total_score(self):
        """총점 미달 → 비추천."""
        result = _make_scoring(total_score=50, risk_grade="B", sig=60)
        m = _extract_metrics(result)
        is_rec, conf = _check_recommended(m)
        assert is_rec is False

    def test_fails_risk_grade(self):
        """리스크 등급 D → 비추천."""
        result = _make_scoring(total_score=65, risk_grade="D", sig=60)
        m = _extract_metrics(result)
        is_rec, conf = _check_recommended(m)
        assert is_rec is False

    def test_fails_signal(self):
        """시그널 점수 미달 → 비추천."""
        result = _make_scoring(total_score=65, risk_grade="B", sig=40)
        m = _extract_metrics(result)
        is_rec, conf = _check_recommended(m)
        assert is_rec is False

    def test_rsi_overbought_fails(self):
        """RSI >70 → 비추천."""
        result = _make_scoring(total_score=65, risk_grade="B", sig=60, rsi=75)
        m = _extract_metrics(result)
        is_rec, conf = _check_recommended(m)
        assert is_rec is False

    def test_high_pbr_fails(self):
        """PBR >=3.0 → 비추천."""
        result = _make_scoring(total_score=65, risk_grade="B", sig=60, pbr=3.5)
        m = _extract_metrics(result)
        is_rec, conf = _check_recommended(m)
        assert is_rec is False

    def test_none_rsi_pbr_passes(self):
        """RSI/PBR None → 해당 조건 패스 (패널티 없음)."""
        result = _make_scoring(total_score=65, risk_grade="B", sig=60, rsi=None, pbr=None)
        m = _extract_metrics(result)
        is_rec, conf = _check_recommended(m)
        assert is_rec is True

    def test_confidence_increases_with_score(self):
        """총점/시그널 높을수록 확신도 상승."""
        r1 = _make_scoring(total_score=56, risk_grade="B", sig=51)
        r2 = _make_scoring(total_score=80, risk_grade="A", sig=80)
        _, conf1 = _check_recommended(_extract_metrics(r1))
        _, conf2 = _check_recommended(_extract_metrics(r2))
        assert conf2 > conf1


# ── _check_avoid ──

class TestCheckAvoid:
    """비추천 조건 판정."""

    def test_low_total(self):
        """총점 <45 → 비추천."""
        result = _make_scoring(total_score=40)
        m = _extract_metrics(result)
        is_avoid, conf, reasons = _check_avoid(m)
        assert is_avoid is True
        assert "low_total" in reasons

    def test_extreme_per(self):
        """PER >100 → 비추천."""
        result = _make_scoring(per=120.0)
        m = _extract_metrics(result)
        is_avoid, conf, reasons = _check_avoid(m)
        assert is_avoid is True
        assert "extreme_per" in reasons

    def test_high_risk_overbought(self):
        """리스크 D + RSI >75 → 비추천."""
        result = _make_scoring(risk_grade="D", rsi=80.0)
        m = _extract_metrics(result)
        is_avoid, conf, reasons = _check_avoid(m)
        assert is_avoid is True
        assert "high_risk_overbought" in reasons
        assert "high_risk" in reasons

    def test_sell_signal(self):
        """시그널 <40 → 비추천."""
        result = _make_scoring(sig=35)
        m = _extract_metrics(result)
        is_avoid, conf, reasons = _check_avoid(m)
        assert is_avoid is True
        assert "sell_signal" in reasons

    def test_no_avoid_healthy_stock(self):
        """건강한 종목 → 비추천 아님."""
        result = _make_scoring(total_score=65, risk_grade="B", sig=60, per=12.0, rsi=50.0)
        m = _extract_metrics(result)
        is_avoid, conf, reasons = _check_avoid(m)
        assert is_avoid is False
        assert len(reasons) == 0

    def test_multiple_reasons_higher_confidence(self):
        """복수 비추천 사유 → 확신도 상승."""
        result = _make_scoring(total_score=35, risk_grade="E", sig=30, per=150.0, rsi=85.0)
        m = _extract_metrics(result)
        is_avoid, conf, reasons = _check_avoid(m)
        assert is_avoid is True
        assert len(reasons) >= 3
        assert conf > 70


# ── evaluate_recommendation ──

class TestEvaluateRecommendation:
    """종합 추천 판정 (통합)."""

    def test_strong_recommend(self):
        """명확한 추천 케이스."""
        result = _make_scoring(total_score=70, risk_grade="B", sig=65, rsi=50, pbr=0.8)
        rec = evaluate_recommendation(result)
        assert rec.verdict == "추천"
        assert rec.confidence > 60
        assert len(rec.positive_factors) > 0

    def test_strong_avoid(self):
        """명확한 비추천 케이스."""
        result = _make_scoring(total_score=35, risk_grade="E", sig=30, rsi=80, per=150.0)
        rec = evaluate_recommendation(result)
        assert rec.verdict == "비추천"
        assert rec.confidence > 50
        assert len(rec.negative_factors) > 0

    def test_neutral(self):
        """추천도 비추천도 아닌 → 중립."""
        result = _make_scoring(total_score=50, risk_grade="C", sig=48, rsi=50, per=15.0)
        rec = evaluate_recommendation(result)
        assert rec.verdict == "중립"

    def test_both_rec_and_avoid_with_low_total(self):
        """추천+비추천 동시 해당 + low_total → 비추천 우선."""
        result = _make_scoring(total_score=40, risk_grade="B", sig=55, rsi=50, pbr=0.8)
        rec = evaluate_recommendation(result)
        # low_total 있으면 비추천
        assert rec.verdict == "비추천"

    def test_reason_not_empty(self):
        """항상 이유 텍스트가 존재."""
        result = _make_scoring()
        rec = evaluate_recommendation(result)
        assert len(rec.reason) > 0

    def test_returns_recommendation_result(self):
        """반환 타입 확인."""
        result = _make_scoring()
        rec = evaluate_recommendation(result)
        assert isinstance(rec, RecommendationResult)


# ── _generate_positive_factors ──

class TestGeneratePositiveFactors:
    """추천 장점 포인트 생성."""

    def test_high_total_score(self):
        result = _make_scoring(total_score=75)
        m = _extract_metrics(result)
        factors = _generate_positive_factors(m)
        assert any("매우 높습니다" in f for f in factors)

    def test_good_fundamentals(self):
        result = _make_scoring(per=8.0, pbr=0.5, roe=15.0, fund=60)
        m = _extract_metrics(result)
        factors = _generate_positive_factors(m)
        assert any("PER" in f or "PBR" in f or "ROE" in f for f in factors)

    def test_bull_regime(self):
        result = _make_scoring(regime="BULL")
        m = _extract_metrics(result)
        factors = _generate_positive_factors(m)
        assert any("BULL" in f for f in factors)

    def test_max_four_factors(self):
        """최대 4개 제한."""
        result = _make_scoring(
            total_score=75, tech=65, fund=60, sig=70, risk_grade="A",
            per=8.0, pbr=0.5, roe=15.0, rsi=50, regime="BULL",
        )
        m = _extract_metrics(result)
        factors = _generate_positive_factors(m)
        assert len(factors) <= 4


# ── _generate_negative_factors ──

class TestGenerateNegativeFactors:
    """비추천 위험 요소 생성."""

    def test_low_total(self):
        result = _make_scoring(total_score=35)
        m = _extract_metrics(result)
        factors = _generate_negative_factors(m, ["low_total"])
        assert any("기준" in f and "미만" in f for f in factors)

    def test_extreme_per(self):
        result = _make_scoring(per=150.0)
        m = _extract_metrics(result)
        factors = _generate_negative_factors(m, ["extreme_per"])
        assert any("고평가" in f for f in factors)

    def test_bear_regime(self):
        result = _make_scoring(regime="BEAR")
        m = _extract_metrics(result)
        factors = _generate_negative_factors(m, [])
        assert any("BEAR" in f for f in factors)

    def test_sell_signals_shown(self):
        result = _make_scoring(sell_signals=["데드크로스", "RSI 과매수"])
        m = _extract_metrics(result)
        factors = _generate_negative_factors(m, [])
        assert any("매도 신호" in f for f in factors)

    def test_max_four_factors(self):
        result = _make_scoring(
            total_score=30, per=150, risk_grade="E", sig=20, rsi=85,
            regime="BEAR", sell_signals=["데드크로스"],
        )
        m = _extract_metrics(result)
        factors = _generate_negative_factors(m, ["low_total", "extreme_per", "high_risk", "sell_signal"])
        assert len(factors) <= 4


# ── _generate_risk_warnings ──

class TestGenerateRiskWarnings:
    """리스크 경고 생성."""

    def test_high_risk_grade(self):
        result = _make_scoring(risk_grade="D")
        m = _extract_metrics(result)
        warnings = _generate_risk_warnings(m)
        assert any("소액" in w for w in warnings)

    def test_overbought_rsi(self):
        result = _make_scoring(rsi=75.0)
        m = _extract_metrics(result)
        warnings = _generate_risk_warnings(m)
        assert any("분할 매수" in w for w in warnings)

    def test_oversold_rsi(self):
        result = _make_scoring(rsi=25.0)
        m = _extract_metrics(result)
        warnings = _generate_risk_warnings(m)
        assert any("과매도" in w for w in warnings)

    def test_negative_per(self):
        result = _make_scoring(per=-5.0)
        m = _extract_metrics(result)
        warnings = _generate_risk_warnings(m)
        assert any("적자" in w for w in warnings)

    def test_max_three_warnings(self):
        result = _make_scoring(risk_grade="E", rsi=75, per=-5.0)
        m = _extract_metrics(result)
        warnings = _generate_risk_warnings(m)
        assert len(warnings) <= 3


# ── _compose_reason ──

class TestComposeReason:
    """이유 텍스트 조합."""

    def test_recommend_reason(self):
        reason = _compose_reason(
            "추천", {},
            ["점수 높음", "기술적 양호"],
            [], ["변동성 주의"],
        )
        assert "(1)" in reason
        assert "[참고]" in reason

    def test_avoid_reason(self):
        reason = _compose_reason(
            "비추천", {},
            [], ["총점 미달", "고평가"],
            ["소액 투자 권장"],
        )
        assert "(1)" in reason
        assert "[주의]" in reason

    def test_neutral_reason(self):
        reason = _compose_reason(
            "중립", {},
            ["일부 긍정"],
            ["일부 부정"],
            [],
        )
        assert "관망" in reason

    def test_empty_factors(self):
        """요소 없으면 기본 텍스트."""
        reason = _compose_reason("추천", {}, [], [], [])
        assert len(reason) > 0


# ── generate_reason (API 호출용) ──

class TestGenerateReason:
    """초보자용 추천/비추천 이유 텍스트."""

    def test_recommended_with_low_per(self):
        result = _make_scoring(per=8.0, tech=70, sig=70, risk=65)
        reason = generate_reason(result, is_recommended=True)
        assert "PER" in reason

    def test_recommended_fallback(self):
        """아무 조건도 안 맞으면 기본 텍스트."""
        result = _make_scoring(per=None, pbr=None, rsi=None, tech=40, sig=40, risk=40)
        reason = generate_reason(result, is_recommended=True)
        assert "종합점수" in reason

    def test_not_recommended_high_per(self):
        result = _make_scoring(per=55.0, tech=30, sig=30)
        reason = generate_reason(result, is_recommended=False)
        assert "PER" in reason or "하락" in reason or "매도" in reason

    def test_not_recommended_negative_per(self):
        result = _make_scoring(per=-10.0)
        reason = generate_reason(result, is_recommended=False)
        assert "적자" in reason


# ── format_stock_item ──

class TestFormatStockItem:
    """스코어링 결과 → 응답 dict 변환."""

    def test_basic_format(self):
        result = _make_scoring(total_score=65, risk_grade="B", rsi=55, per=12.0, pbr=0.8)
        item = format_stock_item(result, is_recommended=True)
        assert item["code"] == "005930"
        assert item["name"] == "삼성전자"
        assert item["total_score"] == 65.0
        assert item["risk_grade"] == "B"
        assert "reason" in item

    def test_overbought_warning_recommended(self):
        """추천 + RSI >80 → overbought_warning."""
        result = _make_scoring(rsi=85.0)
        item = format_stock_item(result, is_recommended=True)
        assert item["overbought_warning"] is True

    def test_no_overbought_warning_not_recommended(self):
        """비추천이면 overbought_warning은 항상 False."""
        result = _make_scoring(rsi=85.0)
        item = format_stock_item(result, is_recommended=False)
        assert item["overbought_warning"] is False

    def test_none_values(self):
        """RSI/PER/PBR None → None 유지."""
        result = _make_scoring(rsi=None, per=None, pbr=None)
        item = format_stock_item(result, is_recommended=True)
        assert item["rsi"] is None
        assert item["per"] is None
        assert item["pbr"] is None

    def test_breakdown_included(self):
        """breakdown dict 포함."""
        result = _make_scoring()
        item = format_stock_item(result, is_recommended=True)
        assert "breakdown" in item
        assert "technical" in item["breakdown"]
        assert "signal" in item["breakdown"]


# ── macro_label ──

class TestMacroLabel:
    """매크로 점수 → 라벨 변환."""

    def test_bullish(self):
        assert macro_label(75.0) == "강세"

    def test_slightly_positive(self):
        assert macro_label(60.0) == "약간 긍정"

    def test_neutral(self):
        assert macro_label(50.0) == "중립"

    def test_slightly_negative(self):
        assert macro_label(35.0) == "약간 부정"

    def test_bearish(self):
        assert macro_label(25.0) == "약세"

    def test_boundaries(self):
        """경계값 테스트."""
        assert macro_label(70.0) == "강세"
        assert macro_label(69.9) == "약간 긍정"
        assert macro_label(55.0) == "약간 긍정"
        assert macro_label(54.9) == "중립"
        assert macro_label(45.0) == "중립"
        assert macro_label(44.9) == "약간 부정"
        assert macro_label(30.0) == "약간 부정"
        assert macro_label(29.9) == "약세"


# ── derive_sector_outlook ──

class TestDeriveSectorOutlook:
    """매크로 데이터 → 섹터별 전망."""

    def test_semiconductor_positive(self):
        """나스닥 강세 + 원화 강세 → 반도체 긍정."""
        details = {
            "nasdaq": {"change_pct": 1.0},
            "usdkrw": {"change_pct": -0.5},
            "copper": {"change_pct": 0.0},
            "shanghai": {"change_pct": 0.0},
            "us10y": {"price": 4.0},
        }
        outlook = derive_sector_outlook(55.0, details)
        assert outlook["반도체"] == "긍정"

    def test_finance_positive_high_rates(self):
        """금리 >4.0 → 금융 긍정."""
        details = {
            "nasdaq": {"change_pct": 0.0},
            "usdkrw": {"change_pct": 0.0},
            "copper": {"change_pct": 0.0},
            "shanghai": {"change_pct": 0.0},
            "us10y": {"price": 4.5},
        }
        outlook = derive_sector_outlook(50.0, details)
        assert outlook["금융"] == "긍정"

    def test_bio_negative_high_rates(self):
        """금리 >4.5 → 바이오 부정."""
        details = {
            "nasdaq": {"change_pct": 0.0},
            "usdkrw": {"change_pct": 0.0},
            "copper": {"change_pct": 0.0},
            "shanghai": {"change_pct": 0.0},
            "us10y": {"price": 5.0},
        }
        outlook = derive_sector_outlook(50.0, details)
        assert outlook["바이오"] == "부정"

    def test_utility_positive_weak_macro(self):
        """매크로 약세(40 미만) → 유틸리티/통신 긍정 (방어주)."""
        details = {
            "nasdaq": {"change_pct": 0.0},
            "usdkrw": {"change_pct": 0.0},
            "copper": {"change_pct": 0.0},
            "shanghai": {"change_pct": 0.0},
            "us10y": {"price": 4.0},
        }
        outlook = derive_sector_outlook(35.0, details)
        assert outlook["유틸리티/통신"] == "긍정"

    def test_all_sectors_present(self):
        """모든 예상 섹터가 결과에 포함."""
        details = {
            "nasdaq": {"change_pct": 0.0},
            "usdkrw": {"change_pct": 0.0},
            "copper": {"change_pct": 0.0},
            "shanghai": {"change_pct": 0.0},
            "us10y": {"price": 4.0},
        }
        outlook = derive_sector_outlook(50.0, details)
        expected_sectors = ["반도체", "금융", "바이오", "2차전지", "자동차", "조선/해운", "유틸리티/통신"]
        for sector in expected_sectors:
            assert sector in outlook

    def test_empty_details(self):
        """빈 details → 모든 섹터 중립."""
        outlook = derive_sector_outlook(50.0, {})
        for val in outlook.values():
            assert val in ("긍정", "부정", "중립")


# ── derive_key_factors ──

class TestDeriveKeyFactors:
    """매크로 환경 요인 도출."""

    def test_tech_bullish(self):
        """나스닥 >1% → '미국 기술주 강세'."""
        details = {"nasdaq": {"change_pct": 2.0}}
        factors = derive_key_factors(details, 55.0)
        assert "미국 기술주 강세" in factors

    def test_tech_bearish(self):
        """나스닥 <-1% → '미국 기술주 약세'."""
        details = {"nasdaq": {"change_pct": -2.0}}
        factors = derive_key_factors(details, 45.0)
        assert "미국 기술주 약세" in factors

    def test_vix_high(self):
        """VIX >30 → '공포지수(VIX) 급등'."""
        details = {"vix": {"price": 35}}
        factors = derive_key_factors(details, 40.0)
        assert "공포지수(VIX) 급등" in factors

    def test_vix_low(self):
        """VIX <15 → '시장 변동성 안정'."""
        details = {"vix": {"price": 12}}
        factors = derive_key_factors(details, 60.0)
        assert "시장 변동성 안정" in factors

    def test_won_weakening(self):
        """USD/KRW >0.3% → '원화 약세 지속'."""
        details = {"usdkrw": {"change_pct": 0.5}}
        factors = derive_key_factors(details, 45.0)
        assert "원화 약세 지속" in factors

    def test_china_recovery(self):
        """상해 >1% → '중국 경기 회복 신호'."""
        details = {"shanghai": {"change_pct": 1.5}}
        factors = derive_key_factors(details, 55.0)
        assert "중국 경기 회복 신호" in factors

    def test_copper_demand(self):
        """구리 >2% → '원자재 수요 증가'."""
        details = {"copper": {"change_pct": 3.0}}
        factors = derive_key_factors(details, 55.0)
        assert "원자재 수요 증가" in factors

    def test_empty_details_fallback(self):
        """빈 데이터 → 최소 1개 요인 보장."""
        factors = derive_key_factors({}, 50.0)
        assert len(factors) >= 1
        assert "시장 방향성 미정" in factors

    def test_positive_macro_fallback(self):
        """양호한 매크로 + 특이사항 없음 → 글로벌 매크로 환경 양호."""
        factors = derive_key_factors({}, 60.0)
        assert "글로벌 매크로 환경 양호" in factors

    def test_negative_macro_fallback(self):
        """부정적 매크로 + 특이사항 없음 → 글로벌 매크로 불확실성."""
        factors = derive_key_factors({}, 40.0)
        assert "글로벌 매크로 불확실성" in factors

    def test_max_five_factors(self):
        """최대 5개 제한."""
        details = {
            "nasdaq": {"change_pct": 2.0},
            "vix": {"price": 35},
            "usdkrw": {"change_pct": 0.5},
            "us10y": {"price": 5.0},
            "shanghai": {"change_pct": 1.5},
            "copper": {"change_pct": 3.0},
        }
        factors = derive_key_factors(details, 50.0)
        assert len(factors) <= 5
