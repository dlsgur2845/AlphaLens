"""지정학 리스크 실시간 분석 서비스.

뉴스 키워드 기반 이벤트 감지 → 섹터 영향 자동 매핑 → 리스크 점수 산출.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import defusedxml.ElementTree as ET
from datetime import datetime
from urllib.parse import quote

from backend.services.cache_service import cache
from backend.services.http_client import get_mobile_client

logger = logging.getLogger(__name__)

_CACHE_TTL = 900  # 15분
_CRISIS_CACHE_TTL = 300  # 위기 시 5분
_TAG_RE = re.compile(r"<[^>]+>")
_PREFIX_RE = re.compile(r"^\[(속보|단독|종합|긴급|1보|2보|3보)\]\s*")

# ── 이벤트 카테고리 및 키워드 ──

EVENT_CATEGORIES: dict[str, dict] = {
    "war_conflict": {
        "label": "전쟁/군사충돌",
        "icon": "⚔️",
        "keywords": [
            "전쟁 발발", "공습", "미사일 공격", "폭격", "군사작전",
            "침공", "교전", "봉쇄", "핵무기", "핵실험", "NATO",
            "호르무즈 해협", "이란 공습", "이란 미사일", "이란 핵",
            "우크라이나 전쟁", "러시아 침공",
            "대만 해협", "남중국해",
            "무력충돌", "보복공격",
            "중동 분쟁", "이스라엘", "가자", "헤즈볼라", "하마스",
            "홍해 위기", "후티 반군", "사이버공격",
        ],
        "en_keywords": [
            "war", "military conflict", "missile strike", "invasion",
            "armed conflict", "airstrike", "bombardment", "nuclear",
            "Ukraine war", "Russia invasion", "Taiwan strait",
            "Middle East conflict", "Israel", "Gaza", "Hezbollah", "Hamas",
            "Red Sea crisis", "Houthi", "cyberattack", "NATO escalation",
        ],
        "weight": 1.5,
    },
    "nk_peninsula": {
        "label": "한반도 안보",
        "icon": "🚀",
        "keywords": [
            "북한 미사일", "북한 도발", "ICBM", "SLBM", "핵탄두",
            "북한 핵실험", "대북제재", "유엔안보리",
            "한미연합훈련", "킬체인", "사드 배치",
            "남북관계", "비핵화", "정전협정",
            "북한 위협", "북한 발사",
        ],
        "en_keywords": [
            "North Korea", "DPRK", "Korean peninsula", "Kim Jong Un",
            "denuclearization", "ICBM launch", "SLBM test",
            "North Korea missile", "North Korea nuclear",
            "THAAD", "UN sanctions DPRK",
        ],
        "weight": 1.4,
    },
    "trade_tariff": {
        "label": "관세/무역정책",
        "icon": "📦",
        "keywords": [
            "관세 부과", "무역전쟁", "수출규제", "수입규제", "반덤핑",
            "트럼프 관세", "상호관세", "보복관세", "무역적자",
            "통상압력", "무역협정", "IRA 법안", "칩스법",
            "수출통제", "엔티티리스트", "디리스킹",
            "EU CBAM", "세이프가드", "공급망실사",
        ],
        "en_keywords": [
            "tariff", "trade war", "sanctions", "trade restrictions",
            "import duty", "export ban", "Trump tariff", "reciprocal tariff",
            "retaliatory tariff", "trade deficit", "CHIPS Act",
            "entity list", "de-risking", "CBAM",
        ],
        "weight": 1.2,
    },
    "monetary_policy": {
        "label": "금리/통화정책",
        "icon": "🏦",
        "keywords": [
            "기준금리", "연준", "FOMC", "파월",
            "금리인하", "금리인상", "금리동결",
            "양적긴축", "양적완화",
            "ECB", "한은", "금통위",
            "통화정책", "긴축 기조", "피벗",
            "인플레이션", "디스인플레이션",
            "잭슨홀",
        ],
        "en_keywords": [
            "Fed rate", "interest rate", "FOMC", "rate hike",
            "rate cut", "quantitative tightening", "quantitative easing",
            "ECB rate", "Powell", "Jackson Hole",
            "inflation", "disinflation", "pivot",
            "hawkish", "dovish", "monetary policy",
        ],
        "weight": 1.1,
        "hawkish_keywords": ["금리인상", "긴축", "양적긴축", "매파", "금리동결"],
        "dovish_keywords": ["금리인하", "피벗", "양적완화", "비둘기파", "유동성 공급"],
        "en_hawkish_keywords": ["rate hike", "tightening", "hawkish", "rate hold"],
        "en_dovish_keywords": ["rate cut", "pivot", "easing", "dovish"],
    },
    "oil_energy": {
        "label": "에너지/유가",
        "icon": "⛽",
        "keywords": [
            "유가 급등", "유가 폭등", "유가 급락",
            "원유 가격", "WTI", "브렌트",
            "OPEC 감산", "OPEC 증산",
            "호르무즈 봉쇄", "에너지위기", "에너지안보",
            "천연가스", "LNG 가격",
        ],
        "en_keywords": [
            "oil price", "OPEC", "crude oil", "energy crisis",
            "natural gas", "LNG", "Brent crude", "WTI crude",
            "oil supply", "oil demand", "Hormuz strait",
            "OPEC cut", "OPEC production",
        ],
        "weight": 1.3,
    },
    "china_economy": {
        "label": "중국 경제",
        "icon": "🇨🇳",
        "keywords": [
            "중국경제", "중국경기", "중국 부동산", "헝다", "비구이위안",
            "중국 GDP", "위안화 약세", "중국 소비", "중국 수출",
            "중국 부양", "경기부양", "시진핑",
            "중국 디플레", "중국 PMI",
            "항셍지수", "중국증시", "중국 실업률",
        ],
        "en_keywords": [
            "China economy", "China GDP", "Evergrande", "Country Garden",
            "China property", "China exports", "China stimulus",
            "Xi Jinping", "China deflation", "China PMI",
            "Hang Seng", "yuan depreciation", "China unemployment",
        ],
        "weight": 1.3,
    },
    "tech_semiconductor": {
        "label": "반도체/AI",
        "icon": "🔬",
        "keywords": [
            "반도체 수출", "반도체 규제", "AI칩",
            "HBM", "엔비디아",
            "첨단반도체", "파운드리", "TSMC",
            "AI 슈퍼사이클", "데이터센터",
            "삼성전자 반도체", "SK하이닉스",
            "메모리반도체", "반도체 사이클", "EUV",
        ],
        "en_keywords": [
            "semiconductor", "chip shortage", "AI chip", "TSMC", "NVIDIA",
            "export controls", "HBM", "foundry", "data center",
            "chip ban", "semiconductor cycle", "EUV lithography",
        ],
        "weight": 1.1,
    },
    "fx_currency": {
        "label": "환율/외환",
        "icon": "💱",
        "keywords": [
            "환율 급등", "원달러 환율", "원화약세", "원화강세",
            "달러강세", "달러인덱스",
            "외환보유", "경상수지", "자본유출",
            "외국인 순매도", "외국인 매도",
            "엔화 약세", "위안화 약세",
            "캐리트레이드",
        ],
        "en_keywords": [
            "dollar index", "USD/KRW", "currency crisis", "forex",
            "won depreciation", "dollar strength", "capital outflow",
            "yen weakness", "yuan weakness", "carry trade",
            "foreign exchange reserves",
        ],
        "weight": 1.1,
    },
    "supply_chain": {
        "label": "공급망/디커플링",
        "icon": "🔗",
        "keywords": [
            "공급망 위기", "공급망 재편",
            "리쇼어링", "프렌드쇼어링", "니어쇼어링",
            "희토류 규제", "탈중국",
            "물류대란", "반도체 부족",
        ],
        "en_keywords": [
            "supply chain", "decoupling", "reshoring", "nearshoring",
            "friendshoring", "rare earth", "chip shortage",
            "logistics crisis", "supply disruption",
        ],
        "weight": 1.0,
    },
}

# ── 영문 키워드 그룹 (RSS 수집용) ──

KEYWORD_GROUPS_EN = [
    ["war", "airstrike", "missile strike", "invasion"],
    ["tariff", "trade war", "Trump tariff", "export ban"],
    ["Fed rate", "FOMC", "interest rate", "monetary policy"],
    ["oil price", "crude oil", "OPEC", "energy crisis"],
    ["China economy", "China property", "yuan depreciation"],
    ["semiconductor", "AI chip", "chip ban", "export controls"],
    ["dollar index", "USD KRW", "currency crisis", "forex"],
    ["North Korea", "DPRK", "missile launch", "Korean peninsula"],
    ["supply chain", "decoupling", "reshoring"],
]

# ── 이벤트 → 섹터 영향 매트릭스 ──
# 양수 = 수혜, 음수 = 피해 (최대 ±20)

EVENT_SECTOR_IMPACT: dict[str, dict[str, int]] = {
    "war_conflict": {
        "방산": 20, "조선": 10, "에너지": 10, "금": 15,
        "사이버보안": 10,
        "금융": -8, "항공": -15, "여행": -15, "자동차": -8,
        "반도체": -5, "2차전지": -5, "보험": -10, "건설": -8,
    },
    "nk_peninsula": {
        "방산": 20, "금": 10,
        "금융": -10, "항공": -10, "여행": -12,
        "내수소비": -5, "부동산": -8, "건설": -8,
    },
    "trade_tariff": {
        "자동차": -15, "반도체": -10, "철강": -15,
        "디스플레이": -8, "2차전지": -10, "화장품": -8,
        "내수소비": 10, "방산": 5, "바이오": 5, "유틸리티": 5,
    },
    "monetary_policy_hawkish": {
        "금융": 5, "보험": 5,
        "바이오": -8, "성장주": -10, "2차전지": -5,
        "부동산": -12, "건설": -8, "유틸리티": 3,
        "배당주": -3,
    },
    "monetary_policy_dovish": {
        "금융": -3, "보험": -3,
        "바이오": 8, "성장주": 10, "2차전지": 5,
        "부동산": 8, "건설": 5,
        "배당주": 8, "반도체": 5,
    },
    "oil_energy": {
        "에너지": 15, "정유": 12, "해운": 8,
        "항공": -15, "화학": -8, "자동차": -5,
        "2차전지": 6, "유틸리티": -5,
    },
    "china_economy": {
        "철강": -10, "화학": -10, "조선": -8, "해운": -8,
        "반도체": -8, "화장품": -15, "카지노": -15,
        "여행": -10, "디스플레이": -8,
        "내수소비": 5, "바이오": 5,
    },
    "tech_semiconductor": {
        "반도체": 15, "AI소프트웨어": 15, "데이터센터": 10,
        "장비": 10, "전자부품": 8, "디스플레이": 3,
        "전통IT": -5,
    },
    "fx_currency": {
        "수출주": 10, "자동차": 8, "반도체": 5,
        "내수소비": -8, "수입의존": -10,
        "항공": -8, "정유": -5, "화학": -5,
    },
    "supply_chain": {
        "반도체": -5, "자동차": -8, "전자부품": -8,
        "바이오": 3, "내수소비": 5, "방산": 3,
    },
}

# ── 뉴스 수집 ──

_fetch_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _fetch_semaphore
    if _fetch_semaphore is None:
        _fetch_semaphore = asyncio.Semaphore(3)
    return _fetch_semaphore


async def _fetch_news_google_rss(
    keywords: list[str], max_articles: int = 10, lang: str = "ko",
) -> list[dict]:
    """Google News RSS 뉴스 수집. lang='ko' 또는 'en' 지원."""
    client = get_mobile_client()
    articles: list[dict] = []

    query = " ".join(keywords[:4])
    encoded = quote(query)
    if lang == "en":
        params = "hl=en&gl=US&ceid=US:en"
    else:
        params = "hl=ko&gl=KR&ceid=KR:ko"
    url = (
        f"https://news.google.com/rss/search"
        f"?q={encoded}&{params}"
    )

    try:
        resp = await client.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8.0,
        )
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            for item in root.iter("item"):
                title_el = item.find("title")
                desc_el = item.find("description")
                title = (
                    _TAG_RE.sub("", html.unescape(title_el.text))
                    if title_el is not None and title_el.text
                    else ""
                )
                desc = (
                    _TAG_RE.sub("", html.unescape(desc_el.text))
                    if desc_el is not None and desc_el.text
                    else ""
                )
                if title:
                    articles.append({"title": title, "body": desc, "lang": lang})
                if len(articles) >= max_articles:
                    break
    except Exception:
        logger.warning(
            "Google News RSS fetch failed for query=%s", query, exc_info=True,
        )

    return articles


async def _fetch_news_naver_finance(max_articles: int = 15) -> list[dict]:
    """네이버 금융 메인 뉴스 수집 (폴백)."""
    client = get_mobile_client()
    articles: list[dict] = []

    try:
        resp = await client.get(
            "https://m.stock.naver.com/api/news/main",
            timeout=8.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            items = (
                data
                if isinstance(data, list)
                else data.get("items", data.get("news", []))
            )
            for item in items[:max_articles]:
                title = _TAG_RE.sub(
                    "", html.unescape(item.get("title", "")),
                )
                body = _TAG_RE.sub(
                    "",
                    html.unescape(
                        item.get("body", item.get("description", "")),
                    ),
                )
                if title:
                    articles.append({"title": title, "body": body})
    except Exception:
        logger.warning("Naver finance news fetch failed", exc_info=True)

    return articles


# ── 이벤트 감지 ──


def _detect_events(articles: list[dict]) -> dict[str, dict]:
    """뉴스에서 이벤트 카테고리별 감지 결과를 계산."""
    detected: dict[str, dict] = {}
    min_articles_for_high = 5

    for cat_id, cat_info in EVENT_CATEGORIES.items():
        hit_count = 0
        ko_hit_count = 0
        en_hit_count = 0
        matched_keywords: set[str] = set()
        matched_titles: list[str] = []

        ko_keywords = cat_info["keywords"]
        en_keywords = cat_info.get("en_keywords", [])

        for article in articles:
            text = article.get("title", "") + " " + article.get("body", "")
            text_lower = text.lower()
            article_lang = article.get("lang", "ko")

            # 기사 언어에 맞는 키워드 세트 선택
            if article_lang == "en":
                kw_list = en_keywords
            else:
                kw_list = ko_keywords

            for kw in kw_list:
                kw_lower = kw.lower()
                # 3글자 미만 키워드 제외 (오탐 방지)
                if len(kw) < 3:
                    continue
                if kw_lower in text_lower:
                    hit_count += 1
                    if article_lang == "en":
                        en_hit_count += 1
                    else:
                        ko_hit_count += 1
                    matched_keywords.add(kw)
                    title = article.get("title", "")
                    if title and title not in matched_titles:
                        matched_titles.append(title)
                    break  # 기사당 1회 카운트

        if hit_count > 0:
            # 강도: 비율(60%) + 절대수(40%)
            ratio_score = hit_count / max(len(articles), 1) * 100
            volume_score = min(hit_count * 12, 100)
            intensity = min(ratio_score * 0.6 + volume_score * 0.4, 100)

            severity = _calc_severity(intensity, cat_info["weight"])
            # 기사 수 부족 시 신뢰도 하향
            if len(articles) < min_articles_for_high and severity in (
                "critical",
                "high",
            ):
                severity = "medium"

            # 한영 교차 확인: 양쪽 모두 감지 시 severity 가중치 20% 증가
            cross_confirmed = ko_hit_count > 0 and en_hit_count > 0
            if cross_confirmed:
                boosted_intensity = min(intensity * 1.2, 100)
                severity = _calc_severity(boosted_intensity, cat_info["weight"])
                # 교차 확인 시 소규모 기사 제한 완화 (high까지 허용)
                if len(articles) < min_articles_for_high and severity == "critical":
                    severity = "high"

            detected[cat_id] = {
                "label": cat_info["label"],
                "icon": cat_info["icon"],
                "hit_count": hit_count,
                "ko_hits": ko_hit_count,
                "en_hits": en_hit_count,
                "cross_confirmed": cross_confirmed,
                "intensity": round(intensity, 1),
                "severity": severity,
                "severity_score": _severity_to_score(severity),
                "matched_keywords": list(matched_keywords)[:5],
                "sample_headlines": matched_titles[:3],
            }

    return detected


def _calc_severity(intensity: float, weight: float) -> str:
    """이벤트 강도와 가중치로 심각도 판정."""
    weighted = intensity * weight
    if weighted >= 60:
        return "critical"
    elif weighted >= 40:
        return "high"
    elif weighted >= 20:
        return "medium"
    return "low"


def _severity_to_score(severity: str) -> float:
    """심각도를 수치로 변환."""
    mapping = {"critical": 4.0, "high": 3.0, "medium": 2.0, "low": 1.0}
    score = mapping.get(severity)
    if score is None:
        logger.warning("Unknown severity: %s, defaulting to 1.0", severity)
        return 1.0
    return score


# ── 통화정책 방향 감지 ──


def _detect_monetary_direction(articles: list[dict]) -> str:
    """통화정책 이벤트의 방향 감지 (hawkish/dovish/mixed)."""
    cat_info = EVENT_CATEGORIES.get("monetary_policy", {})
    hawkish_kws = cat_info.get("hawkish_keywords", [])
    dovish_kws = cat_info.get("dovish_keywords", [])
    en_hawkish_kws = cat_info.get("en_hawkish_keywords", [])
    en_dovish_kws = cat_info.get("en_dovish_keywords", [])

    hawk_count = 0
    dove_count = 0
    for article in articles:
        text = (
            article.get("title", "") + " " + article.get("body", "")
        ).lower()
        article_lang = article.get("lang", "ko")

        hawk_kw_set = en_hawkish_kws if article_lang == "en" else hawkish_kws
        dove_kw_set = en_dovish_kws if article_lang == "en" else dovish_kws

        for kw in hawk_kw_set:
            if kw.lower() in text:
                hawk_count += 1
                break
        for kw in dove_kw_set:
            if kw.lower() in text:
                dove_count += 1
                break

    if hawk_count > dove_count * 1.5:
        return "hawkish"
    elif dove_count > hawk_count * 1.5:
        return "dovish"
    return "mixed"


# ── 섹터 영향 계산 ──


def _calc_sector_impacts(
    detected_events: dict, articles: list[dict] | None = None,
) -> dict[str, dict]:
    """감지된 이벤트들의 섹터별 영향을 합산."""
    sector_scores: dict[str, float] = {}
    sector_events: dict[str, list] = {}

    # 통화정책 방향 사전 감지
    monetary_dir = "mixed"
    if "monetary_policy" in detected_events and articles:
        monetary_dir = _detect_monetary_direction(articles)

    for cat_id, event in detected_events.items():
        # 통화정책: 방향에 따라 다른 매트릭스 적용
        if cat_id == "monetary_policy":
            if monetary_dir == "hawkish":
                impact_key = "monetary_policy_hawkish"
            elif monetary_dir == "dovish":
                impact_key = "monetary_policy_dovish"
            else:
                # mixed: 영향 축소 (hawkish 기본, 0.5배)
                impact_key = "monetary_policy_hawkish"
        else:
            impact_key = cat_id

        impacts = EVENT_SECTOR_IMPACT.get(impact_key, {})
        severity_mult = event["severity_score"] / 4.0  # 0.25 ~ 1.0
        # mixed 통화정책은 영향 반감
        if cat_id == "monetary_policy" and monetary_dir == "mixed":
            severity_mult *= 0.5

        for sector, impact in impacts.items():
            adjusted = impact * severity_mult
            sector_scores[sector] = sector_scores.get(sector, 0) + adjusted
            if sector not in sector_events:
                sector_events[sector] = []
            direction = "수혜" if impact > 0 else "피해"
            sector_events[sector].append({
                "event": event["label"],
                "direction": direction,
                "impact": round(adjusted, 1),
            })

    result: dict[str, dict] = {}
    for sector in sorted(
        sector_scores, key=lambda s: abs(sector_scores[s]), reverse=True,
    ):
        score = sector_scores[sector]
        clamped = max(min(score, 30), -30)
        result[sector] = {
            "total_impact": round(float(clamped), 1),
            "direction": (
                "수혜" if score > 0 else "피해" if score < 0 else "중립"
            ),
            "events": sector_events.get(sector, []),
        }

    return result


# ── 리스크 인덱스 ──


def _calc_risk_index(
    detected_events: dict, macro_data: dict | None = None,
) -> dict:
    """종합 지정학 리스크 인덱스 계산 (0~100)."""
    if not detected_events:
        # 이벤트 없어도 매크로 데이터로 기본 리스크 보정
        base = 15.0
        if macro_data:
            vix = macro_data.get("vix", {}).get("price", 20)
            usdkrw = macro_data.get("usdkrw", {}).get("price", 1400)
            if vix > 25:
                base += 10
            if usdkrw > 1450:
                base += 5
        score = max(min(base, 100), 0)
        if score >= 30:
            return {"score": round(score, 1), "level": "보통", "label": "주의"}
        return {"score": round(score, 1), "level": "낮음", "label": "안정"}

    total_severity = sum(e["severity_score"] for e in detected_events.values())
    event_count = len(detected_events)

    # 교차 확인된 이벤트 수
    cross_count = sum(
        1 for e in detected_events.values() if e.get("cross_confirmed")
    )

    # 심각도 중심 공식 (심각도 6x > 이벤트 수)
    avg_severity = total_severity / event_count if event_count > 0 else 0
    base_score = min(avg_severity * 18 + event_count * 3, 85)

    # 교차 확인 보너스: 한영 양쪽 감지 이벤트당 +5
    if cross_count > 0:
        base_score += cross_count * 5

    # 3개 이상 동시 이벤트 상관관계 보정
    if event_count >= 3:
        base_score *= 1.15

    # 매크로 데이터 보정
    if macro_data:
        vix = macro_data.get("vix", {}).get("price", 20)
        oil_chg = macro_data.get("wti", {}).get("change_pct", 0)
        gold_chg = macro_data.get("gold", {}).get("change_pct", 0)
        usdkrw = macro_data.get("usdkrw", {}).get("price", 1400)

        if vix > 30:
            base_score += 10
        elif vix > 25:
            base_score += 5

        if abs(oil_chg) > 3:
            base_score += 5
        if gold_chg > 2:
            base_score += 3

        if usdkrw > 1480:
            base_score += 8
        elif usdkrw > 1450:
            base_score += 3

    score = max(min(float(base_score), 100), 0)

    if score >= 70:
        level, label = "매우 높음", "위험"
    elif score >= 50:
        level, label = "높음", "경계"
    elif score >= 30:
        level, label = "보통", "주의"
    else:
        level, label = "낮음", "안정"

    return {"score": round(score, 1), "level": level, "label": label}


# ── 시나리오 트리거 ──


def _get_scenario_triggers(macro_data: dict | None) -> list[dict]:
    """현재 매크로 데이터 기반 시나리오 전환 트리거."""
    triggers: list[dict] = []
    if not macro_data:
        return triggers

    vix = macro_data.get("vix", {}).get("price", 20)
    oil_price = macro_data.get("wti", {}).get("price", 70)
    usdkrw = macro_data.get("usdkrw", {}).get("price", 1400)
    gold_chg = macro_data.get("gold", {}).get("change_pct", 0)

    if vix > 30:
        triggers.append({
            "signal": f"VIX {vix:.1f} (30 초과)",
            "action": "방어 모드 전환 - 현금 비중 40%로 확대",
            "severity": "critical",
        })
    elif vix > 25:
        triggers.append({
            "signal": f"VIX {vix:.1f} (25 초과)",
            "action": "경계 - 위험자산 비중 축소 검토",
            "severity": "high",
        })

    if oil_price > 100:
        triggers.append({
            "signal": f"유가 ${oil_price:.1f} ($100 초과)",
            "action": "에너지/방산 비중 확대, 항공/자동차 축소",
            "severity": "critical",
        })
    elif oil_price > 90:
        triggers.append({
            "signal": f"유가 ${oil_price:.1f} ($90 초과)",
            "action": "에너지 섹터 주시, 수입의존 업종 주의",
            "severity": "high",
        })

    if usdkrw > 1480:
        triggers.append({
            "signal": f"USD/KRW {usdkrw:.0f}원 (1,480 초과)",
            "action": "달러 자산 확대, 원화 자산 축소 검토",
            "severity": "critical",
        })
    elif usdkrw > 1430:
        triggers.append({
            "signal": f"USD/KRW {usdkrw:.0f}원 (1,430 초과)",
            "action": "환율 리스크 모니터링 강화",
            "severity": "medium",
        })

    if gold_chg > 3:
        triggers.append({
            "signal": f"금 가격 +{gold_chg:.1f}% (급등)",
            "action": "안전자산 수요 급증 신호 - 리스크 경계",
            "severity": "high",
        })

    if not triggers:
        triggers.append({
            "signal": "특이사항 없음",
            "action": "현재 포지션 유지",
            "severity": "low",
        })

    return triggers


def _get_macro_snapshot(macro_data: dict | None) -> dict:
    """매크로 데이터 요약 스냅샷 (필요한 필드만)."""
    if not macro_data:
        return {}
    snapshot: dict = {}
    for key in ("vix", "wti", "gold", "usdkrw", "sp500", "nasdaq", "us10y"):
        entry = macro_data.get(key)
        if entry and isinstance(entry, dict):
            snapshot[key] = {
                "price": entry.get("price"),
                "change_pct": entry.get("change_pct"),
            }
    return snapshot


# ── 메인 분석 함수 ──


async def get_geopolitical_analysis() -> dict:
    """지정학 리스크 종합 분석 수행."""
    cache_key = "geopolitical:analysis"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # 핵심 키워드 그룹별 뉴스 병렬 수집
    keyword_groups_ko = [
        ["전쟁", "공습", "미사일", "이란 핵"],
        ["관세", "무역전쟁", "트럼프 관세", "수출규제"],
        ["금리", "연준", "FOMC", "통화정책"],
        ["유가", "원유", "OPEC", "에너지위기"],
        ["중국경제", "부동산위기", "위안화"],
        ["반도체", "AI칩", "HBM", "수출규제"],
        ["환율", "원달러", "원화약세", "외국인매도"],
        ["북한", "미사일", "도발", "한반도"],
        ["공급망", "디커플링", "리쇼어링"],
    ]

    sem = _get_semaphore()

    async def _fetch_limited(coro):
        async with sem:
            return await coro

    # 한국어 RSS + 영문 RSS 병렬 수집
    tasks = [
        _fetch_limited(_fetch_news_google_rss(group, max_articles=8, lang="ko"))
        for group in keyword_groups_ko
    ]
    tasks.extend([
        _fetch_limited(_fetch_news_google_rss(group, max_articles=5, lang="en"))
        for group in KEYWORD_GROUPS_EN
    ])
    tasks.append(_fetch_limited(_fetch_news_naver_finance(max_articles=15)))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_articles: list[dict] = []
    fetch_failures = 0
    for result in results:
        if isinstance(result, list):
            all_articles.extend(result)
        else:
            fetch_failures += 1
            if isinstance(result, Exception):
                logger.warning("News fetch group failed: %s", result)

    # 중복 제거 (제목 정규화)
    seen_titles: set[str] = set()
    unique_articles: list[dict] = []
    for article in all_articles:
        title = article.get("title", "").strip()
        normalized = _PREFIX_RE.sub("", title)
        if normalized and normalized not in seen_titles:
            seen_titles.add(normalized)
            unique_articles.append(article)

    is_data_available = len(unique_articles) > 0

    # 이벤트 감지
    detected_events = _detect_events(unique_articles)

    # 매크로 데이터
    macro_data = None
    try:
        from backend.services.macro_service import get_macro_score

        macro_result = await get_macro_score()
        macro_data = (
            macro_result.details
            if isinstance(macro_result.details, dict)
            else None
        )
    except Exception:
        logger.warning(
            "Failed to fetch macro data for geopolitical analysis",
            exc_info=True,
        )

    # 섹터 영향 (통화정책 양방향 감지)
    sector_impacts = _calc_sector_impacts(detected_events, unique_articles)

    # 리스크 인덱스
    risk_index = _calc_risk_index(detected_events, macro_data)

    # 시나리오 트리거
    triggers = _get_scenario_triggers(macro_data)

    # 신뢰도
    if len(unique_articles) >= 20:
        confidence = "high"
    elif len(unique_articles) >= 5:
        confidence = "medium"
    elif is_data_available:
        confidence = "low"
    else:
        confidence = "none"

    result = {
        "risk_index": risk_index,
        "detected_events": detected_events,
        "sector_impacts": sector_impacts,
        "scenario_triggers": triggers,
        "articles_analyzed": len(unique_articles),
        "confidence": confidence,
        "macro_snapshot": _get_macro_snapshot(macro_data),
        "updated_at": datetime.now().isoformat(),
    }

    # 데이터 없으면 캐시 안 함 (수집 실패 가능성)
    if is_data_available:
        ttl = (
            _CRISIS_CACHE_TTL
            if risk_index["score"] >= 70
            else _CACHE_TTL
        )
        cache.set(cache_key, result, ttl=ttl)

    return result


async def get_geopolitical_risk_score() -> float:
    """지정학 리스크 점수만 반환 (매크로 점수 연동용)."""
    try:
        analysis = await get_geopolitical_analysis()
        return analysis.get("risk_index", {}).get("score", 20.0)
    except Exception:
        logger.warning("Geopolitical risk score fetch failed", exc_info=True)
        return 20.0
