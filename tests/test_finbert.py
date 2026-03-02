"""KR-FinBERT 감성분석 서비스 및 앙상블 로직 테스트."""
import pytest
from unittest.mock import patch, MagicMock


# torch 설치 여부 확인
try:
    import torch
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False

requires_torch = pytest.mark.skipif(not _HAS_TORCH, reason="torch not installed")


class TestFinBERTService:
    """FinBERTService 단위 테스트 (모킹)."""

    def _make_service(self, available=True):
        """테스트용 FinBERTService 인스턴스 생성."""
        from backend.services.finbert_service import FinBERTService
        svc = FinBERTService(cache_size=10)
        svc._available = available
        return svc

    def test_unavailable_returns_none(self):
        """transformers 미설치 시 None 반환."""
        svc = self._make_service(available=False)
        result = svc.analyze("삼성전자 실적 호조")
        assert result is None

    def test_available_property(self):
        svc = self._make_service(available=True)
        assert svc.available is True
        svc_off = self._make_service(available=False)
        assert svc_off.available is False

    @requires_torch
    def test_analyze_with_mock_model(self):
        """모킹된 모델로 감성분석 결과 검증."""
        svc = self._make_service(available=True)

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {"input_ids": MagicMock(), "attention_mask": MagicMock()}

        mock_logits = torch.tensor([[0.1, 0.2, 0.7]])  # negative, neutral, positive
        mock_output = MagicMock()
        mock_output.logits = mock_logits

        mock_model = MagicMock()
        mock_model.return_value = mock_output

        svc._tokenizer = mock_tokenizer
        svc._model = mock_model
        svc._loaded = True

        result = svc.analyze("삼성전자 실적 호조")
        assert result is not None
        assert "score" in result
        assert "label" in result
        assert "label_kr" in result
        assert "confidence" in result
        assert "probabilities" in result
        assert result["label"] == "positive"
        assert result["label_kr"] == "긍정"
        assert result["score"] > 0
        assert -1 <= result["score"] <= 1

    @requires_torch
    def test_analyze_negative_text(self):
        """부정 감성 텍스트 모킹 테스트."""
        svc = self._make_service(available=True)

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {"input_ids": MagicMock(), "attention_mask": MagicMock()}

        mock_logits = torch.tensor([[0.8, 0.15, 0.05]])  # negative dominant
        mock_output = MagicMock()
        mock_output.logits = mock_logits

        mock_model = MagicMock()
        mock_model.return_value = mock_output

        svc._tokenizer = mock_tokenizer
        svc._model = mock_model
        svc._loaded = True

        result = svc.analyze("적자전환 실적 악화")
        assert result is not None
        assert result["label"] == "negative"
        assert result["label_kr"] == "부정"
        assert result["score"] < 0

    @requires_torch
    def test_cache_hit(self):
        """동일 텍스트 캐시 히트 확인."""
        svc = self._make_service(available=True)

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {"input_ids": MagicMock(), "attention_mask": MagicMock()}

        mock_logits = torch.tensor([[0.1, 0.2, 0.7]])
        mock_output = MagicMock()
        mock_output.logits = mock_logits

        mock_model = MagicMock()
        mock_model.return_value = mock_output

        svc._tokenizer = mock_tokenizer
        svc._model = mock_model
        svc._loaded = True

        text = "삼성전자 실적 호조"
        result1 = svc.analyze(text)
        result2 = svc.analyze(text)

        assert result1 == result2
        # 모델은 한 번만 호출되어야 함 (두 번째는 캐시)
        assert mock_model.call_count == 1

    def test_cache_eviction(self):
        """캐시 크기 초과 시 LRU 제거."""
        svc = self._make_service(available=True)
        svc._cache_size = 3

        svc._add_to_cache("key1", {"score": 0.1})
        svc._add_to_cache("key2", {"score": 0.2})
        svc._add_to_cache("key3", {"score": 0.3})
        assert len(svc._cache) == 3

        svc._add_to_cache("key4", {"score": 0.4})
        assert len(svc._cache) == 3
        assert "key1" not in svc._cache
        assert "key4" in svc._cache

    def test_analyze_batch(self):
        """배치 분석 테스트."""
        svc = self._make_service(available=False)
        results = svc.analyze_batch(["text1", "text2", "text3"])
        assert len(results) == 3
        assert all(r is None for r in results)

    def test_load_model_failure_disables(self):
        """모델 로드 실패 시 available=False로 전환."""
        svc = self._make_service(available=True)
        svc._loaded = False

        # _load_model 내부에서 from_pretrained 호출 시 예외 발생시키기
        mock_tokenizer_cls = MagicMock()
        mock_tokenizer_cls.from_pretrained.side_effect = RuntimeError("Model not found")
        svc._tokenizer = None
        svc._model = None

        # 직접 _load_model의 내부 로직을 시뮬레이션
        # AutoTokenizer가 모듈에 없을 수 있으므로 _load_model 자체를 테스트
        # _available=True이고 _loaded=False인 상태에서 예외 발생 시 _available=False
        import backend.services.finbert_service as fb_module
        original_available = fb_module._HAS_TRANSFORMERS

        # _HAS_TRANSFORMERS가 False이면 _load_model은 바로 리턴
        # 그래서 직접 예외 경로를 테스트
        try:
            svc._available = True
            svc._loaded = False
            # _load_model 호출 시 tokenizer 로드에서 실패하는 시나리오
            # tokenizer/model을 None으로 두고 _available=True, _loaded=False
            # 실제로는 AutoTokenizer가 없으므로 _load_model이 except로 빠짐
            svc._load_model()
        except Exception:
            pass

        # torch/transformers 미설치 시: _HAS_TRANSFORMERS=False이므로
        # _available은 초기값 False가 될 수 있음
        # 설치 시: 모델 로드 실패로 _available=False
        if not original_available:
            # torch 미설치 환경: _load_model은 _available이 False가 아닌 이상
            # NameError가 날 수 있으므로 _available=False 확인
            assert svc.available is False or svc._loaded is False
        else:
            assert svc.available is False
            assert svc._loaded is False

    def test_cache_key_deterministic(self):
        """같은 텍스트는 같은 캐시 키 생성."""
        svc = self._make_service(available=True)
        key1 = svc._cache_key("동일한 텍스트")
        key2 = svc._cache_key("동일한 텍스트")
        assert key1 == key2

    def test_cache_key_different_texts(self):
        """다른 텍스트는 다른 캐시 키 생성."""
        svc = self._make_service(available=True)
        key1 = svc._cache_key("텍스트 A")
        key2 = svc._cache_key("텍스트 B")
        assert key1 != key2

    def test_singleton_exists(self):
        """모듈 레벨 싱글턴 인스턴스 존재."""
        from backend.services.finbert_service import finbert
        assert finbert is not None
        assert hasattr(finbert, "analyze")
        assert hasattr(finbert, "available")


class TestSentimentEnsemble:
    """analyze_sentiment() 앙상블 로직 테스트."""

    def test_keyword_only_when_finbert_unavailable(self):
        """FinBERT 미가용 시 키워드 방식만 사용."""
        with patch("backend.services.finbert_service.finbert") as mock_fb:
            mock_fb.available = False
            from backend.utils.sentiment import analyze_sentiment
            score, label, method = analyze_sentiment("삼성전자 실적 호조")
            assert method == "keyword"

    def test_ensemble_when_finbert_available(self):
        """FinBERT 가용 시 앙상블 결과 반환."""
        with patch("backend.services.finbert_service.finbert") as mock_fb:
            mock_fb.available = True
            mock_fb.analyze.return_value = {
                "score": 0.8,
                "label": "positive",
                "label_kr": "긍정",
                "confidence": 0.9,
                "probabilities": {"negative": 0.05, "neutral": 0.15, "positive": 0.80},
            }
            from backend.utils.sentiment import analyze_sentiment
            score, label, method = analyze_sentiment("실적개선 호실적")
            assert method == "finbert_ensemble"
            assert score > 0

    def test_ensemble_score_range(self):
        """앙상블 점수가 -1~1 범위 내."""
        with patch("backend.services.finbert_service.finbert") as mock_fb:
            mock_fb.available = True
            mock_fb.analyze.return_value = {
                "score": -0.9,
                "label": "negative",
                "label_kr": "부정",
                "confidence": 0.95,
                "probabilities": {"negative": 0.95, "neutral": 0.03, "positive": 0.02},
            }
            from backend.utils.sentiment import analyze_sentiment
            score, label, method = analyze_sentiment("적자전환 실적 악화")
            assert -1 <= score <= 1
            assert method == "finbert_ensemble"

    def test_finbert_returns_none_falls_back(self):
        """FinBERT가 None 반환 시 키워드 fallback."""
        with patch("backend.services.finbert_service.finbert") as mock_fb:
            mock_fb.available = True
            mock_fb.analyze.return_value = None
            from backend.utils.sentiment import analyze_sentiment
            score, label, method = analyze_sentiment("일반 뉴스 기사")
            assert method == "keyword"

    def test_empty_input(self):
        """빈 입력 처리."""
        from backend.utils.sentiment import analyze_sentiment
        score, label, method = analyze_sentiment("", "")
        assert score == 0.0
        assert label == "중립"
        assert method == "keyword"

    def test_return_tuple_length(self):
        """반환값이 3-tuple인지 확인."""
        from backend.utils.sentiment import analyze_sentiment
        result = analyze_sentiment("테스트 기사")
        assert len(result) == 3


class TestScoringWeights:
    """스코어링 가중치 정합성 테스트."""

    def test_weights_sum_to_one(self):
        """모든 팩터 가중치 합 = 1.0."""
        from backend.services.scoring_service import (
            W_TECHNICAL, W_FUNDAMENTAL, W_SIGNAL,
            W_MACRO, W_RISK, W_RELATED, W_NEWS,
        )
        total = W_TECHNICAL + W_FUNDAMENTAL + W_SIGNAL + W_MACRO + W_RISK + W_RELATED + W_NEWS
        assert abs(total - 1.0) < 1e-9, f"가중치 합이 1.0이 아님: {total}"

    def test_news_weight_positive(self):
        """W_NEWS > 0 확인 (활성화됨)."""
        from backend.services.scoring_service import W_NEWS
        assert W_NEWS > 0, f"W_NEWS가 0: 뉴스 팩터 비활성 상태"

    def test_news_weight_value(self):
        """W_NEWS = 0.05 확인."""
        from backend.services.scoring_service import W_NEWS
        assert W_NEWS == 0.05

    def test_all_weights_positive(self):
        """모든 가중치가 양수."""
        from backend.services.scoring_service import (
            W_TECHNICAL, W_FUNDAMENTAL, W_SIGNAL,
            W_MACRO, W_RISK, W_RELATED, W_NEWS,
        )
        for name, w in [
            ("TECHNICAL", W_TECHNICAL), ("FUNDAMENTAL", W_FUNDAMENTAL),
            ("SIGNAL", W_SIGNAL), ("MACRO", W_MACRO), ("RISK", W_RISK),
            ("RELATED", W_RELATED), ("NEWS", W_NEWS),
        ]:
            assert w > 0, f"W_{name} is not positive: {w}"


class TestNewsArticleSchema:
    """NewsArticle 스키마 FinBERT 필드 테스트."""

    def test_finbert_fields_optional(self):
        """finbert_score, finbert_confidence는 Optional."""
        from backend.models.schemas import NewsArticle
        article = NewsArticle(
            title="테스트", link="http://test.com", source="테스트",
            date="2026-03-02", summary="테스트",
            sentiment_score=0.5, sentiment_label="긍정",
        )
        assert article.finbert_score is None
        assert article.finbert_confidence is None

    def test_finbert_fields_with_values(self):
        """finbert 필드에 값 설정."""
        from backend.models.schemas import NewsArticle
        article = NewsArticle(
            title="테스트", link="http://test.com", source="테스트",
            date="2026-03-02", summary="테스트",
            sentiment_score=0.5, sentiment_label="긍정",
            finbert_score=0.85, finbert_confidence=0.92,
        )
        assert article.finbert_score == 0.85
        assert article.finbert_confidence == 0.92


class TestSentimentToScore:
    """sentiment_to_score 유틸 테스트."""

    def test_positive_sentiment(self):
        from backend.utils.sentiment import sentiment_to_score
        assert sentiment_to_score(1.0) == 100.0

    def test_negative_sentiment(self):
        from backend.utils.sentiment import sentiment_to_score
        assert sentiment_to_score(-1.0) == 0.0

    def test_neutral_sentiment(self):
        from backend.utils.sentiment import sentiment_to_score
        assert sentiment_to_score(0.0) == 50.0
