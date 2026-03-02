# AlphaLens Enterprise Team Configuration v2.0
# 13명 전문가 분석 결과 반영 (2026-03-02)
# `team-config.md 기반으로 팀 스폰해줘`로 재생성 가능

## 프로젝트 미션
- **회사**: 캐피탈사 (투자법인)
- **목표**: 중/장기적 투자 수익 실현
- **핵심 KPI**: 정확한 매수/매도 타이밍 → 수익률 극대화
- **제품**: AlphaLens - 한국 주식 AI 멀티팩터 스코어링 플랫폼
- **6-팩터 모델**: Tech 25% + Fund 20% + Signal 20% + Macro 15% + Risk 15% + Related 5% (Risk 상향 조정)

---

## 식별된 핵심 이슈 (170+ 개선사항 중 우선순위 정리)

### CRITICAL (즉시 수정)
| ID | 이슈 | 담당 | 파일 |
|----|------|------|------|
| C1 | workers=4 + 인메모리 캐시 → 캐시 히트율 1/4, WS 브로드캐스트 불가 | backend-senior | run.py, cache_service.py |
| C2 | 인증/인가 전무 → 투자 데이터 무방비 공개 | security-lead | main.py, ws.py |
| C3 | Technical↔Signal 다중공선성 (상관 0.65-0.80) → 50%에 이중 반영 | quant-expert | scoring_service.py, signal_service.py |
| C4 | Risk veto 부재 → Risk=E등급이어도 종합 60+점 가능 | quant-expert | scoring_service.py |
| C5 | 매도 시그널 취약 + 매수 편향 (매수+75 vs 매도-45) | signal-strategist | signal_service.py |
| C6 | 리스크 등급 100점 fallthrough 버그 | risk-manager | risk_service.py |
| C7 | yfinance 100% 의존 → 비공식 API, 차단 리스크 | macro-strategist | macro_service.py |
| C8 | HTML 스크래핑 의존 → 네이버 UI 변경 시 즉시 장애 | data-engineer | stock_service.py |
| C9 | 서킷 브레이커/재시도 없음 → 외부 API 장애 시 연쇄 지연 | data-engineer | stock_service.py |
| C10 | CI/CD 파이프라인 완전 부재 | devops-sre | .github/ |
| C11 | DB/영속 저장소 없음 → 히스토리 축적/백테스팅 불가 | data-engineer | 신규 |

### HIGH (투자 성과 직결)
| ID | 이슈 | 담당 |
|----|------|------|
| H1 | ADX 추세강도 지표 누락 → 횡보장 거짓 신호 억제 불가 | ta-expert |
| H2 | 매도에 MACD 데드크로스/RSI 과매수/ATR 트레일링 스탑 미통합 | signal-strategist |
| H3 | 한국 금리(KR10Y) 완전 부재 → 외국인 자금 흐름 예측 불가 | macro-strategist |
| H4 | 시차 효과 미반영 → change_5d 수집만 하고 미사용 | macro-strategist |
| H5 | 테일 리스크(VaR/CVaR) 완전 부재 | risk-manager |
| H6 | 변동성 단순화 (20일 단일 윈도우, EWMA/하방 변동성 미반영) | risk-manager |
| H7 | 포지션 사이징 과도 (최대 25%, 리스크 등급 미연동) | risk-manager |
| H8 | 지정학 리스크 과소 반영 (실질 2-3%) | geopolitical-analyst |
| H9 | 검증 함수 4회 중복 + 종목명 조회 6회 중복 (DRY 위반) | backend-senior |
| H10 | 광범위 except + pass/return None → 장애 감지 불가 | backend-senior |
| H11 | 구조화 로깅 없음 (JSON, request_id 트레이싱 미적용) | backend-senior |
| H12 | 테스트 커버리지 ~25%, 핵심 서비스 7개 미테스트 | test-lead |
| H13 | 정보 밀도 부족 → 목표가/손절가/비중 액션 가이드 없음 | frontend-senior |
| H14 | 차트 리빌드 성능 → 토글마다 전체 재생성 | frontend-senior |
| H15 | WCAG 1.4.1 위반 → 색상만으로 상승/하락 구분 | frontend-senior |
| H16 | 이중 시그널 라벨 버그 (signal vs action_label 불일치) | quant-expert |
| H17 | 뉴스 감성분석 키워드 기반 한계 → KR-FinBERT 도입 권고 | ai-ml-engineer |

---

## 팀 구성 (총 16명) - 구현 중심 재편

### Tier 1: 프로젝트 관리 (1명)
| 역할 | 에이전트명 | subagent_type | 핵심 책임 |
|------|-----------|---------------|----------|
| PM / 팀 리드 | team-lead | team-lead | 스프린트 관리, 태스크 배분, 교차 이슈 조율, 최종 보고 |

### Tier 2: 핵심 개발팀 (4명)
| 역할 | 에이전트명 | subagent_type | 담당 이슈 | Sprint |
|------|-----------|---------------|----------|--------|
| 백엔드 시니어 | backend-senior | general-purpose | C1, H9, H10, H11 + 코드 품질 전반 | 1-2 |
| 프론트엔드 시니어 | frontend-senior | general-purpose | H13, H14, H15 + 상태관리, 차트 | 2-3 |
| DevOps/SRE | devops-sre | general-purpose | C10 + 모니터링, Nginx, 환경 분리 | 1-2 |
| 데이터 엔지니어 | data-engineer | general-purpose | C8, C9, C11 + 캐싱, 배치 스케줄러 | 2-3 |

### Tier 3: 스코어링 모델팀 (5명)
| 역할 | 에이전트명 | subagent_type | 담당 이슈 | Sprint |
|------|-----------|---------------|----------|--------|
| 퀀트 분석가 | quant-expert | general-purpose | C3, C4, H16 + 가중치 재조정, 합산 로직 | 1-2 |
| 기술적 분석가 | ta-expert | general-purpose | H1 + BB 스퀴즈, OBV 벡터화, MFI 추가 | 2 |
| 매매 타이밍 전략가 | signal-strategist | general-purpose | C5, H2 + 다중 시간축, 시그널 합의도 | 1-2 |
| 리스크 매니저 | risk-manager | general-purpose | C6, H5, H6, H7 + Rolling MDD, 유동성 보간 | 1-2 |
| 글로벌 매크로 전략가 | macro-strategist | general-purpose | C7, H3, H4 + 데이터 소스 다변화, 환율 레벨 | 2-3 |

### Tier 4: 품질/보안팀 (3명)
| 역할 | 에이전트명 | subagent_type | 담당 이슈 | Sprint |
|------|-----------|---------------|----------|--------|
| 보안 담당 | security-lead | general-purpose | C2 + HTTPS, JWT, WebSocket 보안, SRI | 1 |
| 통합테스트 담당 | test-lead | general-purpose | H12 + macro/geo/recommendation 순수함수 테스트 | 2-3 |
| 지정학 분석가 | geopolitical-analyst | general-purpose | H8 + 영문 RSS, NLP 고도화, 시나리오 시뮬레이션 | 3 |

### Tier 5: AI/ML 신규 (1명)
| 역할 | 에이전트명 | subagent_type | 담당 이슈 | Sprint |
|------|-----------|---------------|----------|--------|
| AI/ML 엔지니어 | ai-ml-engineer | general-purpose | H17 + KR-FinBERT 통합, 감성분석 교체, 뉴스 팩터 활성화 | 3-4 |

### Tier 6: 전략/기획 (2명)
| 역할 | 에이전트명 | subagent_type | 담당 이슈 | Sprint |
|------|-----------|---------------|----------|--------|
| 프로덕트 기획자 | product-planner | general-purpose | AI/LLM 로드맵, 캐피탈사 요구사항, UX 전략 | 지속 |
| 백테스트 엔지니어 | backtest-engineer | general-purpose | 파라미터 민감도 분석, 전략 검증, 성과 귀인 | 3-4 |

---

## 스프린트 계획

### Sprint 1: 즉시 수정 (1-3일)
**목표**: 시스템 안정성 확보 + 치명적 모델 버그 수정

| 담당 | 태스크 | 예상 |
|------|--------|------|
| backend-senior | workers=1 변경, 중복 함수 통합(validators.py), except→구체 예외+로깅 | 1일 |
| security-lead | API Key 인증, docs 비활성화, DEBUG=false, CDN SRI, CORS 헤더 명시 | 1일 |
| quant-expert | Risk veto 룰(Risk<25→상한45), 리스크 등급 100점 버그, 이중 라벨 수정 | 1일 |
| signal-strategist | 매수/매도 점수 범위 균형 조정, 레짐 보정 이중 적용 제거 | 1일 |
| risk-manager | 등급 100점 fallthrough 수정, 유동성 연속 보간, 포지션 상한 25%→15% | 1일 |
| devops-sre | GitHub Actions CI 기본 파이프라인(lint+test+build) | 1일 |

### Sprint 2: 모델 고도화 (1-2주)
**목표**: 스코어링 정확도 향상 + 인프라 안정화

| 담당 | 태스크 |
|------|--------|
| quant-expert | Technical↔Signal 역할 분리(다중공선성 해소), Risk 가중치 10%→15% |
| ta-expert | ADX 추세강도 지표 구현, BB bandwidth 스퀴즈 신호, MACD 점수 축소 |
| signal-strategist | 매도 시그널 강화(MACD 데드크로스+RSI+트레일링 스탑), 다중 시간축 모멘텀 |
| risk-manager | 테일 리스크(VaR/CVaR), 다중 윈도우 변동성, Rolling MDD+회복률 |
| backend-senior | JSON 구조화 로깅, recommendations.py 서비스 분리, 순환 import 해결 |
| data-engineer | 서킷 브레이커(tenacity), 캐시 LRU 제한, _stock_list 주기적 갱신 |
| devops-sre | Nginx 리버스 프록시, docker-compose.prod.yml, 모니터링(/metrics) |
| test-lead | macro/geopolitical/recommendation 순수함수 테스트, 커버리지 60%+ |

### Sprint 3: 확장 기능 (2-4주)
**목표**: 데이터 인프라 + 프론트엔드 + 매크로 고도화

| 담당 | 태스크 |
|------|--------|
| macro-strategist | 한국 금리(KR10Y), 한미 금리차, change_5d 활용, FRED/ECOS API 연동 |
| frontend-senior | 액션 가이드 UI, 차트 메모이제이션, 상태 관리 통합, WCAG 접근성 |
| data-engineer | PostgreSQL/TimescaleDB 도입, 배치 스케줄러(APScheduler), 일봉 자동 저장 |
| geopolitical-analyst | 영문 RSS(Reuters/AP), 제재 카테고리 보강, 스코어링 직접 반영 |
| security-lead | JWT 인증 체계, HTTPS(TLS), WebSocket 인증, pip-audit CI |
| test-lead | API 통합 테스트(7개 라우터), 미들웨어 테스트, 모킹 인프라 |

### Sprint 4: AI/ML 통합 (1-2개월)
**목표**: LLM 기반 감성분석 + 리포트 자동화

| 담당 | 태스크 |
|------|--------|
| ai-ml-engineer | KR-FinBERT 감성분석 통합(sentiment.py 교체), 뉴스 팩터 0%→5% 활성화 |
| product-planner | AI/LLM Phase 2 로드맵(지정학 LLM 보강, 애널리스트 리포트 RAG) |
| backtest-engineer | 파라미터 민감도 분석, 3년 KOSPI/KOSDAQ 백테스트, 성과 귀인 분석 |

---

## 교차 이슈 (다수 에이전트 협업 필요)

| 이슈 | 관련 에이전트 | 조율 방법 |
|------|-------------|----------|
| Redis 도입 | backend, devops, data | devops가 인프라, backend가 코드 변경, data가 캐시 전략 |
| 다중공선성 해소 | quant, ta, signal | quant가 설계, ta/signal이 구현 |
| 인증 체계 | security, backend, frontend | security가 설계, backend가 API, frontend가 토큰 관리 |
| DB 도입 | data, devops, backend | data가 스키마, devops가 인프라, backend가 ORM |
| 매도 시그널 | signal, ta, risk | signal이 메인, ta가 ADX, risk가 트레일링 스탑 |

---

## AI/LLM 도입 전략 (product-planner 분석 결과)

**핵심 원칙**: "정량은 규칙, 정성은 LLM"
- Phase 1 (Sprint 4): KR-FinBERT 감성분석 → 뉴스 팩터 활성화 (무료/로컬, 롤백 용이)
- Phase 2 (이후): 지정학 LLM 보강 + 애널리스트 리포트 RAG
- Phase 3 (이후): 자연어 질의 + 자동 리포트 생성
- **절대 금지**: 기술적 분석/시그널/리스크 계산을 LLM으로 대체

---

## 전체 팀 목록 (총 16명)
1. team-lead (PM)
2. backend-senior (백엔드 시니어) - Sprint 1-2
3. frontend-senior (프론트엔드 시니어) - Sprint 2-3
4. devops-sre (DevOps/SRE) - Sprint 1-3
5. data-engineer (데이터 엔지니어) - Sprint 2-3
6. quant-expert (퀀트 분석가) - Sprint 1-2
7. ta-expert (기술적 분석가) - Sprint 2
8. signal-strategist (매매 타이밍 전략가) - Sprint 1-2
9. risk-manager (리스크 매니저) - Sprint 1-2
10. macro-strategist (글로벌 매크로 전략가) - Sprint 2-3
11. security-lead (보안 담당) - Sprint 1, 3
12. test-lead (통합테스트) - Sprint 2-3
13. geopolitical-analyst (지정학 분석가) - Sprint 3
14. ai-ml-engineer (AI/ML 엔지니어) - Sprint 4 [신규]
15. product-planner (프로덕트 기획자) - 지속
16. backtest-engineer (백테스트 엔지니어) - Sprint 4

## 스폰 전략
- **Sprint 1 우선 스폰 (6명)**: backend-senior, security-lead, quant-expert, signal-strategist, risk-manager, devops-sre
- **Sprint 2 추가 스폰**: ta-expert, test-lead, data-engineer
- **Sprint 3 추가 스폰**: frontend-senior, macro-strategist, geopolitical-analyst
- **Sprint 4 추가 스폰**: ai-ml-engineer, backtest-engineer, product-planner

## 팀 재구성 명령
이 파일을 참조하여 `팀 재구성해줘` 또는 `team-config.md 기반으로 팀 스폰해줘`로 동일 팀 재생성 가능
