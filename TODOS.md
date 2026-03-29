# TODOS.md

## P1 — High Priority

### DESIGN.md 생성 (/design-consultation)
- **What**: 현재 CSS 변수 40+개를 기반으로 색상 팔레트, 타이포그래피 스케일, 스페이싱 체계, 컴포넌트 규격을 문서화한 DESIGN.md 생성.
- **Why**: 새 컴포넌트 추가 시 어떤 토큰을 써야 하는지 가이드가 없어 일관성 깨짐. 모든 UI 작업의 기반 문서.
- **Pros**: 디자인 일관성, 신규 개발자 온보딩, 컴포넌트 재사용성 향상
- **Cons**: 초기 작성 시간 (~15분 CC+gstack)
- **Effort**: S (인간) → XS (CC+gstack, /design-consultation)
- **Depends on**: 없음
- **Context**: 디자인 리뷰(2026-03-29)에서 Pass 5 결과. Inter 폰트는 금융 대시보드에 적합하므로 유지. CSS :root 변수가 de facto 시스템.

### 프론트엔드 상태 커버리지 구현
- **What**: 검색 빈 결과, 팩터 부분 로딩 (4/7 진행 표시), 스켈레톤 대시보드 (전체 로딩 오버레이 대체), 빈 상태 CTA 등 25개+ 미정의 상태 구현.
- **Why**: 현재 로딩/에러 시 블랙박스 경험. "분석 중..." 오버레이가 3초 이상 지속되면 사용자가 이탈.
- **Pros**: 인지 부하 감소, 데이터 스트리밍 느낌, 에러 복구 경로 제공
- **Cons**: HTML/JS 변경량 많음
- **Effort**: L (인간) → M (CC+gstack, ~30분)
- **Depends on**: 없음
- **Context**: 디자인 리뷰(2026-03-29) Pass 2 결과. 전체 상태 매트릭스 정의 완료 (12 기능 × 5 상태). 핵심: 스켈레톤 대시보드, 팩터 진행 표시, 빈 상태 CTA.

### 접근성 WCAG 2.1 AA 충족
- **What**: (1) focus-visible 스타일 추가 (outline: 2px solid accent), (2) 터치 타겟 최소 44px (차트 버튼 등), (3) --text-muted 대비 보정 (#64748b→#8594a9, 4.5:1+).
- **Why**: 키보드 사용자가 현재 포커스 위치를 모름. 모바일 차트 버튼 터치 불편. 무테드 텍스트 WCAG AA 미달.
- **Pros**: 접근성 법적 요건 충족, 키보드 사용자 UX 개선, 저시력 사용자 가독성
- **Cons**: 일부 시각적 미세 조정 필요
- **Effort**: S (인간) → XS (CC+gstack, ~15분)
- **Depends on**: 없음
- **Context**: 디자인 리뷰(2026-03-29) Pass 6 결과. prefers-reduced-motion은 이미 지원. ARIA 라벨 부분 존재.

### UI 계층 개선 구현
- **What**: (1) 홈 히어로에 480px 검색바 복제, (2) 투자의견 카드 2x 높이 + accent 배경 강조, (3) 스코어 카드에 "기술적 강세 + 매크로 중립 → 매수 우위" 한줄 요약, (4) 팩터 바 점수 기반 색상 (70+녹/50-70파/30-50노/30미만 빨강), (5) 대시보드 상단에 "포트폴리오+" "비교+" 인라인 버튼.
- **Why**: 검색이 히어로 CTA가 되어야 함. 액션 가이드에 시각적 계층 없음. 스코어 내러티브 부재. 팩터 구분 안됨. 워크플로우 단축 필요.
- **Pros**: 첫 인상 개선, 애널리스트 워크플로우 단축, 정보 스캔 속도 향상
- **Cons**: HTML 구조 변경 필요
- **Effort**: M (인간) → S (CC+gstack, ~30분)
- **Depends on**: 없음 (DESIGN.md 전에도 가능)
- **Context**: 디자인 리뷰(2026-03-29) Pass 1, 3, 4, 7 결과. 모든 결정 사항 확정됨.

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
