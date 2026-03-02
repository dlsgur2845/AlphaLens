"""API Key + JWT 인증 유틸리티."""

import time
from typing import Optional

import jwt
from fastapi import Header, HTTPException, Query

from backend.config import settings


async def verify_api_key(x_api_key: str = Header(default="")) -> None:
    """X-API-Key 헤더 또는 JWT Bearer 토큰 검증."""
    if not settings.api_key and not settings.jwt_secret:
        return  # 인증 미설정 → 개발 모드

    # 1. API Key 체크
    if settings.api_key and x_api_key == settings.api_key:
        return

    # 2. JWT Bearer 체크 (Authorization 헤더 또는 X-API-Key에 Bearer 토큰)
    if settings.jwt_secret and x_api_key.startswith("Bearer "):
        token = x_api_key[7:]
        try:
            jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            return
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")

    # 3. 둘 다 실패
    if settings.api_key or settings.jwt_secret:
        raise HTTPException(status_code=401, detail="Invalid API Key or token")


def create_access_token(data: dict = None) -> str:
    """JWT 액세스 토큰 생성."""
    if not settings.jwt_secret:
        raise HTTPException(status_code=500, detail="JWT not configured")
    payload = {
        "sub": "alphalens",
        "iat": int(time.time()),
        "exp": int(time.time()) + settings.jwt_expire_minutes * 60,
    }
    if data:
        payload.update(data)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def verify_ws_auth(api_key: str = Query(default="")) -> None:
    """WebSocket 인증 (query parameter)."""
    if not settings.api_key and not settings.jwt_secret:
        return

    # API Key 체크
    if settings.api_key and api_key == settings.api_key:
        return

    # JWT 체크
    if settings.jwt_secret and api_key:
        try:
            jwt.decode(api_key, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            return
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            pass

    if settings.api_key or settings.jwt_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")
