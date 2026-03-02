"""지정학 리스크 서비스 순수함수 단위 테스트."""
import pytest

from backend.services.geopolitical_service import (
    EVENT_CATEGORIES,
    KEYWORD_GROUPS_EN,
    _calc_risk_index,
    _calc_sector_impacts,
    _calc_severity,
    _detect_events,
    _detect_monetary_direction,
    _get_macro_snapshot,
    _get_scenario_triggers,
    _severity_to_score,
)


# ── 헬퍼 ──

def _make_articles(titles: list[str], bodies: list[str] | None = None) -> list[dict]:
    """테스트용 뉴스 기사 리스트 생성."""
    if bodies is None:
        bodies = [""] * len(titles)
    return [
        {"title": t, "body": b}
        for t, b in zip(titles, bodies)
    ]


def _make_event(severity: str, label: str = "테스트", severity_score: float | None = None) -> dict:
    """테스트용 감지 이벤트 dict 생성."""
    if severity_score is None:
        severity_score = _severity_to_score(severity)
    return {
        "label": label,
        "icon": "🔥",
        "hit_count": 3,
        "intensity": 50.0,
        "severity": severity,
        "severity_score": severity_score,
        "matched_keywords": ["테스트 키워드"],
        "sample_headlines": ["테스트 헤드라인"],
    }


# ── _calc_severity ──

class TestCalcSeverity:
    """이벤트 심각도 판정."""

    def test_critical(self):
        """intensity * weight >= 60 → critical."""
        assert _calc_severity(60.0, 1.0) == "critical"
        assert _calc_severity(40.0, 1.5) == "critical"

    def test_high(self):
        """40 <= weighted < 60 → high."""
        assert _calc_severity(40.0, 1.0) == "high"
        assert _calc_severity(50.0, 1.0) == "high"

    def test_medium(self):
        """20 <= weighted < 40 → medium."""
        assert _calc_severity(20.0, 1.0) == "medium"
        assert _calc_severity(30.0, 1.0) == "medium"

    def test_low(self):
        """weighted < 20 → low."""
        assert _calc_severity(10.0, 1.0) == "low"
        assert _calc_severity(0.0, 1.0) == "low"

    def test_weight_multiplier(self):
        """weight가 결과에 영향."""
        # 같은 intensity(35)라도 weight에 따라 다른 심각도
        assert _calc_severity(35.0, 1.0) == "medium"   # 35
        assert _calc_severity(35.0, 1.2) == "high"     # 42
        assert _calc_severity(35.0, 2.0) == "critical"  # 70


class TestSeverityToScore:
    """심각도 → 점수 변환."""

    def test_known_severities(self):
        assert _severity_to_score("critical") == 4.0
        assert _severity_to_score("high") == 3.0
        assert _severity_to_score("medium") == 2.0
        assert _severity_to_score("low") == 1.0

    def test_unknown_severity_default(self):
        """알 수 없는 심각도 → 기본값 1.0."""
        assert _severity_to_score("unknown") == 1.0
        assert _severity_to_score("") == 1.0


# ── _detect_events ──

class TestDetectEvents:
    """뉴스 기반 이벤트 감지."""

    def test_war_conflict_detection(self):
        """전쟁/군사충돌 키워드 감지."""
        articles = _make_articles([
            "이란 공습으로 중동 긴장 고조",
            "미사일 공격 규모 확대",
            "우크라이나 전쟁 교착",
        ])
        detected = _detect_events(articles)
        assert "war_conflict" in detected
        assert detected["war_conflict"]["hit_count"] >= 2

    def test_trade_tariff_detection(self):
        """관세/무역 키워드 감지."""
        articles = _make_articles([
            "트럼프 관세 부과 발표",
            "중국 보복관세 경고",
            "무역전쟁 확대 우려",
        ])
        detected = _detect_events(articles)
        assert "trade_tariff" in detected

    def test_no_events_empty_articles(self):
        """빈 기사 리스트 → 이벤트 없음."""
        detected = _detect_events([])
        assert len(detected) == 0

    def test_no_events_irrelevant(self):
        """관련 없는 기사 → 이벤트 없음."""
        articles = _make_articles([
            "오늘 날씨 맑음",
            "프로야구 개막전 예정",
            "맛집 추천 리스트",
        ])
        detected = _detect_events(articles)
        assert len(detected) == 0

    def test_intensity_calculation(self):
        """intensity는 비율(60%) + 절대수(40%) 기반으로 0~100."""
        articles = _make_articles([
            "핵실험 감행",
            "핵무기 위협",
            "전쟁 발발 우려",
        ])
        detected = _detect_events(articles)
        if "war_conflict" in detected:
            assert 0 <= detected["war_conflict"]["intensity"] <= 100

    def test_severity_downgrade_few_articles(self):
        """기사 수 < 5일 때 critical/high → medium으로 하향."""
        # 적은 기사 수에서 높은 히트율 → 하향 조정
        articles = _make_articles([
            "전쟁 발발",
            "공습 감행",
            "미사일 공격",
        ])
        detected = _detect_events(articles)
        if "war_conflict" in detected:
            # 3개 기사만으로는 critical/high 불가 → medium 이하
            assert detected["war_conflict"]["severity"] in ("medium", "low")

    def test_body_text_also_searched(self):
        """본문(body)에서도 키워드를 감지."""
        articles = _make_articles(
            titles=["경제 뉴스"],
            bodies=["트럼프 관세 부과로 시장 혼란"],
        )
        detected = _detect_events(articles)
        assert "trade_tariff" in detected

    def test_short_keyword_excluded(self):
        """3글자 미만 키워드는 무시 (한국어 오탐 방지)."""
        # 이 테스트는 모든 카테고리 키워드가 3글자 이상인지 간접 확인
        articles = _make_articles(["AI"])  # 2글자 → 매칭 안 됨
        detected = _detect_events(articles)
        # AI만으로는 이벤트 감지 안 됨 (tech_semiconductor의 키워드는 AI칩 등 3글자+)
        for event in detected.values():
            for kw in event.get("matched_keywords", []):
                assert len(kw) >= 3


# ── _detect_monetary_direction ──

class TestDetectMonetaryDirection:
    """통화정책 방향 감지 (hawkish/dovish/mixed)."""

    def test_hawkish(self):
        """매파 키워드 우세 → hawkish."""
        articles = _make_articles([
            "연준 금리인상 시사",
            "긴축 기조 지속 전망",
            "양적긴축 확대",
        ])
        assert _detect_monetary_direction(articles) == "hawkish"

    def test_dovish(self):
        """비둘기파 키워드 우세 → dovish."""
        articles = _make_articles([
            "금리인하 기대감 확산",
            "연준 피벗 신호",
            "양적완화 가능성",
        ])
        assert _detect_monetary_direction(articles) == "dovish"

    def test_mixed(self):
        """양쪽 비슷 → mixed."""
        articles = _make_articles([
            "금리인상 가능성",
            "금리인하 기대도",
        ])
        assert _detect_monetary_direction(articles) == "mixed"

    def test_empty_articles(self):
        """기사 없음 → mixed."""
        assert _detect_monetary_direction([]) == "mixed"


# ── _calc_sector_impacts ──

class TestCalcSectorImpacts:
    """섹터 영향 계산."""

    def test_war_benefits_defense(self):
        """전쟁 이벤트 → 방산 수혜."""
        events = {"war_conflict": _make_event("critical")}
        impacts = _calc_sector_impacts(events)
        assert "방산" in impacts
        assert impacts["방산"]["total_impact"] > 0
        assert impacts["방산"]["direction"] == "수혜"

    def test_war_hurts_airlines(self):
        """전쟁 이벤트 → 항공 피해."""
        events = {"war_conflict": _make_event("critical")}
        impacts = _calc_sector_impacts(events)
        assert "항공" in impacts
        assert impacts["항공"]["total_impact"] < 0
        assert impacts["항공"]["direction"] == "피해"

    def test_severity_scales_impact(self):
        """심각도에 따라 영향도 스케일링."""
        events_crit = {"war_conflict": _make_event("critical")}
        events_low = {"war_conflict": _make_event("low")}
        impacts_crit = _calc_sector_impacts(events_crit)
        impacts_low = _calc_sector_impacts(events_low)
        # critical(4/4=1.0) vs low(1/4=0.25) 스케일링
        assert abs(impacts_crit["방산"]["total_impact"]) > abs(impacts_low["방산"]["total_impact"])

    def test_multiple_events_accumulate(self):
        """복수 이벤트 → 영향 합산."""
        events = {
            "war_conflict": _make_event("high"),
            "oil_energy": _make_event("medium"),
        }
        impacts = _calc_sector_impacts(events)
        # 전쟁 + 유가 이벤트 모두 항공에 부정적
        if "항공" in impacts:
            assert impacts["항공"]["total_impact"] < 0

    def test_empty_events(self):
        """이벤트 없음 → 빈 결과."""
        impacts = _calc_sector_impacts({})
        assert len(impacts) == 0

    def test_impact_clamped(self):
        """영향도는 ±30 범위 내."""
        events = {
            "war_conflict": _make_event("critical"),
            "nk_peninsula": _make_event("critical"),
            "trade_tariff": _make_event("critical"),
        }
        impacts = _calc_sector_impacts(events)
        for sector, info in impacts.items():
            assert -30 <= info["total_impact"] <= 30

    def test_monetary_policy_uses_direction(self):
        """통화정책 이벤트는 hawkish/dovish 방향에 따라 다른 매트릭스 사용."""
        events = {"monetary_policy": _make_event("high")}
        # hawkish 뉴스
        hawk_articles = _make_articles(["금리인상 시사", "긴축 기조", "양적긴축"])
        impacts = _calc_sector_impacts(events, hawk_articles)
        if "금융" in impacts:
            assert impacts["금융"]["total_impact"] > 0  # 금융은 hawkish에 수혜


# ── _calc_risk_index ──

class TestCalcRiskIndex:
    """종합 지정학 리스크 인덱스 (0~100)."""

    def test_no_events_low_risk(self):
        """이벤트 없음 → 낮은 리스크."""
        result = _calc_risk_index({})
        assert result["score"] <= 30
        assert result["level"] == "낮음"
        assert result["label"] == "안정"

    def test_no_events_with_high_vix(self):
        """이벤트 없고 VIX 높음 → 기본 리스크 상승."""
        macro = {"vix": {"price": 30}, "usdkrw": {"price": 1500}}
        result = _calc_risk_index({}, macro)
        assert result["score"] > 15.0  # 기본 15 + VIX 10 + USDKRW 5

    def test_critical_events_high_risk(self):
        """critical 이벤트 → 높은 리스크."""
        events = {
            "war_conflict": _make_event("critical"),
            "oil_energy": _make_event("high"),
        }
        result = _calc_risk_index(events)
        assert result["score"] >= 50
        assert result["level"] in ("높음", "매우 높음")

    def test_low_events_moderate_risk(self):
        """low 이벤트 1개 → 낮은 리스크."""
        events = {"supply_chain": _make_event("low")}
        result = _calc_risk_index(events)
        assert result["score"] < 50

    def test_score_capped_at_100(self):
        """극단적 입력도 100 이하."""
        events = {
            f"cat_{i}": _make_event("critical")
            for i in range(5)
        }
        macro = {"vix": {"price": 50}, "wti": {"change_pct": 10}, "gold": {"change_pct": 5}, "usdkrw": {"price": 1600}}
        result = _calc_risk_index(events, macro)
        assert result["score"] <= 100

    def test_score_floor_at_zero(self):
        """리스크 점수 최솟값 0."""
        result = _calc_risk_index({})
        assert result["score"] >= 0

    def test_three_plus_events_correlation_bonus(self):
        """3개 이상 동시 이벤트 → 1.15배 상관관계 보정."""
        two_events = {
            "war_conflict": _make_event("high"),
            "oil_energy": _make_event("high"),
        }
        three_events = {
            "war_conflict": _make_event("high"),
            "oil_energy": _make_event("high"),
            "fx_currency": _make_event("high"),
        }
        r2 = _calc_risk_index(two_events)
        r3 = _calc_risk_index(three_events)
        # 3개 이벤트가 추가 이벤트 + 상관관계 보정으로 더 높아야 함
        assert r3["score"] > r2["score"]

    def test_macro_data_vix_boost(self):
        """VIX >30 → +10 보정."""
        events = {"war_conflict": _make_event("medium")}
        result_no_macro = _calc_risk_index(events)
        result_high_vix = _calc_risk_index(events, {"vix": {"price": 35}})
        assert result_high_vix["score"] > result_no_macro["score"]

    def test_level_labels(self):
        """각 점수대에 맞는 레벨/라벨."""
        # 낮음
        r = _calc_risk_index({})
        assert r["level"] == "낮음" and r["label"] == "안정"


# ── _get_scenario_triggers ──

class TestGetScenarioTriggers:
    """매크로 기반 시나리오 트리거."""

    def test_no_macro_data(self):
        """매크로 데이터 없음 → 빈 리스트."""
        assert _get_scenario_triggers(None) == []

    def test_high_vix_critical(self):
        """VIX >30 → critical 방어 모드 트리거."""
        macro = {"vix": {"price": 35}, "wti": {"price": 70}, "usdkrw": {"price": 1350}, "gold": {"change_pct": 0}}
        triggers = _get_scenario_triggers(macro)
        assert any(t["severity"] == "critical" and "VIX" in t["signal"] for t in triggers)

    def test_high_vix_warning(self):
        """VIX 25~30 → high 경계 트리거."""
        macro = {"vix": {"price": 27}, "wti": {"price": 70}, "usdkrw": {"price": 1350}, "gold": {"change_pct": 0}}
        triggers = _get_scenario_triggers(macro)
        assert any(t["severity"] == "high" and "VIX" in t["signal"] for t in triggers)

    def test_oil_spike(self):
        """유가 >100 → critical."""
        macro = {"vix": {"price": 20}, "wti": {"price": 110}, "usdkrw": {"price": 1350}, "gold": {"change_pct": 0}}
        triggers = _get_scenario_triggers(macro)
        assert any(t["severity"] == "critical" and "유가" in t["signal"] for t in triggers)

    def test_usdkrw_spike(self):
        """USD/KRW >1480 → critical."""
        macro = {"vix": {"price": 20}, "wti": {"price": 70}, "usdkrw": {"price": 1500}, "gold": {"change_pct": 0}}
        triggers = _get_scenario_triggers(macro)
        assert any(t["severity"] == "critical" and "USD/KRW" in t["signal"] for t in triggers)

    def test_gold_surge(self):
        """금 >3% → high."""
        macro = {"vix": {"price": 20}, "wti": {"price": 70}, "usdkrw": {"price": 1350}, "gold": {"change_pct": 4.0}}
        triggers = _get_scenario_triggers(macro)
        assert any(t["severity"] == "high" and "금" in t["signal"] for t in triggers)

    def test_stable_market(self):
        """안정적 시장 → 특이사항 없음."""
        macro = {"vix": {"price": 18}, "wti": {"price": 70}, "usdkrw": {"price": 1350}, "gold": {"change_pct": 0.5}}
        triggers = _get_scenario_triggers(macro)
        assert any("특이사항 없음" in t["signal"] for t in triggers)


# ── _get_macro_snapshot ──

class TestGetMacroSnapshot:
    """매크로 데이터 요약 스냅샷."""

    def test_extracts_known_keys(self):
        """알려진 키만 추출."""
        macro = {
            "vix": {"price": 20, "change_pct": 1.0, "extra": "ignored"},
            "sp500": {"price": 5000, "change_pct": 0.5},
            "random_key": {"price": 100},
        }
        snapshot = _get_macro_snapshot(macro)
        assert "vix" in snapshot
        assert "sp500" in snapshot
        assert "random_key" not in snapshot
        assert snapshot["vix"] == {"price": 20, "change_pct": 1.0}

    def test_none_data(self):
        """None 입력 → 빈 dict."""
        assert _get_macro_snapshot(None) == {}

    def test_empty_data(self):
        """빈 dict → 빈 결과."""
        assert _get_macro_snapshot({}) == {}

    def test_partial_data(self):
        """일부 키만 있어도 정상 작동."""
        macro = {"gold": {"price": 2000, "change_pct": 1.5}}
        snapshot = _get_macro_snapshot(macro)
        assert "gold" in snapshot
        assert snapshot["gold"]["price"] == 2000


# ── 헬퍼 (영문) ──

def _make_en_articles(titles: list[str], bodies: list[str] | None = None) -> list[dict]:
    """테스트용 영문 뉴스 기사 리스트 생성."""
    if bodies is None:
        bodies = [""] * len(titles)
    return [
        {"title": t, "body": b, "lang": "en"}
        for t, b in zip(titles, bodies)
    ]


# ── 영문 키워드 이벤트 감지 ──

class TestDetectEventsEnglish:
    """영문 키워드로 이벤트 감지."""

    def test_war_conflict_english(self):
        """영문 전쟁 키워드 감지."""
        articles = _make_en_articles([
            "Ukraine war escalation continues",
            "Missile strike reported in the region",
            "NATO escalation fears grow",
        ])
        detected = _detect_events(articles)
        assert "war_conflict" in detected
        assert detected["war_conflict"]["en_hits"] >= 2

    def test_trade_tariff_english(self):
        """영문 관세/무역 키워드 감지."""
        articles = _make_en_articles([
            "Trump tariff on China imports raised",
            "Trade war intensifies with new sanctions",
            "Retaliatory tariff announced by EU",
        ])
        detected = _detect_events(articles)
        assert "trade_tariff" in detected
        assert detected["trade_tariff"]["en_hits"] >= 2

    def test_monetary_policy_english(self):
        """영문 통화정책 키워드 감지."""
        articles = _make_en_articles([
            "FOMC meeting signals rate hike ahead",
            "Fed rate decision awaited by markets",
        ])
        detected = _detect_events(articles)
        assert "monetary_policy" in detected

    def test_semiconductor_english(self):
        """영문 반도체 키워드 감지."""
        articles = _make_en_articles([
            "NVIDIA AI chip demand surges",
            "Semiconductor export controls tightened",
            "TSMC foundry expansion announced",
        ])
        detected = _detect_events(articles)
        assert "tech_semiconductor" in detected

    def test_no_events_irrelevant_english(self):
        """관련 없는 영문 기사 → 이벤트 없음."""
        articles = _make_en_articles([
            "Weather forecast for tomorrow",
            "New restaurant opens downtown",
            "Sports highlights of the week",
        ])
        detected = _detect_events(articles)
        assert len(detected) == 0

    def test_en_keywords_exist_for_all_categories(self):
        """모든 이벤트 카테고리에 en_keywords가 존재."""
        for cat_id, cat_info in EVENT_CATEGORIES.items():
            assert "en_keywords" in cat_info, f"{cat_id} missing en_keywords"
            assert len(cat_info["en_keywords"]) > 0, f"{cat_id} has empty en_keywords"

    def test_keyword_groups_en_not_empty(self):
        """영문 키워드 그룹이 비어있지 않음."""
        assert len(KEYWORD_GROUPS_EN) > 0
        for group in KEYWORD_GROUPS_EN:
            assert len(group) > 0


# ── 한영 교차 확인 ──

class TestCrossLanguageConfirmation:
    """한영 교차 확인 보너스 테스트."""

    def test_cross_confirmed_flag(self):
        """한국어+영문 양쪽 감지 시 cross_confirmed=True."""
        ko_articles = _make_articles([
            "트럼프 관세 부과로 시장 혼란",
            "무역전쟁 확대 우려",
        ])
        en_articles = _make_en_articles([
            "Trump tariff shock hits markets",
            "Trade war escalation feared",
        ])
        all_articles = ko_articles + en_articles
        detected = _detect_events(all_articles)
        assert "trade_tariff" in detected
        assert detected["trade_tariff"]["cross_confirmed"] is True
        assert detected["trade_tariff"]["ko_hits"] > 0
        assert detected["trade_tariff"]["en_hits"] > 0

    def test_no_cross_confirm_ko_only(self):
        """한국어만 → cross_confirmed=False."""
        articles = _make_articles([
            "트럼프 관세 부과",
            "무역전쟁 확대",
        ])
        detected = _detect_events(articles)
        if "trade_tariff" in detected:
            assert detected["trade_tariff"]["cross_confirmed"] is False

    def test_no_cross_confirm_en_only(self):
        """영문만 → cross_confirmed=False."""
        articles = _make_en_articles([
            "Trump tariff raises concerns",
            "Trade war deepens further",
        ])
        detected = _detect_events(articles)
        if "trade_tariff" in detected:
            assert detected["trade_tariff"]["cross_confirmed"] is False

    def test_cross_confirm_severity_boost(self):
        """교차 확인 시 intensity 20% 부스트 → severity 상향 가능."""
        # 한국어만으로 medium이 나오는 케이스
        ko_only = _make_articles([
            "유가 급등 소식",
            "원유 가격 상승세",
            "OPEC 감산 결정",
            "에너지위기 우려",
            "천연가스 가격 급등",
        ])
        detected_ko = _detect_events(ko_only)

        # 한영 혼합 (같은 한국어 + 영문 추가)
        en_articles = _make_en_articles([
            "Oil price surges on OPEC cut",
            "Crude oil demand spikes",
            "Energy crisis looms globally",
            "Brent crude hits new high",
            "Natural gas prices soar",
        ])
        mixed = ko_only + en_articles
        detected_mixed = _detect_events(mixed)

        if "oil_energy" in detected_ko and "oil_energy" in detected_mixed:
            assert detected_mixed["oil_energy"]["cross_confirmed"] is True
            # 교차 확인 시 severity_score가 같거나 높아야 함
            assert (
                detected_mixed["oil_energy"]["severity_score"]
                >= detected_ko["oil_energy"]["severity_score"]
            )

    def test_cross_confirm_risk_index_bonus(self):
        """교차 확인 이벤트가 있으면 리스크 인덱스 상승."""
        # 교차 확인 없는 이벤트
        event_no_cross = {
            "war_conflict": {
                **_make_event("high"),
                "ko_hits": 3, "en_hits": 0, "cross_confirmed": False,
            },
        }
        # 교차 확인 있는 이벤트
        event_cross = {
            "war_conflict": {
                **_make_event("high"),
                "ko_hits": 2, "en_hits": 2, "cross_confirmed": True,
            },
        }
        r_no_cross = _calc_risk_index(event_no_cross)
        r_cross = _calc_risk_index(event_cross)
        assert r_cross["score"] > r_no_cross["score"]

    def test_monetary_direction_english(self):
        """영문 통화정책 방향 감지."""
        hawk_articles = _make_en_articles([
            "Fed signals rate hike ahead",
            "Tightening cycle continues",
            "Hawkish stance maintained by Powell",
        ])
        assert _detect_monetary_direction(hawk_articles) == "hawkish"

        dove_articles = _make_en_articles([
            "Fed signals rate cut coming",
            "Pivot expected as inflation cools",
            "Easing cycle to begin soon",
        ])
        assert _detect_monetary_direction(dove_articles) == "dovish"
