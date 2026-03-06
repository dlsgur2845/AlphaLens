"""추천/비추천 종목 API 엔드포인트."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.services.cache_service import cache
from backend.services import scoring_service
from backend.utils.auth import verify_api_key
from backend.services.http_client import get_mobile_client
from backend.services.macro_service import get_macro_score
from backend.services.stock_service import _get_stock_list
from backend.services.recommendation_logic import (
    format_stock_item,
    derive_key_factors,
    derive_market_strategy,
    derive_sector_outlook,
    macro_label,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

# 동시 스코어링 세마포어 (외부 API 부하 제어, 다른 API 연결 여유 확보)
_CONCURRENCY_LIMIT = 5
_CACHE_KEY_PREFIX = "recommendations"
_CACHE_TTL = 300  # 5분

# 백그라운드 갱신 락
_refresh_lock = asyncio.Lock()


async def _score_single(code: str, semaphore: asyncio.Semaphore) -> dict | None:
    """세마포어 제한 하에 단일 종목 스코어링. 실패/타임아웃 시 None 반환."""
    async with semaphore:
        try:
            result = await asyncio.wait_for(
                scoring_service.calculate_score(code), timeout=15.0,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning("종목 스코어링 타임아웃 (%s)", code)
            return None
        except Exception as e:
            logger.warning("종목 스코어링 실패 (%s): %s", code, e)
            return None


async def _fetch_index_price(index_code: str) -> dict | None:
    """네이버 금융 모바일 API에서 주요 지수 현재가 조회."""
    try:
        client = get_mobile_client()
        resp = await client.get(
            f"https://m.stock.naver.com/api/index/{index_code}/basic",
        )
        data = resp.json()
        close_price = data.get("closePrice", "0").replace(",", "")
        change_raw = data.get("compareToPreviousClosePrice", "0").replace(",", "")
        change_pct = float(data.get("fluctuationsRatio", "0"))
        direction = data.get("compareToPreviousPrice", {}).get("name", "")
        change_val = float(change_raw)
        if direction in ("FALLING", "LOWER_LIMIT"):
            change_val = -abs(change_val)
            change_pct = -abs(change_pct)
        return {
            "value": float(close_price),
            "change": round(change_val, 2),
            "change_pct": round(change_pct, 2),
        }
    except Exception:
        logger.debug("지수 %s 조회 실패", index_code)
        return None


async def _build_market_summary() -> dict:
    """시장 요약 데이터 생성 (매크로 점수 + 지수 + 섹터 전망)."""
    cache_key = "market_summary:latest"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # 매크로 점수 + KOSPI/KOSDAQ 지수 병렬 조회
    macro_result, kospi_data, kosdaq_data = await asyncio.gather(
        get_macro_score(),
        _fetch_index_price("KOSPI"),
        _fetch_index_price("KOSDAQ"),
    )

    macro_score_val = macro_result.score
    macro_details = macro_result.details if isinstance(macro_result.details, dict) else {}

    # 환율 데이터 (매크로 서비스에서 이미 수집)
    usdkrw_info = macro_details.get("usdkrw", {})
    usd_krw = usdkrw_info.get("price") if usdkrw_info else None

    summary = {
        "kospi": kospi_data,
        "kosdaq": kosdaq_data,
        "macro_score": round(macro_score_val, 1),
        "macro_label": macro_label(macro_score_val),
        "usd_krw": round(usd_krw, 2) if usd_krw else None,
        "usd_krw_change_pct": round(usdkrw_info.get("change_pct", 0), 2) if usdkrw_info else None,
        "key_factors": derive_key_factors(macro_details, macro_score_val),
        "sector_outlook": derive_sector_outlook(macro_score_val, macro_details),
        "market_strategy": derive_market_strategy(macro_score_val, macro_details),
        "macro_breakdown": {
            "us_market": macro_result.breakdown.us_market,
            "fx": macro_result.breakdown.fx,
            "rates": macro_result.breakdown.rates,
            "commodities": macro_result.breakdown.commodities,
            "china": macro_result.breakdown.china,
        },
        "updated_at": datetime.now().isoformat(),
    }

    cache.set(cache_key, summary, ttl=300)  # 5분 캐시
    return summary


async def _build_recommendations(top_n: int = 5) -> dict:
    """전체 종목을 스코어링하여 추천/비추천 목록 생성."""
    start_time = time.time()

    # KOSPI + KOSDAQ 종목 리스트 가져오기
    all_stocks = await _get_stock_list()
    if not all_stocks:
        return {
            "recommended": [],
            "not_recommended": [],
            "market_summary": {"total_scanned": 0, "scored": 0, "failed": 0},
            "updated_at": datetime.now().isoformat(),
        }

    # 상위 종목 추출 (전체를 스코어링하면 너무 오래 걸리므로 시장별 상위 종목)
    # screener와 동일하게 앞에서부터 가져옴 (시가총액 순)
    kospi = [s for s in all_stocks if s["market"] == "KOSPI"][:50]
    kosdaq = [s for s in all_stocks if s["market"] == "KOSDAQ"][:30]
    target_stocks = kospi + kosdaq

    # 병렬 스코어링 (세마포어로 동시 실행 수 제어)
    semaphore = asyncio.Semaphore(_CONCURRENCY_LIMIT)
    tasks = [_score_single(s["code"], semaphore) for s in target_stocks]
    results = await asyncio.gather(*tasks)

    # 성공한 결과만 필터링
    scored = [r for r in results if r is not None]
    failed_count = len(results) - len(scored)

    # total_score 기준 정렬
    scored.sort(key=lambda r: r.total_score, reverse=True)

    # 추천: 상위 N개
    recommended = []
    for r in scored[:top_n]:
        item = format_stock_item(r, is_recommended=True)
        recommended.append(item)

    # 비추천: 하위 N개 (실패 종목 제외 - 이미 필터됨)
    not_recommended = []
    bottom = scored[-top_n:] if len(scored) >= top_n else scored
    bottom.reverse()  # 최하위부터
    for r in bottom:
        # 추천 목록과 겹치지 않게
        if r.code not in {item["code"] for item in recommended}:
            item = format_stock_item(r, is_recommended=False)
            not_recommended.append(item)

    elapsed = round(time.time() - start_time, 1)

    # 시장 요약 데이터 (매크로 + 지수 + 섹터 전망)
    market_summary_base = await _build_market_summary()
    market_summary = {**market_summary_base}
    market_summary["total_scanned"] = len(target_stocks)
    market_summary["scored"] = len(scored)
    market_summary["failed"] = failed_count
    market_summary["elapsed_seconds"] = elapsed

    return {
        "recommended": recommended,
        "not_recommended": not_recommended[:top_n],
        "market_summary": market_summary,
        "updated_at": datetime.now().isoformat(),
    }


async def _get_or_refresh_recommendations(top_n: int = 5) -> dict:
    """캐시된 추천 결과 반환. 만료 시 갱신."""
    cache_key = f"{_CACHE_KEY_PREFIX}:top_{top_n}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # 캐시 미스 - 락을 잡고 갱신 (중복 방지)
    async with _refresh_lock:
        # 더블 체크
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        result = await _build_recommendations(top_n)
        cache.set(cache_key, result, ttl=_CACHE_TTL)
        return result


@router.get("/market-summary")
async def get_market_summary():
    """시장 요약 API (매크로 + 지수). 추천 스코어링과 독립적으로 빠르게 반환."""
    try:
        summary = await _build_market_summary()
        return {"market_summary": summary, "updated_at": datetime.now().isoformat()}
    except Exception:
        logger.exception("시장 요약 생성 실패")
        raise HTTPException(status_code=500, detail="시장 요약 데이터를 불러올 수 없습니다")


@router.get("")
async def get_recommendations(
    top_n: int = Query(5, ge=1, le=20, description="추천/비추천 종목 수"),
):
    """추천/비추천 종목 목록 API.

    전체 KOSPI/KOSDAQ 상위 종목을 실시간 스코어링하여
    추천(상위)과 비추천(하위) 목록을 반환합니다.
    결과는 5분간 캐시됩니다.
    """
    try:
        return await _get_or_refresh_recommendations(top_n)
    except Exception:
        logger.exception("추천 목록 생성 실패")
        raise HTTPException(
            status_code=500,
            detail="추천 목록을 생성하는 중 오류가 발생했습니다",
        )
