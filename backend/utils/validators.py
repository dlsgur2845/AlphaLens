"""공통 입력 유효성 검증 유틸리티."""

import re

from fastapi import HTTPException


def validate_stock_code(code: str) -> str:
    """종목코드 유효성 검증 (6자리 숫자). 검증 통과 시 코드 반환."""
    if not re.match(r"^\d{6}$", code):
        raise HTTPException(status_code=400, detail="종목코드는 6자리 숫자여야 합니다")
    return code
