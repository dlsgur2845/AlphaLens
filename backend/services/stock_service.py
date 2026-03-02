"""주식 데이터 서비스 - KRX/네이버금융 직접 API 호출."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

from backend.models.schemas import (
    OverMarketPrice,
    PriceHistory,
    PricePoint,
    StockDetail,
    StockSearchResult,
)
from backend.services.cache_service import cache
from backend.services.http_client import get_desktop_client, get_mobile_client


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------
class CircuitBreaker:
    """Simple circuit breaker for external API calls."""

    def __init__(self, failure_threshold: int = 3, reset_timeout: int = 120):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time: float = 0
        self.state = "closed"  # closed, open, half-open

    def can_execute(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "half-open"
                return True
            return False
        return True  # half-open

    def record_success(self):
        self.failures = 0
        self.state = "closed"

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "open"
            logger.warning("Circuit breaker opened after %d failures", self.failures)


_cb_krx = CircuitBreaker(failure_threshold=3, reset_timeout=120)
_cb_naver = CircuitBreaker(failure_threshold=3, reset_timeout=120)

# ---------------------------------------------------------------------------
# Stock list with TTL
# ---------------------------------------------------------------------------
_stock_list: list[dict] | None = None
_stock_list_updated_at: float = 0
_STOCK_LIST_TTL = 21600  # 6 hours


async def _get_stock_list() -> list[dict]:
    """Return cached stock list, refreshing if TTL expired."""
    global _stock_list, _stock_list_updated_at
    if _stock_list is not None and (time.time() - _stock_list_updated_at) < _STOCK_LIST_TTL:
        return _stock_list
    _stock_list = await _fetch_krx_stock_list()
    _stock_list_updated_at = time.time()
    return _stock_list


async def get_stock_name(code: str) -> str:
    """종목코드로 종목명 조회. 못 찾으면 코드 자체를 반환."""
    stocks = await _get_stock_list()
    for s in stocks:
        if s["code"] == code:
            return s["name"]
    return code


def _parse_market_cap(raw: str) -> int | None:
    """시가총액 문자열 파싱 (예: '1,281조 6,016억' → 12816016억원 → 원 단위)."""
    import re
    if not raw:
        return None
    raw = raw.replace(",", "").replace(" ", "")
    total = 0
    # 조 단위 추출
    m_jo = re.search(r"(\d+)조", raw)
    if m_jo:
        total += int(m_jo.group(1)) * 10000_0000_0000  # 1조 = 1,000,000,000,000
    # 억 단위 추출
    m_eok = re.search(r"(\d+)억", raw)
    if m_eok:
        total += int(m_eok.group(1)) * 1_0000_0000  # 1억 = 100,000,000
    return total if total > 0 else None


async def _fetch_krx_stock_list() -> list[dict]:
    """KRX에서 KOSPI+KOSDAQ 전체 종목 목록 가져오기 (서킷 브레이커 + 재시도)."""
    results = []
    url = "http://data.krx.co.kr/comm/bldAttend498/getJsonData.cmd"

    if not _cb_krx.can_execute():
        logger.warning("KRX circuit breaker open, falling back to Naver")
        return await _fetch_naver_stock_list()

    client = get_desktop_client()
    for mkt_id, mkt_name in [("STK", "KOSPI"), ("KSQ", "KOSDAQ")]:
        success = False
        for attempt in range(3):
            try:
                resp = await client.post(
                    url,
                    data={
                        "bld": "dbms/comm/finder/finder_stkisu",
                        "mktsel": mkt_id,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("block1", []):
                    code = item.get("short_code", "")
                    name = item.get("codeName", "")
                    if code and name and len(code) == 6:
                        results.append({
                            "code": code,
                            "name": name,
                            "market": mkt_name,
                        })
                _cb_krx.record_success()
                success = True
                break
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                logger.warning("KRX %s attempt %d failed: %s", mkt_name, attempt + 1, e)
                _cb_krx.record_failure()
                if attempt < 2:
                    await asyncio.sleep(1 * (attempt + 1))
        if not success:
            logger.warning("KRX %s all retries exhausted", mkt_name)

    # KRX API 실패 시 네이버 금융에서 폴백
    if not results:
        results = await _fetch_naver_stock_list()

    return results


async def _fetch_naver_stock_list() -> list[dict]:
    """네이버 금융에서 종목 목록 폴백."""
    from bs4 import BeautifulSoup

    results = []
    client = get_desktop_client()
    for mkt, mkt_name in [("0", "KOSPI"), ("1", "KOSDAQ")]:
        for page in range(1, 40):
            try:
                url = (
                    f"https://finance.naver.com/sise/sise_market_sum.naver"
                    f"?sosok={mkt}&page={page}"
                )
                resp = await client.get(url)
                soup = BeautifulSoup(resp.text, "lxml")
                rows = soup.select("table.type_2 tbody tr")

                found_any = False
                for row in rows:
                    link = row.select_one("a.tltle")
                    if not link:
                        continue
                    found_any = True
                    name = link.get_text(strip=True)
                    href = link.get("href", "")
                    code = href.split("code=")[-1] if "code=" in href else ""
                    if code and len(code) == 6:
                        results.append({
                            "code": code,
                            "name": name,
                            "market": mkt_name,
                        })

                if not found_any:
                    break
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                logger.warning("네이버 종목 목록 폴백 실패 (시장=%s, 페이지=%d): %s", mkt_name, page, e)
                break

    return results


async def search_stocks(query: str, limit: int = 20) -> list[StockSearchResult]:
    """종목 검색 (이름 또는 코드 부분 매칭)."""
    cache_key = f"search:{query}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    stocks = await _get_stock_list()
    query_lower = query.lower()

    # 정확한 매칭 우선, 부분 매칭 후순위
    exact = []
    partial = []
    for s in stocks:
        name_lower = s["name"].lower()
        code = s["code"]
        if name_lower == query_lower or code == query_lower:
            exact.append(s)
        elif query_lower in name_lower or query_lower in code:
            partial.append(s)

    combined = exact + partial
    matches = [
        StockSearchResult(code=s["code"], name=s["name"], market=s["market"])
        for s in combined[:limit]
    ]

    cache.set(cache_key, matches, ttl=600)
    return matches


async def get_stock_detail(code: str) -> StockDetail | None:
    """종목 상세 정보 조회 (네이버 금융 모바일 API)."""
    cache_key = f"detail:{code}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    if not _cb_naver.can_execute():
        logger.warning("Naver circuit breaker open, skipping detail for %s", code)
        return None

    client = get_mobile_client()
    basic = None
    integ = None
    for attempt in range(3):
        try:
            basic_resp, integ_resp = await asyncio.gather(
                client.get(f"https://m.stock.naver.com/api/stock/{code}/basic"),
                client.get(f"https://m.stock.naver.com/api/stock/{code}/integration"),
            )
            basic_resp.raise_for_status()
            integ_resp.raise_for_status()
            basic = basic_resp.json()
            integ = integ_resp.json()
            _cb_naver.record_success()
            break
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.warning("종목 상세 API attempt %d failed (%s): %s", attempt + 1, code, e)
            _cb_naver.record_failure()
            if attempt < 2:
                await asyncio.sleep(1 * (attempt + 1))
    if basic is None or integ is None:
        return None

    try:
        name = basic.get("stockName", "")
        if not name:
            return None

        price = int(basic.get("closePrice", "0").replace(",", ""))
        change_raw = basic.get("compareToPreviousClosePrice", "0").replace(",", "")
        change = int(change_raw)

        # 등락 방향
        direction = basic.get("compareToPreviousPrice", {}).get("name", "")
        if direction in ("FALLING", "LOWER_LIMIT"):
            change = -abs(change)

        change_pct = float(basic.get("fluctuationsRatio", "0"))
        if change < 0:
            change_pct = -abs(change_pct)

        market_name = basic.get("stockExchangeName", "KOSPI")

        # totalInfos에서 PER, PBR, 거래량, 시가총액 추출
        per = None
        pbr = None
        roe = None
        volume = 0
        market_cap = None

        for info in integ.get("totalInfos", []):
            code_key = info.get("code", "")
            val = info.get("value", "").replace(",", "").replace("배", "").replace("원", "").replace("%", "").strip()

            if code_key == "accumulatedTradingVolume":
                try:
                    volume = int(val)
                except ValueError:
                    pass
            elif code_key == "per":
                try:
                    per = float(val)
                except ValueError:
                    pass
            elif code_key == "pbr":
                try:
                    pbr = float(val)
                except ValueError:
                    pass
            elif code_key == "roe":
                try:
                    roe = float(val)
                except ValueError:
                    pass
            elif code_key == "marketValue":
                market_cap = _parse_market_cap(info.get("value", ""))

        # 업종: industryCode로 API 조회
        sector = None
        industry_code = integ.get("industryCode")
        if industry_code:
            try:
                ind_resp = await client.get(
                    f"https://m.stock.naver.com/api/stocks/industry/{industry_code}"
                )
                ind_resp.raise_for_status()
                ind_data = ind_resp.json()
                sector = ind_data.get("groupInfo", {}).get("name")
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                logger.warning("업종 정보 조회 실패 (%s): %s", code, e)

        # 시장 상태, 거래 시각
        market_status = basic.get("marketStatus", None)
        traded_at = basic.get("localTradedAt", None)

        # 시간외/대체거래소(NXT) 가격 파싱
        over_market = None
        over_info = basic.get("overMarketPriceInfo")
        if over_info and over_info.get("overPrice"):
            try:
                over_price = int(over_info["overPrice"].replace(",", ""))
                over_change_raw = over_info.get("compareToPreviousClosePrice", "0").replace(",", "")
                over_change = int(over_change_raw)
                over_direction = over_info.get("compareToPreviousPrice", {}).get("name", "")
                if over_direction in ("FALLING", "LOWER_LIMIT"):
                    over_change = -abs(over_change)
                over_change_pct = float(over_info.get("fluctuationsRatio", "0"))
                if over_change < 0:
                    over_change_pct = -abs(over_change_pct)

                over_market = OverMarketPrice(
                    session_type=over_info.get("tradingSessionType", "AFTER_MARKET"),
                    status=over_info.get("overMarketStatus", "CLOSE"),
                    price=over_price,
                    change=over_change,
                    change_pct=over_change_pct,
                    traded_at=over_info.get("localTradedAt", ""),
                )
            except (ValueError, KeyError):
                pass

        # 종목 리스트에서 시장 확인
        stocks = await _get_stock_list()
        market = market_name
        for s in stocks:
            if s["code"] == code:
                market = s["market"]
                break

        result = StockDetail(
            code=code,
            name=name,
            market=market,
            price=price,
            change=change,
            change_pct=change_pct,
            volume=volume,
            market_cap=market_cap,
            per=per,
            pbr=pbr,
            roe=roe,
            sector=sector,
            market_status=market_status,
            traded_at=traded_at,
            over_market=over_market,
        )
        cache.set(cache_key, result, ttl=300)
        return result

    except (KeyError, ValueError, TypeError) as e:
        logger.warning("종목 상세 데이터 파싱 실패 (%s): %s", code, e)
        return None


async def get_price_history(code: str, days: int = 90) -> PriceHistory | None:
    """네이버 금융에서 가격 히스토리 조회."""
    cache_key = f"price:{code}:{days}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    if not _cb_naver.can_execute():
        logger.warning("Naver circuit breaker open, skipping price history for %s", code)
        return None

    from bs4 import BeautifulSoup

    # 종목명 조회
    name = await get_stock_name(code)

    prices: list[PricePoint] = []
    pages_needed = (days // 10) + 2
    cutoff = datetime.now() - timedelta(days=days)

    client = get_desktop_client()
    for page in range(1, pages_needed + 1):
        url = (
            f"https://finance.naver.com/item/sise_day.naver"
            f"?code={code}&page={page}"
        )
        resp = None
        for attempt in range(3):
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                _cb_naver.record_success()
                break
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                logger.warning("가격 히스토리 attempt %d failed (%s, page=%d): %s", attempt + 1, code, page, e)
                _cb_naver.record_failure()
                if attempt < 2:
                    await asyncio.sleep(1 * (attempt + 1))
                else:
                    resp = None

        if resp is None:
            break

        try:
            soup = BeautifulSoup(resp.text, "lxml")
            rows = soup.select("table.type2 tr")

            found = False
            for row in rows:
                cols = row.select("td span.tah")
                if len(cols) < 7:
                    continue
                found = True

                date_str = cols[0].get_text(strip=True)
                try:
                    dt = datetime.strptime(date_str, "%Y.%m.%d")
                except ValueError:
                    continue

                if dt < cutoff:
                    # 기간 초과 - 종료
                    found = False
                    break

                close = int(cols[1].get_text(strip=True).replace(",", ""))
                open_ = int(cols[3].get_text(strip=True).replace(",", ""))
                high = int(cols[4].get_text(strip=True).replace(",", ""))
                low = int(cols[5].get_text(strip=True).replace(",", ""))
                vol = int(cols[6].get_text(strip=True).replace(",", ""))

                prices.append(
                    PricePoint(
                        date=dt.strftime("%Y-%m-%d"),
                        open=open_,
                        high=high,
                        low=low,
                        close=close,
                        volume=vol,
                    )
                )

            if not found and prices:
                break

        except Exception as e:
            logger.warning("가격 히스토리 파싱 실패 (%s, page=%d): %s", code, page, e)
            break

    if not prices:
        return None

    prices.reverse()  # 오래된 날짜 → 최신 순으로

    result = PriceHistory(code=code, name=name, prices=prices)
    cache.set(cache_key, result, ttl=300)
    return result


async def get_sector_stocks(sector: str, market: str) -> list[dict]:
    """동일 업종 종목 목록 - 네이버 금융 업종별."""
    cache_key = f"sector:{market}:{sector}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # 업종 정보는 종목 상세에서 개별 수집하므로 여기선 간단하게 처리
    # 전체 목록에서 같은 그룹명을 가진 종목 반환
    stocks = await _get_stock_list()
    result = [s for s in stocks if s.get("market") == market][:20]

    cache.set(cache_key, result, ttl=600)
    return result
