/**
 * AlphaLens 시장 현황 & 추천 종목 모듈
 * - Market: 시장 요약 로드/렌더
 * - Recommend: 추천/비추천 종목 로드/렌더
 */

const Market = {
  async load() {
    const section = document.getElementById('marketSummarySection');
    section.style.display = '';

    // 로딩 상태 표시
    ['msKospi', 'msKosdaq', 'msUsdKrw'].forEach(id => {
      const el = document.getElementById(id);
      el.querySelector('.market-index-value').textContent = '-';
      const chg = el.querySelector('.market-index-change');
      chg.textContent = '-';
      chg.className = 'market-index-change';
    });
    document.getElementById('msMacro').querySelector('.market-index-value').textContent = '-';
    document.getElementById('msMacroLabel').textContent = '분석 중...';
    document.getElementById('msKeyFactors').innerHTML = '<div class="section-loading-msg">시장 데이터 로딩 중</div>';
    document.getElementById('msSectorOutlook').innerHTML = '';

    SectionProgress.start('#marketSummarySection', 'market');
    try {
      const data = await API.getMarketSummary();
      if (data.market_summary) {
        this.render(data.market_summary);
      } else {
        document.getElementById('msMacroLabel').textContent = '데이터 없음';
        document.getElementById('msKeyFactors').innerHTML = '<div class="loading">시장 데이터가 없습니다</div>';
      }
      SectionProgress.complete('market');
    } catch (e) {
      console.warn('Market summary load failed:', e.message);
      SectionProgress.error('market');
      document.getElementById('msMacroLabel').textContent = '로드 실패';
      document.getElementById('msKeyFactors').innerHTML = '<div class="section-error-msg">시장 데이터를 불러올 수 없습니다</div>';
    }
  },

  render(ms) {
    if (!ms) return;

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
      fxChangeEl.className = `market-index-change ${fxChg > 0 ? 'up' : fxChg < 0 ? 'down' : 'flat'}`;
      fxChangeEl.setAttribute('aria-label', `USD/KRW 변동률 ${formatChange(fxChg)}`);
    }

    // 매크로 점수
    const macroEl = document.getElementById('msMacro');
    macroEl.querySelector('.market-index-value').textContent = (ms.macro_score || 50).toFixed(1);
    const macroLabel = document.getElementById('msMacroLabel');
    macroLabel.textContent = ms.macro_label || '중립';
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

    // 홈에서는 하단 상세 숨김
    const isHomeView = Router.activeNav === 'home';
    const bottomEl = document.querySelector('.market-summary-bottom');
    if (bottomEl) bottomEl.style.display = isHomeView ? 'none' : '';

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

    // 투자 전략 가이드
    const strategyEl = document.getElementById('msStrategy');
    const st = ms.market_strategy;
    if (st && strategyEl) {
      const allocHtml = st.allocation
        ? Object.entries(st.allocation).map(([k, v]) =>
          `<div class="alloc-item"><span class="alloc-label">${escapeHTML(k)}</span><div class="alloc-bar-wrap"><div class="alloc-bar-fill alloc-${k}" style="width:${v}%"></div></div><span class="alloc-pct">${v}%</span></div>`
        ).join('')
        : '';

      const tacticsHtml = (st.tactics || []).map(t =>
        `<li>${escapeHTML(t)}</li>`
      ).join('');

      const cautionsHtml = (st.cautions || []).map(c =>
        `<li>${escapeHTML(c)}</li>`
      ).join('');

      const sectorsHtml = (st.preferred_sectors || []).map(s =>
        `<span class="preferred-sector-tag">${escapeHTML(s)}</span>`
      ).join('');

      strategyEl.innerHTML = `
        <div class="strategy-header">
          <div class="strategy-regime">${escapeHTML(st.regime)}</div>
          <div class="strategy-name">${escapeHTML(st.strategy)}</div>
        </div>
        <div class="strategy-desc">${escapeHTML(st.regime_desc)}</div>
        <div class="strategy-body">
          <div class="strategy-col">
            <div class="strategy-section-label">자산 배분 제안</div>
            <div class="alloc-chart">${allocHtml}</div>
          </div>
          <div class="strategy-col">
            <div class="strategy-section-label">전술</div>
            <ul class="strategy-list tactics-list">${tacticsHtml}</ul>
          </div>
          <div class="strategy-col">
            <div class="strategy-section-label">주의사항</div>
            <ul class="strategy-list cautions-list">${cautionsHtml}</ul>
          </div>
        </div>
        ${sectorsHtml ? `<div class="strategy-sectors"><span class="strategy-section-label">유망 섹터</span><div class="preferred-sectors">${sectorsHtml}</div></div>` : ''}
      `;
      strategyEl.style.display = isHomeView ? 'none' : '';
    }

    // 업데이트 시간 + 캐시 상태 실시간 추적
    if (ms.updated_at) {
      const t = new Date(ms.updated_at);
      document.getElementById('marketSummaryTime').textContent =
        `${t.toLocaleTimeString('ko', { hour: '2-digit', minute: '2-digit' })} 기준`;
      CacheTracker.register('market', 'marketCacheStatus', ms, 300, () => Market.load());
    }
  },
};

const Recommend = {
  async load() {
    const recSection = document.getElementById('recommendSection');
    const avoidSection = document.getElementById('avoidSection');
    const recGrid = document.getElementById('recommendGrid');
    const avoidGrid = document.getElementById('avoidGrid');

    recSection.style.display = '';
    avoidSection.style.display = '';

    // 스트리밍 프로그레스 UI 표시
    recGrid.innerHTML = this._renderProgressUI();
    avoidGrid.innerHTML = '<div class="section-loading-msg">주의 종목 분석 중</div>';

    SectionProgress.start('#recommendSection', 'recommend');

    const progressEl = recGrid.querySelector('.recommend-progress');
    const progressBar = recGrid.querySelector('.recommend-progress-fill');
    const progressText = recGrid.querySelector('.recommend-progress-text');
    const progressDetail = recGrid.querySelector('.recommend-progress-detail');

    try {
      const data = await API.streamRecommendations((prog) => {
        if (!progressEl) return;
        const pct = prog.total > 0 ? Math.round((prog.current / prog.total) * 100) : 0;

        if (prog.phase === 'cached') {
          progressBar.style.width = '100%';
          progressText.textContent = '캐시 데이터 로드 완료';
          progressDetail.textContent = '';
        } else if (prog.phase === 'init') {
          progressBar.style.width = '2%';
          progressText.textContent = prog.message;
          progressDetail.textContent = '';
        } else if (prog.phase === 'scoring') {
          const displayPct = Math.max(5, Math.min(pct, 90));
          progressBar.style.width = displayPct + '%';
          progressText.textContent = `스코어링 진행 중 (${prog.current}/${prog.total})`;
          progressDetail.textContent = prog.message;
        } else if (prog.phase === 'ranking') {
          progressBar.style.width = '92%';
          progressText.textContent = prog.message;
          progressDetail.textContent = '';
        } else if (prog.phase === 'market') {
          progressBar.style.width = '96%';
          progressText.textContent = prog.message;
          progressDetail.textContent = '';
        }
      });

      // 시장 요약은 현재 시장 탭에 있을 때만 렌더 (다른 탭 침범 방지)
      if (data.market_summary && Router.activeNav === 'market') {
        Market.render(data.market_summary);
      }

      if (data.recommended && data.recommended.length > 0) {
        this._renderCards(recGrid, data.recommended, true);
        this._bindCards(recGrid);
      } else {
        recGrid.innerHTML = '<div class="loading">추천 종목이 없습니다</div>';
      }

      if (data.not_recommended && data.not_recommended.length > 0) {
        this._renderCards(avoidGrid, data.not_recommended, false);
        this._bindCards(avoidGrid);
      } else {
        avoidGrid.innerHTML = '<div class="loading">주의 종목이 없습니다</div>';
      }

      if (data.updated_at) {
        const t = new Date(data.updated_at);
        document.getElementById('recommendUpdateTime').textContent =
          `${t.toLocaleTimeString('ko', { hour: '2-digit', minute: '2-digit' })} 기준`;
        CacheTracker.register('recommend', 'recommendCacheStatus', data, 300, () => Recommend.load());
      }
      SectionProgress.complete('recommend');
    } catch (e) {
      console.warn('Recommendations load failed:', e.message);
      SectionProgress.error('recommend');
      recGrid.innerHTML = '<div class="section-error-msg">데이터를 불러올 수 없습니다</div>';
      avoidGrid.innerHTML = '<div class="section-error-msg">데이터를 불러올 수 없습니다</div>';
    }
  },

  _renderProgressUI() {
    return `
      <div class="recommend-progress">
        <div class="recommend-progress-header">
          <span class="recommend-progress-icon"></span>
          <span class="recommend-progress-text">추천 종목 분석 준비 중...</span>
        </div>
        <div class="recommend-progress-bar-wrap">
          <div class="recommend-progress-fill" style="width:0%"></div>
        </div>
        <div class="recommend-progress-detail"></div>
      </div>
    `;
  },

  _renderCards(container, stocks, isRecommended) {
    container.innerHTML = stocks.map((s) => {
      const score = s.total_score != null ? s.total_score : 50;
      const color = ScoreGauge.getColor(score);
      const signalLabel = s.action_label || s.signal || '';
      const signalClass = ScoreGauge.getSignalClass(signalLabel);
      const cardClass = isRecommended ? 'recommended' : 'not-recommended';
      const reason = s.reason || '';
      const priceStr = s.price ? s.price.toLocaleString() + '원' : '';

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

      // 당일 이슈 뉴스
      const issues = s.daily_issues || [];
      const issuesHtml = issues.length > 0
        ? `<div class="recommend-card-issues">
            ${issues.map(n => {
              const sentCls = n.sentiment === '긍정' ? 'positive' : n.sentiment === '부정' ? 'negative' : 'neutral-news';
              return `<div class="recommend-issue-item ${sentCls}">
                <span class="recommend-issue-dot"></span>
                <span class="recommend-issue-text">${escapeHTML(n.title)}</span>
              </div>`;
            }).join('')}
          </div>`
        : '';

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
          ${issuesHtml}
          ${badges.length > 0 ? `<div class="recommend-card-indicators">${badges.join('')}</div>` : ''}
        </div>
      `;
    }).join('');
  },

  _bindCards(container) {
    container.querySelectorAll('.recommend-card').forEach((card) => {
      card.addEventListener('click', () => {
        const code = card.dataset.code;
        const name = card.dataset.name;
        document.getElementById('searchInput').value = name;
        App.loadStock(code);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });
  },
};
