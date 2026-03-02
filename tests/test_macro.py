"""매크로 서비스 순수함수 단위 테스트."""
import pytest

from backend.services.macro_service import (
    SECTOR_MACRO_BETA,
    _china_signal,
    _commodity_signal,
    _fx_signal,
    _rate_signal,
    _rate_spread_signal,
    _us_market_signal,
    get_sector_beta,
)


# ── 헬퍼: 매크로 데이터 dict 생성 ──

def _make_data(**overrides) -> dict:
    """기본 중립 매크로 데이터를 생성하고 overrides로 덮어쓴다.

    사용 예: _make_data(sp500={"change_pct": 2.0})
    """
    base = {
        "sp500": {"price": 5000, "change_pct": 0.0, "change_5d": 0.0},
        "nasdaq": {"price": 16000, "change_pct": 0.0, "change_5d": 0.0},
        "vix": {"price": 20.0, "change_pct": 0.0, "change_5d": 0.0},
        "usdkrw": {"price": 1350, "change_pct": 0.0, "change_5d": 0.0},
        "dxy": {"price": 104, "change_pct": 0.0, "change_5d": 0.0},
        "us10y": {"price": 4.0, "change_pct": 0.0, "change_5d": 0.0},
        "wti": {"price": 75.0, "change_pct": 0.0, "change_5d": 0.0},
        "copper": {"price": 4.5, "change_pct": 0.0, "change_5d": 0.0},
        "gold": {"price": 2000, "change_pct": 0.0, "change_5d": 0.0},
        "shanghai": {"price": 3100, "change_pct": 0.0, "change_5d": 0.0},
    }
    for key, val in overrides.items():
        if key in base:
            base[key] = {**base[key], **val}
        else:
            base[key] = val
    return base


class TestUsMarketSignal:
    """미국 시장 신호 (±15점 범위)."""

    def test_strong_bull(self):
        """SP500 >1%, NASDAQ >1.5%, VIX <15 -> 최대 양수."""
        data = _make_data(
            sp500={"change_pct": 1.5},
            nasdaq={"change_pct": 2.0},
            vix={"price": 13.0},
        )
        score = _us_market_signal(data)
        assert score > 0
        # sp500 +5, nasdaq +4, vix +3, trend 0 = 12
        assert score == 12.0

    def test_strong_bear(self):
        """SP500 <-1%, NASDAQ <-1.5%, VIX >35 -> 최대 음수."""
        data = _make_data(
            sp500={"change_pct": -1.5},
            nasdaq={"change_pct": -2.0},
            vix={"price": 40.0},
        )
        score = _us_market_signal(data)
        assert score < 0
        # sp500 -5, nasdaq -4, vix -5, trend 0 = -14 -> clipped -15 range ok
        assert score == -14.0

    def test_moderate_positive(self):
        """SP500 0.3~1%, NASDAQ 0.5~1.5% -> 중간 양수."""
        data = _make_data(
            sp500={"change_pct": 0.5},
            nasdaq={"change_pct": 1.0},
            vix={"price": 20.0},
        )
        score = _us_market_signal(data)
        # sp500 +3, nasdaq +2, trend 0 = 5
        assert score == 5.0

    def test_neutral_returns_zero(self):
        """모든 지표 중립 -> 0점."""
        data = _make_data()
        score = _us_market_signal(data)
        assert score == 0.0

    def test_score_range(self):
        """어떤 입력이든 ±15 범위 내."""
        extreme = _make_data(
            sp500={"change_pct": 10.0, "change_5d": 20.0},
            nasdaq={"change_pct": 10.0, "change_5d": 20.0},
            vix={"price": 5.0},
        )
        assert -15.0 <= _us_market_signal(extreme) <= 15.0

    def test_high_vix_penalty(self):
        """VIX 25~35 사이 → -3 감점."""
        data = _make_data(vix={"price": 28.0})
        score = _us_market_signal(data)
        assert score == -3.0

    def test_empty_data(self):
        """빈 데이터 -> 0점 (기본값 사용)."""
        score = _us_market_signal({})
        assert score == 0.0

    def test_5d_trend_bonus(self):
        """5일 추세 양수 → trend_bonus 추가."""
        data = _make_data(
            sp500={"change_pct": 0.0, "change_5d": 3.0},
            nasdaq={"change_pct": 0.0, "change_5d": 2.0},
        )
        score = _us_market_signal(data)
        # (3.0 + 2.0) * 0.3 = 1.5
        assert score == pytest.approx(1.5)

    def test_5d_trend_penalty(self):
        """5일 추세 음수 → trend 감점."""
        data = _make_data(
            sp500={"change_pct": 0.0, "change_5d": -5.0},
            nasdaq={"change_pct": 0.0, "change_5d": -5.0},
        )
        score = _us_market_signal(data)
        # (-5.0 + -5.0) * 0.3 = -3.0 (clipped to -3)
        assert score == -3.0

    def test_5d_trend_clipped(self):
        """5일 추세 극단값 → ±3으로 클리핑."""
        data = _make_data(
            sp500={"change_pct": 0.0, "change_5d": 50.0},
            nasdaq={"change_pct": 0.0, "change_5d": 50.0},
        )
        score = _us_market_signal(data)
        # (50 + 50) * 0.3 = 30 → clipped to 3
        assert score == 3.0


class TestFxSignal:
    """환율 신호 (±10점 범위)."""

    def test_won_weakening(self):
        """원화 약세 (USD/KRW 상승) → 음수."""
        data = _make_data(usdkrw={"change_pct": 1.0}, dxy={"change_pct": 0.8})
        score = _fx_signal(data)
        assert score < 0
        # usdkrw +1.0 > 0.5 → -5, dxy +0.8 > 0.5 → -3, trend 0 = -8
        assert score == -8.0

    def test_won_strengthening(self):
        """원화 강세 (USD/KRW 하락) → 양수."""
        data = _make_data(usdkrw={"change_pct": -0.6}, dxy={"change_pct": -0.6})
        score = _fx_signal(data)
        assert score > 0
        # usdkrw -0.6 < -0.5 → +5, dxy -0.6 < -0.5 → +3, trend 0 = 8
        assert score == 8.0

    def test_neutral(self):
        """환율 변동 미미 → 0점."""
        data = _make_data(usdkrw={"change_pct": 0.0}, dxy={"change_pct": 0.0})
        score = _fx_signal(data)
        assert score == 0.0

    def test_score_range(self):
        """어떤 입력이든 ±10 범위 내."""
        extreme = _make_data(
            usdkrw={"change_pct": 5.0, "change_5d": 10.0},
            dxy={"change_pct": 5.0},
        )
        assert -10.0 <= _fx_signal(extreme) <= 10.0

    def test_moderate_weakening(self):
        """USD/KRW 0.2~0.5 → -3점."""
        data = _make_data(usdkrw={"change_pct": 0.3})
        score = _fx_signal(data)
        assert score == -3.0

    def test_empty_data(self):
        """빈 데이터 → 0점."""
        assert _fx_signal({}) == 0.0

    def test_5d_trend_weakening(self):
        """5일간 원화 약세 추세 → 추가 감점."""
        data = _make_data(usdkrw={"change_pct": 0.0, "change_5d": 5.0})
        score = _fx_signal(data)
        # -5.0 * 0.2 = -1.0
        assert score == -1.0

    def test_5d_trend_strengthening(self):
        """5일간 원화 강세 추세 → 보너스."""
        data = _make_data(usdkrw={"change_pct": 0.0, "change_5d": -5.0})
        score = _fx_signal(data)
        # -(-5.0) * 0.2 = 1.0
        assert score == 1.0


class TestRateSignal:
    """금리 신호 (±10점 범위)."""

    def test_high_yield_penalty(self):
        """US10Y >5.0% → -5점."""
        data = _make_data(us10y={"price": 5.5, "change_pct": 0.0})
        score = _rate_signal(data)
        assert score == -5.0

    def test_low_yield_bonus(self):
        """US10Y <3.0% → +3점."""
        data = _make_data(us10y={"price": 2.5, "change_pct": 0.0})
        score = _rate_signal(data)
        assert score == 3.0

    def test_rate_spike(self):
        """금리 급등 (8bp 이상) → 추가 감점."""
        # 4.5% 금리에서 2% 상승 -> bp_change = 4.5 * 2 / 100 = 0.09 > 0.08
        data = _make_data(us10y={"price": 4.5, "change_pct": 2.0})
        score = _rate_signal(data)
        # price 4.5 is not >4.5, not >5.0, not <3.0 → 0, bp 0.09 > 0.08 → -3, trend 0 = -3
        assert score == -3.0

    def test_rate_drop(self):
        """금리 급락 (8bp 이상) → 보너스."""
        data = _make_data(us10y={"price": 4.5, "change_pct": -2.0})
        score = _rate_signal(data)
        # price 4.5 → 0, bp 0.09 > 0.08 → +3, trend 0 = 3
        assert score == 3.0

    def test_neutral_rate(self):
        """금리 4.0% 변동 없음 → 0점."""
        data = _make_data(us10y={"price": 4.0, "change_pct": 0.0})
        score = _rate_signal(data)
        assert score == 0.0

    def test_score_range(self):
        """어떤 입력이든 ±10 범위 내."""
        extreme = _make_data(us10y={"price": 6.0, "change_pct": 5.0, "change_5d": 10.0})
        assert -10.0 <= _rate_signal(extreme) <= 10.0

    def test_empty_data(self):
        """빈 데이터 → 기본값(price=4.0, chg=0) → 0점."""
        assert _rate_signal({}) == 0.0

    def test_5d_rate_rising_trend(self):
        """금리 5일 상승 추세 → 감점."""
        data = _make_data(us10y={"price": 4.0, "change_pct": 0.0, "change_5d": 2.0})
        score = _rate_signal(data)
        # -2.0 * 0.5 = -1.0
        assert score == -1.0

    def test_5d_rate_falling_trend(self):
        """금리 5일 하락 추세 → 보너스."""
        data = _make_data(us10y={"price": 4.0, "change_pct": 0.0, "change_5d": -2.0})
        score = _rate_signal(data)
        # -(-2.0) * 0.5 = 1.0
        assert score == 1.0


class TestCommoditySignal:
    """원자재 신호 (±8점 범위)."""

    def test_copper_surge_positive(self):
        """구리 >2% → +3점."""
        data = _make_data(copper={"change_pct": 3.0}, gold={"change_pct": 0.0})
        score = _commodity_signal(data)
        assert score == 3.0

    def test_gold_surge_negative(self):
        """금 >2% (안전자산 수요) → -2점."""
        data = _make_data(copper={"change_pct": 0.0}, gold={"change_pct": 3.0})
        score = _commodity_signal(data)
        assert score == -2.0

    def test_gold_drop_positive(self):
        """금 <-1% (위험선호) → +2점."""
        data = _make_data(copper={"change_pct": 0.0}, gold={"change_pct": -1.5})
        score = _commodity_signal(data)
        assert score == 2.0

    def test_copper_crash_negative(self):
        """구리 <-2% → -3점."""
        data = _make_data(copper={"change_pct": -3.0}, gold={"change_pct": 0.0})
        score = _commodity_signal(data)
        assert score == -3.0

    def test_neutral(self):
        """변동 없음 → 0점."""
        data = _make_data()
        assert _commodity_signal(data) == 0.0

    def test_score_range(self):
        """어떤 입력이든 ±8 범위 내."""
        extreme = _make_data(
            copper={"change_pct": 10.0, "change_5d": 20.0},
            gold={"change_pct": 10.0},
            wti={"change_pct": 10.0},
        )
        assert -8.0 <= _commodity_signal(extreme) <= 8.0

    def test_empty_data(self):
        """빈 데이터 → 0점."""
        assert _commodity_signal({}) == 0.0

    def test_wti_surge_penalty(self):
        """WTI >3% 급등 → 비용 압박 감점."""
        data = _make_data(wti={"change_pct": 5.0})
        score = _commodity_signal(data)
        # -5.0 * 0.3 = -1.5, clipped to [-2, 2] → -1.5
        assert score == pytest.approx(-1.5)

    def test_wti_crash_bonus(self):
        """WTI <-3% 급락 → 비용 절감 보너스."""
        data = _make_data(wti={"change_pct": -5.0})
        score = _commodity_signal(data)
        # -(-5.0) * 0.3 = 1.5, clipped → 1.5
        assert score == pytest.approx(1.5)

    def test_wti_moderate_no_effect(self):
        """WTI 변동 ≤3% → 영향 없음."""
        data = _make_data(wti={"change_pct": 2.5})
        score = _commodity_signal(data)
        assert score == 0.0

    def test_copper_5d_trend(self):
        """구리 5일 상승 추세 → 경기 선행 보너스."""
        data = _make_data(copper={"change_pct": 0.0, "change_5d": 5.0})
        score = _commodity_signal(data)
        # 5.0 * 0.2 = 1.0
        assert score == 1.0


class TestChinaSignal:
    """중국 시장 신호 (±7점 범위)."""

    def test_strong_rally(self):
        """상해지수 >1% → +4점."""
        data = _make_data(shanghai={"change_pct": 1.5})
        score = _china_signal(data)
        assert score == 4.0

    def test_moderate_up(self):
        """상해지수 0.3~1% → +2점."""
        data = _make_data(shanghai={"change_pct": 0.5})
        score = _china_signal(data)
        assert score == 2.0

    def test_strong_drop(self):
        """상해지수 <-1% → -4점."""
        data = _make_data(shanghai={"change_pct": -1.5})
        score = _china_signal(data)
        assert score == -4.0

    def test_moderate_down(self):
        """상해지수 -0.3~-1% → -2점."""
        data = _make_data(shanghai={"change_pct": -0.5})
        score = _china_signal(data)
        assert score == -2.0

    def test_neutral(self):
        """변동 미미 → 0점."""
        data = _make_data(shanghai={"change_pct": 0.1})
        score = _china_signal(data)
        assert score == 0.0

    def test_score_range(self):
        """어떤 입력이든 ±7 범위 내."""
        extreme = _make_data(shanghai={"change_pct": 10.0})
        assert -7.0 <= _china_signal(extreme) <= 7.0

    def test_empty_data(self):
        """빈 데이터 → 0점."""
        assert _china_signal({}) == 0.0


class TestRateSpreadSignal:
    """한미 금리차 프록시 시그널 (±8점 범위)."""

    def test_high_rate_penalty(self):
        """US10Y >5.0% → -5점."""
        data = _make_data(us10y={"price": 5.5})
        score = _rate_spread_signal(data)
        assert score <= -5.0

    def test_moderate_high_rate(self):
        """US10Y 4.5~5.0% → -3점."""
        data = _make_data(
            us10y={"price": 4.7},
            usdkrw={"price": 1300},  # 환율 낮음 → 이중 압박 없음
        )
        score = _rate_spread_signal(data)
        assert score == -3.0

    def test_low_rate_bonus(self):
        """US10Y <3.5% → +3점."""
        data = _make_data(us10y={"price": 3.0})
        score = _rate_spread_signal(data)
        assert score == 3.0

    def test_slightly_low_rate(self):
        """US10Y 3.5~4.0% → +1점."""
        data = _make_data(us10y={"price": 3.8})
        score = _rate_spread_signal(data)
        assert score == 1.0

    def test_double_pressure(self):
        """고금리 + 원화약세 동반 → 이중 압박."""
        data = _make_data(
            us10y={"price": 4.7},
            usdkrw={"price": 1400},
        )
        score = _rate_spread_signal(data)
        # -3 (금리) + -3 (이중압박) = -6
        assert score == -6.0

    def test_extreme_double_pressure(self):
        """극단적 고금리 + 원화약세 → 클리핑."""
        data = _make_data(
            us10y={"price": 5.5},
            usdkrw={"price": 1450},
        )
        score = _rate_spread_signal(data)
        # -5 (금리) + -3 (이중압박) = -8 (clipped)
        assert score == -8.0

    def test_5d_rate_surge(self):
        """5일간 금리 급등 (>20bp) → 추가 감점."""
        data = _make_data(us10y={"price": 4.2, "change_5d": 25.0})
        score = _rate_spread_signal(data)
        # 4.0~4.5 중립구간, 5d: -25 * 0.05 = -1.25
        assert score == pytest.approx(-1.25)

    def test_5d_rate_drop(self):
        """5일간 금리 급락 (>20bp) → 보너스."""
        data = _make_data(us10y={"price": 4.2, "change_5d": -25.0})
        score = _rate_spread_signal(data)
        # 중립구간, 5d: -(-25) * 0.05 = +1.25
        assert score == pytest.approx(1.25)

    def test_5d_moderate_no_effect(self):
        """5일 변동 ≤20bp → 영향 없음."""
        data = _make_data(us10y={"price": 4.2, "change_5d": 15.0})
        score = _rate_spread_signal(data)
        assert score == 0.0

    def test_neutral_zone(self):
        """US10Y 4.0~4.5%, 환율 안정 → 0점."""
        data = _make_data(
            us10y={"price": 4.2},
            usdkrw={"price": 1300},
        )
        score = _rate_spread_signal(data)
        assert score == 0.0

    def test_score_range(self):
        """어떤 입력이든 ±8 범위 내."""
        extreme = _make_data(
            us10y={"price": 7.0, "change_5d": 50.0},
            usdkrw={"price": 1500},
        )
        assert -8.0 <= _rate_spread_signal(extreme) <= 8.0

    def test_empty_data(self):
        """빈 데이터 → 0점 (price=0은 모든 조건 미충족)."""
        assert _rate_spread_signal({}) == 0.0


class TestGetSectorBeta:
    """섹터별 매크로 민감도 계수."""

    def test_known_sectors(self):
        """등록된 섹터는 정확한 베타 반환."""
        assert get_sector_beta("반도체") == 1.3
        assert get_sector_beta("음식료") == 0.5
        assert get_sector_beta("은행") == 1.0
        assert get_sector_beta("게임") == 0.9

    def test_partial_match(self):
        """부분 문자열 매칭 (예: '삼성전자 반도체')."""
        assert get_sector_beta("삼성전자 반도체") == 1.3

    def test_unknown_sector_default(self):
        """미등록 섹터 → 기본값 0.8."""
        assert get_sector_beta("우주항공") == SECTOR_MACRO_BETA["default"]
        assert get_sector_beta("우주항공") == 0.8

    def test_none_sector_default(self):
        """None 입력 → 기본값."""
        assert get_sector_beta(None) == 0.8

    def test_empty_string_default(self):
        """빈 문자열 → 기본값."""
        assert get_sector_beta("") == 0.8
