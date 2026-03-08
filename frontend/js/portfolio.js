/**
 * AlphaLens 포트폴리오 관리 모듈
 * - Portfolio: 종목 추가/삭제/수정, 분석 요청, 결과 렌더링
 */

const Portfolio = {
  _selectedCode: null,
  _selectedName: null,
  _analyzing: false,

  init() {
    const searchInput = document.getElementById('portfolioSearchInput');
    const dropdown = document.getElementById('portfolioSearchDropdown');
    const qtyInput = document.getElementById('portfolioQty');
    const priceInput = document.getElementById('portfolioAvgPrice');
    const addBtn = document.getElementById('portfolioAddBtn');
    const refreshBtn = document.getElementById('portfolioRefreshBtn');
    const infoEl = document.getElementById('portfolioAddInfo');

    if (!searchInput) return;

    let timer = null;
    searchInput.addEventListener('input', () => {
      clearTimeout(timer);
      this._selectedCode = null;
      this._selectedName = null;
      addBtn.disabled = true;
      infoEl.textContent = '';
      const q = searchInput.value.trim();
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
              this._selectedCode = item.dataset.code;
              this._selectedName = item.dataset.name;
              searchInput.value = item.dataset.name;
              dropdown.classList.remove('active');
              infoEl.textContent = `${item.dataset.name} (${item.dataset.code})`;
              this._updateAddBtn();
            });
          });
        } catch (e) { /* ignore */ }
      }, 300);
    });

    document.addEventListener('click', (e) => {
      if (!e.target.closest('.portfolio-search-wrap')) dropdown.classList.remove('active');
    });

    qtyInput.addEventListener('input', () => this._updateAddBtn());
    priceInput.addEventListener('input', () => this._updateAddBtn());

    addBtn.addEventListener('click', () => {
      if (!this._selectedCode) return;
      const qty = parseInt(qtyInput.value, 10);
      const price = parseInt(priceInput.value, 10);
      if (!qty || qty <= 0 || !price || price <= 0) return;

      Storage.addPortfolioHolding({
        code: this._selectedCode,
        name: this._selectedName || this._selectedCode,
        quantity: qty,
        avg_price: price,
      });

      searchInput.value = '';
      qtyInput.value = '';
      priceInput.value = '';
      this._selectedCode = null;
      this._selectedName = null;
      addBtn.disabled = true;
      infoEl.textContent = '';

      Toast.show('종목이 추가되었습니다', 'success');
      this.renderHoldings();
      this.loadAnalysis();
    });

    refreshBtn.addEventListener('click', () => {
      this.loadAnalysis();
    });

    this.renderHoldings();
  },

  _updateAddBtn() {
    const addBtn = document.getElementById('portfolioAddBtn');
    const qty = parseInt(document.getElementById('portfolioQty').value, 10);
    const price = parseInt(document.getElementById('portfolioAvgPrice').value, 10);
    addBtn.disabled = !(this._selectedCode && qty > 0 && price > 0);
  },

  renderHoldings() {
    const holdings = Storage.getPortfolio();
    const container = document.getElementById('portfolioHoldings');
    const summary = document.getElementById('portfolioSummary');

    if (holdings.length === 0) {
      container.innerHTML = `
        <div class="portfolio-empty">
          <p>보유 종목이 없습니다</p>
          <p class="portfolio-empty-sub">위 검색창에서 종목을 추가하세요</p>
        </div>`;
      summary.style.display = 'none';
      return;
    }

    summary.style.display = '';

    // 로컬 데이터로 투자금 즉시 표시 (API 응답 전)
    const localInvested = holdings.reduce((sum, h) => sum + h.quantity * h.avg_price, 0);
    document.getElementById('pfTotalInvested').textContent = localInvested.toLocaleString() + '원';
    document.getElementById('pfTotalValue').textContent = '분석 중...';
    document.getElementById('pfTotalPnl').textContent = '-';
    document.getElementById('pfTotalPnl').className = 'portfolio-stat-value';
    document.getElementById('pfTotalPnlPct').textContent = '-';
    document.getElementById('pfTotalPnlPct').className = 'portfolio-stat-value';
    document.getElementById('pfAvgScore').textContent = '-';
    document.getElementById('pfDirection').textContent = '-';

    container.innerHTML = holdings.map((h) => `
      <div class="portfolio-card" data-code="${h.code}">
        <div class="portfolio-card-header">
          <div>
            <span class="portfolio-card-name">${escapeHTML(h.name)}</span>
            <span class="portfolio-card-code">${h.code}</span>
          </div>
          <div class="portfolio-card-actions">
            <button class="portfolio-edit-btn" data-code="${h.code}" title="수정">수정</button>
            <button class="portfolio-remove-btn" data-code="${h.code}" title="삭제">삭제</button>
          </div>
        </div>
        <div class="portfolio-card-body">
          <div class="portfolio-card-row">
            <span>보유 수량</span><span>${h.quantity.toLocaleString()}주</span>
          </div>
          <div class="portfolio-card-row">
            <span>평균단가</span><span>${h.avg_price.toLocaleString()}원</span>
          </div>
          <div class="portfolio-card-row">
            <span>투자금</span><span>${(h.quantity * h.avg_price).toLocaleString()}원</span>
          </div>
          <div class="portfolio-card-analysis" id="pfAnalysis_${h.code}">
            <div class="skeleton-block" style="height:60px"></div>
          </div>
        </div>
      </div>
    `).join('');

    // 삭제 버튼
    container.querySelectorAll('.portfolio-remove-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const code = btn.dataset.code;
        Storage.removePortfolioHolding(code);
        Toast.show('종목이 삭제되었습니다', 'info');
        this.renderHoldings();
        this.loadAnalysis();
      });
    });

    // 수정 버튼
    container.querySelectorAll('.portfolio-edit-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const code = btn.dataset.code;
        const holding = Storage.getPortfolio().find((h) => h.code === code);
        if (!holding) return;
        const newQty = prompt('수량 입력:', holding.quantity);
        if (newQty === null) return;
        const newPrice = prompt('평균단가 입력:', holding.avg_price);
        if (newPrice === null) return;
        const q = parseInt(newQty, 10);
        const p = parseInt(newPrice, 10);
        if (q > 0 && p > 0) {
          Storage.updatePortfolioHolding(code, { quantity: q, avg_price: p });
          Toast.show('수정되었습니다', 'success');
          this.renderHoldings();
          this.loadAnalysis();
        }
      });
    });

    // 카드 클릭 -> 종목 상세 이동
    container.querySelectorAll('.portfolio-card').forEach((card) => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('button')) return;
        App.loadStock(card.dataset.code);
      });
    });
  },

  async loadAnalysis() {
    const holdings = Storage.getPortfolio();
    if (holdings.length === 0) return;
    if (this._analyzing) return;
    this._analyzing = true;

    SectionProgress.start('#portfolioSection', 'portfolio');

    try {
      const apiHoldings = holdings.map((h) => ({
        code: h.code,
        quantity: h.quantity,
        avg_price: h.avg_price,
      }));
      const result = await API.analyzePortfolio(apiHoldings);
      this._renderAnalysisResult(result);
      SectionProgress.complete('portfolio');
    } catch (e) {
      console.error('포트폴리오 분석 실패:', e);
      Toast.show('포트폴리오 분석 실패: ' + e.message, 'error');
      SectionProgress.error('portfolio');
    } finally {
      this._analyzing = false;
    }
  },

  _renderAnalysisResult(result) {
    const s = result.summary;

    const pnlClass = s.total_pnl >= 0 ? 'up' : 'down';
    document.getElementById('pfTotalInvested').textContent = s.total_invested.toLocaleString() + '원';
    document.getElementById('pfTotalValue').textContent = s.total_value.toLocaleString() + '원';

    const pnlEl = document.getElementById('pfTotalPnl');
    pnlEl.textContent = (s.total_pnl >= 0 ? '+' : '') + s.total_pnl.toLocaleString() + '원';
    pnlEl.className = 'portfolio-stat-value ' + pnlClass;

    const pctEl = document.getElementById('pfTotalPnlPct');
    pctEl.textContent = (s.total_pnl_pct >= 0 ? '▲ +' : '▼ ') + s.total_pnl_pct.toFixed(2) + '%';
    pctEl.className = 'portfolio-stat-value ' + pnlClass;

    const scoreEl = document.getElementById('pfAvgScore');
    scoreEl.textContent = s.avg_score.toFixed(1) + '점';
    scoreEl.style.color = s.avg_score >= 60 ? 'var(--green)' : s.avg_score <= 40 ? 'var(--red)' : 'var(--yellow)';

    document.getElementById('pfDirection').textContent = s.overall_strategy.direction;

    // 전체 전략 상세
    const stratEl = document.getElementById('pfOverallStrategy');
    stratEl.style.display = '';
    let stratHTML = `<div class="pf-strategy-desc">${escapeHTML(s.overall_strategy.direction_detail)}</div>`;
    if (s.overall_strategy.tactics.length > 0) {
      stratHTML += '<div class="pf-strategy-section"><strong>전략</strong><ul>';
      s.overall_strategy.tactics.forEach((t) => { stratHTML += `<li>${escapeHTML(t)}</li>`; });
      stratHTML += '</ul></div>';
    }
    if (s.overall_strategy.cautions.length > 0) {
      stratHTML += '<div class="pf-strategy-section pf-caution"><strong>주의사항</strong><ul>';
      s.overall_strategy.cautions.forEach((c) => { stratHTML += `<li>${escapeHTML(c)}</li>`; });
      stratHTML += '</ul></div>';
    }
    stratEl.innerHTML = stratHTML;

    // 종목별 분석 결과
    (result.holdings || []).forEach((h) => {
      const el = document.getElementById(`pfAnalysis_${h.code}`);
      if (!el) return;

      const pClass = h.pnl >= 0 ? 'up' : 'down';
      const scoreColor = h.total_score != null
        ? (h.total_score >= 65 ? 'var(--green)' : h.total_score <= 35 ? 'var(--red)' : 'var(--yellow)')
        : 'var(--text-muted)';

      const actionClass = {
        '추가매수': 'pf-action-buy',
        '보유': 'pf-action-hold',
        '관망': 'pf-action-hold',
        '부분매도': 'pf-action-partial',
        '매도': 'pf-action-sell',
        '조건부매도': 'pf-action-sell',
      }[h.strategy.action] || 'pf-action-hold';

      let html = `
        <div class="pf-analysis-grid">
          <div class="pf-analysis-item">
            <span>현재가</span><span>${h.current_price.toLocaleString()}원</span>
          </div>
          <div class="pf-analysis-item">
            <span>평가금</span><span>${h.current_value.toLocaleString()}원</span>
          </div>
          <div class="pf-analysis-item">
            <span>수익</span><span class="${pClass}">${h.pnl >= 0 ? '+' : ''}${h.pnl.toLocaleString()}원</span>
          </div>
          <div class="pf-analysis-item">
            <span>수익률</span><span class="${pClass}">${h.pnl_pct >= 0 ? '▲ +' : '▼ '}${h.pnl_pct.toFixed(2)}%</span>
          </div>
          <div class="pf-analysis-item">
            <span>종합점수</span><span style="color:${scoreColor}">${h.total_score != null ? h.total_score.toFixed(1) : '-'}</span>
          </div>
          <div class="pf-analysis-item">
            <span>리스크</span><span>${h.risk_grade}</span>
          </div>
        </div>
        <div class="pf-strategy-badge ${actionClass}">${escapeHTML(h.strategy.action)}</div>
        <div class="pf-strategy-detail">${escapeHTML(h.strategy.action_detail)}</div>
      `;

      if (h.strategy.tactics && h.strategy.tactics.length > 0) {
        html += '<ul class="pf-tactics">';
        h.strategy.tactics.forEach((t) => { html += `<li>${escapeHTML(t)}</li>`; });
        html += '</ul>';
      }

      if (h.strategy.target_price || h.strategy.stop_loss) {
        html += '<div class="pf-price-targets">';
        if (h.strategy.target_price) html += `<span class="pf-target">목표 ${h.strategy.target_price.toLocaleString()}원</span>`;
        if (h.strategy.stop_loss) html += `<span class="pf-stop">손절 ${h.strategy.stop_loss.toLocaleString()}원</span>`;
        html += '</div>';
      }

      el.innerHTML = html;
    });
  },
};
