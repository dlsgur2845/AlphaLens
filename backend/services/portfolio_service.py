"""포트폴리오 분석 서비스 - 보유종목 실시간 분석 및 전략 생성."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

from backend.services.scoring_service import calculate_score
from backend.services.stock_service import get_stock_detail
from backend.services.recommendation_logic import evaluate_recommendation


async def analyze_portfolio(holdings: list[dict]) -> dict:
    """포트폴리오 전체 분석.

    Args:
        holdings: [{"code": "005930", "quantity": 10, "avg_price": 70000}, ...]

    Returns:
        dict with per-stock analysis and portfolio-level summary
    """
    if not holdings:
        return {"holdings": [], "summary": _empty_summary()}

    # 병렬로 모든 종목 분석
    tasks = [_analyze_holding(h) for h in holdings]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    analyzed = []
    for i, r in enumerate(results):
        if isinstance(r, BaseException):
            logger.warning("포트폴리오 종목 분석 실패 (%s): %s", holdings[i].get("code"), r)
            analyzed.append(_fallback_holding(holdings[i]))
        else:
            analyzed.append(r)

    summary = _calc_portfolio_summary(analyzed)

    return {
        "holdings": analyzed,
        "summary": summary,
        "updated_at": datetime.now().isoformat(),
    }


async def _analyze_holding(holding: dict) -> dict:
    """개별 보유 종목 분석."""
    code = holding["code"]
    quantity = holding.get("quantity", 0)
    avg_price = holding.get("avg_price", 0)

    # 병렬: 상세 정보 + 스코어링
    detail_task = get_stock_detail(code)
    score_task = calculate_score(code)

    detail, scoring = await asyncio.gather(
        asyncio.wait_for(detail_task, timeout=15.0),
        asyncio.wait_for(score_task, timeout=30.0),
        return_exceptions=True,
    )

    if isinstance(detail, BaseException):
        detail = None
    if isinstance(scoring, BaseException):
        scoring = None

    # 현재가 / 수익률
    current_price = detail.price if detail else 0
    invested = avg_price * quantity
    current_value = current_price * quantity
    pnl = current_value - invested
    pnl_pct = ((current_price / avg_price) - 1) * 100 if avg_price > 0 else 0

    # 추천 판정
    recommendation = None
    if scoring:
        rec = evaluate_recommendation(scoring)
        recommendation = {
            "verdict": rec.verdict,
            "confidence": rec.confidence,
            "reason": rec.reason,
            "positive_factors": rec.positive_factors,
            "negative_factors": rec.negative_factors,
            "risk_warnings": rec.risk_warnings,
        }

    # 세부 전략 생성
    strategy = _generate_holding_strategy(
        scoring=scoring,
        detail=detail,
        pnl_pct=pnl_pct,
        quantity=quantity,
        avg_price=avg_price,
    )

    return {
        "code": code,
        "name": detail.name if detail else code,
        "market": detail.market if detail else "",
        "quantity": quantity,
        "avg_price": avg_price,
        "current_price": current_price,
        "invested": invested,
        "current_value": current_value,
        "pnl": pnl,
        "pnl_pct": round(pnl_pct, 2),
        "change_pct": detail.change_pct if detail else 0,
        "total_score": scoring.total_score if scoring else None,
        "action_label": scoring.action_label if scoring else "분석중",
        "risk_grade": scoring.risk_grade if scoring else "C",
        "signal": scoring.signal if scoring else "분석중",
        "recommendation": recommendation,
        "strategy": strategy,
        "breakdown": {
            "technical": scoring.breakdown.technical if scoring else 50,
            "signal": scoring.breakdown.signal if scoring else 50,
            "fundamental": scoring.breakdown.fundamental if scoring else 50,
            "macro": scoring.breakdown.macro if scoring else 50,
            "risk": scoring.breakdown.risk if scoring else 50,
        },
    }


def _generate_holding_strategy(
    scoring,
    detail,
    pnl_pct: float,
    quantity: int,
    avg_price: int,
) -> dict:
    """보유 종목별 세부 전략 생성."""
    if not scoring:
        return {
            "action": "관망",
            "action_detail": "데이터 부족으로 분석이 불가합니다. 잠시 후 다시 시도해주세요.",
            "tactics": [],
            "target_price": None,
            "stop_loss": None,
        }

    total = scoring.total_score
    risk_grade = scoring.risk_grade
    details = scoring.details or {}
    atr = details.get("risk", {}).get("atr") or details.get("risk", {}).get("breakdown", {}).get("volatility", 0)

    # ATR 기반 목표가/손절가
    risk_detail = details.get("risk", {})
    atr_val = risk_detail.get("atr") or 0
    current_price = detail.price if detail else avg_price

    target_price = None
    stop_loss = None
    if atr_val > 0 and current_price > 0:
        if total >= 65:
            target_price = int(current_price + atr_val * 3)
        elif total >= 55:
            target_price = int(current_price + atr_val * 2)
        else:
            target_price = int(current_price + atr_val * 1.5)
        stop_loss = int(current_price - atr_val * 2)

    # 전략 결정 로직
    action = "관망"
    action_detail = ""
    tactics = []

    if total >= 65 and pnl_pct < 30:
        # 강한 매수 시그널 + 아직 큰 수익 아님 → 추가 매수
        action = "추가매수"
        action_detail = f"종합 점수 {total:.0f}점으로 매수 구간입니다."
        tactics.append("현재가 기준 분할 매수 (2~3회 나눠서)")
        if risk_grade in ("A", "B"):
            tactics.append("리스크 안정적 → 비중 확대 가능")
        if pnl_pct > 0:
            tactics.append(f"수익률 +{pnl_pct:.1f}% → 추가 매수 시 평균단가 상승 감안")
        if target_price:
            tactics.append(f"목표가 {target_price:,}원 도달 시 부분 익절 고려")

    elif total >= 55 and pnl_pct >= -5:
        # 양호한 점수 + 큰 손실 없음 → 보유
        action = "보유"
        action_detail = f"종합 점수 {total:.0f}점, 현재 보유 유지가 적절합니다."
        if pnl_pct > 20:
            tactics.append(f"수익률 +{pnl_pct:.1f}% → 절반 익절 후 나머지 보유 고려")
        elif pnl_pct > 10:
            tactics.append(f"수익률 +{pnl_pct:.1f}% → 보유 유지, 추가 상승 기대")
        elif pnl_pct > 0:
            tactics.append("소폭 수익 구간 → 인내심 있게 보유")
        else:
            tactics.append("소폭 손실이나 점수 양호 → 반등 대기")
        if stop_loss and current_price > 0:
            tactics.append(f"손절가 {stop_loss:,}원 이탈 시 매도 검토")

    elif total >= 45 and pnl_pct >= -10:
        # 중립 점수 → 관망
        action = "관망"
        action_detail = f"종합 점수 {total:.0f}점으로 중립 구간입니다."
        if pnl_pct > 15:
            tactics.append(f"수익률 +{pnl_pct:.1f}% → 일부 차익 실현 고려")
            action = "부분매도"
            action_detail += " 수익 확보 차원에서 일부 매도를 고려하세요."
        elif pnl_pct > 0:
            tactics.append("소폭 수익 → 추세 전환 여부 모니터링")
        else:
            tactics.append("소폭 손실 → 반등 가능성과 추가 하락 위험 모니터링")
        tactics.append("신규 매수/추가 매수는 보류")

    elif total < 35 or pnl_pct < -15:
        # 매도 시그널 또는 큰 손실 → 매도
        action = "매도"
        if pnl_pct < -20:
            action_detail = f"수익률 {pnl_pct:.1f}%, 손실 확대 방지를 위해 매도를 권장합니다."
            tactics.append("즉시 전량 매도 또는 절반 매도 후 나머지 관망")
        elif total < 25:
            action_detail = f"종합 점수 {total:.0f}점으로 강력 매도 구간입니다."
            tactics.append("전량 매도 권장 (추가 하락 위험 높음)")
        else:
            action_detail = f"종합 점수 {total:.0f}점, 매도 검토가 필요합니다."
            tactics.append("분할 매도 (2~3회 나눠서 리스크 관리)")
        if risk_grade in ("D", "E"):
            tactics.append(f"리스크 등급 {risk_grade} → 변동성 높아 빠른 대응 필요")
        tactics.append("매도 후 재진입은 점수 개선 확인 후")

    elif pnl_pct < -5:
        # 중립이지만 손실 중 → 조건부 매도
        action = "조건부매도"
        action_detail = f"수익률 {pnl_pct:.1f}%, 점수 {total:.0f}점. 추가 하락 시 매도 준비."
        if stop_loss:
            tactics.append(f"손절가 {stop_loss:,}원 이탈 시 매도 실행")
        tactics.append("반등 모멘텀 발생 시 보유 전환")
        tactics.append("물타기(추가매수)는 비권장")

    else:
        # 기본 보유
        action = "보유"
        action_detail = f"종합 점수 {total:.0f}점, 특별한 매매 시그널이 없습니다."
        tactics.append("현 포지션 유지, 시장 상황 모니터링")

    # 공통 전략 추가
    signal_details = details.get("signal", {})
    regime = signal_details.get("regime", "UNKNOWN")
    if regime == "BEAR" and action not in ("매도",):
        tactics.append("하락 추세 주의 → 손절 라인을 타이트하게 설정")
    elif regime == "BULL" and action == "보유":
        tactics.append("상승 추세 → 추가 매수 기회 탐색")

    return {
        "action": action,
        "action_detail": action_detail,
        "tactics": tactics[:5],
        "target_price": target_price,
        "stop_loss": stop_loss,
    }


def _calc_portfolio_summary(analyzed: list[dict]) -> dict:
    """포트폴리오 전체 요약."""
    total_invested = sum(h["invested"] for h in analyzed)
    total_value = sum(h["current_value"] for h in analyzed)
    total_pnl = total_value - total_invested
    total_pnl_pct = ((total_value / total_invested) - 1) * 100 if total_invested > 0 else 0

    # 종목별 비중
    weights = []
    for h in analyzed:
        w = (h["current_value"] / total_value * 100) if total_value > 0 else 0
        weights.append({"code": h["code"], "name": h["name"], "weight": round(w, 1)})

    # 평균 점수
    scores = [h["total_score"] for h in analyzed if h["total_score"] is not None]
    avg_score = sum(scores) / len(scores) if scores else 50.0

    # 리스크 분포
    risk_dist = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
    for h in analyzed:
        grade = h.get("risk_grade", "C")
        if grade in risk_dist:
            risk_dist[grade] += 1

    # 액션 분포
    action_counts = {}
    for h in analyzed:
        act = h["strategy"]["action"]
        action_counts[act] = action_counts.get(act, 0) + 1

    # 포트폴리오 전체 전략
    overall_strategy = _generate_portfolio_strategy(
        analyzed, total_pnl_pct, avg_score, risk_dist, action_counts
    )

    return {
        "total_invested": total_invested,
        "total_value": total_value,
        "total_pnl": total_pnl,
        "total_pnl_pct": round(total_pnl_pct, 2),
        "holdings_count": len(analyzed),
        "avg_score": round(avg_score, 1),
        "weights": sorted(weights, key=lambda x: x["weight"], reverse=True),
        "risk_distribution": risk_dist,
        "action_distribution": action_counts,
        "overall_strategy": overall_strategy,
    }


def _generate_portfolio_strategy(
    analyzed: list[dict],
    total_pnl_pct: float,
    avg_score: float,
    risk_dist: dict,
    action_counts: dict,
) -> dict:
    """포트폴리오 전체 전략 생성."""
    tactics = []
    cautions = []

    # 전체 방향성
    sell_count = action_counts.get("매도", 0) + action_counts.get("조건부매도", 0)
    buy_count = action_counts.get("추가매수", 0)
    total_count = len(analyzed)

    if sell_count > total_count * 0.5:
        direction = "방어적 축소"
        direction_detail = "매도 시그널 종목이 과반 → 포트폴리오 축소 권장"
    elif buy_count > total_count * 0.3 and avg_score >= 60:
        direction = "적극적 확대"
        direction_detail = "매수 기회 종목 다수 → 비중 확대 검토"
    elif avg_score >= 55:
        direction = "선별적 유지"
        direction_detail = "전체적으로 양호 → 현 포트폴리오 유지하며 선별 조정"
    else:
        direction = "보수적 운용"
        direction_detail = "평균 점수 보통 → 신규 매수 자제, 기존 보유 관리 집중"

    # 수익률 기반 전략
    if total_pnl_pct > 20:
        tactics.append(f"총 수익률 +{total_pnl_pct:.1f}% → 이익 실현 일부 진행 권장")
    elif total_pnl_pct > 10:
        tactics.append(f"총 수익률 +{total_pnl_pct:.1f}% → 수익 종목 일부 익절 고려")
    elif total_pnl_pct < -10:
        tactics.append(f"총 수익률 {total_pnl_pct:.1f}% → 손실 종목 정리 우선")
        cautions.append("물타기보다는 손절 후 유망 종목으로 교체 검토")
    elif total_pnl_pct < -5:
        tactics.append("소폭 손실 구간 → 손절 라인 재점검")

    # 집중도 리스크
    total_val = sum(x["current_value"] for x in analyzed)
    if total_val > 0:
        for h in analyzed:
            w = h["current_value"] / total_val * 100
            if w > 30:
                cautions.append(f"{h['name']} 비중 {w:.0f}% → 과도한 집중, 분산 필요")
                break

    # 리스크 등급 경고
    high_risk = risk_dist.get("D", 0) + risk_dist.get("E", 0)
    if high_risk > 0:
        cautions.append(f"리스크 D/E 등급 종목 {high_risk}개 → 우선 정리 대상")

    # 분산 권고
    if total_count < 3:
        tactics.append("보유 종목 3개 미만 → 분산 투자로 리스크 분산 권장")
    elif total_count > 10:
        tactics.append("보유 종목 10개 초과 → 핵심 종목 위주로 집중 관리 권장")

    if not tactics:
        tactics.append("현 포트폴리오 유지, 정기적인 리밸런싱 검토")

    if not cautions:
        cautions.append("특별한 경고 사항 없음")

    return {
        "direction": direction,
        "direction_detail": direction_detail,
        "tactics": tactics[:5],
        "cautions": cautions[:4],
    }


def _fallback_holding(holding: dict) -> dict:
    """분석 실패 시 기본 홀딩 정보."""
    return {
        "code": holding.get("code", ""),
        "name": holding.get("code", ""),
        "market": "",
        "quantity": holding.get("quantity", 0),
        "avg_price": holding.get("avg_price", 0),
        "current_price": 0,
        "invested": holding.get("avg_price", 0) * holding.get("quantity", 0),
        "current_value": 0,
        "pnl": 0,
        "pnl_pct": 0,
        "change_pct": 0,
        "total_score": None,
        "action_label": "분석실패",
        "risk_grade": "C",
        "signal": "분석실패",
        "recommendation": None,
        "strategy": {
            "action": "관망",
            "action_detail": "데이터를 불러올 수 없습니다.",
            "tactics": ["잠시 후 다시 시도해주세요"],
            "target_price": None,
            "stop_loss": None,
        },
        "breakdown": {
            "technical": 50, "signal": 50, "fundamental": 50,
            "macro": 50, "risk": 50,
        },
    }


def _empty_summary() -> dict:
    """빈 포트폴리오 요약."""
    return {
        "total_invested": 0,
        "total_value": 0,
        "total_pnl": 0,
        "total_pnl_pct": 0,
        "holdings_count": 0,
        "avg_score": 0,
        "weights": [],
        "risk_distribution": {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0},
        "action_distribution": {},
        "overall_strategy": {
            "direction": "시작하기",
            "direction_detail": "종목을 추가하여 포트폴리오 분석을 시작하세요.",
            "tactics": ["상단 검색에서 종목을 검색한 뒤 포트폴리오에 추가하세요"],
            "cautions": [],
        },
    }
