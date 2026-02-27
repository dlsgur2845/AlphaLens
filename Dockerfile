FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성 (lxml 빌드에 필요할 수 있음)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# 의존성 먼저 설치 (캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY backend/ backend/
COPY frontend/ frontend/
COPY run.py .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["python", "run.py"]
