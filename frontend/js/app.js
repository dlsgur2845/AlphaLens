/**
 * AlphaLens 메인 앱 로직
 * - Phase 1: 차트 컨트롤 (캔들/라인, MA, 거래량)
 * - Phase 2: URL 딥링크, 토스트, 키보드 단축키
 * - Phase 3: 종목 비교, 스코어 히스토리
 */

/* ── WCAG 1.4.1 접근성: 변동률 포맷 헬퍼 ── */
function formatChange(value, suffix = '%') {
  if (value == null) return '-';
  const num = parseFloat(value);
  if (num > 0) return `▲ +${num.toFixed(2)}${suffix}`;
  if (num < 0) return `▼ ${num.toFixed(2)}${suffix}`;
  return `- 0.00${suffix}`;
}

/* ── 토스트 시스템 ── */
const Toast = {
  show(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = message;
    container.appendChild(el);

    setTimeout(() => {
      el.classList.add('toast-out');
      el.addEventListener('animationend', () => el.remove());
    }, duration);
  },
};

/* ── 섹션 프로그레스 바 ── */
const SectionProgress = {
  _bars: {},

  start(selector, key) {
    this.remove(key);
    const el = document.querySelector(selector);
    if (!el) return;
    const bar = document.createElement('div');
    bar.className = 'section-progress';
    bar.setAttribute('role', 'progressbar');
    bar.setAttribute('aria-label', `${key} 로딩 중`);
    bar.innerHTML = '<div class="section-progress-bar"></div>';
    el.prepend(bar);
    this._bars[key] = bar;
  },

  complete(key) {
    const bar = this._bars[key];
    if (!bar) return;
    bar.classList.add('completing');
    setTimeout(() => {
      bar.classList.add('completed');
      bar.addEventListener('transitionend', () => bar.remove(), { once: true });
      // fallback removal
      setTimeout(() => bar.remove(), 800);
    }, 300);
    delete this._bars[key];
  },

  error(key) {
    const bar = this._bars[key];
    if (!bar) return;
    bar.classList.add('error');
    setTimeout(() => {
      bar.classList.add('completed');
      bar.addEventListener('transitionend', () => bar.remove(), { once: true });
      setTimeout(() => bar.remove(), 800);
    }, 1500);
    delete this._bars[key];
  },

  remove(key) {
    const bar = this._bars[key];
    if (bar) { bar.remove(); delete this._bars[key]; }
  },

  clear() {
    Object.keys(this._bars).forEach((k) => {
      this._bars[k].remove();
      delete this._bars[k];
    });
  },
};

/* ── 메인 앱 ── */
const App = {
  currentCode: null,
  currentDays: 30,
  _lastDetail: null,

  init() {
    Search.init();
    PriceChart.init();
    AlphaStream.connect();

    this._initChartControls();
    this._initKeyboardShortcuts();
    this._initCompareMode();
    this._initNavigation();

    // 로고 클릭 → 홈 복귀
    document.getElementById('logoHome').addEventListener('click', () => this.goHome());

    // 즐겨찾기 지우기
    document.getElementById('clearFavorites').addEventListener('click', () => {
      Storage._save(Storage.KEYS.FAVORITES, []);
      this.renderWelcomeData();
      Toast.show('즐겨찾기를 비웠습니다', 'info');
    });

    // 최근검색 지우기
    document.getElementById('clearRecent').addEventListener('click', () => {
      Storage.clearRecent();
      this.renderWelcomeData();
      Toast.show('최근 검색을 비웠습니다', 'info');
    });

    // 대시보드 즐겨찾기 토글
    document.getElementById('favToggle').addEventListener('click', () => {
      if (!this._lastDetail) return;
      const d = this._lastDetail;
      const added = Storage.toggleFavorite({
        code: d.code, name: d.name, market: d.market,
        price: d.price, change_pct: d.change_pct,
        over_market: d.over_market || null,
      });
      this.updateFavToggle(d.code);
      Toast.show(added ? `${d.name} 즐겨찾기 추가` : `${d.name} 즐겨찾기 해제`, added ? 'success' : 'info');
    });

    // welcome 데이터 렌더
    this.renderWelcomeData();
    this._loadRecommendations();
    this._loadGeopolitical();

    // URL 해시 라우팅
    this._handleHash();
  },

  // ── 차트 컨트롤 ──

  _initChartControls() {
    // 차트 기간 버튼
    document.querySelectorAll('.chart-btn[data-days]').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.chart-btn[data-days]').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        this.currentDays = parseInt(btn.dataset.days);
        if (this.currentCode) this.loadChart(this.currentCode, this.currentDays);
      });
    });

    // 라인/캔들 전환
    document.querySelectorAll('.chart-toggle-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.chart-toggle-btn').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        PriceChart.setMode(btn.dataset.mode);
      });
    });

    // MA 토글
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
      // 입력 필드에 포커스 중이면 무시 (Escape 제외)
      const active = document.activeElement;
      const isInput = active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA');

      if (e.key === 'Escape') {
        e.preventDefault();
        // 비교 모드 닫기
        const overlay = document.getElementById('compareOverlay');
        if (overlay && overlay.style.display !== 'none') {
          overlay.style.display = 'none';
          return;
        }
        // 검색 드롭다운 닫기
        const dropdown = document.getElementById('searchResults');
        if (dropdown && dropdown.classList.contains('active')) {
          dropdown.classList.remove('active');
          document.getElementById('searchInput').blur();
          return;
        }
        // 홈으로
        this.goHome();
        return;
      }

      if (isInput) return;

      if (e.key === '/' || e.key === 's') {
        e.preventDefault();
        document.getElementById('searchInput').focus();
      } else if (e.key === 'f' || e.key === 'F') {
        e.preventDefault();
        document.getElementById('favToggle')?.click();
      }
    });
  },

  // ── URL 해시 라우팅 ──

  _initNavigation() {
    window.addEventListener('hashchange', () => this._handleHash());
  },

  _handleHash() {
    const hash = location.hash;
    const match = hash.match(/^#\/stock\/(\d{6})$/);
    if (match) {
      const code = match[1];
      if (this.currentCode !== code) {
        this.loadStock(code);
      }
    } else if (hash === '' || hash === '#' || hash === '#/') {
      if (this.currentCode) this.goHome();
    }
  },

  // ── 비교 모드 ──

  _initCompareMode() {
    const overlay = document.getElementById('compareOverlay');
    const compareBtn = document.getElementById('compareBtn');
    const closeBtn = document.getElementById('compareClose');

    compareBtn.addEventListener('click', () => {
      overlay.style.display = '';
      // 현재 종목을 첫 슬롯에 자동 입력
      if (this._lastDetail) {
        document.getElementById('compareInput1').value = this._lastDetail.name;
        this._loadCompareResult(1, this._lastDetail.code);
      }
    });

    closeBtn.addEventListener('click', () => {
      overlay.style.display = 'none';
    });

    // 비교 검색 입력
    [1, 2].forEach((slot) => {
      const input = document.getElementById(`compareInput${slot}`);
      const dropdown = document.getElementById(`compareDropdown${slot}`);
      let timer = null;

      input.addEventListener('input', () => {
        clearTimeout(timer);
        const q = input.value.trim();
        if (q.length === 0) { dropdown.classList.remove('active'); return; }
        timer = setTimeout(async () => {
          try {
            const results = await API.searchStocks(q);
            dropdown.innerHTML = results.map((s) => `
              <div class="search-item" data-code="${s.code}" data-name="${escapeHTML(s.name)}">
                <div><span class="search-item-name">${escapeHTML(s.name)}</span>
                <span class="search-item-code">${s.code}</span></div>
                <span class="search-item-market">${escapeHTML(s.market)}</span>
              </div>
            `).join('');
            dropdown.classList.add('active');
            dropdown.querySelectorAll('.search-item').forEach((item) => {
              item.addEventListener('click', () => {
                input.value = item.dataset.name;
                dropdown.classList.remove('active');
                this._loadCompareResult(slot, item.dataset.code);
              });
            });
          } catch (e) { /* ignore */ }
        }, 300);
      });

      document.addEventListener('click', (e) => {
        if (!e.target.closest(`.compare-slot`)) dropdown.classList.remove('active');
      });
    });
  },

  async _loadCompareResult(slot, code) {
    const el = document.getElementById(`compareResult${slot}`);
    el.innerHTML = '<div class="skeleton-block"></div>';
    try {
      const scoring = await API.getScoring(code);
      const color = ScoreGauge.getColor(scoring.total_score);
      const signalClass = ScoreGauge.getSignalClass(scoring.signal);
      const compareLabel = scoring.action_label || scoring.signal;
      const riskBadge = scoring.risk_grade ? ` · 리스크 ${scoring.risk_grade}` : '';
      el.innerHTML = `
        <div class="compare-name">${escapeHTML(scoring.name)}</div>
        <div class="compare-code">${scoring.code}</div>
        <div class="compare-score" style="color:${color}">${scoring.total_score.toFixed(1)}</div>
        <span class="compare-signal score-signal ${signalClass}">${compareLabel}${riskBadge}</span>
        <div class="compare-breakdown">
          <div class="compare-breakdown-row"><span>기술적 분석 (23%)</span><span>${scoring.breakdown.technical.toFixed(1)}</span></div>
          <div class="compare-breakdown-row"><span>매매 시그널 (19%)</span><span>${(scoring.breakdown.signal || 50).toFixed(1)}</span></div>
          <div class="compare-breakdown-row"><span>펀더멘탈 (19%)</span><span>${scoring.breakdown.fundamental.toFixed(1)}</span></div>
          <div class="compare-breakdown-row"><span>글로벌 매크로 (14%)</span><span>${(scoring.breakdown.macro || 50).toFixed(1)}</span></div>
          <div class="compare-breakdown-row"><span>리스크 (15%)</span><span>${(scoring.breakdown.risk || 50).toFixed(1)}</span></div>
          <div class="compare-breakdown-row"><span>관련기업 (5%)</span><span>${scoring.breakdown.related_momentum.toFixed(1)}</span></div>
          <div class="compare-breakdown-row"><span>뉴스 감성 (5%)</span><span>${scoring.breakdown.news_sentiment.toFixed(1)}</span></div>
        </div>
      `;
    } catch (e) {
      el.innerHTML = '<div style="color:var(--text-muted);padding:20px">데이터를 불러올 수 없습니다</div>';
    }
  },

  // ── 네비게이션 ──

  goHome() {
    this.currentCode = null;
    this._lastDetail = null;
    SectionProgress.clear();
    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('welcomeScreen').style.display = '';
    document.getElementById('searchInput').value = '';
    document.getElementById('compareBtn').style.display = 'none';
    if (AlphaStream._currentCode) {
      AlphaStream._send?.({ action: 'unsubscribe', code: AlphaStream._currentCode });
      AlphaStream._currentCode = null;
    }
    this.renderWelcomeData();
    this._loadRecommendations();
    this._loadGeopolitical();
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (location.hash !== '' && location.hash !== '#/') {
      history.pushState(null, '', '#/');
    }
  },

  // ── 종목 로드 ──

  async loadStock(code) {
    this.currentCode = code;

    document.getElementById('welcomeScreen').style.display = 'none';
    document.getElementById('dashboard').style.display = 'flex';
    document.getElementById('compareBtn').style.display = '';

    // URL 해시 갱신
    const newHash = `#/stock/${code}`;
    if (location.hash !== newHash) {
      history.pushState(null, '', newHash);
    }

    // 실시간 구독
    AlphaStream.subscribe(code);

    // 섹션별 스켈레톤 표시
    this._showSectionSkeletons();

    // 프로그레스 바 시작
    SectionProgress.clear();
    SectionProgress.start('.stock-summary', 'summary');
    SectionProgress.start('.score-section', 'score');
    SectionProgress.start('.chart-panel', 'chart');
    SectionProgress.start('.news-panel', 'news');
    SectionProgress.start('.related-section', 'related');

    // 각 요청을 독립적으로 실행 → 데이터 도착 즉시 해당 섹션 렌더링
    const guard = (fn) => { if (this.currentCode === code) fn(); };

    API.getStockDetail(code).then((data) => guard(() => {
      this._lastDetail = data;
      this.renderStockDetail(data);
      SectionProgress.complete('summary');
      const stockData = {
        code: data.code, name: data.name, market: data.market,
        price: data.price, change_pct: data.change_pct,
        over_market: data.over_market || null,
      };
      Storage.addRecent(stockData);
      Storage.updatePrice(stockData);
      this.updateFavToggle(data.code);
    })).catch((e) => { console.error('Detail error:', e); SectionProgress.error('summary'); });

    API.getPriceHistory(code, this.currentDays).then((data) => guard(() => {
      PriceChart.update(data);
      SectionProgress.complete('chart');
    })).catch((e) => { console.error('Chart error:', e); SectionProgress.error('chart'); });

    API.getScoring(code).then((data) => guard(() => {
      this.renderScoring(data);
      SectionProgress.complete('score');
      Storage.addScoreHistory(code, data.total_score, data.signal);
      ScoreGauge.drawHistory(code);
    })).catch((e) => { console.error('Scoring error:', e); SectionProgress.error('score'); });

    API.getNews(code).then((data) => guard(() => {
      this.renderNews(data);
      SectionProgress.complete('news');
    })).catch((e) => { console.error('News error:', e); SectionProgress.error('news'); });

    API.getRelatedCompanies(code).then((data) => guard(() => {
      this.renderRelated(data);
      SectionProgress.complete('related');
    })).catch((e) => { console.error('Related error:', e); SectionProgress.error('related'); });
  },

  _showSectionSkeletons() {
    // 각 섹션에 스켈레톤 표시
    const newsList = document.getElementById('newsList');
    if (newsList) newsList.innerHTML = '<div class="skeleton-block"></div><div class="skeleton-block" style="height:60px"></div><div class="skeleton-block" style="height:60px"></div>';
    const relGrid = document.getElementById('relatedGrid');
    if (relGrid) relGrid.innerHTML = '<div class="skeleton-block"></div><div class="skeleton-block"></div><div class="skeleton-block"></div>';
  },

  // ── Welcome 화면 데이터 ──

  renderWelcomeData() {
    const favs = Storage.getFavorites();
    const recent = Storage.getRecent();

    const favSection = document.getElementById('favoritesSection');
    const favGrid = document.getElementById('favoritesGrid');
    if (favs.length > 0) {
      favSection.style.display = '';
      favGrid.innerHTML = favs.map((s) => this._stockCardHTML(s, 'favorite')).join('');
      this._bindStockCards(favGrid, 'favorite');
    } else {
      favSection.style.display = 'none';
    }

    const recentSection = document.getElementById('recentSection');
    const recentGrid = document.getElementById('recentGrid');
    if (recent.length > 0) {
      recentSection.style.display = '';
      recentGrid.innerHTML = recent.map((s) => this._stockCardHTML(s, 'recent')).join('');
      this._bindStockCards(recentGrid, 'recent');
    } else {
      recentSection.style.display = 'none';
    }
  },

  _stockCardHTML(stock, type) {
    const changePct = stock.change_pct != null ? stock.change_pct : 0;
    const changeClass = changePct > 0 ? 'up' : changePct < 0 ? 'down' : '';
    const changeStr = formatChange(changePct);
    const priceStr = stock.price != null ? stock.price.toLocaleString() + '원' : '-';
    const ts = stock.timestamp || stock.addedAt;
    const timeStr = ts ? this._relativeTime(ts) : '';

    const actionBtn = type === 'favorite'
      ? `<button class="stock-card-action star" data-action="unfav" data-code="${stock.code}" title="즐겨찾기 해제">&#9733;</button>`
      : `<button class="stock-card-action" data-action="remove" data-code="${stock.code}" title="삭제">&#10005;</button>`;

    let overMarketHTML = '';
    const om = stock.over_market;
    if (om && om.price) {
      const omPct = om.change_pct != null ? om.change_pct : 0;
      const omClass = omPct > 0 ? 'up' : omPct < 0 ? 'down' : '';
      overMarketHTML = `
        <div class="stock-card-over">
          <span class="stock-card-over-label">시간외</span>
          <span class="stock-card-over-price">${om.price.toLocaleString()}원</span>
          <span class="stock-card-over-change ${omClass}" aria-label="시간외 변동률 ${formatChange(omPct)}">${formatChange(omPct)}</span>
        </div>`;
    }

    return `
      <div class="stock-card" data-code="${stock.code}" data-name="${escapeHTML(stock.name)}">
        ${actionBtn}
        <div class="stock-card-name">${escapeHTML(stock.name)}</div>
        <div class="stock-card-meta">${stock.code} · ${stock.market || ''}</div>
        <div class="stock-card-price">${priceStr}</div>
        <div class="stock-card-change ${changeClass}" aria-label="변동률 ${changeStr}">${changeStr}</div>
        ${overMarketHTML}
        ${timeStr ? `<div class="stock-card-time">${timeStr}</div>` : ''}
      </div>
    `;
  },

  // ── 지정학 리스크 ──

  async _loadGeopolitical() {
    const section = document.getElementById('geopoliticalSection');
    SectionProgress.start('#geopoliticalSection', 'geopolitical');
    try {
      const data = await API.getGeopolitical();
      if (!data || !data.risk_index) {
        SectionProgress.complete('geopolitical');
        section.style.display = 'none';
        return;
      }
      section.style.display = '';
      this._renderGeopolitical(data);
      SectionProgress.complete('geopolitical');
    } catch (e) {
      SectionProgress.error('geopolitical');
      section.style.display = 'none';
    }
  },

  _renderGeopolitical(data) {
    const ri = data.risk_index || {};
    const score = Number(ri.score) || 0;
    const SEVERITY_ALLOW = ['critical', 'high', 'medium', 'low'];
    const safeSeverity = (s) => SEVERITY_ALLOW.includes(s) ? s : 'low';

    // 리스크 점수
    const scoreEl = document.getElementById('geoRiskScore');
    scoreEl.textContent = score.toFixed(0);
    const scoreColor = score >= 70 ? 'var(--red)' : score >= 50 ? '#fb923c' : score >= 30 ? 'var(--yellow)' : 'var(--green)';
    scoreEl.style.color = scoreColor;

    // 리스크 라벨
    const labelEl = document.getElementById('geoRiskLabel');
    labelEl.textContent = ri.label || '분석 중';
    const labelClass = score >= 70 ? 'danger' : score >= 50 ? 'alert' : score >= 30 ? 'caution' : 'safe';
    labelEl.className = `geo-risk-label ${labelClass}`;

    // 리스크 바
    const barFill = document.getElementById('geoRiskBarFill');
    const barEl = document.getElementById('geoRiskBar');
    if (barEl) barEl.setAttribute('aria-valuenow', score.toFixed(0));
    barFill.style.width = `${Math.min(score, 100)}%`;
    barFill.style.background = score >= 70
      ? 'linear-gradient(90deg, #fb923c, var(--red))'
      : score >= 50
        ? 'linear-gradient(90deg, var(--yellow), #fb923c)'
        : score >= 30
          ? 'linear-gradient(90deg, var(--green), var(--yellow))'
          : 'var(--green)';

    // 감지된 이벤트
    const eventsEl = document.getElementById('geoEvents');
    const events = data.detected_events || {};
    const eventEntries = Object.entries(events);
    if (eventEntries.length > 0) {
      eventsEl.innerHTML = eventEntries.map(([, ev]) => {
        const sev = safeSeverity(ev.severity);
        const hitCount = Number(ev.hit_count) || 0;
        return `<div class="geo-event-chip">
          <span class="geo-event-icon">${escapeHTML(ev.icon || '')}</span>
          <span class="geo-event-label">${escapeHTML(ev.label || '')}</span>
          <span class="geo-event-severity ${sev}">${sev}</span>
          <span class="geo-event-count">${hitCount}건</span>
        </div>`;
      }).join('');
    } else {
      eventsEl.innerHTML = '<span class="geo-empty">감지된 이벤트 없음</span>';
    }

    // 섹터 영향
    const sectorEl = document.getElementById('geoSectorImpacts');
    const sectors = data.sector_impacts || {};
    const sectorEntries = Object.entries(sectors);
    if (sectorEntries.length > 0) {
      sectorEl.innerHTML = sectorEntries.slice(0, 12).map(([name, info]) => {
        const dir = info.direction || '';
        const cls = dir === '수혜' ? 'positive' : dir === '피해' ? 'negative' : 'neutral-impact';
        const impact = Number(info.total_impact) || 0;
        const sign = impact > 0 ? '+' : '';
        return `<span class="geo-sector-tag ${cls}">${dir === '수혜' ? '&#9650;' : dir === '피해' ? '&#9660;' : '&#9679;'} ${escapeHTML(name)} ${sign}${impact}</span>`;
      }).join('');
    } else {
      sectorEl.innerHTML = '<span class="geo-empty">영향 분석 데이터 없음</span>';
    }

    // 시나리오 트리거
    const triggersEl = document.getElementById('geoTriggers');
    const triggers = data.scenario_triggers || [];
    if (triggers.length > 0) {
      triggersEl.innerHTML = triggers.map((t) => {
        const sev = safeSeverity(t.severity);
        return `<div class="geo-trigger-item ${sev}">
          <span class="geo-trigger-signal">${escapeHTML(t.signal || '')}</span>
          <span class="geo-trigger-action">${escapeHTML(t.action || '')}</span>
        </div>`;
      }).join('');
    } else {
      triggersEl.innerHTML = '<span class="geo-empty">트리거 없음</span>';
    }

    // 업데이트 시간
    if (data.updated_at) {
      const t = new Date(data.updated_at);
      const articlesCount = Number(data.articles_analyzed) || 0;
      document.getElementById('geoUpdateTime').textContent =
        `${t.toLocaleTimeString('ko', { hour: '2-digit', minute: '2-digit' })} 기준 · ${articlesCount}건 분석`;
    }
  },

  // ── 추천/비추천 종목 ──

  async _loadRecommendations() {
    const recSection = document.getElementById('recommendSection');
    const avoidSection = document.getElementById('avoidSection');
    const recGrid = document.getElementById('recommendGrid');
    const avoidGrid = document.getElementById('avoidGrid');

    SectionProgress.start('#recommendSection', 'recommend');
    try {
      const data = await API.getRecommendations();

      // 시장 요약 렌더링
      if (data.market_summary) {
        this._renderMarketSummary(data.market_summary);
      }

      if (data.recommended && data.recommended.length > 0) {
        recSection.style.display = '';
        this._renderRecommendCards(recGrid, data.recommended, true);
        this._bindRecommendCards(recGrid);
      } else {
        recSection.style.display = 'none';
      }

      if (data.not_recommended && data.not_recommended.length > 0) {
        avoidSection.style.display = '';
        this._renderRecommendCards(avoidGrid, data.not_recommended, false);
        this._bindRecommendCards(avoidGrid);
      } else {
        avoidSection.style.display = 'none';
      }

      // 업데이트 시간 표시
      if (data.updated_at) {
        const t = new Date(data.updated_at);
        document.getElementById('recommendUpdateTime').textContent =
          `${t.toLocaleTimeString('ko', { hour: '2-digit', minute: '2-digit' })} 기준`;
      }
      SectionProgress.complete('recommend');
    } catch (e) {
      SectionProgress.error('recommend');
      // API 미구현 또는 실패 시 섹션 숨김
      recSection.style.display = 'none';
      avoidSection.style.display = 'none';
      document.getElementById('marketSummarySection').style.display = 'none';
    }
  },

  _renderMarketSummary(ms) {
    const section = document.getElementById('marketSummarySection');
    if (!ms) { section.style.display = 'none'; return; }
    section.style.display = '';

    // KOSPI
    const kospiEl = document.getElementById('msKospi');
    if (ms.kospi) {
      kospiEl.querySelector('.market-index-value').textContent = ms.kospi.value.toLocaleString(undefined, { maximumFractionDigits: 2 });
      const kChg = ms.kospi.change_pct || 0;
      const kChangeEl = kospiEl.querySelector('.market-index-change');
      kChangeEl.textContent = formatChange(kChg);
      kChangeEl.className = `market-index-change ${kChg > 0 ? 'up' : kChg < 0 ? 'down' : 'flat'}`;
      kChangeEl.setAttribute('aria-label', `KOSPI 변동률 ${formatChange(kChg)}`);
    }

    // KOSDAQ
    const kosdaqEl = document.getElementById('msKosdaq');
    if (ms.kosdaq) {
      kosdaqEl.querySelector('.market-index-value').textContent = ms.kosdaq.value.toLocaleString(undefined, { maximumFractionDigits: 2 });
      const qChg = ms.kosdaq.change_pct || 0;
      const qChangeEl = kosdaqEl.querySelector('.market-index-change');
      qChangeEl.textContent = formatChange(qChg);
      qChangeEl.className = `market-index-change ${qChg > 0 ? 'up' : qChg < 0 ? 'down' : 'flat'}`;
      qChangeEl.setAttribute('aria-label', `KOSDAQ 변동률 ${formatChange(qChg)}`);
    }

    // USD/KRW
    const fxEl = document.getElementById('msUsdKrw');
    if (ms.usd_krw != null) {
      fxEl.querySelector('.market-index-value').textContent = ms.usd_krw.toLocaleString(undefined, { maximumFractionDigits: 2 });
      const fxChg = ms.usd_krw_change_pct || 0;
      const fxChangeEl = fxEl.querySelector('.market-index-change');
      fxChangeEl.textContent = formatChange(fxChg);
      // 원화 기준: 환율 상승 = 원화 약세 = 부정적(red), 환율 하락 = 원화 강세 = 긍정적(blue)
      fxChangeEl.className = `market-index-change ${fxChg > 0 ? 'up' : fxChg < 0 ? 'down' : 'flat'}`;
      fxChangeEl.setAttribute('aria-label', `USD/KRW 변동률 ${formatChange(fxChg)}`);
    }

    // 매크로 점수
    const macroEl = document.getElementById('msMacro');
    macroEl.querySelector('.market-index-value').textContent = (ms.macro_score || 50).toFixed(1);
    const macroLabel = document.getElementById('msMacroLabel');
    macroLabel.textContent = ms.macro_label || '중립';
    // 라벨 색상 클래스
    const labelMap = { '강세': 'bullish', '약간 긍정': 'slightly-bullish', '중립': 'neutral', '약간 부정': 'slightly-bearish', '약세': 'bearish' };
    macroLabel.className = `market-macro-label ${labelMap[ms.macro_label] || 'neutral'}`;

    // 주요 요인
    const factorsEl = document.getElementById('msKeyFactors');
    if (ms.key_factors && ms.key_factors.length > 0) {
      factorsEl.innerHTML = ms.key_factors.map((f) =>
        `<span class="market-factor-tag">${escapeHTML(f)}</span>`
      ).join('');
    } else {
      factorsEl.innerHTML = '';
    }

    // 섹터 전망
    const sectorEl = document.getElementById('msSectorOutlook');
    if (ms.sector_outlook) {
      const entries = Object.entries(ms.sector_outlook);
      sectorEl.innerHTML = entries.map(([sector, outlook]) => {
        const cls = outlook === '긍정' ? 'positive' : outlook === '부정' ? 'negative' : 'neutral-sector';
        const icon = outlook === '긍정' ? '&#9650;' : outlook === '부정' ? '&#9660;' : '&#9679;';
        return `<span class="sector-tag ${cls}">${icon} ${escapeHTML(sector)}</span>`;
      }).join('');
    } else {
      sectorEl.innerHTML = '';
    }

    // 업데이트 시간
    if (ms.updated_at) {
      const t = new Date(ms.updated_at);
      document.getElementById('marketSummaryTime').textContent =
        `${t.toLocaleTimeString('ko', { hour: '2-digit', minute: '2-digit' })} 기준`;
    }
  },

  _renderRecommendCards(container, stocks, isRecommended) {
    container.innerHTML = stocks.map((s) => {
      const score = s.total_score != null ? s.total_score : 50;
      const color = ScoreGauge.getColor(score);
      const signalLabel = s.action_label || s.signal || '';
      const signalClass = ScoreGauge.getSignalClass(signalLabel);
      const cardClass = isRecommended ? 'recommended' : 'not-recommended';
      const reason = s.reason || '';

      // 가격 정보
      const priceStr = s.price ? s.price.toLocaleString() + '원' : '';

      // 지표 뱃지 (risk_grade, RSI overbought, PER/PBR)
      const badges = [];
      if (s.risk_grade) {
        const riskCls = 'risk-' + s.risk_grade.toLowerCase();
        badges.push(`<span class="recommend-card-badge ${riskCls}">리스크 ${escapeHTML(s.risk_grade)}</span>`);
      }
      if (s.overbought_warning) {
        badges.push(`<span class="recommend-card-badge overbought">과매수 주의</span>`);
      }
      if (s.rsi != null) {
        badges.push(`<span class="recommend-card-badge">RSI ${s.rsi.toFixed(0)}</span>`);
      }
      if (s.per != null && s.per > 0) {
        badges.push(`<span class="recommend-card-badge">PER ${s.per.toFixed(1)}</span>`);
      }

      return `
        <div class="recommend-card ${cardClass}" data-code="${s.code}" data-name="${escapeHTML(s.name)}">
          <div class="recommend-card-header">
            <div class="recommend-card-name">${escapeHTML(s.name)}</div>
            <div class="recommend-card-score" style="color:${color}">${score.toFixed(1)}</div>
          </div>
          <div class="recommend-card-meta">${s.code}${priceStr ? ' · ' + priceStr : ''}</div>
          <div class="recommend-card-bar">
            <div class="recommend-card-bar-fill" style="width:${score}%;background:${color}"></div>
          </div>
          <span class="recommend-card-signal score-signal ${signalClass}">${escapeHTML(signalLabel)}</span>
          ${reason ? `<div class="recommend-card-reason">${escapeHTML(reason)}</div>` : ''}
          ${badges.length > 0 ? `<div class="recommend-card-indicators">${badges.join('')}</div>` : ''}
        </div>
      `;
    }).join('');
  },

  _bindRecommendCards(container) {
    container.querySelectorAll('.recommend-card').forEach((card) => {
      card.addEventListener('click', () => {
        const code = card.dataset.code;
        const name = card.dataset.name;
        document.getElementById('searchInput').value = name;
        this.loadStock(code);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });
  },

  _relativeTime(timestamp) {
    const diff = Date.now() - timestamp;
    const sec = Math.floor(diff / 1000);
    if (sec < 60) return '방금 전';
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}분 전`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}시간 전`;
    const day = Math.floor(hr / 24);
    if (day < 30) return `${day}일 전`;
    return `${Math.floor(day / 30)}달 전`;
  },

  _bindStockCards(container, type) {
    container.querySelectorAll('.stock-card').forEach((card) => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('.stock-card-action')) return;
        const code = card.dataset.code;
        const name = card.dataset.name;
        document.getElementById('searchInput').value = name;
        this.loadStock(code);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });

    container.querySelectorAll('.stock-card-action').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const code = btn.dataset.code;
        const action = btn.dataset.action;
        if (action === 'remove') {
          Storage.removeRecent(code);
          Toast.show('최근 검색에서 삭제됨', 'info');
        } else if (action === 'unfav') {
          Storage.removeFavorite(code);
          Toast.show('즐겨찾기 해제됨', 'info');
        }
        this.renderWelcomeData();
      });
    });
  },

  updateFavToggle(code) {
    const btn = document.getElementById('favToggle');
    if (Storage.isFavorite(code)) {
      btn.innerHTML = '&#9733;';
      btn.classList.add('active');
    } else {
      btn.innerHTML = '&#9734;';
      btn.classList.remove('active');
    }
  },

  // ── 렌더 메서드 ──

  renderStockDetail(data) {
    document.getElementById('stockName').textContent = data.name;
    document.getElementById('stockCode').textContent = data.code;
    document.getElementById('stockMarket').textContent = data.market;
    document.getElementById('stockSector').textContent = data.sector || '';

    const statusText = data.market_status === 'OPEN' ? '거래중' : '장마감';
    document.getElementById('priceLabel').innerHTML =
      `KRX 종가 <span class="market-status-badge ${data.market_status === 'OPEN' ? 'open' : 'close'}">${statusText}</span>`;

    document.getElementById('stockPrice').textContent = data.price.toLocaleString() + '원';

    const changeEl = document.getElementById('stockChange');
    const changeSymbol = data.change > 0 ? '▲' : data.change < 0 ? '▼' : '-';
    const sign = data.change >= 0 ? '+' : '';
    changeEl.textContent = `${changeSymbol} ${sign}${data.change.toLocaleString()}원 (${sign}${data.change_pct}%)`;
    changeEl.className = `stock-change ${data.change >= 0 ? 'up' : 'down'}`;
    changeEl.setAttribute('aria-label', `변동 ${changeSymbol} ${sign}${data.change.toLocaleString()}원, ${formatChange(data.change_pct)}`);

    const overGroup = document.getElementById('overMarketGroup');
    if (data.over_market && data.over_market.price) {
      overGroup.style.display = 'block';
      const sessionLabel = data.over_market.session_type === 'PRE_MARKET' ? '프리마켓(NXT)' : '시간외(NXT)';
      const overStatus = data.over_market.status === 'OPEN' ? '거래중' : '마감';
      document.getElementById('overMarketLabel').innerHTML =
        `${sessionLabel} <span class="market-status-badge ${data.over_market.status === 'OPEN' ? 'open' : 'close'}">${overStatus}</span>`;
      document.getElementById('overMarketPrice').textContent = data.over_market.price.toLocaleString() + '원';
      const overSymbol = data.over_market.change > 0 ? '▲' : data.over_market.change < 0 ? '▼' : '-';
      const overSign = data.over_market.change >= 0 ? '+' : '';
      const overChangeEl = document.getElementById('overMarketChange');
      overChangeEl.textContent = `${overSymbol} ${overSign}${data.over_market.change.toLocaleString()}원 (${overSign}${data.over_market.change_pct}%)`;
      overChangeEl.className = `over-market-change ${data.over_market.change >= 0 ? 'up' : 'down'}`;
      overChangeEl.setAttribute('aria-label', `시간외 변동 ${overSymbol} ${overSign}${data.over_market.change.toLocaleString()}원, ${formatChange(data.over_market.change_pct)}`);
      if (data.over_market.price !== data.price) {
        const diff = data.over_market.price - data.price;
        const diffPct = ((diff / data.price) * 100).toFixed(2);
        const diffSign = diff >= 0 ? '+' : '';
        document.getElementById('overMarketTime').textContent =
          `KRX 대비 ${diffSign}${diff.toLocaleString()}원 (${diffSign}${diffPct}%)`;
      } else {
        document.getElementById('overMarketTime').textContent = '';
      }
    } else {
      overGroup.style.display = 'none';
    }
  },

  renderScoring(data) {
    ScoreGauge.draw('scoreGauge', data.total_score);
    document.getElementById('scoreValue').textContent = data.total_score.toFixed(1);

    // 7단계 시그널 라벨 (action_label 우선, fallback: signal)
    const label = data.action_label || data.signal;
    const signalEl = document.getElementById('scoreSignal');
    signalEl.textContent = label;
    signalEl.className = `score-signal ${ScoreGauge.getSignalClass(label)}`;

    // 리스크 등급 표시
    if (data.risk_grade) {
      signalEl.textContent = `${label} · 리스크 ${data.risk_grade}`;
    }

    const updated = new Date(data.updated_at);
    document.getElementById('scoreUpdated').textContent =
      `${updated.toLocaleDateString('ko')} ${updated.toLocaleTimeString('ko', { hour: '2-digit', minute: '2-digit' })} 기준`;

    ScoreGauge.updateBreakdown(data.breakdown);
    if (data.details) this._renderScoreTooltips(data.details, data.breakdown);

    // 액션 가이드 렌더링
    this.renderActionGuide(data);
  },

  renderActionGuide(data) {
    const guide = document.getElementById('actionGuide');
    if (!guide || !data) return;
    guide.style.display = '';

    const price = this._lastDetail?.price || 0;
    const atr = data.details?.technical?.atr || 0;
    const totalScore = data.total_score || 50;
    const riskGrade = data.details?.risk?.grade || data.risk_grade || '-';
    const positionPct = data.details?.risk?.position_size_pct || 0;
    const actionLabel = data.action_label || data.signal || '중립';

    // 목표가: 현재가 + ATR x 배수 (스코어 기반)
    const targetMultiplier = totalScore > 65 ? 3.0 : totalScore > 55 ? 2.0 : 1.5;
    const targetPrice = price > 0 && atr > 0 ? Math.round(price + atr * targetMultiplier) : null;

    // 손절가: 현재가 - ATR x 2
    const stopLoss = price > 0 && atr > 0 ? Math.round(price - atr * 2) : null;

    // 확신도: 점수 편차 기반
    const deviation = Math.abs(totalScore - 50);
    const confidence = deviation > 25 ? '높음' : deviation > 15 ? '보통' : '낮음';

    document.getElementById('actionOpinion').textContent = actionLabel;
    document.getElementById('actionTarget').textContent = targetPrice ? targetPrice.toLocaleString() + '원' : '-';
    document.getElementById('actionStopLoss').textContent = stopLoss ? stopLoss.toLocaleString() + '원' : '-';
    document.getElementById('actionPosition').textContent = positionPct > 0 ? positionPct.toFixed(1) + '%' : '-';
    document.getElementById('actionRiskGrade').textContent = riskGrade;
    document.getElementById('actionConfidence').textContent = confidence;

    // 의견 색상
    const opinionEl = document.getElementById('actionOpinion');
    opinionEl.className = 'action-value';
    if (totalScore >= 65) opinionEl.classList.add('bullish');
    else if (totalScore <= 35) opinionEl.classList.add('bearish');
  },

  _renderScoreTooltips(details, breakdown) {
    const tech = details.technical || {};
    const ma = tech.moving_averages || {};
    const macd = tech.macd || {};
    const vol = tech.volume_trend || {};
    const obv = tech.obv || {};
    const over = details.over_market;

    let techHTML = `<div class="tip-title">기술적 분석 (비중 23%)</div>`;
    techHTML += this._tipRow('RSI (14)', tech.rsi != null ? tech.rsi.toFixed(1) : '-',
      tech.rsi < 30 ? 'positive' : tech.rsi > 70 ? 'negative' : '');
    techHTML += this._tipRow('MACD 히스토그램', macd.histogram != null ? macd.histogram.toFixed(1) : '-',
      macd.bullish ? 'positive' : macd.bullish === false ? 'negative' : '');
    if (macd.crossover) techHTML += this._tipRow('MACD 크로스오버', '매수 신호', 'positive');
    if (macd.crossunder) techHTML += this._tipRow('MACD 크로스언더', '매도 신호', 'negative');
    techHTML += this._tipRow('20일선 위', ma.above_ma20 ? 'Yes' : 'No', ma.above_ma20 ? 'positive' : 'negative');
    techHTML += this._tipRow('60일선 위', ma.above_ma60 != null ? (ma.above_ma60 ? 'Yes' : 'No') : '-',
      ma.above_ma60 ? 'positive' : ma.above_ma60 === false ? 'negative' : '');
    if (ma.ma_aligned_bull) techHTML += this._tipRow('MA 정배열', '강세', 'positive');
    if (ma.ma_aligned_bear) techHTML += this._tipRow('MA 역배열', '약세', 'negative');
    if (ma.golden_cross) techHTML += this._tipRow('골든크로스', '발생', 'positive');
    if (ma.dead_cross) techHTML += this._tipRow('데드크로스', '발생', 'negative');
    if (vol.volume_ratio) techHTML += this._tipRow('거래량 비율', vol.volume_ratio.toFixed(2) + 'x', vol.high_volume ? 'positive' : '');
    if (obv.obv_trend) techHTML += this._tipRow('OBV 추세', obv.obv_trend === 'bullish' ? '강세' : obv.obv_trend === 'bearish' ? '약세' : '중립',
      obv.obv_trend === 'bullish' ? 'positive' : obv.obv_trend === 'bearish' ? 'negative' : '');
    if (obv.divergence) techHTML += this._tipRow('OBV 다이버전스', obv.divergence === 'bullish' ? '강세' : '약세',
      obv.divergence === 'bullish' ? 'positive' : 'negative');
    const bb = tech.bollinger_bands || {};
    if (bb.pct_b != null) {
      techHTML += this._tipRow('BB %B', bb.pct_b.toFixed(2),
        bb.pct_b < 0.2 ? 'positive' : bb.pct_b > 0.8 ? 'negative' : '');
    }
    if (over) {
      techHTML += '<div class="tip-divider"></div>';
      techHTML += this._tipRow('NXT 괴리', (over.diff_pct >= 0 ? '+' : '') + over.diff_pct + '%',
        over.diff_pct > 0 ? 'positive' : over.diff_pct < 0 ? 'negative' : '');
    }
    document.getElementById('tooltipTechnical').innerHTML = techHTML;

    // 매매 시그널 툴팁
    const sig = details.signal || {};
    let sigHTML = `<div class="tip-title">매매 시그널 (비중 19%)</div>`;
    sigHTML += this._tipRow('레짐', sig.regime || '-',
      sig.regime === 'BULL' ? 'positive' : sig.regime === 'BEAR' ? 'negative' : '');
    sigHTML += this._tipRow('액션', sig.action_label || '-');
    if (sig.breakdown) {
      sigHTML += this._tipRow('모멘텀', sig.breakdown.momentum != null ? sig.breakdown.momentum.toFixed(1) : '-');
      sigHTML += this._tipRow('평균회귀', sig.breakdown.mean_reversion != null ? sig.breakdown.mean_reversion.toFixed(1) : '-');
      sigHTML += this._tipRow('돌파', sig.breakdown.breakout != null ? sig.breakdown.breakout.toFixed(1) : '-');
    }
    if (sig.buy_signals && sig.buy_signals.length > 0) {
      sigHTML += '<div class="tip-divider"></div>';
      sig.buy_signals.forEach((s) => { sigHTML += this._tipRow('매수', s, 'positive'); });
    }
    if (sig.sell_signals && sig.sell_signals.length > 0) {
      sig.sell_signals.forEach((s) => { sigHTML += this._tipRow('매도', s, 'negative'); });
    }
    const sigEl = document.getElementById('tooltipSignal');
    if (sigEl) sigEl.innerHTML = sigHTML;

    // 펀더멘탈 툴팁
    const fund = details.fundamental || {};
    let fundHTML = `<div class="tip-title">펀더멘탈 (비중 19%)</div>`;
    fundHTML += this._tipRow('PER', fund.per != null ? fund.per.toFixed(2) + '배' : '-',
      fund.per != null ? (fund.per > 0 && fund.per < 15 ? 'positive' : fund.per >= 40 || fund.per < 0 ? 'negative' : '') : '');
    fundHTML += this._tipRow('PBR', fund.pbr != null ? fund.pbr.toFixed(2) + '배' : '-',
      fund.pbr != null ? (fund.pbr < 1.0 ? 'positive' : fund.pbr >= 3.0 ? 'negative' : '') : '');
    if (fund.roe != null) {
      fundHTML += this._tipRow('ROE', fund.roe.toFixed(2) + '%',
        fund.roe > 15 ? 'positive' : fund.roe < 0 ? 'negative' : '');
    }
    if (fund.sector_standard) {
      fundHTML += this._tipRow('섹터 PER 기준', fund.sector_standard + '배');
    }
    fundHTML += '<div class="tip-divider"></div>';
    fundHTML += '<div class="tip-note">PER·PBR·ROE 기반 섹터별 밸류에이션 평가</div>';
    document.getElementById('tooltipFundamental').innerHTML = fundHTML;

    // 글로벌 매크로 툴팁
    const macro = details.macro || {};
    let macroHTML = `<div class="tip-title">글로벌 매크로 (비중 14%)</div>`;
    if (macro.breakdown) {
      macroHTML += this._tipRow('미국 시장', macro.breakdown.us_market != null ? (macro.breakdown.us_market >= 0 ? '+' : '') + macro.breakdown.us_market.toFixed(1) : '-',
        macro.breakdown.us_market > 0 ? 'positive' : macro.breakdown.us_market < 0 ? 'negative' : '');
      macroHTML += this._tipRow('환율', macro.breakdown.fx != null ? (macro.breakdown.fx >= 0 ? '+' : '') + macro.breakdown.fx.toFixed(1) : '-',
        macro.breakdown.fx > 0 ? 'positive' : macro.breakdown.fx < 0 ? 'negative' : '');
      macroHTML += this._tipRow('금리', macro.breakdown.rates != null ? (macro.breakdown.rates >= 0 ? '+' : '') + macro.breakdown.rates.toFixed(1) : '-',
        macro.breakdown.rates > 0 ? 'positive' : macro.breakdown.rates < 0 ? 'negative' : '');
      macroHTML += this._tipRow('원자재', macro.breakdown.commodities != null ? (macro.breakdown.commodities >= 0 ? '+' : '') + macro.breakdown.commodities.toFixed(1) : '-',
        macro.breakdown.commodities > 0 ? 'positive' : macro.breakdown.commodities < 0 ? 'negative' : '');
      macroHTML += this._tipRow('중국', macro.breakdown.china != null ? (macro.breakdown.china >= 0 ? '+' : '') + macro.breakdown.china.toFixed(1) : '-',
        macro.breakdown.china > 0 ? 'positive' : macro.breakdown.china < 0 ? 'negative' : '');
    }
    if (macro.details) {
      macroHTML += '<div class="tip-divider"></div>';
      if (macro.details.sp500) macroHTML += this._tipRow('S&P 500', formatChange(macro.details.sp500.change_pct),
        macro.details.sp500.change_pct > 0 ? 'positive' : macro.details.sp500.change_pct < 0 ? 'negative' : '');
      if (macro.details.usdkrw) macroHTML += this._tipRow('USD/KRW', macro.details.usdkrw.price.toLocaleString());
      if (macro.details.vix) macroHTML += this._tipRow('VIX', macro.details.vix.price.toFixed(1),
        macro.details.vix.price > 25 ? 'negative' : macro.details.vix.price < 15 ? 'positive' : '');
    }
    const macroEl = document.getElementById('tooltipMacro');
    if (macroEl) macroEl.innerHTML = macroHTML;

    // 리스크 툴팁
    const risk = details.risk || {};
    let riskHTML = `<div class="tip-title">리스크 관리 (비중 15%)</div>`;
    if (risk.grade) riskHTML += this._tipRow('리스크 등급', risk.grade,
      risk.grade === 'A' || risk.grade === 'B' ? 'positive' : risk.grade === 'D' || risk.grade === 'E' ? 'negative' : '');
    if (risk.breakdown) {
      riskHTML += this._tipRow('변동성', risk.breakdown.volatility != null ? risk.breakdown.volatility.toFixed(1) : '-');
      riskHTML += this._tipRow('MDD', risk.breakdown.mdd != null ? risk.breakdown.mdd.toFixed(1) : '-');
      riskHTML += this._tipRow('VaR/CVaR', risk.breakdown.var_cvar != null ? risk.breakdown.var_cvar.toFixed(1) : '-');
      riskHTML += this._tipRow('유동성', risk.breakdown.liquidity != null ? risk.breakdown.liquidity.toFixed(1) : '-');
    }
    if (risk.position_size_pct) riskHTML += this._tipRow('추천 비중', risk.position_size_pct.toFixed(1) + '%');
    if (risk.atr) riskHTML += this._tipRow('ATR', risk.atr.toFixed(0) + '원');
    const riskEl = document.getElementById('tooltipRisk');
    if (riskEl) riskEl.innerHTML = riskHTML;

    // 뉴스 감성 툴팁
    const news = details.news || {};
    let newsHTML = `<div class="tip-title">뉴스 감성분석 (비중 5%)</div>`;
    newsHTML += this._tipRow('분석 기사 수', (news.total_articles || 0) + '건');
    newsHTML += this._tipRow('긍정', (news.positive || 0) + '건', 'positive');
    newsHTML += this._tipRow('부정', (news.negative || 0) + '건', 'negative');
    newsHTML += this._tipRow('중립', (news.neutral || 0) + '건');
    newsHTML += this._tipRow('종합 감성', news.overall_sentiment != null ? (news.overall_sentiment > 0 ? '+' : '') + news.overall_sentiment.toFixed(3) : '-',
      news.overall_sentiment > 0.15 ? 'positive' : news.overall_sentiment < -0.15 ? 'negative' : '');
    newsHTML += '<div class="tip-divider"></div>';
    newsHTML += '<div class="tip-note">종합 점수에 5% 비중으로 반영됩니다</div>';
    document.getElementById('tooltipNews').innerHTML = newsHTML;

    // 관련기업 툴팁
    const rel = details.related || {};
    let relHTML = `<div class="tip-title">관련기업 모멘텀 (비중 5%)</div>`;
    relHTML += this._tipRow('탐색 기업 수', (rel.related_count || 0) + '개');
    relHTML += this._tipRow('평균 수익률', rel.avg_change_pct != null ? formatChange(rel.avg_change_pct) : '-',
      rel.avg_change_pct > 0 ? 'positive' : rel.avg_change_pct < 0 ? 'negative' : '');
    if (rel.companies && rel.companies.length > 0) {
      relHTML += '<div class="tip-divider"></div>';
      rel.companies.slice(0, 5).forEach((c) => {
        relHTML += this._tipRow(escapeHTML(c.name), formatChange(c.change_pct),
          c.change_pct > 0 ? 'positive' : c.change_pct < 0 ? 'negative' : '');
      });
      if (rel.companies.length > 5) {
        relHTML += `<div class="tip-note">외 ${rel.companies.length - 5}개 기업</div>`;
      }
    }
    document.getElementById('tooltipRelated').innerHTML = relHTML;
  },

  _tipRow(label, value, colorClass) {
    const cls = colorClass ? ` ${colorClass}` : '';
    return `<div class="tip-row"><span>${label}</span><span class="tip-val${cls}">${value}</span></div>`;
  },

  renderNews(data) {
    const summaryEl = document.getElementById('newsSummary');
    const listEl = document.getElementById('newsList');

    const sentColor =
      data.overall_label === '긍정' ? 'var(--green)' :
      data.overall_label === '부정' ? 'var(--red)' : 'var(--yellow)';

    summaryEl.innerHTML = `
      <span style="color:${sentColor}">${data.overall_label}</span>
      <span style="color:var(--text-muted)">
        (긍정 ${data.positive_count} / 부정 ${data.negative_count} / 중립 ${data.neutral_count})
      </span>
    `;

    if (data.articles.length === 0) {
      listEl.innerHTML = '<div class="loading">관련 뉴스가 없습니다</div>';
      return;
    }

    listEl.innerHTML = data.articles
      .map((article) => {
        const sentClass =
          article.sentiment_label === '긍정' ? 'positive' :
          article.sentiment_label === '부정' ? 'negative' : 'neutral';
        const scoreSign = article.sentiment_score > 0 ? '+' : '';
        return `
        <a href="${safeURL(article.link)}" target="_blank" rel="noopener noreferrer" class="news-item" title="${escapeHTML(article.title)}">
          <div class="news-sentiment-badge ${sentClass}">${article.sentiment_label}</div>
          <div class="news-item-content">
            <div class="news-item-title">${escapeHTML(article.title)}</div>
            <div class="news-item-meta">
              <span>${escapeHTML(article.source)}</span>
              <span>${article.date}</span>
              <span class="news-item-score ${sentClass}">${scoreSign}${article.sentiment_score.toFixed(2)}</span>
            </div>
          </div>
        </a>
      `;
      })
      .join('');
  },

  renderRelated(data) {
    const countEl = document.getElementById('relatedCount');
    const gridEl = document.getElementById('relatedGrid');

    countEl.textContent = `${data.total}개 기업 발견`;

    if (data.companies.length === 0) {
      gridEl.innerHTML = '<div class="loading">관련기업을 찾지 못했습니다</div>';
      return;
    }

    gridEl.innerHTML = data.companies
      .map((c) => {
        const changeStr = c.change_pct !== null ? formatChange(c.change_pct) : '-';
        const changeClass = c.change_pct > 0 ? 'up' : c.change_pct < 0 ? 'down' : '';
        return `
        <div class="related-card" data-code="${c.code}">
          <div class="related-card-name">${escapeHTML(c.name)}</div>
          <div class="related-card-code">${c.code} · ${c.market}</div>
          <div class="related-card-type">${escapeHTML(c.relation_type)}</div>
          <div class="related-card-change ${changeClass}" aria-label="10일 변동률 ${changeStr}"><span class="related-card-period">10일</span> ${changeStr}</div>
        </div>
      `;
      })
      .join('');

    gridEl.querySelectorAll('.related-card').forEach((card) => {
      card.addEventListener('click', () => {
        const code = card.dataset.code;
        document.getElementById('searchInput').value = card.querySelector('.related-card-name').textContent;
        this.loadStock(code);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });
  },

  async loadChart(code, days) {
    try {
      const data = await API.getPriceHistory(code, days);
      PriceChart.update(data);
    } catch (err) {
      console.error('차트 로드 실패:', err);
    }
  },
};

// 초기화
document.addEventListener('DOMContentLoaded', () => App.init());
