/**
 * AlphaLens 메인 앱 로직
 * - Phase 1: 차트 컨트롤 (캔들/라인, MA, 거래량)
 * - Phase 2: URL 딥링크, 토스트, 키보드 단축키
 * - Phase 3: 종목 비교, 스코어 히스토리
 */

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
              <div class="search-item" data-code="${s.code}" data-name="${s.name}">
                <div><span class="search-item-name">${s.name}</span>
                <span class="search-item-code">${s.code}</span></div>
                <span class="search-item-market">${s.market}</span>
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
      el.innerHTML = `
        <div class="compare-name">${scoring.name}</div>
        <div class="compare-code">${scoring.code}</div>
        <div class="compare-score" style="color:${color}">${scoring.total_score.toFixed(1)}</div>
        <span class="compare-signal score-signal ${signalClass}">${scoring.signal}</span>
        <div class="compare-breakdown">
          <div class="compare-breakdown-row"><span>기술적 분석</span><span>${scoring.breakdown.technical.toFixed(1)}</span></div>
          <div class="compare-breakdown-row"><span>뉴스 감성</span><span>${scoring.breakdown.news_sentiment.toFixed(1)}</span></div>
          <div class="compare-breakdown-row"><span>펀더멘탈</span><span>${scoring.breakdown.fundamental.toFixed(1)}</span></div>
          <div class="compare-breakdown-row"><span>관련기업</span><span>${scoring.breakdown.related_momentum.toFixed(1)}</span></div>
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
    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('welcomeScreen').style.display = '';
    document.getElementById('searchInput').value = '';
    document.getElementById('compareBtn').style.display = 'none';
    if (AlphaStream._currentCode) {
      AlphaStream._send?.({ action: 'unsubscribe', code: AlphaStream._currentCode });
      AlphaStream._currentCode = null;
    }
    this.renderWelcomeData();
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

    // 각 요청을 독립적으로 실행 → 데이터 도착 즉시 해당 섹션 렌더링
    const guard = (fn) => { if (this.currentCode === code) fn(); };

    API.getStockDetail(code).then((data) => guard(() => {
      this._lastDetail = data;
      this.renderStockDetail(data);
      const stockData = {
        code: data.code, name: data.name, market: data.market,
        price: data.price, change_pct: data.change_pct,
        over_market: data.over_market || null,
      };
      Storage.addRecent(stockData);
      Storage.updatePrice(stockData);
      this.updateFavToggle(data.code);
    })).catch((e) => console.error('Detail error:', e));

    API.getPriceHistory(code, this.currentDays).then((data) => guard(() => {
      PriceChart.update(data);
    })).catch((e) => console.error('Chart error:', e));

    API.getScoring(code).then((data) => guard(() => {
      this.renderScoring(data);
      Storage.addScoreHistory(code, data.total_score, data.signal);
      ScoreGauge.drawHistory(code);
    })).catch((e) => console.error('Scoring error:', e));

    API.getNews(code).then((data) => guard(() => {
      this.renderNews(data);
    })).catch((e) => console.error('News error:', e));

    API.getRelatedCompanies(code).then((data) => guard(() => {
      this.renderRelated(data);
    })).catch((e) => console.error('Related error:', e));
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
    const changeStr = changePct > 0 ? `+${changePct}%` : `${changePct}%`;
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
      const omSign = omPct > 0 ? '+' : '';
      overMarketHTML = `
        <div class="stock-card-over">
          <span class="stock-card-over-label">시간외</span>
          <span class="stock-card-over-price">${om.price.toLocaleString()}원</span>
          <span class="stock-card-over-change ${omClass}">${omSign}${omPct}%</span>
        </div>`;
    }

    return `
      <div class="stock-card" data-code="${stock.code}" data-name="${stock.name}">
        ${actionBtn}
        <div class="stock-card-name">${stock.name}</div>
        <div class="stock-card-meta">${stock.code} · ${stock.market || ''}</div>
        <div class="stock-card-price">${priceStr}</div>
        <div class="stock-card-change ${changeClass}">${changeStr}</div>
        ${overMarketHTML}
        ${timeStr ? `<div class="stock-card-time">${timeStr}</div>` : ''}
      </div>
    `;
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
    const sign = data.change >= 0 ? '+' : '';
    changeEl.textContent = `${sign}${data.change.toLocaleString()}원 (${sign}${data.change_pct}%)`;
    changeEl.className = `stock-change ${data.change >= 0 ? 'up' : 'down'}`;

    const overGroup = document.getElementById('overMarketGroup');
    if (data.over_market && data.over_market.price) {
      overGroup.style.display = 'block';
      const sessionLabel = data.over_market.session_type === 'PRE_MARKET' ? '프리마켓(NXT)' : '시간외(NXT)';
      const overStatus = data.over_market.status === 'OPEN' ? '거래중' : '마감';
      document.getElementById('overMarketLabel').innerHTML =
        `${sessionLabel} <span class="market-status-badge ${data.over_market.status === 'OPEN' ? 'open' : 'close'}">${overStatus}</span>`;
      document.getElementById('overMarketPrice').textContent = data.over_market.price.toLocaleString() + '원';
      const overSign = data.over_market.change >= 0 ? '+' : '';
      const overChangeEl = document.getElementById('overMarketChange');
      overChangeEl.textContent = `${overSign}${data.over_market.change.toLocaleString()}원 (${overSign}${data.over_market.change_pct}%)`;
      overChangeEl.className = `over-market-change ${data.over_market.change >= 0 ? 'up' : 'down'}`;
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

    const signalEl = document.getElementById('scoreSignal');
    signalEl.textContent = data.signal;
    signalEl.className = `score-signal ${ScoreGauge.getSignalClass(data.signal)}`;

    const updated = new Date(data.updated_at);
    document.getElementById('scoreUpdated').textContent =
      `${updated.toLocaleDateString('ko')} ${updated.toLocaleTimeString('ko', { hour: '2-digit', minute: '2-digit' })} 기준`;

    ScoreGauge.updateBreakdown(data.breakdown);
    if (data.details) this._renderScoreTooltips(data.details, data.breakdown);
  },

  _renderScoreTooltips(details, breakdown) {
    const tech = details.technical || {};
    const ma = tech.moving_averages || {};
    const macd = tech.macd || {};
    const vol = tech.volume_trend || {};
    const over = details.over_market;

    let techHTML = `<div class="tip-title">기술적 분석 (비중 50%)</div>`;
    techHTML += this._tipRow('RSI (14)', tech.rsi != null ? tech.rsi.toFixed(1) : '-',
      tech.rsi < 30 ? 'positive' : tech.rsi > 70 ? 'negative' : '');
    techHTML += this._tipRow('MACD 히스토그램', macd.histogram != null ? macd.histogram.toFixed(1) : '-',
      macd.bullish ? 'positive' : macd.bullish === false ? 'negative' : '');
    techHTML += this._tipRow('5일선 위', ma.above_ma5 ? 'Yes' : 'No', ma.above_ma5 ? 'positive' : 'negative');
    techHTML += this._tipRow('20일선 위', ma.above_ma20 ? 'Yes' : 'No', ma.above_ma20 ? 'positive' : 'negative');
    techHTML += this._tipRow('60일선 위', ma.above_ma60 != null ? (ma.above_ma60 ? 'Yes' : 'No') : '-',
      ma.above_ma60 ? 'positive' : ma.above_ma60 === false ? 'negative' : '');
    if (ma.golden_cross) techHTML += this._tipRow('골든크로스', '발생', 'positive');
    if (ma.dead_cross) techHTML += this._tipRow('데드크로스', '발생', 'negative');
    if (vol.volume_ratio) techHTML += this._tipRow('거래량 비율', vol.volume_ratio.toFixed(2) + 'x', vol.high_volume ? 'positive' : '');
    if (over) {
      techHTML += '<div class="tip-divider"></div>';
      techHTML += this._tipRow('NXT 괴리', (over.diff_pct >= 0 ? '+' : '') + over.diff_pct + '%',
        over.diff_pct > 0 ? 'positive' : over.diff_pct < 0 ? 'negative' : '');
    }
    document.getElementById('tooltipTechnical').innerHTML = techHTML;

    const news = details.news || {};
    let newsHTML = `<div class="tip-title">뉴스 감성분석</div>`;
    newsHTML += this._tipRow('분석 기사 수', (news.total_articles || 0) + '건');
    newsHTML += this._tipRow('긍정', (news.positive || 0) + '건', 'positive');
    newsHTML += this._tipRow('부정', (news.negative || 0) + '건', 'negative');
    newsHTML += this._tipRow('중립', (news.neutral || 0) + '건');
    newsHTML += this._tipRow('종합 감성', news.overall_sentiment != null ? (news.overall_sentiment > 0 ? '+' : '') + news.overall_sentiment.toFixed(3) : '-',
      news.overall_sentiment > 0.15 ? 'positive' : news.overall_sentiment < -0.15 ? 'negative' : '');
    newsHTML += '<div class="tip-divider"></div>';
    newsHTML += '<div class="tip-note">종합 점수에 반영되지 않습니다 (참고용)</div>';
    document.getElementById('tooltipNews').innerHTML = newsHTML;

    const fund = details.fundamental || {};
    let fundHTML = `<div class="tip-title">펀더멘탈 (비중 30%)</div>`;
    fundHTML += this._tipRow('PER', fund.per != null ? fund.per.toFixed(2) + '배' : '-',
      fund.per != null ? (fund.per > 0 && fund.per < 15 ? 'positive' : fund.per >= 40 || fund.per < 0 ? 'negative' : '') : '');
    fundHTML += this._tipRow('PBR', fund.pbr != null ? fund.pbr.toFixed(2) + '배' : '-',
      fund.pbr != null ? (fund.pbr < 1.0 ? 'positive' : fund.pbr >= 3.0 ? 'negative' : '') : '');
    fundHTML += '<div class="tip-divider"></div>';
    fundHTML += '<div class="tip-note">PER·PBR 기반 밸류에이션 평가</div>';
    document.getElementById('tooltipFundamental').innerHTML = fundHTML;

    const rel = details.related || {};
    let relHTML = `<div class="tip-title">관련기업 모멘텀 (비중 20%)</div>`;
    relHTML += this._tipRow('탐색 기업 수', (rel.related_count || 0) + '개');
    relHTML += this._tipRow('평균 10일 수익률', rel.avg_change_pct != null ? (rel.avg_change_pct >= 0 ? '+' : '') + rel.avg_change_pct + '%' : '-',
      rel.avg_change_pct > 0 ? 'positive' : rel.avg_change_pct < 0 ? 'negative' : '');
    if (rel.companies && rel.companies.length > 0) {
      relHTML += '<div class="tip-divider"></div>';
      rel.companies.slice(0, 5).forEach((c) => {
        const csign = c.change_pct >= 0 ? '+' : '';
        relHTML += this._tipRow(c.name, csign + c.change_pct + '%',
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
        <a href="${article.link}" target="_blank" class="news-item" title="${article.title}">
          <div class="news-sentiment-badge ${sentClass}">${article.sentiment_label}</div>
          <div class="news-item-content">
            <div class="news-item-title">${article.title}</div>
            <div class="news-item-meta">
              <span>${article.source}</span>
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
        const changeStr = c.change_pct !== null ? `${c.change_pct > 0 ? '+' : ''}${c.change_pct}%` : '-';
        const changeClass = c.change_pct > 0 ? 'up' : c.change_pct < 0 ? 'down' : '';
        return `
        <div class="related-card" data-code="${c.code}">
          <div class="related-card-name">${c.name}</div>
          <div class="related-card-code">${c.code} · ${c.market}</div>
          <div class="related-card-type">${c.relation_type}</div>
          <div class="related-card-change ${changeClass}"><span class="related-card-period">10일</span> ${changeStr}</div>
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
