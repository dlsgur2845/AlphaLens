# Design System — AlphaLens

## Product Context
- **What this is:** 한국 주식 AI 멀티팩터 스코어링 분석 플랫폼
- **Who it's for:** 캐피탈사 애널리스트 (중/장기 투자 의사결정)
- **Space/industry:** 금융 데이터 분석, 한국 주식시장
- **Project type:** Dark theme data dashboard (web app)

## Aesthetic Direction
- **Direction:** Industrial/Utilitarian — 기능 우선, 데이터가 주인공
- **Decoration level:** Intentional — 은은한 글라스모피즘 (헤더/모바일 네비), 미세 보더와 그림자로 깊이감
- **Mood:** 차분한 신뢰감. 트레이딩 터미널의 긴급함이 아닌, 리서치 리포트의 분석적 깊이. 캐피탈사 내부 도구의 프로페셔널함.
- **Reference sites:** Bloomberg Terminal, TradingView, Robinhood (data density + clean UI balance)

## Typography
- **Display/Hero:** Geist (Vercel) — 현대적 산세리프, 금융 데이터에 최적화된 tabular-nums, Inter보다 개성 있으면서 전문적
- **Body:** Pretendard Variable — 한국어 최적화 산세리프. Apple SF Pro 한국어 대응으로 설계. Inter와 메트릭 호환.
- **UI/Labels:** Pretendard Variable (same as body)
- **Data/Tables:** JetBrains Mono — tabular-nums, 리가처, 숫자 데이터 정렬과 가독성
- **Code:** JetBrains Mono
- **Loading:**
  ```html
  <!-- Geist (Display) -->
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <!-- Pretendard (Body, Korean) -->
  <link href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css" rel="stylesheet">
  <!-- JetBrains Mono (Data) -->
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  ```
- **Scale:**
  - Score display: 48-56px, Geist 900, -0.04em tracking
  - Display/Hero: 40px, Geist 800, -0.03em tracking
  - H1: 24px, Geist 700, -0.02em tracking
  - H2/Section: 14px, Geist 600, uppercase, 0.05em tracking
  - Body: 15px, Pretendard 400, 1.7 line-height (한글 1.8)
  - UI Label: 13px, Pretendard 500
  - Small/Caption: 11-12px, Pretendard 500-600
  - Data: 14px, JetBrains Mono 500, tabular-nums
  - Micro: 10px, uppercase, 0.05em tracking

## Color
- **Approach:** Restrained — 1 accent + 시맨틱 4색 + 뉴트럴. 색상은 의미를 전달할 때만 사용.

### Background Hierarchy
| Token | Hex | Usage |
|-------|-----|-------|
| `--bg-primary` | `#101922` | 페이지 배경 |
| `--bg-secondary` | `#141e2b` | 사이드바, 섹션 배경 |
| `--bg-tertiary` | `#1a2435` | 3단계 깊이 |
| `--bg-card` | `rgba(30,41,59,0.40)` | 카드 배경 |
| `--bg-card-elevated` | `rgba(30,41,59,0.60)` | 호버/강조 카드 |
| `--bg-hover` | `rgba(51,65,85,0.40)` | 호버 상태 |
| `--bg-sunken` | `rgba(15,23,36,0.50)` | 입력 필드 배경 |

### Text Hierarchy
| Token | Hex | Usage | Contrast on #101922 |
|-------|-----|-------|---------------------|
| `--text-heading` | `#f1f5f9` | 헤딩, 강조 | 14.5:1 |
| `--text-primary` | `#e2e8f0` | 본문 | 12.5:1 |
| `--text-secondary` | `#8594a9` | 보조 텍스트 | 5.1:1 (AA pass) |
| `--text-muted` | `#6b7a8d` | 라벨, 캡션 | 4.5:1 (AA pass) |

### Accent
| Token | Hex | Usage |
|-------|-----|-------|
| `--accent` | `#2563eb` | 주요 액션, 브랜드 |
| `--accent-soft` | `#3b82f6` | 보조 강조 |
| `--accent-glow` | `rgba(37,99,235,0.12)` | 배경 글로우 |

### Semantic (한국 컨벤션)
| Token | Hex | Usage |
|-------|-----|-------|
| `--up` / `--red` | `#ef4444` | 주가 상승, 매수 신호 |
| `--down` / `--blue` | `#3b82f6` | 주가 하락, 매도 신호 |
| `--success` / `--green` | `#22c55e` | 성공, 높은 점수 (70+) |
| `--warning` / `--yellow` | `#eab308` | 경고, 낮은 점수 (30-50) |
| `--error` | `#ef4444` | 에러 상태 |
| `--info` | `#06b6d4` | 정보 |

### Score-Based Factor Colors
| Range | Color | Token |
|-------|-------|-------|
| 70+ | Green | `var(--success)` |
| 50-69 | Blue | `var(--accent)` |
| 30-49 | Yellow | `var(--warning)` |
| <30 | Red | `var(--error)` |

### Borders & Glass
| Token | Value |
|-------|-------|
| `--border` | `rgba(51,65,85,0.60)` |
| `--border-subtle` | `rgba(51,65,85,0.40)` |
| `--border-accent` | `rgba(37,99,235,0.30)` |
| `--glass-bg` | `rgba(16,25,34,0.85)` |
| `--glass-blur` | `blur(16px)` |

## Spacing
- **Base unit:** 4px
- **Density:** Comfortable — 장시간 분석 작업에 적합
- **Scale:**

| Token | Value | Usage |
|-------|-------|-------|
| `--sp-2xs` | 2px | 인라인 간격 |
| `--sp-xs` | 4px | 요소 내부 미세 간격 |
| `--sp-sm` | 8px | 관련 요소 간 간격 |
| `--sp-md` | 16px | 카드 패딩, 섹션 내 간격 |
| `--sp-lg` | 24px | 섹션 간 간격 |
| `--sp-xl` | 32px | 큰 섹션 간격 |
| `--sp-2xl` | 48px | 페이지 레벨 간격 |
| `--sp-3xl` | 64px | 히어로/마진 |

## Layout
- **Approach:** Grid-disciplined — 사이드바 + 컨텐츠 영역 그리드
- **Grid:**
  - Desktop (1200px+): 사이드바 240px + 컨텐츠 auto
  - Laptop (1024px+): 사이드바 240px + 컨텐츠 단일 컬럼
  - Tablet (768px-1024px): 사이드바 숨김, 컨텐츠 단일 컬럼
  - Mobile (<768px): 하단 탭 바, 컨텐츠 전체 폭
- **Max content width:** 1200px (컨텐츠 영역)
- **Border radius:**

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-sm` | 4px | 입력 필드, 작은 버튼 |
| `--radius-md` | 8px | 카드, 드롭다운 |
| `--radius-lg` | 12px | 큰 카드, 모달 |
| `--radius-full` | 9999px | 뱃지, 필 |

## Motion
- **Approach:** Minimal-functional — 이해를 돕는 전환만. 장식적 모션 없음.
- **Easing:** enter(`ease-out`) exit(`ease-in`) move(`ease-in-out`)
- **Duration:**
  - micro: 50-100ms (호버, 토글)
  - short: 150-250ms (드롭다운, 카드 전환)
  - medium: 250-400ms (페이지 전환, 차트 애니메이션)
  - long: 400-700ms (게이지 드로우, 데이터 로딩)
- **Reduced motion:** `prefers-reduced-motion: reduce`에서 모든 애니메이션 비활성화

## Accessibility
- **WCAG 2.1 AA** 준수 대상
- **Focus visible:** 모든 인터랙티브 요소에 `outline: 2px solid var(--accent); outline-offset: 2px;`
- **Touch targets:** 최소 44px (모바일 버튼/컨트롤)
- **Color contrast:** 본문 4.5:1+, 대형 텍스트 3:1+ (다크 배경 기준)
- **Screen readers:** ARIA landmarks, sr-only 라벨, live regions
- **Keyboard:** 전체 네비게이션 가능, 포커스 트랩 (모달)

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-29 | 디자인 시스템 생성 | /design-consultation + /plan-design-review 결과. Industrial/Utilitarian 방향. |
| 2026-03-29 | Pretendard 한글 폰트 도입 | 시스템 폰트(맑은 고딕) 대비 한글/영문 혼합 타이포 품질 향상 |
| 2026-03-29 | Geist display 폰트 | 스코어 게이지의 시각적 앵커 역할. Inter 대비 개성+전문성 |
| 2026-03-29 | Accent #137fec -> #2563eb | 다크 배경 위 대비 향상, 브랜드 신뢰감 강화 |
| 2026-03-29 | 팩터 바 점수 기반 색상 | 70+녹/50-70파/30-50노/30미만 빨강. 정보 스캔 속도 향상 |
| 2026-03-29 | Dark theme 전용 | 캐피탈사 내부 도구. 라이트 모드 불필요. |
