# ── Stage 1: 의존성 설치 ──
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .

# PyTorch CPU-only 먼저 설치 (CUDA 제거: ~3.5GB 절약), 그 후 나머지 의존성
RUN pip install --no-cache-dir --prefix=/install \
    torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: 런타임 ──
FROM python:3.12-slim

WORKDIR /app

# HuggingFace 캐시 경로 통일 (빌드/런타임 동일 경로 사용)
ENV HF_HOME=/app/.hf_cache

# non-root 사용자 생성
RUN groupadd -r alphalens && useradd -r -g alphalens -d /app -s /sbin/nologin alphalens

# 의존성 복사
COPY --from=builder /install /usr/local

# 소스 복사
COPY backend/ backend/
COPY frontend/ frontend/
COPY run.py .

# KR-FinBERT 모델을 빌드 타임에 미리 다운로드 (매 실행시 다운로드 방지)
RUN mkdir -p $HF_HOME && \
    python -c "\
from transformers import AutoTokenizer, AutoModelForSequenceClassification; \
AutoTokenizer.from_pretrained('snunlp/KR-FinBert-SC'); \
AutoModelForSequenceClassification.from_pretrained('snunlp/KR-FinBert-SC'); \
print('KR-FinBERT model cached successfully')"

# 소유권 변경 및 non-root 전환
RUN chown -R alphalens:alphalens /app
USER alphalens

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

CMD ["python", "run.py"]
