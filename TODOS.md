# TODOS.md

## P1 — High Priority

### 과거 스코어 캐시 파이프라인 구축
- **What**: 매일 모든 종목의 7-factor 스코어를 DB(ScoringSnapshot)에 저장하는 스케줄러 태스크 구축. 이 데이터가 축적되면 전체 7-factor 백테스트 가능.
- **Why**: 현재 펀더멘탈/매크로/뉴스의 과거 시점별 스냅샷이 없어 7-factor 백테스트 불가. 3-factor(가격 기반) 검증 후 전체 모델 검증에 필수.
- **Effort**: L (인간) → M (CC+gstack)
- **Depends on**: 데이터 소스 안정화 (공식 API 마이그레이션)
- **Context**: Phase 1 3-factor 백테스트는 가격 기반 팩터만 검증. 7-factor 전체 검증을 위해서는 과거 스코어 데이터가 필요. DB에 ScoringSnapshot 테이블은 이미 존재 (backend/models/database.py).

## P2 — Medium Priority

### _simulate() 성능 최적화 (O(n²) → O(n))
- **What**: 매 거래일마다 전체 히스토리를 슬라이싱하여 인디케이터를 재계산하는 대신, 인디케이터를 점진적으로 업데이트하는 방식으로 변경.
- **Why**: 현재 100종목 × 1000일 = ~94,000회 풀 인디케이터 계산. Outside Voice 추정 10-50시간 소요. 실측 필요하지만 성능 문제는 실제로 존재.
- **Effort**: M (인간) → S (CC+gstack)
- **Depends on**: Phase 1 백테스트 실행 후 실제 성능 병목 확인
- **Context**: backtest_service.py:83 `window_closes = pd.Series(closes[:i+1])` 라인. calc_technical_score, calc_signal_score 모두 이 슬라이스에서 MA/RSI/MACD 등 재계산.

### 통계적 유의성 프레임워크
- **What**: 백테스트 결과에 신뢰구간, bootstrap 분석, 다중검정 보정(Bonferroni/FDR) 추가.
- **Why**: 100종목 × 1기간 결과로 알파를 주장하려면 통계적 근거 필요. p-value 없이는 우연과 알파를 구분할 수 없음.
- **Effort**: M (인간) → S (CC+gstack)
- **Depends on**: Phase 1 백테스트 결과가 양의 알파를 보일 때
- **Context**: out-of-sample 검증(2021-2023 학습, 2024-2025 검증)도 고려. 한국 시장의 regime 변화(2022 베어 → 2023-2025 회복)도 분석 대상.
