/**
 * AlphaLens 페이지 라우터
 * - 페이지 레지스트리 패턴: switch/if 없이 페이지 추가 가능
 * - 해시 기반 SPA 라우팅
 */

const Router = {
  activeNav: 'home',

  // 페이지 레지스트리 — 새 페이지 추가 시 여기만 등록
  _pages: {
    home: {
      hash: '#/',
      sections: ['favoritesSection', 'recentSection', 'marketSummarySection', 'geopoliticalSection'],
      showHero: true,
      load() {
        Favorites.render();
        Market.load();
        Geopolitical.load();
      },
    },
    market: {
      hash: '#/market',
      sections: ['marketSummarySection', 'geopoliticalSection'],
      load() {
        Market.load();
        Geopolitical.load();
      },
    },
    recommend: {
      hash: '#/recommend',
      sections: ['recommendSection', 'avoidSection'],
      load() { Recommend.load(); },
    },
    portfolio: {
      hash: '#/portfolio',
      sections: ['portfolioSection'],
      load() {
        Portfolio.renderHoldings();
        Portfolio.loadAnalysis();
      },
    },
    compare: {
      hash: '#/compare',
      sections: ['compareSection'],
      load() {},
    },
    favorites: {
      hash: '#/favorites',
      sections: ['favoritesSection', 'recentSection'],
      load() { Favorites.render({ limit: 0 }); },
    },
  },

  init() {
    window.addEventListener('hashchange', () => this._handleHash());

    const navSelector = '.sidebar-item[data-nav], .header-link[data-nav], .mobile-nav-item[data-nav]';
    document.querySelectorAll(navSelector).forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        this.navigate(btn.dataset.nav);
      });
    });
  },

  navigate(nav) {
    if (nav === 'home') {
      this._goHome();
      return;
    }

    const page = this._pages[nav];
    if (!page) return;

    // 리소스 정리
    StockDetail.cleanup();
    CacheTracker.clear();
    this._setActiveNav(nav);

    if (location.hash !== page.hash) {
      history.pushState(null, '', page.hash);
    }

    this._showPage(page);
    page.load();
  },

  refresh() {
    const btn = document.getElementById('globalRefresh');
    if (btn) {
      btn.classList.add('spinning');
      setTimeout(() => btn.classList.remove('spinning'), 800);
    }

    if (StockDetail.currentCode) {
      StockDetail.load(StockDetail.currentCode);
      return;
    }

    const page = this._pages[this.activeNav];
    if (page) page.load();
  },

  _goHome() {
    StockDetail.cleanup();
    StockDetail._lastDetail = null;
    StockDetail._loadRequestId++;
    this._setActiveNav('home');
    SectionProgress.clear();
    CacheTracker.clear();

    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('welcomeScreen').style.display = '';

    const hero = document.getElementById('welcomeHero');
    if (hero) hero.style.display = '';

    const page = this._pages.home;
    const sectionSet = new Set(page.sections);
    document.querySelectorAll('#welcomeScreen .content-section').forEach(el => {
      el.style.display = sectionSet.has(el.id) ? '' : 'none';
    });

    document.getElementById('searchInput').value = '';
    if (AlphaStream._currentCode) {
      AlphaStream._send?.({ action: 'unsubscribe', code: AlphaStream._currentCode });
      AlphaStream._currentCode = null;
    }

    page.load();
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (location.hash !== '' && location.hash !== '#/') {
      history.pushState(null, '', '#/');
    }
  },

  _showPage(page) {
    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('welcomeScreen').style.display = '';

    const hero = document.getElementById('welcomeHero');
    if (hero) hero.style.display = page.showHero ? '' : 'none';

    const sectionSet = new Set(page.sections);
    document.querySelectorAll('#welcomeScreen .content-section').forEach(el => {
      el.style.display = sectionSet.has(el.id) ? '' : 'none';
    });

    window.scrollTo({ top: 0, behavior: 'smooth' });
  },

  _setActiveNav(nav) {
    this.activeNav = nav;
    document.querySelectorAll('.sidebar-item[data-nav], .header-link[data-nav], .mobile-nav-item[data-nav]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.nav === nav);
    });
  },

  _handleHash() {
    const hash = location.hash;

    // 종목 상세: #/stock/005930
    const stockMatch = hash.match(/^#\/stock\/(\d{6})$/);
    if (stockMatch) {
      const code = stockMatch[1];
      if (StockDetail.currentCode !== code) {
        StockDetail.load(code);
      }
      return;
    }

    // 페이지 라우팅 — 해시 → 페이지 이름 역방향 매핑
    for (const [nav, page] of Object.entries(this._pages)) {
      if (nav !== 'home' && page.hash === hash) {
        if (this.activeNav !== nav) this.navigate(nav);
        return;
      }
    }

    // 홈 (빈 해시 또는 #/)
    if (hash === '' || hash === '#' || hash === '#/') {
      if (StockDetail.currentCode || this.activeNav !== 'home') {
        this._goHome();
      }
    }
  },
};
