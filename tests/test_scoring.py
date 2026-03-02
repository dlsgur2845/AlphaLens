"""스코어링 서비스 순수 함수 단위 테스트."""
import pytest

from backend.services.scoring_service import (
    SECTOR_PER_STANDARDS,
    _calc_fundamental_score,
    _get_per_standard,
    _signal_label,
)


class TestSignalLabel:
    """점수 -> 7단계 라벨 매핑 테스트."""

    @pytest.mark.parametrize("score,expected", [
        (95, "강력매수"),
        (80, "강력매수"),
        (72, "매수"),
        (65, "매수"),
        (60, "관망(매수우위)"),
        (55, "관망(매수우위)"),
        (50, "중립"),
        (45, "중립"),
        (40, "관망(매도우위)"),
        (35, "관망(매도우위)"),
        (25, "매도"),
        (20, "매도"),
        (10, "강력매도"),
        (0, "강력매도"),
    ])
    def test_label_mapping(self, score, expected):
        assert _signal_label(score) == expected

    def test_boundary_80(self):
        assert _signal_label(80) == "강력매수"
        assert _signal_label(79.9) == "매수"

    def test_boundary_65(self):
        assert _signal_label(65) == "매수"
        assert _signal_label(64.9) == "관망(매수우위)"

    def test_boundary_20(self):
        assert _signal_label(20) == "매도"
        assert _signal_label(19.9) == "강력매도"


class TestGetPerStandard:
    """섹터별 PER 기준 반환 테스트."""

    def test_known_sector(self):
        std = _get_per_standard("반도체")
        assert std == {"low": 8, "mid": 15, "high": 25}

    def test_bank_sector(self):
        std = _get_per_standard("은행")
        assert std == {"low": 4, "mid": 7, "high": 12}

    def test_none_returns_default(self):
        std = _get_per_standard(None)
        assert std == SECTOR_PER_STANDARDS["default"]

    def test_unknown_returns_default(self):
        std = _get_per_standard("우주항공")
        assert std == SECTOR_PER_STANDARDS["default"]

    def test_partial_match(self):
        """섹터명에 키워드가 포함되면 매칭."""
        std = _get_per_standard("2차전지/배터리")
        assert std == SECTOR_PER_STANDARDS["2차전지"]

    def test_all_sectors_have_required_keys(self):
        for sector, std in SECTOR_PER_STANDARDS.items():
            assert "low" in std, f"{sector} missing 'low'"
            assert "mid" in std, f"{sector} missing 'mid'"
            assert "high" in std, f"{sector} missing 'high'"
            assert std["low"] < std["mid"] < std["high"]


class TestCalcFundamentalScore:
    """펀더멘탈 점수 계산 테스트."""

    def _make_detail(self, per=None, pbr=None, roe=None):
        """간이 detail 객체 생성."""
        class FakeDetail:
            pass
        d = FakeDetail()
        d.per = per
        d.pbr = pbr
        d.roe = roe
        return d

    def test_returns_tuple(self):
        detail = self._make_detail(per=10, pbr=0.8, roe=12)
        result = _calc_fundamental_score(detail)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_score_range(self):
        detail = self._make_detail(per=10, pbr=0.8, roe=12)
        score, details = _calc_fundamental_score(detail)
        assert 0 <= score <= 100

    def test_low_per_high_score(self):
        """저PER -> 높은 점수."""
        detail = self._make_detail(per=5, pbr=0.5, roe=15)
        score, _ = _calc_fundamental_score(detail)
        assert score > 60, f"저PER에서 높은 점수 기대: {score}"

    def test_high_per_low_score(self):
        """고PER -> 낮은 점수."""
        detail = self._make_detail(per=100, pbr=5.0, roe=2)
        score, _ = _calc_fundamental_score(detail)
        assert score < 50, f"고PER에서 낮은 점수 기대: {score}"

    def test_negative_per(self):
        """음수 PER -> 감점."""
        detail = self._make_detail(per=-10, pbr=1.0, roe=5)
        score, _ = _calc_fundamental_score(detail)
        assert score < 50

    def test_none_detail(self):
        """detail이 None이면 기본 50점."""
        score, details = _calc_fundamental_score(None)
        assert score == 50.0
        assert details == {}

    def test_sector_affects_score(self):
        """같은 PER이라도 섹터에 따라 점수가 다를 수 있음."""
        detail = self._make_detail(per=10, pbr=1.0, roe=10)
        score_bank, _ = _calc_fundamental_score(detail, sector="은행")
        score_bio, _ = _calc_fundamental_score(detail, sector="바이오")
        # 은행 PER 10은 고평가, 바이오 PER 10은 저평가
        assert score_bio > score_bank, (
            f"바이오({score_bio}) > 은행({score_bank}) 기대"
        )

    def test_details_contains_per(self):
        detail = self._make_detail(per=15, pbr=1.2, roe=10)
        _, details = _calc_fundamental_score(detail)
        assert "per" in details
        assert details["per"] == 15
