/**
 * AlphaLens 메인 앱 (슬림 오케스트레이터)
 *
 * 분리된 모듈:
 *   utils.js        - formatChange, Toast, SectionProgress
 *   router.js       - 페이지 라우팅 (레지스트리 패턴)
 *   favorites.js    - 관심종목/최근검색 카드
 *   compare.js      - 종목 비교
 *   stock-detail.js - 종목 상세 로드/렌더
 *   geopolitical.js - 지정학 리스크
 *   market.js       - Market, Recommend (시장 현황, 추천 종목)
 *   investor.js     - InvestorTrend (투자자별 매매동향)
 *   portfolio.js    - Portfolio (포트폴리오 관리)
 *   monitor.js      - SystemMonitor (서버 모니터링)
 */

const App = {
  // 하위 호환 getter — 기존 모듈에서 App.loadStock(code) 호출 유지
  get currentCode() { return StockDetail.currentCode; },
  set currentCode(v) { StockDetail.currentCode = v; },

  init() {
    Search.init();
    PriceChart.init();
    AlphaStream.connect();

    this._initChartControls();
    this._initKeyboardShortcuts();
    Compare.init();
    Portfolio.init();
    Favorites.init();
    Router.init();

    // 로고 클릭 → 홈
    document.getElementById('logoHome').addEventListener('click', () => Router.navigate('home'));

    // 새로고침 버튼
    document.getElementById('globalRefresh').addEventListener('click', () => Router.refresh());

    // 대시보드 즐겨찾기 토글
    document.getElementById('favToggle').addEventListener('click', () => {
      if (!StockDetail._lastDetail) return;
      const d = StockDetail._lastDetail;
      const added = Storage.toggleFavorite({
        code: d.code, name: d.name, market: d.market,
        price: d.price, change_pct: d.change_pct,
        over_market: d.over_market || null,
      });
      StockDetail.updateFavToggle(d.code);
      Toast.show(added ? `${d.name} 즐겨찾기 추가` : `${d.name} 즐겨찾기 해제`, added ? 'success' : 'info');
    });

    // 초기 홈 데이터 로드
    Favorites.render();
    Market.load();
    Geopolitical.load();

    // 홈 자동 갱신 (3분)
    setInterval(() => {
      if (!StockDetail.currentCode && Router.activeNav === 'home') {
        Market.load();
        Geopolitical.load();
        Recommend.load();
      }
    }, 180000);

    // URL 해시 라우팅
    Router._handleHash();
  },

  // 하위 호환 — 추천카드/관련기업 등에서 App.loadStock(code) 호출
  loadStock(code) {
    StockDetail.load(code);
  },

  goHome() {
    Router.navigate('home');
  },

  navigateTo(nav) {
    Router.navigate(nav);
  },

  // ── 차트 컨트롤 ──

  _initChartControls() {
    document.querySelectorAll('.chart-btn[data-days]').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.chart-btn[data-days]').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        StockDetail.currentDays = parseInt(btn.dataset.days);
        if (StockDetail.currentCode) StockDetail.loadChart(StockDetail.currentCode, StockDetail.currentDays);
      });
    });

    document.querySelectorAll('.chart-toggle-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.chart-toggle-btn').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        PriceChart.setMode(btn.dataset.mode);
      });
    });

    document.querySelectorAll('.chart-ma-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.ma;
        if (key === 'vol') {
          const active = PriceChart.toggleVolume();
          btn.classList.toggle('active', active);
        } else if (key === 'bb') {
          const active = PriceChart.toggleBB();
          btn.classList.toggle('active', active);
        } else if (key === 'rsi') {
          const active = PriceChart.toggleRSI();
          btn.classList.toggle('active', active);
        } else {
          const active = PriceChart.toggleMA(parseInt(key));
          btn.classList.toggle('active', active);
        }
      });
    });
  },

  // ── 키보드 단축키 ──

  _initKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      const active = document.activeElement;
      const isInput = active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA');

      if (e.key === 'Escape') {
        e.preventDefault();
        const dropdown = document.getElementById('searchResults');
        if (dropdown && dropdown.classList.contains('active')) {
          dropdown.classList.remove('active');
          document.getElementById('searchInput').blur();
          return;
        }
        if (StockDetail.currentCode) {
          Router.navigate('home');
        }
        return;
      }

      if (isInput) return;

      if (e.key === '/' || e.key === 's') {
        e.preventDefault();
        document.getElementById('searchInput').focus();
      } else if (e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        Router.refresh();
      } else if (e.key === 'f' || e.key === 'F') {
        e.preventDefault();
        document.getElementById('favToggle')?.click();
      }
    });
  },
};

// 초기화
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    App.init();
    SystemMonitor.start();
  });
} else {
  App.init();
  SystemMonitor.start();
}
