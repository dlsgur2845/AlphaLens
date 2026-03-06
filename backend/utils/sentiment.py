"""한국어 금융 감성분석 — KR-FinBERT 앙상블 + 부정어 처리 + 제목 가중 + 문맥 인식."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── 긍정 키워드 (가중치) ──

POSITIVE_KEYWORDS: dict[str, float] = {
    # 실적
    "실적개선": 1.5, "호실적": 1.5, "매출증가": 1.3, "영업이익증가": 1.5,
    "순이익증가": 1.4, "흑자전환": 1.8, "사상최대": 1.5, "어닝서프라이즈": 1.8,
    "실적호조": 1.5, "성장세": 1.0, "이익증가": 1.3, "매출성장": 1.3,
    "영업이익": 0.9, "순이익": 0.9, "깜짝실적": 1.6, "컨센서스상회": 1.5,
    "분기최대": 1.3, "연간최대": 1.4,
    # 사업
    "수주": 1.3, "대형수주": 1.6, "신사업": 1.2, "사업확장": 1.3,
    "계약체결": 1.2, "합작": 1.0, "인수합병": 1.0, "전략적제휴": 1.1,
    "대규모투자": 1.2, "신제품": 1.2, "기술개발": 1.0, "특허": 1.0,
    "해외진출": 1.2, "독점공급": 1.5, "납품계약": 1.3, "시장점유율확대": 1.4,
    # 주가/시장
    "신고가": 1.5, "급등": 1.2, "강세": 0.9, "반등": 0.9,
    "돌파": 0.9, "목표가상향": 1.5, "매수추천": 1.5, "매수의견": 1.4,
    "비중확대": 1.3, "저평가": 1.1, "아웃퍼폼": 1.3,
    "투자의견상향": 1.5, "컨센서스상향": 1.3,
    # 배당/주주환원
    "배당확대": 1.3, "배당증가": 1.3, "자사주매입": 1.3, "주주환원": 1.2,
    "배당금": 0.8, "무상증자": 1.1, "자사주소각": 1.4,
    # 산업
    "AI": 0.5, "반도체": 0.4, "전기차": 0.4, "2차전지": 0.4,
    "친환경": 0.4, "디지털전환": 0.4, "클라우드": 0.4,
    # 일반
    "호재": 1.5, "기대감": 0.7, "긍정적": 0.9, "개선": 0.7,
    "회복": 0.8, "안정": 0.5, "우호적": 0.7, "낙관": 0.8,
    "청신호": 1.2, "훈풍": 1.0, "수혜": 1.1, "모멘텀": 0.8,
}

# ── 부정 키워드 (가중치) ──

NEGATIVE_KEYWORDS: dict[str, float] = {
    # 실적
    "적자": 1.5, "적자전환": 1.8, "실적악화": 1.5, "매출감소": 1.3,
    "영업손실": 1.5, "순손실": 1.5, "어닝쇼크": 1.8, "실적부진": 1.3,
    "감익": 1.2, "역성장": 1.3, "이익감소": 1.3, "적자지속": 1.6,
    "컨센서스하회": 1.5, "기대이하": 1.0, "실적쇼크": 1.7,
    # 리스크
    "리콜": 1.5, "소송": 1.2, "과징금": 1.3, "벌금": 1.3,
    "부채증가": 1.2, "부도": 2.0, "파산": 2.0, "워크아웃": 1.8,
    "감사의견": 1.5, "횡령": 1.8, "배임": 1.8, "불법": 1.5,
    "제재": 1.3, "수사": 1.2, "기소": 1.5, "검찰": 1.0,
    "압수수색": 1.5, "분식회계": 1.8,
    # 주가/시장
    "급락": 1.5, "폭락": 1.8, "약세": 0.9, "하한가": 1.8,
    "신저가": 1.5, "목표가하향": 1.5, "매도추천": 1.5, "매도의견": 1.4,
    "비중축소": 1.3, "고평가": 0.9, "차익실현": 0.7,
    "투자의견하향": 1.5, "언더퍼폼": 1.3,
    # 부정적 이벤트
    "유상증자": 1.2, "전환사채": 0.7, "지분매각": 1.0, "대량매도": 1.3,
    "공매도": 0.7, "감자": 1.5, "상장폐지": 2.0, "거래정지": 1.8,
    "관리종목": 1.8, "투자경고": 1.5,
    # 거시
    "금리인상": 0.6, "경기침체": 0.9, "인플레이션": 0.5, "무역전쟁": 0.8,
    "환율급등": 0.7, "원자재상승": 0.5,
    # 일반
    "악재": 1.5, "우려": 0.6, "부정적": 0.9, "악화": 0.9,
    "위기": 0.9, "불안": 0.7, "비관": 0.8, "리스크": 0.5,
    "불확실": 0.5, "경고": 0.8, "먹구름": 1.0, "역풍": 1.0,
    "부담": 0.5, "둔화": 0.7, "위축": 0.8,
}

# ── 부정어 패턴 ──
# 키워드 앞에 이 표현이 등장하면 감성을 반전
NEGATION_WORDS = [
    "없", "않", "아니", "못", "안 ", "불가", "미", "무관",
    "벗어", "해소", "극복", "탈피", "전환", "개선",
]

# 부정어 검사 범위 (키워드 앞 몇 글자까지)
NEGATION_WINDOW = 8


def _has_negation(text: str, keyword_pos: int) -> bool:
    """키워드 앞 NEGATION_WINDOW 글자 내에 부정어가 있는지 확인."""
    start = max(0, keyword_pos - NEGATION_WINDOW)
    context = text[start:keyword_pos]
    return any(neg in context for neg in NEGATION_WORDS)


def _score_text(text: str) -> tuple[float, float]:
    """텍스트에서 긍정/부정 점수를 계산. 부정어 반전 처리 포함."""
    pos_score = 0.0
    neg_score = 0.0

    for keyword, weight in POSITIVE_KEYWORDS.items():
        start = 0
        while True:
            idx = text.find(keyword, start)
            if idx == -1:
                break
            if _has_negation(text, idx):
                neg_score += weight * 0.7  # 긍정 키워드가 부정되면 부정으로 전환 (약화)
            else:
                pos_score += weight
            start = idx + len(keyword)

    for keyword, weight in NEGATIVE_KEYWORDS.items():
        start = 0
        while True:
            idx = text.find(keyword, start)
            if idx == -1:
                break
            if _has_negation(text, idx):
                pos_score += weight * 0.5  # 부정 키워드가 부정되면 긍정으로 전환 (약화)
            else:
                neg_score += weight
            start = idx + len(keyword)

    return pos_score, neg_score


def _keyword_sentiment(
    title: str,
    body: str = "",
    title_weight: float = 2.5,
) -> tuple[float, str]:
    """키워드 기반 감성분석 (내부 함수).

    Returns:
        (score, label) — score: -1.0~1.0, label: 긍정/부정/중립
    """
    if not title and not body:
        return 0.0, "중립"

    # 제목 분석 (가중)
    t_pos, t_neg = _score_text(title)
    t_pos *= title_weight
    t_neg *= title_weight

    # 본문 분석
    b_pos, b_neg = _score_text(body)

    pos_total = t_pos + b_pos
    neg_total = t_neg + b_neg
    total = pos_total + neg_total

    if total == 0:
        return 0.0, "중립"

    score = (pos_total - neg_total) / total

    if score > 0.12:
        label = "긍정"
    elif score < -0.12:
        label = "부정"
    else:
        label = "중립"

    return round(score, 3), label


def analyze_sentiment(
    title: str,
    body: str = "",
    title_weight: float = 2.5,
) -> tuple[float, str, str]:
    """제목 + 본문 감성분석. KR-FinBERT 앙상블 또는 키워드 기반.

    FinBERT 가용 시: FinBERT 0.7 + 키워드 0.3 앙상블
    FinBERT 미가용 시: 기존 키워드 방식 100%

    Args:
        title: 기사 제목
        body: 기사 본문 (없으면 빈 문자열)
        title_weight: 제목 점수 배율 (기본 2.5x)

    Returns:
        (score, label, method) — score: -1.0~1.0, label: 긍정/부정/중립,
        method: "finbert_ensemble" 또는 "keyword"
    """
    # 키워드 기반 점수
    kw_score, kw_label = _keyword_sentiment(title, body, title_weight)

    # FinBERT 시도
    try:
        from backend.services.finbert_service import finbert
        if finbert.available:
            # 제목 기반 FinBERT 분석 (제목이 감성 판단에 가장 중요)
            fb_result = finbert.analyze(title)
            if fb_result is not None:
                fb_score = fb_result["score"]
                # 앙상블: FinBERT 70% + 키워드 30%
                ensemble_score = round(fb_score * 0.7 + kw_score * 0.3, 3)

                if ensemble_score > 0.12:
                    label = "긍정"
                elif ensemble_score < -0.12:
                    label = "부정"
                else:
                    label = "중립"

                return ensemble_score, label, "finbert_ensemble"
    except ImportError:
        pass
    except Exception as e:
        logger.warning("FinBERT ensemble failed, falling back to keyword: %s", e)

    return kw_score, kw_label, "keyword"


async def analyze_sentiment_enhanced(
    title: str,
    body: str = "",
    title_weight: float = 2.5,
) -> tuple[float, str, str]:
    """감성분석 (async wrapper).

    KR-FinBERT 앙상블 또는 키워드 기반 분석만 수행.

    Returns:
        (score, label, method)
    """
    return analyze_sentiment(title, body, title_weight)


def sentiment_to_score(sentiment: float) -> float:
    """감성 점수(-1~1)를 스코어링 점수(0~100)로 변환."""
    return round((sentiment + 1) * 50, 2)
