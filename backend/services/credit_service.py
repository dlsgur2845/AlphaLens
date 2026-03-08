"""신용잔고 데이터 서비스 - 네이버 금융 스크래핑."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

from backend.services.cache_service import cache
from backend.services.http_client import get_desktop_client
from backend.services.stock_service import CircuitBreaker

_cb_credit = CircuitBreaker(failure_threshold=3, reset_timeout=300)


async def get_credit_balance(code: str) -> dict | None:
    """종목의 신용잔고 데이터를 조회.

    Returns:
        dict with keys:
            credit_ratio: 신용비율 (%)
            credit_amount: 신용잔고 금액
            short_ratio: 대차잔고비율 (%)
        or None if unavailable
    """
    cache_key = f"credit:{code}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached != "_none_" else None

    result = await _fetch_naver_credit(code)

    if result:
        cache.set(cache_key, result, ttl=3600)  # 1시간 (T+2 지연 데이터)
    else:
        cache.set(cache_key, "_none_", ttl=300)  # 실패 시 5분

    return result


async def _fetch_naver_credit(code: str) -> dict | None:
    """네이버 금융 sise 페이지에서 신용비율 추출."""
    if not _cb_credit.can_execute():
        return None

    from bs4 import BeautifulSoup

    client = get_desktop_client()

    try:
        resp = await client.get(
            f"https://finance.naver.com/item/sise.naver?code={code}"
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        result = {}

        # 종합 정보 테이블에서 신용비율 등 추출
        for td in soup.select("td"):
            text = td.get_text(strip=True)

            # 신용비율 (예: "2.34%")
            if "신용비율" in text:
                val_td = td.find_next_sibling("td")
                if val_td:
                    val = val_td.get_text(strip=True).replace("%", "").replace(",", "")
                    try:
                        result["credit_ratio"] = float(val)
                    except ValueError:
                        pass

        # 테이블 내 id="tab_con1" 영역에서 신용비율 탐색 (대체 위치)
        if "credit_ratio" not in result:
            for span in soup.select("span.blind, em"):
                parent = span.parent
                if parent and "신용비율" in parent.get_text():
                    siblings = parent.find_next_siblings()
                    for sib in siblings:
                        val = sib.get_text(strip=True).replace("%", "").replace(",", "")
                        try:
                            result["credit_ratio"] = float(val)
                            break
                        except ValueError:
                            continue

        # 대차잔고(공매도) 데이터 시도
        try:
            resp2 = await client.get(
                f"https://finance.naver.com/item/sise_deal.naver?code={code}"
            )
            resp2.raise_for_status()
            soup2 = BeautifulSoup(resp2.text, "lxml")

            # 대차잔고비율 추출
            for td2 in soup2.select("td"):
                t = td2.get_text(strip=True)
                if "대차잔고" in t:
                    val_td = td2.find_next_sibling("td")
                    if val_td:
                        val = val_td.get_text(strip=True).replace("%", "").replace(",", "")
                        try:
                            result["short_ratio"] = float(val)
                        except ValueError:
                            pass
        except Exception:
            pass  # 대차잔고는 보조 데이터

        if result:
            _cb_credit.record_success()
            # 기본값 채우기
            result.setdefault("credit_ratio", 0.0)
            result.setdefault("short_ratio", 0.0)
            return result

        # 데이터 추출 실패해도 CB는 성공으로 (HTTP는 성공)
        _cb_credit.record_success()
        return None

    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.warning("신용잔고 조회 실패 (%s): %s", code, e)
        _cb_credit.record_failure()
        return None
    except Exception as e:
        logger.warning("신용잔고 파싱 실패 (%s): %s", code, e)
        return None
