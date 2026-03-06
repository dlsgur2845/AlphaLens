"""관련기업 탐색 서비스 - BFS 기반, 무한루프 방지."""

from __future__ import annotations

import asyncio
from collections import deque

from bs4 import BeautifulSoup

from backend.models.schemas import RelatedCompany
from backend.services.cache_service import cache
from backend.services.http_client import get_desktop_client
from backend.services.stock_service import _get_stock_list, get_price_history

# 병렬 요청 동시성 제한 (네이버 rate limit 방지)
_SEMAPHORE = asyncio.Semaphore(3)

# 주요 그룹 키워드
GROUP_KEYWORDS = [
    "삼성", "SK", "LG", "현대", "롯데", "포스코", "POSCO", "한화",
    "GS", "두산", "CJ", "신세계", "카카오", "네이버", "NAVER",
    "KT", "HD", "LS", "OCI", "효성", "코오롱", "아모레",
    "셀트리온", "크래프톤", "엔씨", "넥슨", "하이브",
]


async def _get_group_companies(name: str, code: str) -> list[dict]:
    """그룹사/계열사 탐색 - 회사명에서 그룹명 추출."""
    matched_keyword = None
    for kw in GROUP_KEYWORDS:
        if kw in name:
            matched_keyword = kw
            break

    if not matched_keyword:
        return []

    stocks = await _get_stock_list()
    results = []

    for s in stocks:
        if s["code"] == code:
            continue
        if matched_keyword in s["name"]:
            results.append({
                "code": s["code"],
                "name": s["name"],
                "market": s["market"],
                "relation_type": f"계열사({matched_keyword}그룹)",
            })

    return results[:15]


async def _get_sector_companies(code: str) -> list[dict]:
    """동종업계 기업 탐색 - 네이버 금융 업종 페이지."""
    # 네이버 금융에서 해당 종목의 업종 동종업계 정보 가져오기
    url = f"https://finance.naver.com/item/main.naver?code={code}"

    client = get_desktop_client()
    try:
        resp = await client.get(url)
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "lxml")

    # 동일업종 비교 섹션에서 종목 추출
    results = []
    compare_section = soup.select("table.tb_type1_ifm tbody tr")
    for row in compare_section:
        link = row.select_one("td a")
        if not link:
            continue

        comp_name = link.get_text(strip=True)
        href = link.get("href", "")
        comp_code = href.split("code=")[-1] if "code=" in href else ""

        if comp_code and comp_code != code and len(comp_code) == 6:
            results.append({
                "code": comp_code,
                "name": comp_name,
                "market": "",
                "relation_type": "동일업종",
            })

    # 업종 정보에서도 탐색
    if not results:
        sector_link = soup.select_one("div.section.trade_compare h4 em a")
        if sector_link:
            sector_href = sector_link.get("href", "")
            sector_name = sector_link.get_text(strip=True)
            if sector_href:
                try:
                    full_url = f"https://finance.naver.com{sector_href}"
                    resp2 = await client.get(full_url)
                    soup2 = BeautifulSoup(resp2.text, "lxml")

                    rows = soup2.select("table.type_1 tbody tr")
                    for row in rows:
                        a_tag = row.select_one("td a.name_area")
                        if not a_tag:
                            a_tag = row.select_one("td a")
                        if not a_tag:
                            continue

                        comp_name = a_tag.get_text(strip=True)
                        href = a_tag.get("href", "")
                        comp_code = href.split("code=")[-1].split("&")[0] if "code=" in href else ""

                        if comp_code and comp_code != code and len(comp_code) == 6:
                            results.append({
                                "code": comp_code,
                                "name": comp_name,
                                "market": "",
                                "relation_type": f"동일업종({sector_name})",
                            })
                except Exception:
                    pass

    # 시장 정보 보완
    stocks = await _get_stock_list()
    stock_map = {s["code"]: s["market"] for s in stocks}
    for r in results:
        if not r["market"]:
            r["market"] = stock_map.get(r["code"], "")

    return results[:15]


async def _get_recent_change(code: str) -> float | None:
    """최근 수익률 계산 (Semaphore + 타임아웃)."""
    try:
        async with _SEMAPHORE:
            history = await asyncio.wait_for(
                get_price_history(code, days=10), timeout=3.0,
            )
    except (asyncio.TimeoutError, Exception):
        return None
    if not history or len(history.prices) < 2:
        return None

    first = history.prices[0].close
    last = history.prices[-1].close
    if first == 0:
        return None
    return round(((last - first) / first) * 100, 2)


async def find_related_companies(
    stock_code: str,
    max_depth: int = 1,
    max_companies: int = 10,
) -> list[RelatedCompany]:
    """BFS 기반 관련기업 탐색. visited set으로 무한루프 방지."""

    cache_key = f"related:{stock_code}:{max_depth}:{max_companies}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    visited: set[str] = set()
    queue: deque[tuple[str, str, int]] = deque()
    results: list[RelatedCompany] = []

    # 시작 종목 이름 조회
    stocks = await _get_stock_list()
    root_name = stock_code
    for s in stocks:
        if s["code"] == stock_code:
            root_name = s["name"]
            break

    visited.add(stock_code)
    queue.append((stock_code, root_name, 0))

    while queue and len(results) < max_companies:
        current_code, current_name, depth = queue.popleft()

        if depth > max_depth:
            continue

        related_raw: list[dict] = []

        if depth == 0:
            # 첫 레벨: 계열사 + 동일업종 모두 탐색
            group_task = _get_group_companies(current_name, current_code)
            sector_task = _get_sector_companies(current_code)
            group_results, sector_results = await asyncio.gather(
                group_task, sector_task
            )
            related_raw.extend(group_results)
            related_raw.extend(sector_results)
        else:
            # 깊은 레벨: 그룹사만 (네트워크 호출 최소화)
            group_results = await _get_group_companies(current_name, current_code)
            related_raw.extend(group_results[:5])

        # 중복 제거
        new_items: list[dict] = []
        for item in related_raw:
            if item["code"] in visited:
                continue
            if len(results) + len(new_items) >= max_companies:
                break
            visited.add(item["code"])
            new_items.append(item)

        # 수익률 병렬 계산 (Semaphore로 동시 요청 3개 제한)
        if new_items:
            change_results = await asyncio.gather(
                *[_get_recent_change(item["code"]) for item in new_items],
                return_exceptions=True,
            )

            for item, change_pct in zip(new_items, change_results):
                if isinstance(change_pct, Exception):
                    change_pct = None

                company = RelatedCompany(
                    code=item["code"],
                    name=item["name"],
                    market=item["market"],
                    relation_type=item["relation_type"],
                    depth=depth + 1,
                    change_pct=change_pct,
                )
                results.append(company)

                if depth + 1 < max_depth:
                    queue.append((item["code"], item["name"], depth + 1))

    cache.set(cache_key, results, ttl=600)
    return results
