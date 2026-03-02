"""KR-FinBERT 감성분석 서비스.

snunlp/KR-FinBert-SC 모델을 사용한 한국어 금융 뉴스 감성분석.
torch/transformers 미설치 시 graceful fallback.
"""
import hashlib
import logging
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger(__name__)

_HAS_TRANSFORMERS = False
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    _HAS_TRANSFORMERS = True
except ImportError:
    logger.info("torch/transformers not installed - FinBERT disabled, using keyword fallback")


class FinBERTService:
    """KR-FinBERT 싱글턴 서비스."""

    MODEL_NAME = "snunlp/KR-FinBert-SC"
    LABELS = ["negative", "neutral", "positive"]
    LABEL_KR = {"negative": "부정", "neutral": "중립", "positive": "긍정"}

    def __init__(self, cache_size: int = 1000):
        self._model = None
        self._tokenizer = None
        self._available = _HAS_TRANSFORMERS
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._cache_size = cache_size
        self._loaded = False

    @property
    def available(self) -> bool:
        return self._available

    def _load_model(self) -> None:
        """Lazy model loading - 첫 호출 시 모델 로드."""
        if self._loaded or not self._available:
            return
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(self.MODEL_NAME)
            self._model = AutoModelForSequenceClassification.from_pretrained(self.MODEL_NAME)
            self._model.eval()
            self._loaded = True
            logger.info("KR-FinBERT model loaded successfully")
        except Exception as e:
            logger.warning("Failed to load KR-FinBERT: %s", e)
            self._available = False

    def _cache_key(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def _add_to_cache(self, key: str, result: dict) -> None:
        if len(self._cache) >= self._cache_size:
            self._cache.popitem(last=False)
        self._cache[key] = result

    def analyze(self, text: str) -> Optional[dict]:
        """단일 텍스트 감성분석.

        Returns:
            {"score": float(-1~1), "label": str, "label_kr": str,
             "confidence": float, "probabilities": {"negative": f, "neutral": f, "positive": f}}
            or None if not available
        """
        if not self._available:
            return None

        self._load_model()
        if not self._loaded:
            return None

        cache_key = self._cache_key(text)
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]

        try:
            inputs = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=512, padding=True)
            with torch.no_grad():
                outputs = self._model(**inputs)

            probs = torch.softmax(outputs.logits, dim=-1)[0].tolist()
            prob_dict = {label: round(p, 4) for label, p in zip(self.LABELS, probs)}

            # score: -1 (negative) ~ +1 (positive)
            score = prob_dict["positive"] - prob_dict["negative"]
            label_idx = probs.index(max(probs))
            label = self.LABELS[label_idx]
            confidence = max(probs)

            result = {
                "score": round(score, 4),
                "label": label,
                "label_kr": self.LABEL_KR[label],
                "confidence": round(confidence, 4),
                "probabilities": prob_dict,
            }
            self._add_to_cache(cache_key, result)
            return result
        except Exception as e:
            logger.warning("FinBERT analysis failed: %s", e)
            return None

    def analyze_batch(self, texts: list[str]) -> list[Optional[dict]]:
        """배치 감성분석."""
        return [self.analyze(text) for text in texts]


# 싱글턴
finbert = FinBERTService()
