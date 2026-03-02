# ── Stage 1: 의존성 설치 ──
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: 런타임 ──
FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성 (curl 제거 - healthcheck에서 Python urllib 사용)

# non-root 사용자 생성
RUN groupadd -r alphalens && useradd -r -g alphalens -d /app -s /sbin/nologin alphalens

# 의존성 복사
COPY --from=builder /install /usr/local

# 소스 복사
COPY backend/ backend/
COPY frontend/ frontend/
COPY run.py .

# 소유권 변경 및 non-root 전환
RUN chown -R alphalens:alphalens /app
USER alphalens

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

CMD ["python", "run.py"]
