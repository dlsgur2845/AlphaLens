"""추천/비추천 종목 선정 및 초보자 친화적 이유 생성 모듈.

6팩터 스코어링 결과(ScoringResult)를 입력받아 복합 기준으로
추천/비추천 여부를 판정하고, 자연스러운 한국어 추천 이유를 생성한다.

API 라우터에서 분리된 순수 비즈니스 로직:
- generate_reason: 스코어링 결과 → 추천/비추천 이유 텍스트
- format_stock_item: 스코어링 결과 → 응답 dict 변환
- derive_sector_outlook: 매크로 데이터 → 섹터별 전망
- derive_key_factors: 매크로 데이터 → 주요 환경 요인
- macro_label: 매크로 점수 → 라벨 텍스트
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.models.schemas import ScoringResult


# ── 추천/비추천 기준 상수 ──

# 추천 기준 (모든 조건 AND)
REC_MIN_TOTAL = 55          # 총점 컷오프
REC_MIN_RISK_GRADES = {"A", "B", "C"}  # 리스크 등급 C 이상
REC_RSI_LOW = 30            # RSI 하한 (과매도 배제)
REC_RSI_HIGH = 70           # RSI 상한 (과매수 배제)
REC_MAX_PBR = 3.0           # PBR 상한 (합리적 밸류에이션)
REC_MIN_SIGNAL = 50         # 시그널 점수 하한 (매수 우위)

# 비추천 기준 (OR 조건 - 하나라도 해당시 비추천)
AVOID_MAX_TOTAL = 45        # 총점 하한
AVOID_MAX_PER = 100         # PER 극단적 고평가
AVOID_HIGH_RISK_GRADES = {"D", "E"}  # 리스크 등급 D 이하
AVOID_RSI_OVERBOUGHT = 75   # 과매수 RSI
AVOID_MAX_SIGNAL = 40       # 매도 시그널 경계


@dataclass
class RecommendationResult:
    """추천 판정 결과."""

    verdict: str                # "추천" | "비추천" | "중립"
    confidence: float           # 판정 확신도 0~100
    reason: str                 # 초보자 친화 한국어 이유
    positive_factors: list[str] = field(default_factory=list)
    negative_factors: list[str] = field(default_factory=list)
    risk_warnings: list[str] = field(default_factory=list)


# ── 내부 헬퍼: 점수 데이터 추출 ──

def _extract_metrics(result: ScoringResult) -> dict:
    """ScoringResult에서 추천 판정에 필요한 지표를 추출."""
    details = result.details or {}
    fund = details.get("fundamental", {})
    tech = details.get("technical", {})
    signal = details.get("signal", {})

    rsi = tech.get("rsi")
    per = fund.get("per")
    pbr = fund.get("pbr")
    roe = fund.get("roe")

    return {
        "total_score": result.total_score,
        "risk_grade": result.risk_grade,
        "signal_score": result.breakdown.signal,
        "tech_score": result.breakdown.technical,
        "fund_score": result.breakdown.fundamental,
        "macro_score": result.breakdown.macro,
        "risk_score": result.breakdown.risk,
        "related_score": result.breakdown.related_momentum,
        "action_label": result.action_label,
        "rsi": rsi,
        "per": per,
        "pbr": pbr,
        "roe": roe,
        "macd": tech.get("macd"),
        "bollinger": tech.get("bollinger_bands"),
        "volume_trend": tech.get("volume_trend"),
        "obv": tech.get("obv"),
        "buy_signals": signal.get("buy_signals", []),
        "sell_signals": signal.get("sell_signals", []),
        "regime": signal.get("regime", "UNKNOWN"),
    }


# ── 추천 판정 ──

def _check_recommended(m: dict) -> tuple[bool, float]:
    """추천 조건 충족 여부와 확신도를 반환."""
    checks = [
        m["total_score"] >= REC_MIN_TOTAL,
        m["risk_grade"] in REC_MIN_RISK_GRADES,
        m["signal_score"] >= REC_MIN_SIGNAL,
    ]

    # RSI: 데이터 없으면 패널티 없음 (패스)
    if m["rsi"] is not None:
        checks.append(REC_RSI_LOW <= m["rsi"] <= REC_RSI_HIGH)

    # PBR: 데이터 없으면 패널티 없음 (패스)
    if m["pbr"] is not None:
        checks.append(m["pbr"] < REC_MAX_PBR)

    passed = sum(checks)
    total = len(checks)

    if passed == total:
        # 확신도: 총점 초과분 + 시그널 초과분 기반
        bonus = (m["total_score"] - REC_MIN_TOTAL) * 0.8
        sig_bonus = (m["signal_score"] - REC_MIN_SIGNAL) * 0.4
        confidence = min(95, 60 + bonus + sig_bonus)
        return True, confidence

    return False, 0.0


def _check_avoid(m: dict) -> tuple[bool, float, list[str]]:
    """비추천 조건 충족 여부, 확신도, 사유 리스트를 반환."""
    reasons: list[str] = []

    # 조건 1: 총점 미달
    if m["total_score"] < AVOID_MAX_TOTAL:
        reasons.append("low_total")

    # 조건 2: PER 극단적 고평가
    if m["per"] is not None and m["per"] > AVOID_MAX_PER:
        reasons.append("extreme_per")

    # 조건 3: 리스크 D 이하 + RSI 과매수
    if m["risk_grade"] in AVOID_HIGH_RISK_GRADES:
        if m["rsi"] is not None and m["rsi"] > AVOID_RSI_OVERBOUGHT:
            reasons.append("high_risk_overbought")
        # 리스크 D/E 단독도 경고 대상
        reasons.append("high_risk")

    # 조건 4: 매도 시그널
    if m["signal_score"] < AVOID_MAX_SIGNAL:
        reasons.append("sell_signal")

    if reasons:
        confidence = min(95, 50 + len(reasons) * 12)
        return True, confidence, reasons

    return False, 0.0, []


# ── 초보자 친화 이유 생성 ──

def _generate_positive_factors(m: dict) -> list[str]:
    """추천 종목의 장점 포인트를 생성."""
    factors: list[str] = []

    # 총점
    if m["total_score"] >= 70:
        factors.append(
            f"종합 점수가 {m['total_score']:.0f}점으로 매우 높습니다"
        )
    elif m["total_score"] >= 55:
        factors.append(
            f"종합 점수가 {m['total_score']:.0f}점으로 양호합니다"
        )

    # 기술적 분석
    if m["tech_score"] >= 60:
        parts = []
        if m["rsi"] is not None and 40 <= m["rsi"] <= 60:
            parts.append(f"RSI(상대강도지수)가 {m['rsi']:.0f}으로 적정 구간")
        macd = m.get("macd")
        if macd and macd.get("bullish"):
            parts.append("MACD(추세지표)가 상승 신호")
        if parts:
            factors.append(
                f"기술적 분석이 긍정적입니다 - {', '.join(parts)}"
            )
        else:
            factors.append(
                f"기술적 분석 점수가 {m['tech_score']:.0f}점으로 좋은 흐름입니다"
            )

    # 펀더멘탈
    fund_parts = []
    if m["per"] is not None and 0 < m["per"] < 15:
        fund_parts.append(f"PER(주가수익비율) {m['per']:.1f}배로 저평가 구간")
    if m["pbr"] is not None and 0 < m["pbr"] < 1.0:
        fund_parts.append(
            f"PBR(주가순자산비율) {m['pbr']:.2f}배로 자산 대비 저평가"
        )
    if m["roe"] is not None and m["roe"] > 10:
        fund_parts.append(
            f"ROE(자기자본이익률) {m['roe']:.1f}%로 수익성 양호"
        )
    if fund_parts:
        factors.append(
            f"기업 가치가 합리적입니다 - {', '.join(fund_parts)}"
        )
    elif m["fund_score"] >= 55:
        factors.append("기업의 재무 지표(PER, PBR 등)가 적정 수준입니다")

    # 시그널
    if m["signal_score"] >= 65:
        factors.append(
            f"매매 시그널이 '{m['action_label']}'로 매수 우위 상황입니다"
        )
    elif m["signal_score"] >= 55:
        factors.append(
            "매매 시그널이 매수 쪽으로 약간 우위를 보이고 있습니다"
        )

    # 리스크
    if m["risk_grade"] in {"A", "B"}:
        grade_text = {"A": "매우 안정적", "B": "안정적"}
        factors.append(
            f"리스크 등급이 {m['risk_grade']}({grade_text[m['risk_grade']]})입니다"
        )

    # 시장 레짐
    if m["regime"] == "BULL":
        factors.append("현재 상승 추세(BULL) 구간으로 시장 분위기가 우호적입니다")

    return factors[:4]  # 최대 4개


def _generate_negative_factors(m: dict, avoid_reasons: list[str]) -> list[str]:
    """비추천 종목의 위험 요소 포인트를 생성."""
    factors: list[str] = []

    if "low_total" in avoid_reasons:
        factors.append(
            f"종합 점수가 {m['total_score']:.0f}점으로 기준(45점) 미만입니다"
        )

    if "extreme_per" in avoid_reasons and m["per"] is not None:
        factors.append(
            f"PER(주가수익비율)이 {m['per']:.1f}배로 극단적 고평가 상태입니다"
        )

    if "high_risk_overbought" in avoid_reasons:
        factors.append(
            f"리스크 등급 {m['risk_grade']}(위험)인데 "
            f"RSI(상대강도지수)가 {m['rsi']:.0f}으로 과매수(과열) 구간입니다"
        )
    elif "high_risk" in avoid_reasons:
        grade_text = {"D": "위험", "E": "매우 위험"}
        factors.append(
            f"리스크 등급이 {m['risk_grade']}"
            f"({grade_text.get(m['risk_grade'], '위험')})입니다 "
            f"- 변동성이 크고 손실 위험이 높습니다"
        )

    if "sell_signal" in avoid_reasons:
        factors.append(
            f"매매 시그널이 '{m['action_label']}'로 매도 우위 상황입니다"
        )

    # 추가 부정 요소 (avoid_reasons에 없어도 경고)
    if m["rsi"] is not None and m["rsi"] > 75 and "high_risk_overbought" not in avoid_reasons:
        factors.append(
            f"RSI(상대강도지수)가 {m['rsi']:.0f}으로 과매수 구간이라 "
            f"단기 하락 가능성이 있습니다"
        )

    if m["regime"] == "BEAR":
        factors.append(
            "현재 하락 추세(BEAR) 구간으로 시장 분위기가 부정적입니다"
        )

    sell_signals = m.get("sell_signals", [])
    if sell_signals:
        factors.append(
            f"매도 신호 감지: {', '.join(sell_signals[:2])}"
        )

    return factors[:4]  # 최대 4개


def _generate_risk_warnings(m: dict) -> list[str]:
    """추천/비추천 공통 리스크 경고를 생성."""
    warnings: list[str] = []

    if m["risk_grade"] in {"D", "E"}:
        warnings.append(
            "이 종목은 변동성이 높아 투자 금액을 소액으로 제한하는 것이 좋습니다"
        )

    if m["rsi"] is not None:
        if m["rsi"] > 70:
            warnings.append(
                "단기 과열 구간이므로 분할 매수(나눠서 사기)를 권장합니다"
            )
        elif m["rsi"] < 30:
            warnings.append(
                "과매도 구간이지만 추가 하락 가능성도 있으므로 주의가 필요합니다"
            )

    vol = m.get("volume_trend")
    if vol and isinstance(vol, dict) and vol.get("volume_ratio", 1.0) < 0.5:
        warnings.append(
            "거래량이 매우 적어 매매 시 원하는 가격에 거래가 어려울 수 있습니다"
        )

    if m["per"] is not None and m["per"] < 0:
        warnings.append(
            "PER이 음수로 현재 적자 상태이므로 재무 상태를 확인하세요"
        )

    return warnings[:3]  # 최대 3개


def _compose_reason(
    verdict: str,
    m: dict,
    pos_factors: list[str],
    neg_factors: list[str],
    risk_warnings: list[str],
) -> str:
    """최종 추천 이유 텍스트를 조합."""
    lines: list[str] = []

    if verdict == "추천":
        main_factors = pos_factors[:3]
        if main_factors:
            lines.append(" ".join(
                f"({i+1}) {f}" for i, f in enumerate(main_factors)
            ))
        if risk_warnings:
            lines.append(f"[참고] {risk_warnings[0]}")

    elif verdict == "비추천":
        main_factors = neg_factors[:3]
        if main_factors:
            lines.append(" ".join(
                f"({i+1}) {f}" for i, f in enumerate(main_factors)
            ))
        if risk_warnings:
            lines.append(f"[주의] {risk_warnings[0]}")

    else:  # 중립
        # 중립은 긍정/부정 섞어서 균형 있게
        if pos_factors:
            lines.append(f"[긍정] {pos_factors[0]}")
        if neg_factors:
            lines.append(f"[유의] {neg_factors[0]}")
        elif risk_warnings:
            lines.append(f"[참고] {risk_warnings[0]}")
        lines.append(
            "현재 뚜렷한 매수/매도 신호가 없어 관망을 추천합니다"
        )

    return " ".join(lines) if lines else "분석 데이터가 부족하여 판단이 어렵습니다."


# ── 공개 API ──

def evaluate_recommendation(result: ScoringResult) -> RecommendationResult:
    """ScoringResult를 분석하여 추천/비추천 판정과 이유를 반환.

    Args:
        result: scoring_service.calculate_score()의 반환값

    Returns:
        RecommendationResult: 판정, 확신도, 한국어 이유, 장단점 리스트
    """
    m = _extract_metrics(result)

    # 1단계: 비추천 먼저 검사 (위험 회피 우선)
    is_avoid, avoid_conf, avoid_reasons = _check_avoid(m)

    # 2단계: 추천 검사
    is_rec, rec_conf = _check_recommended(m)

    # 3단계: 판정 (비추천이 추천보다 우선)
    if is_avoid and not is_rec:
        verdict = "비추천"
        confidence = avoid_conf
    elif is_rec and not is_avoid:
        verdict = "추천"
        confidence = rec_conf
    elif is_rec and is_avoid:
        # 추천과 비추천 동시 해당 → 비추천 사유가 강하면 비추천, 아니면 중립
        if "low_total" in avoid_reasons or "high_risk_overbought" in avoid_reasons:
            verdict = "비추천"
            confidence = avoid_conf * 0.8
        else:
            verdict = "중립"
            confidence = 50.0
    else:
        verdict = "중립"
        confidence = 40.0

    # 4단계: 이유 생성
    pos_factors = _generate_positive_factors(m)
    neg_factors = _generate_negative_factors(m, avoid_reasons if is_avoid else [])
    risk_warnings = _generate_risk_warnings(m)

    reason = _compose_reason(verdict, m, pos_factors, neg_factors, risk_warnings)

    return RecommendationResult(
        verdict=verdict,
        confidence=round(confidence, 1),
        reason=reason,
        positive_factors=pos_factors,
        negative_factors=neg_factors,
        risk_warnings=risk_warnings,
    )


def generate_recommendation_reason(stock_data: dict, is_recommended: bool) -> str:
    """점수 데이터 dict를 기반으로 추천/비추천 이유 텍스트를 생성.

    scoring_service.calculate_score() 결과를 dict로 변환한 데이터와
    추천 여부를 받아 자연스러운 한국어 이유 텍스트를 반환한다.

    Args:
        stock_data: ScoringResult.model_dump() 형태의 dict
        is_recommended: True면 추천, False면 비추천

    Returns:
        한국어 이유 텍스트 문자열
    """
    # dict에서 ScoringResult 복원
    result = ScoringResult(**stock_data)
    rec = evaluate_recommendation(result)

    if is_recommended:
        factors = rec.positive_factors[:3]
        if not factors:
            return f"종합 점수 {result.total_score:.0f}점으로 양호합니다."
        text = " ".join(f"({i+1}) {f}" for i, f in enumerate(factors))
        if rec.risk_warnings:
            text += f" [참고] {rec.risk_warnings[0]}"
        return text
    else:
        factors = rec.negative_factors[:3]
        if not factors:
            return f"종합 점수 {result.total_score:.0f}점으로 기준 미달입니다."
        text = " ".join(f"({i+1}) {f}" for i, f in enumerate(factors))
        if rec.risk_warnings:
            text += f" [주의] {rec.risk_warnings[0]}"
        return text


# ── API 라우터에서 분리된 순수 비즈니스 로직 ──


def generate_reason(scoring_result, is_recommended: bool) -> str:
    """초보자용 추천/비추천 이유 텍스트 자동 생성.

    ScoringResult 객체의 details/breakdown을 직접 참조하여
    간결한 이유 텍스트를 생성한다.
    """
    parts: list[str] = []
    details = scoring_result.details
    bd = scoring_result.breakdown

    per = details.get("fundamental", {}).get("per")
    pbr = details.get("fundamental", {}).get("pbr")
    rsi = details.get("technical", {}).get("rsi")

    if is_recommended:
        if per is not None and per > 0:
            if per < 10:
                parts.append(f"PER {per:.1f}배로 저평가")
            elif per < 15:
                parts.append(f"PER {per:.1f}배로 적정 수준")

        if pbr is not None and 0 < pbr < 1.0:
            parts.append(f"PBR {pbr:.2f}배로 자산가치 대비 저평가")

        if bd.technical >= 65:
            parts.append("기술적 상승 신호 포착")
        elif bd.technical >= 55:
            parts.append("안정적 기술적 흐름")

        if rsi is not None:
            if 40 <= rsi <= 60:
                parts.append(f"RSI {rsi:.0f}으로 안정적 구간")
            elif rsi < 30:
                parts.append(f"RSI {rsi:.0f}으로 과매도 반등 기대")

        if bd.signal >= 65:
            parts.append("매수 시그널 감지")

        if bd.risk >= 60:
            parts.append("리스크 관리 양호")

        if not parts:
            parts.append(f"종합점수 {scoring_result.total_score:.1f}점으로 상위권")

    else:
        if per is not None:
            if per < 0:
                parts.append("적자 기업 (PER 음수)")
            elif per > 50:
                parts.append(f"PER {per:.1f}배 극단적 고평가")
            elif per > 30:
                parts.append(f"PER {per:.1f}배 고평가 구간")

        if pbr is not None and pbr > 3.0:
            parts.append(f"PBR {pbr:.2f}배 고평가")

        if bd.technical <= 35:
            parts.append("기술적 하락 신호")

        if rsi is not None and rsi > 80:
            parts.append(f"RSI {rsi:.0f}으로 과매수 위험")

        if bd.signal <= 35:
            parts.append("매도 시그널 발생")

        if bd.risk <= 35:
            parts.append("리스크 수준 높음")

        if not parts:
            parts.append(f"종합점수 {scoring_result.total_score:.1f}점으로 하위권")

    return ", ".join(parts[:3])


def format_stock_item(scoring_result, is_recommended: bool) -> dict:
    """스코어링 결과를 추천 종목 응답 형식으로 변환."""
    details = scoring_result.details
    rsi = details.get("technical", {}).get("rsi")
    per = details.get("fundamental", {}).get("per")
    pbr = details.get("fundamental", {}).get("pbr")

    overbought_warning = bool(rsi is not None and rsi > 80)

    return {
        "code": scoring_result.code,
        "name": scoring_result.name,
        "total_score": float(scoring_result.total_score),
        "signal": scoring_result.signal,
        "action_label": scoring_result.action_label,
        "risk_grade": scoring_result.risk_grade,
        "breakdown": {
            "technical": float(scoring_result.breakdown.technical),
            "signal": float(scoring_result.breakdown.signal),
            "fundamental": float(scoring_result.breakdown.fundamental),
            "macro": float(scoring_result.breakdown.macro),
            "risk": float(scoring_result.breakdown.risk),
            "related_momentum": float(scoring_result.breakdown.related_momentum),
            "news_sentiment": float(scoring_result.breakdown.news_sentiment),
        },
        "price": details.get("over_market", {}).get("krx_price", 0),
        "per": float(per) if per is not None else None,
        "pbr": float(pbr) if pbr is not None else None,
        "rsi": round(float(rsi), 2) if rsi is not None else None,
        "overbought_warning": overbought_warning if is_recommended else False,
        "reason": generate_reason(scoring_result, is_recommended),
    }


def derive_sector_outlook(macro_score_val: float, macro_details: dict) -> dict:
    """매크로 점수와 세부 데이터로 섹터별 전망 도출."""
    outlook = {}

    us_chg = macro_details.get("nasdaq", {}).get("change_pct", 0)
    usdkrw_chg = macro_details.get("usdkrw", {}).get("change_pct", 0)
    copper_chg = macro_details.get("copper", {}).get("change_pct", 0)
    shanghai_chg = macro_details.get("shanghai", {}).get("change_pct", 0)
    us10y = macro_details.get("us10y", {}).get("price", 4.0)

    # 반도체: 나스닥 강세 + 달러 안정 -> 긍정
    semi_score = (1 if us_chg > 0.3 else -1 if us_chg < -0.3 else 0) + \
                 (1 if usdkrw_chg < 0 else -1 if usdkrw_chg > 0.5 else 0)
    outlook["반도체"] = "긍정" if semi_score > 0 else "부정" if semi_score < 0 else "중립"

    # 금융: 금리 높으면 긍정 (이자 마진)
    outlook["금융"] = "긍정" if us10y > 4.0 else "부정" if us10y < 2.5 else "중립"

    # 바이오: 금리 높으면 부정 (성장주 할인)
    outlook["바이오"] = "부정" if us10y > 4.5 else "긍정" if us10y < 3.0 else "중립"

    # 2차전지: 원자재 + 나스닥
    batt_score = (1 if copper_chg > 1.0 else -1 if copper_chg < -1.0 else 0) + \
                 (1 if us_chg > 0.5 else -1 if us_chg < -0.5 else 0)
    outlook["2차전지"] = "긍정" if batt_score > 0 else "부정" if batt_score < 0 else "중립"

    # 자동차: 환율 약세(원화 약세) -> 수출 긍정
    outlook["자동차"] = "긍정" if usdkrw_chg > 0.2 else "부정" if usdkrw_chg < -0.5 else "중립"

    # 조선/해운: 중국 경기 + 원자재
    ship_score = (1 if shanghai_chg > 0.3 else -1 if shanghai_chg < -0.3 else 0) + \
                 (1 if copper_chg > 0.5 else -1 if copper_chg < -0.5 else 0)
    outlook["조선/해운"] = "긍정" if ship_score > 0 else "부정" if ship_score < 0 else "중립"

    # 유틸리티/통신: 방어주 - 매크로 불안 시 긍정
    outlook["유틸리티/통신"] = "긍정" if macro_score_val < 40 else "부정" if macro_score_val > 65 else "중립"

    return outlook


def derive_market_strategy(macro_score_val: float, macro_details: dict) -> dict:
    """매크로 환경 기반 투자 전략 가이드 도출.

    Returns:
        dict with keys: regime, strategy, allocation, tactics, cautions
    """
    us10y = macro_details.get("us10y", {}).get("price", 4.0)
    us10y_chg = macro_details.get("us10y", {}).get("change_pct", 0)
    vix = macro_details.get("vix", {}).get("price", 20)
    nasdaq_chg = macro_details.get("nasdaq", {}).get("change_pct", 0)
    usdkrw_chg = macro_details.get("usdkrw", {}).get("change_pct", 0)
    copper_chg = macro_details.get("copper", {}).get("change_pct", 0)
    gold_chg = macro_details.get("gold", {}).get("change_pct", 0)
    shanghai_chg = macro_details.get("shanghai", {}).get("change_pct", 0)
    wti_chg = macro_details.get("wti", {}).get("change_pct", 0)

    # 시장 국면 판정
    if macro_score_val >= 65 and vix < 20:
        regime = "강세장"
        regime_desc = "글로벌 매크로 환경이 우호적이고 시장 변동성이 낮습니다"
    elif macro_score_val >= 55:
        regime = "완만한 상승"
        regime_desc = "대체로 긍정적이나 일부 불확실성이 남아있습니다"
    elif macro_score_val >= 45:
        regime = "박스권 횡보"
        regime_desc = "뚜렷한 방향성 없이 등락을 반복하는 구간입니다"
    elif macro_score_val >= 35:
        regime = "약세 전환"
        regime_desc = "매크로 환경이 악화되고 있어 하방 리스크에 주의해야 합니다"
    else:
        regime = "약세장"
        regime_desc = "글로벌 불확실성이 높고 리스크 회피 심리가 강합니다"

    # VIX 공포 오버라이드
    if vix > 30:
        regime = "공포 구간"
        regime_desc = f"VIX {vix:.0f}으로 시장 공포가 극대화된 구간입니다"

    # 전략 방향
    strategy = ""
    allocation = {}  # 자산 배분 비율 제안
    tactics = []     # 구체적 전술
    cautions = []    # 주의사항

    if regime in ("강세장", "완만한 상승"):
        strategy = "적극 매수 (공격적 배분)"
        allocation = {"주식": 70, "현금": 15, "채권": 10, "금": 5}
        tactics.append("성장주·모멘텀 전략 유효 - 기술적 상승 추세 종목 위주 매수")
        tactics.append("분할 매수로 평균 단가를 관리하며 비중 확대")
        if nasdaq_chg > 0.5:
            tactics.append("미국 기술주 강세 → 국내 반도체·IT 수혜 기대")
        if usdkrw_chg > 0.3:
            tactics.append("원화 약세 → 수출주(자동차·조선) 유리")
        if us10y < 3.5:
            tactics.append("저금리 환경 → 성장주·바이오 밸류에이션 부담 완화")

    elif regime == "박스권 횡보":
        strategy = "선별적 매수 (균형 배분)"
        allocation = {"주식": 50, "현금": 25, "채권": 15, "금": 10}
        tactics.append("밸류에이션 저평가 종목 중심 선별 매수")
        tactics.append("배당주·방어주 비중 유지로 안정성 확보")
        tactics.append("박스권 하단 매수, 상단 부분 익절 전략")
        if us10y > 4.0:
            tactics.append("고금리 환경 → 금융주 이자 마진 수혜")

    elif regime == "약세 전환":
        strategy = "방어적 운용 (보수적 배분)"
        allocation = {"주식": 30, "현금": 35, "채권": 20, "금": 15}
        tactics.append("주식 비중 축소, 현금 비중 확대로 유동성 확보")
        tactics.append("고배당·유틸리티·통신 등 방어주 중심 포트폴리오")
        tactics.append("손절 라인을 타이트하게 설정하여 손실 제한")
        if gold_chg > 0:
            tactics.append("금 가격 상승 중 → 안전자산 헤지 비중 유지")

    elif regime in ("약세장", "공포 구간"):
        strategy = "현금 비중 확대 (수비 모드)"
        allocation = {"주식": 15, "현금": 45, "채권": 25, "금": 15}
        tactics.append("신규 매수 자제, 기존 포지션 방어에 집중")
        tactics.append("급락 시 우량주 소량 분할 매수로 장기 관점 접근")
        tactics.append("역발상 투자: 공포 극대화 구간은 중장기 매수 기회")
        if vix > 30:
            tactics.append(f"VIX {vix:.0f} → 극단적 공포 후 반등 가능성 모니터링")

    # 공통 주의사항
    if vix > 25:
        cautions.append(f"변동성 지수(VIX) {vix:.0f}으로 높은 편 - 포지션 규모 축소 권장")
    if abs(usdkrw_chg) > 0.5:
        direction = "급등" if usdkrw_chg > 0 else "급락"
        cautions.append(f"환율 {direction} 중 - 외국인 수급 변동에 주의")
    if us10y > 4.5:
        cautions.append("미국 장기 금리 고공행진 - 성장주 밸류에이션 부담")
    if us10y_chg > 3:
        cautions.append("금리 급등 구간 - 채권 가격 하락, 주식 시장 압박")
    if wti_chg > 3:
        cautions.append("유가 급등 - 인플레이션 우려 및 운송·항공 비용 부담")
    if shanghai_chg < -1.5:
        cautions.append("중국 증시 급락 - 국내 수출주·원자재 관련주 영향 주의")
    if not cautions:
        cautions.append("특별한 리스크 요인은 감지되지 않았습니다")

    # 유망 섹터
    preferred_sectors = []
    if regime in ("강세장", "완만한 상승"):
        if nasdaq_chg > 0.3:
            preferred_sectors.append("반도체")
        if usdkrw_chg > 0.2:
            preferred_sectors.extend(["자동차", "조선/해운"])
        if copper_chg > 0.5:
            preferred_sectors.append("2차전지")
        if us10y < 3.5:
            preferred_sectors.append("바이오")
        if not preferred_sectors:
            preferred_sectors = ["대형 우량주", "IT"]
    elif regime == "박스권 횡보":
        preferred_sectors = ["고배당주", "금융"]
        if us10y > 4.0:
            preferred_sectors.append("보험")
    else:
        preferred_sectors = ["유틸리티/통신", "고배당주", "금"]
        if gold_chg > 0:
            preferred_sectors.append("금 관련주")

    return {
        "regime": regime,
        "regime_desc": regime_desc,
        "strategy": strategy,
        "allocation": allocation,
        "tactics": tactics[:5],
        "cautions": cautions[:4],
        "preferred_sectors": preferred_sectors[:5],
    }


def macro_label(score: float) -> str:
    """매크로 점수를 라벨로 변환."""
    if score >= 70:
        return "강세"
    elif score >= 55:
        return "약간 긍정"
    elif score >= 45:
        return "중립"
    elif score >= 30:
        return "약간 부정"
    return "약세"


def derive_key_factors(macro_details: dict, macro_score_val: float) -> list[str]:
    """매크로 세부 데이터에서 주요 환경 요인 도출."""
    factors = []

    nasdaq = macro_details.get("nasdaq", {})
    if nasdaq.get("change_pct", 0) > 1.0:
        factors.append("미국 기술주 강세")
    elif nasdaq.get("change_pct", 0) < -1.0:
        factors.append("미국 기술주 약세")

    vix = macro_details.get("vix", {})
    if vix.get("price", 20) > 30:
        factors.append("공포지수(VIX) 급등")
    elif vix.get("price", 20) < 15:
        factors.append("시장 변동성 안정")

    usdkrw = macro_details.get("usdkrw", {})
    if usdkrw.get("change_pct", 0) > 0.3:
        factors.append("원화 약세 지속")
    elif usdkrw.get("change_pct", 0) < -0.3:
        factors.append("원화 강세 전환")

    us10y = macro_details.get("us10y", {})
    if us10y.get("price", 4.0) > 4.5:
        factors.append("미국 금리 고공행진")
    elif us10y.get("change_pct", 0) < -2.0:
        factors.append("금리 인하 기대")

    shanghai = macro_details.get("shanghai", {})
    if shanghai.get("change_pct", 0) > 1.0:
        factors.append("중국 경기 회복 신호")
    elif shanghai.get("change_pct", 0) < -1.0:
        factors.append("중국 경기 둔화 우려")

    copper = macro_details.get("copper", {})
    if copper.get("change_pct", 0) > 2.0:
        factors.append("원자재 수요 증가")

    # 최소 1개 보장
    if not factors:
        if macro_score_val >= 55:
            factors.append("글로벌 매크로 환경 양호")
        elif macro_score_val <= 45:
            factors.append("글로벌 매크로 불확실성")
        else:
            factors.append("시장 방향성 미정")

    return factors[:5]
