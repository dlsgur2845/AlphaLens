"""뉴스 서비스 - 네이버 금융 모바일 API + 감성분석."""

from __future__ import annotations

import asyncio
import html
from datetime import datetime

from backend.models.schemas import NewsArticle, NewsResult
from backend.services.cache_service import cache
from backend.services.http_client import get_mobile_client
from backend.utils.sentiment import analyze_sentiment


async def get_stock_news(
    stock_code: str,
    stock_name: str | None = None,
    max_articles: int = 20,
) -> NewsResult:
    """종목 관련 뉴스 조회 + 감성분석."""
    cache_key = f"news:{stock_code}:{max_articles}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    if not stock_name:
        from backend.services.stock_service import _fetch_krx_stock_list
        stocks = await _fetch_krx_stock_list()
        stock_name = stock_code
        for s in stocks:
            if s["code"] == stock_code:
                stock_name = s["name"]
                break

    # 네이버 금융 모바일 API에서 뉴스 가져오기
    url = f"https://m.stock.naver.com/api/news/stock/{stock_code}"

    raw_articles: list[dict] = []

    client = get_mobile_client()
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

        for record in data:
            items = record.get("items", [])
            for item in items:
                title = html.unescape(item.get("title", ""))
                office = item.get("officeName", "")
                dt_str = item.get("datetime", "")
                oid = item.get("officeId", "")
                aid = item.get("articleId", "")
                body = html.unescape(item.get("body", ""))

                # 날짜 포맷팅
                date_display = ""
                if len(dt_str) >= 12:
                    try:
                        dt = datetime.strptime(dt_str[:12], "%Y%m%d%H%M")
                        date_display = dt.strftime("%Y-%m-%d %H:%M")
                    except ValueError:
                        date_display = dt_str

                link = f"https://n.news.naver.com/mnews/article/{oid}/{aid}"

                raw_articles.append({
                    "title": title,
                    "link": link,
                    "source": office,
                    "date": date_display,
                    "body": body,
                })

                if len(raw_articles) >= max_articles:
                    break

            if len(raw_articles) >= max_articles:
                break

    except Exception:
        pass

    # 감성분석 수행
    articles: list[NewsArticle] = []
    pos_count = neg_count = neu_count = 0
    total_sentiment = 0.0

    for raw in raw_articles:
        # 제목(가중) + 본문 분리 감성분석
        score, label = analyze_sentiment(raw["title"], raw.get("body", ""))

        articles.append(
            NewsArticle(
                title=raw["title"],
                link=raw["link"],
                source=raw["source"],
                date=raw["date"],
                summary=raw["title"],
                sentiment_score=score,
                sentiment_label=label,
            )
        )

        total_sentiment += score
        if label == "긍정":
            pos_count += 1
        elif label == "부정":
            neg_count += 1
        else:
            neu_count += 1

    overall = total_sentiment / len(articles) if articles else 0.0
    if overall > 0.15:
        overall_label = "긍정"
    elif overall < -0.15:
        overall_label = "부정"
    else:
        overall_label = "중립"

    result = NewsResult(
        code=stock_code,
        name=stock_name or stock_code,
        articles=articles,
        overall_sentiment=round(overall, 3),
        overall_label=overall_label,
        positive_count=pos_count,
        negative_count=neg_count,
        neutral_count=neu_count,
    )

    cache.set(cache_key, result, ttl=600)
    return result
