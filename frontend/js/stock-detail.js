/**
 * AlphaLens 종목 상세 모듈
 * - 종목 로드/렌더링, 스코어링, 뉴스, 관련기업
 * - 스코어 툴팁, 액션 가이드
 */

const StockDetail = {
  currentCode: null,
  currentDays: 30,
  _lastDetail: null,
  _loadRequestId: 0,
  _refreshInterval: null,

  cleanup() {
    if (this._refreshInterval) {
      clearInterval(this._refreshInterval);
      this._refreshInterval = null;
    }
    this.currentCode = null;
  },

  async load(code) {
    this.currentCode = code;
    this.cleanup();
    this.currentCode = code; // restore after cleanup

    document.getElementById('welcomeScreen').style.display = 'none';
    document.getElementById('dashboard').style.display = 'flex';

    const newHash = `#/stock/${code}`;
    if (location.hash !== newHash) {
      history.pushState(null, '', newHash);
    }

    AlphaStream.subscribe(code);
    this._showSkeletons();

    SectionProgress.clear();
    SectionProgress.start('.stock-summary', 'summary');
    SectionProgress.start('.stats-grid', 'score');
    SectionProgress.start('.chart-panel', 'chart');
    SectionProgress.start('.news-panel', 'news');
    SectionProgress.start('.related-section', 'related');

    const requestId = ++this._loadRequestId;
    const guard = (fn) => { if (this._loadRequestId === requestId) fn(); };

    API.getStockDetail(code).then((data) => guard(() => {
      this._lastDetail = data;
      this.renderDetail(data);
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

    API.getInvestorTrend(code).then((data) => guard(() => {
      InvestorTrend.render(data);
    })).catch((e) => { console.warn('Investor trend error:', e.message); });

    // 개별종목 자동 갱신 (2분)
    this._refreshInterval = setInterval(() => {
      if (this.currentCode !== code) return;
      API.getStockDetail(code).then((data) => {
        if (this.currentCode !== code) return;
        this._lastDetail = data;
        this.renderDetail(data);
      }).catch(() => {});
      API.getScoring(code).then((data) => {
        if (this.currentCode !== code) return;
        this.renderScoring(data);
      }).catch(() => {});
    }, 120000);
  },

  async loadChart(code, days) {
    try {
      const data = await API.getPriceHistory(code, days);
      PriceChart.update(data);
    } catch (err) {
      console.error('Chart load failed:', err);
    }
  },

  updateFavToggle(code) {
    const btn = document.getElementById('favToggle');
    if (!btn) return;
    if (Storage.isFavorite(code)) {
      btn.innerHTML = '\uAD00\uC2EC\uC885\uBAA9 \uD574\uC81C';
      btn.classList.add('active');
    } else {
      btn.innerHTML = '\uAD00\uC2EC\uC885\uBAA9 \uCD94\uAC00';
      btn.classList.remove('active');
    }
  },

  _showSkeletons() {
    document.getElementById('stockName').textContent = '-';
    document.getElementById('stockCode').textContent = '-';
    document.getElementById('stockMarket').textContent = '-';
    document.getElementById('stockSector').textContent = '-';
    document.getElementById('stockPrice').textContent = '-';
    const changeEl = document.getElementById('stockChange');
    changeEl.textContent = '-';
    changeEl.className = 'stat-card-change';
    const overGroup = document.getElementById('overMarketGroup');
    if (overGroup) overGroup.style.display = 'none';

    document.getElementById('scoreValue').textContent = '-';
    const signalEl = document.getElementById('scoreSignal');
    signalEl.textContent = '\uBD84\uC11D \uC911...';
    signalEl.className = 'score-signal';
    document.getElementById('scoreUpdated').textContent = '';
    const scoreGauge = document.getElementById('scoreGauge');
    if (scoreGauge) {
      const ctx = scoreGauge.getContext('2d');
      ctx.clearRect(0, 0, scoreGauge.width, scoreGauge.height);
    }

    ['barTechnical', 'barSignal', 'barFundamental', 'barMacro', 'barRisk', 'barRelated', 'barNews'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) { el.style.width = '0%'; el.style.background = ''; }
    });
    ['valTechnical', 'valSignal', 'valFundamental', 'valMacro', 'valRisk', 'valRelated', 'valNews'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.textContent = '-';
    });

    const historyWrap = document.getElementById('scoreHistoryWrap');
    if (historyWrap) historyWrap.style.display = 'none';

    const guide = document.getElementById('actionGuide');
    if (guide) guide.style.display = 'none';

    ['tooltipTechnical', 'tooltipSignal', 'tooltipFundamental', 'tooltipMacro', 'tooltipRisk', 'tooltipRelated', 'tooltipNews'].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = '';
    });

    if (typeof PriceChart !== 'undefined' && PriceChart.chart) {
      PriceChart.chart.data.labels = [];
      PriceChart.chart.data.datasets.forEach((ds) => { ds.data = []; });
      PriceChart.chart.update('none');
    }

    const newsList = document.getElementById('newsList');
    if (newsList) newsList.innerHTML = '<div class="skeleton-block"></div><div class="skeleton-block" style="height:60px"></div><div class="skeleton-block" style="height:60px"></div>';

    const relGrid = document.getElementById('relatedGrid');
    if (relGrid) relGrid.innerHTML = '<div class="skeleton-block"></div><div class="skeleton-block"></div><div class="skeleton-block"></div>';
  },

  // ── Render methods ──

  renderDetail(data) {
    document.getElementById('stockName').textContent = data.name;
    document.getElementById('stockCode').textContent = data.code;
    document.getElementById('stockMarket').textContent = data.market;
    document.getElementById('stockSector').textContent = data.sector || '';

    const statusText = data.market_status === 'OPEN' ? '\uAC70\uB798\uC911' : '\uC7A5\uB9C8\uAC10';
    document.getElementById('priceLabel').innerHTML =
      `KRX \uC885\uAC00 <span class="market-status-badge ${data.market_status === 'OPEN' ? 'open' : 'close'}">${statusText}</span>`;

    document.getElementById('stockPrice').textContent = data.price.toLocaleString() + '\uC6D0';

    const changeEl = document.getElementById('stockChange');
    const changeSymbol = data.change > 0 ? '\u25B2' : data.change < 0 ? '\u25BC' : '-';
    const sign = data.change >= 0 ? '+' : '';
    changeEl.textContent = `${changeSymbol} ${sign}${data.change.toLocaleString()}\uC6D0 (${sign}${data.change_pct}%)`;
    changeEl.className = `stat-card-change ${data.change >= 0 ? 'up' : 'down'}`;
    changeEl.setAttribute('aria-label', `\uBCC0\uB3D9 ${changeSymbol} ${sign}${data.change.toLocaleString()}\uC6D0, ${formatChange(data.change_pct)}`);

    const overGroup = document.getElementById('overMarketGroup');
    if (data.over_market && data.over_market.price) {
      overGroup.style.display = 'block';
      const sessionLabel = data.over_market.session_type === 'PRE_MARKET' ? '\uD504\uB9AC\uB9C8\uCF13(NXT)' : '\uC2DC\uAC04\uC678(NXT)';
      const overStatus = data.over_market.status === 'OPEN' ? '\uAC70\uB798\uC911' : '\uB9C8\uAC10';
      document.getElementById('overMarketLabel').innerHTML =
        `${sessionLabel} <span class="market-status-badge ${data.over_market.status === 'OPEN' ? 'open' : 'close'}">${overStatus}</span>`;
      document.getElementById('overMarketPrice').textContent = data.over_market.price.toLocaleString() + '\uC6D0';
      const overSymbol = data.over_market.change > 0 ? '\u25B2' : data.over_market.change < 0 ? '\u25BC' : '-';
      const overSign = data.over_market.change >= 0 ? '+' : '';
      const overChangeEl = document.getElementById('overMarketChange');
      overChangeEl.textContent = `${overSymbol} ${overSign}${data.over_market.change.toLocaleString()}\uC6D0 (${overSign}${data.over_market.change_pct}%)`;
      overChangeEl.className = `stat-card-sub-change ${data.over_market.change >= 0 ? 'up' : 'down'}`;
      overChangeEl.setAttribute('aria-label', `\uC2DC\uAC04\uC678 \uBCC0\uB3D9 ${overSymbol} ${overSign}${data.over_market.change.toLocaleString()}\uC6D0, ${formatChange(data.over_market.change_pct)}`);
      if (data.over_market.price !== data.price) {
        const diff = data.over_market.price - data.price;
        const diffPct = ((diff / data.price) * 100).toFixed(2);
        const diffSign = diff >= 0 ? '+' : '';
        document.getElementById('overMarketTime').textContent =
          `KRX \uB300\uBE44 ${diffSign}${diff.toLocaleString()}\uC6D0 (${diffSign}${diffPct}%)`;
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

    const label = data.action_label || data.signal;
    const signalEl = document.getElementById('scoreSignal');
    signalEl.textContent = label;
    signalEl.className = `score-signal ${ScoreGauge.getSignalClass(label)}`;

    if (data.risk_grade) {
      signalEl.textContent = `${label} \u00B7 \uB9AC\uC2A4\uD06C ${data.risk_grade}`;
    }

    const updated = new Date(data.updated_at);
    document.getElementById('scoreUpdated').textContent =
      `${updated.toLocaleDateString('ko')} ${updated.toLocaleTimeString('ko', { hour: '2-digit', minute: '2-digit' })} \uAE30\uC900`;

    ScoreGauge.updateBreakdown(data.breakdown);
    if (data.details) this._renderTooltips(data.details, data.breakdown);

    this._renderActionGuide(data);
  },

  _renderActionGuide(data) {
    const guide = document.getElementById('actionGuide');
    if (!guide || !data) return;
    guide.style.display = '';

    const price = this._lastDetail?.price || 0;
    const atr = data.details?.technical?.atr || 0;
    const totalScore = data.total_score || 50;
    const riskGrade = data.details?.risk?.grade || data.risk_grade || '-';
    const positionPct = data.details?.risk?.position_size_pct || 0;
    const actionLabel = data.action_label || data.signal || '\uC911\uB9BD';

    const targetMultiplier = totalScore > 65 ? 3.0 : totalScore > 55 ? 2.0 : 1.5;
    const targetPrice = price > 0 && atr > 0 ? Math.round(price + atr * targetMultiplier) : null;
    const stopLoss = price > 0 && atr > 0 ? Math.round(price - atr * 2) : null;

    const deviation = Math.abs(totalScore - 50);
    const confidence = deviation > 25 ? '\uB192\uC74C' : deviation > 15 ? '\uBCF4\uD1B5' : '\uB0AE\uC74C';

    document.getElementById('actionOpinion').textContent = actionLabel;
    document.getElementById('actionTarget').textContent = targetPrice ? targetPrice.toLocaleString() + '\uC6D0' : '-';
    document.getElementById('actionStopLoss').textContent = stopLoss ? stopLoss.toLocaleString() + '\uC6D0' : '-';
    document.getElementById('actionPosition').textContent = positionPct > 0 ? positionPct.toFixed(1) + '%' : '-';
    document.getElementById('actionRiskGrade').textContent = riskGrade;
    document.getElementById('actionConfidence').textContent = confidence;

    const opinionEl = document.getElementById('actionOpinion');
    opinionEl.className = 'action-value';
    if (totalScore >= 65) opinionEl.classList.add('bullish');
    else if (totalScore <= 35) opinionEl.classList.add('bearish');
  },

  _renderTooltips(details, breakdown) {
    const tech = details.technical || {};
    const ma = tech.moving_averages || {};
    const macd = tech.macd || {};
    const vol = tech.volume_trend || {};
    const obv = tech.obv || {};
    const over = details.over_market;

    let techHTML = `<div class="tip-title">\uAE30\uC220\uC801 \uBD84\uC11D (\uBE44\uC911 23%)</div>`;
    techHTML += this._tipRow('RSI (14)', tech.rsi != null ? tech.rsi.toFixed(1) : '-',
      tech.rsi < 30 ? 'positive' : tech.rsi > 70 ? 'negative' : '');
    techHTML += this._tipRow('MACD \uD788\uC2A4\uD1A0\uADF8\uB7A8', macd.histogram != null ? macd.histogram.toFixed(1) : '-',
      macd.bullish ? 'positive' : macd.bullish === false ? 'negative' : '');
    if (macd.crossover) techHTML += this._tipRow('MACD \uD06C\uB85C\uC2A4\uC624\uBC84', '\uB9E4\uC218 \uC2E0\uD638', 'positive');
    if (macd.crossunder) techHTML += this._tipRow('MACD \uD06C\uB85C\uC2A4\uC5B8\uB354', '\uB9E4\uB3C4 \uC2E0\uD638', 'negative');
    techHTML += this._tipRow('20\uC77C\uC120 \uC704', ma.above_ma20 ? 'Yes' : 'No', ma.above_ma20 ? 'positive' : 'negative');
    techHTML += this._tipRow('60\uC77C\uC120 \uC704', ma.above_ma60 != null ? (ma.above_ma60 ? 'Yes' : 'No') : '-',
      ma.above_ma60 ? 'positive' : ma.above_ma60 === false ? 'negative' : '');
    if (ma.ma_aligned_bull) techHTML += this._tipRow('MA \uC815\uBC30\uC5F4', '\uAC15\uC138', 'positive');
    if (ma.ma_aligned_bear) techHTML += this._tipRow('MA \uC5ED\uBC30\uC5F4', '\uC57D\uC138', 'negative');
    if (ma.golden_cross) techHTML += this._tipRow('\uACE8\uB4E0\uD06C\uB85C\uC2A4', '\uBC1C\uC0DD', 'positive');
    if (ma.dead_cross) techHTML += this._tipRow('\uB370\uB4DC\uD06C\uB85C\uC2A4', '\uBC1C\uC0DD', 'negative');
    if (vol.volume_ratio) techHTML += this._tipRow('\uAC70\uB798\uB7C9 \uBE44\uC728', vol.volume_ratio.toFixed(2) + 'x', vol.high_volume ? 'positive' : '');
    if (obv.obv_trend) techHTML += this._tipRow('OBV \uCD94\uC138', obv.obv_trend === 'bullish' ? '\uAC15\uC138' : obv.obv_trend === 'bearish' ? '\uC57D\uC138' : '\uC911\uB9BD',
      obv.obv_trend === 'bullish' ? 'positive' : obv.obv_trend === 'bearish' ? 'negative' : '');
    if (obv.divergence) techHTML += this._tipRow('OBV \uB2E4\uC774\uBC84\uC804\uC2A4', obv.divergence === 'bullish' ? '\uAC15\uC138' : '\uC57D\uC138',
      obv.divergence === 'bullish' ? 'positive' : 'negative');
    const bb = tech.bollinger_bands || {};
    if (bb.pct_b != null) {
      techHTML += this._tipRow('BB %B', bb.pct_b.toFixed(2),
        bb.pct_b < 0.2 ? 'positive' : bb.pct_b > 0.8 ? 'negative' : '');
    }
    if (over) {
      techHTML += '<div class="tip-divider"></div>';
      techHTML += this._tipRow('NXT \uAD34\uB9AC', (over.diff_pct >= 0 ? '+' : '') + over.diff_pct + '%',
        over.diff_pct > 0 ? 'positive' : over.diff_pct < 0 ? 'negative' : '');
    }
    document.getElementById('tooltipTechnical').innerHTML = techHTML;

    const sig = details.signal || {};
    let sigHTML = `<div class="tip-title">\uB9E4\uB9E4 \uC2DC\uADF8\uB110 (\uBE44\uC911 19%)</div>`;
    sigHTML += this._tipRow('\uB808\uC9D0', sig.regime || '-',
      sig.regime === 'BULL' ? 'positive' : sig.regime === 'BEAR' ? 'negative' : '');
    sigHTML += this._tipRow('\uC561\uC158', sig.action_label || '-');
    if (sig.breakdown) {
      sigHTML += this._tipRow('\uBAA8\uBA58\uD140', sig.breakdown.momentum != null ? sig.breakdown.momentum.toFixed(1) : '-');
      sigHTML += this._tipRow('\uD3C9\uADE0\uD68C\uADC0', sig.breakdown.mean_reversion != null ? sig.breakdown.mean_reversion.toFixed(1) : '-');
      sigHTML += this._tipRow('\uB3CC\uD30C', sig.breakdown.breakout != null ? sig.breakdown.breakout.toFixed(1) : '-');
    }
    if (sig.buy_signals && sig.buy_signals.length > 0) {
      sigHTML += '<div class="tip-divider"></div>';
      sig.buy_signals.forEach((s) => { sigHTML += this._tipRow('\uB9E4\uC218', s, 'positive'); });
    }
    if (sig.sell_signals && sig.sell_signals.length > 0) {
      sig.sell_signals.forEach((s) => { sigHTML += this._tipRow('\uB9E4\uB3C4', s, 'negative'); });
    }
    const sigEl = document.getElementById('tooltipSignal');
    if (sigEl) sigEl.innerHTML = sigHTML;

    const fund = details.fundamental || {};
    let fundHTML = `<div class="tip-title">\uD380\uB354\uBA58\uD0C8 (\uBE44\uC911 19%)</div>`;
    fundHTML += this._tipRow('PER', fund.per != null ? fund.per.toFixed(2) + '\uBC30' : '-',
      fund.per != null ? (fund.per > 0 && fund.per < 15 ? 'positive' : fund.per >= 40 || fund.per < 0 ? 'negative' : '') : '');
    fundHTML += this._tipRow('PBR', fund.pbr != null ? fund.pbr.toFixed(2) + '\uBC30' : '-',
      fund.pbr != null ? (fund.pbr < 1.0 ? 'positive' : fund.pbr >= 3.0 ? 'negative' : '') : '');
    if (fund.roe != null) {
      fundHTML += this._tipRow('ROE', fund.roe.toFixed(2) + '%',
        fund.roe > 15 ? 'positive' : fund.roe < 0 ? 'negative' : '');
    }
    if (fund.sector_standard) {
      fundHTML += this._tipRow('\uC139\uD130 PER \uAE30\uC900', fund.sector_standard + '\uBC30');
    }
    fundHTML += '<div class="tip-divider"></div>';
    fundHTML += '<div class="tip-note">PER\u00B7PBR\u00B7ROE \uAE30\uBC18 \uC139\uD130\uBCC4 \uBC38\uB958\uC5D0\uC774\uC158 \uD3C9\uAC00</div>';
    document.getElementById('tooltipFundamental').innerHTML = fundHTML;

    const macro = details.macro || {};
    let macroHTML = `<div class="tip-title">\uAE00\uB85C\uBC8C \uB9E4\uD06C\uB85C (\uBE44\uC911 14%)</div>`;
    if (macro.breakdown) {
      macroHTML += this._tipRow('\uBBF8\uAD6D \uC2DC\uC7A5', macro.breakdown.us_market != null ? (macro.breakdown.us_market >= 0 ? '+' : '') + macro.breakdown.us_market.toFixed(1) : '-',
        macro.breakdown.us_market > 0 ? 'positive' : macro.breakdown.us_market < 0 ? 'negative' : '');
      macroHTML += this._tipRow('\uD658\uC728', macro.breakdown.fx != null ? (macro.breakdown.fx >= 0 ? '+' : '') + macro.breakdown.fx.toFixed(1) : '-',
        macro.breakdown.fx > 0 ? 'positive' : macro.breakdown.fx < 0 ? 'negative' : '');
      macroHTML += this._tipRow('\uAE08\uB9AC', macro.breakdown.rates != null ? (macro.breakdown.rates >= 0 ? '+' : '') + macro.breakdown.rates.toFixed(1) : '-',
        macro.breakdown.rates > 0 ? 'positive' : macro.breakdown.rates < 0 ? 'negative' : '');
      macroHTML += this._tipRow('\uC6D0\uC790\uC7AC', macro.breakdown.commodities != null ? (macro.breakdown.commodities >= 0 ? '+' : '') + macro.breakdown.commodities.toFixed(1) : '-',
        macro.breakdown.commodities > 0 ? 'positive' : macro.breakdown.commodities < 0 ? 'negative' : '');
      macroHTML += this._tipRow('\uC911\uAD6D', macro.breakdown.china != null ? (macro.breakdown.china >= 0 ? '+' : '') + macro.breakdown.china.toFixed(1) : '-',
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

    const risk = details.risk || {};
    let riskHTML = `<div class="tip-title">\uB9AC\uC2A4\uD06C \uAD00\uB9AC (\uBE44\uC911 15%)</div>`;
    if (risk.grade) riskHTML += this._tipRow('\uB9AC\uC2A4\uD06C \uB4F1\uAE09', risk.grade,
      risk.grade === 'A' || risk.grade === 'B' ? 'positive' : risk.grade === 'D' || risk.grade === 'E' ? 'negative' : '');
    if (risk.breakdown) {
      riskHTML += this._tipRow('\uBCC0\uB3D9\uC131', risk.breakdown.volatility != null ? risk.breakdown.volatility.toFixed(1) : '-');
      riskHTML += this._tipRow('MDD', risk.breakdown.mdd != null ? risk.breakdown.mdd.toFixed(1) : '-');
      riskHTML += this._tipRow('VaR/CVaR', risk.breakdown.var_cvar != null ? risk.breakdown.var_cvar.toFixed(1) : '-');
      riskHTML += this._tipRow('\uC720\uB3D9\uC131', risk.breakdown.liquidity != null ? risk.breakdown.liquidity.toFixed(1) : '-');
      if (risk.breakdown.leverage != null && risk.breakdown.leverage !== 50) {
        riskHTML += this._tipRow('\uB808\uBC84\uB9AC\uC9C0', risk.breakdown.leverage.toFixed(1),
          risk.breakdown.leverage >= 70 ? 'positive' : risk.breakdown.leverage <= 30 ? 'negative' : '');
      }
    }
    if (risk.position_size_pct) riskHTML += this._tipRow('\uCD94\uCC9C \uBE44\uC911', risk.position_size_pct.toFixed(1) + '%');
    if (risk.atr) riskHTML += this._tipRow('ATR', risk.atr.toFixed(0) + '\uC6D0');
    const credit = details.credit || {};
    if (credit.credit_ratio != null) {
      riskHTML += '<div class="tip-divider"></div>';
      riskHTML += this._tipRow('\uC2E0\uC6A9\uBE44\uC728', credit.credit_ratio.toFixed(2) + '%',
        credit.credit_ratio > 5 ? 'negative' : credit.credit_ratio < 2 ? 'positive' : '');
      if (credit.short_ratio) {
        riskHTML += this._tipRow('\uACF5\uB9E4\uB3C4\uBE44\uC728', credit.short_ratio.toFixed(2) + '%');
      }
    }
    const riskEl = document.getElementById('tooltipRisk');
    if (riskEl) riskEl.innerHTML = riskHTML;

    const news = details.news || {};
    let newsHTML = `<div class="tip-title">\uB274\uC2A4 \uAC10\uC131\uBD84\uC11D (\uBE44\uC911 5%)</div>`;
    newsHTML += this._tipRow('\uBD84\uC11D \uAE30\uC0AC \uC218', (news.total_articles || 0) + '\uAC74');
    newsHTML += this._tipRow('\uAE0D\uC815', (news.positive || 0) + '\uAC74', 'positive');
    newsHTML += this._tipRow('\uBD80\uC815', (news.negative || 0) + '\uAC74', 'negative');
    newsHTML += this._tipRow('\uC911\uB9BD', (news.neutral || 0) + '\uAC74');
    newsHTML += this._tipRow('\uC885\uD569 \uAC10\uC131', news.overall_sentiment != null ? (news.overall_sentiment > 0 ? '+' : '') + news.overall_sentiment.toFixed(3) : '-',
      news.overall_sentiment > 0.15 ? 'positive' : news.overall_sentiment < -0.15 ? 'negative' : '');
    newsHTML += '<div class="tip-divider"></div>';
    newsHTML += '<div class="tip-note">\uC885\uD569 \uC810\uC218\uC5D0 5% \uBE44\uC911\uC73C\uB85C \uBC18\uC601\uB429\uB2C8\uB2E4</div>';
    document.getElementById('tooltipNews').innerHTML = newsHTML;

    const rel = details.related || {};
    let relHTML = `<div class="tip-title">\uAD00\uB828\uAE30\uC5C5 \uBAA8\uBA58\uD140 (\uBE44\uC911 5%)</div>`;
    relHTML += this._tipRow('\uD0D0\uC0C9 \uAE30\uC5C5 \uC218', (rel.related_count || 0) + '\uAC1C');
    relHTML += this._tipRow('\uD3C9\uADE0 \uC218\uC775\uB960', rel.avg_change_pct != null ? formatChange(rel.avg_change_pct) : '-',
      rel.avg_change_pct > 0 ? 'positive' : rel.avg_change_pct < 0 ? 'negative' : '');
    if (rel.companies && rel.companies.length > 0) {
      relHTML += '<div class="tip-divider"></div>';
      rel.companies.slice(0, 5).forEach((c) => {
        relHTML += this._tipRow(escapeHTML(c.name), formatChange(c.change_pct),
          c.change_pct > 0 ? 'positive' : c.change_pct < 0 ? 'negative' : '');
      });
      if (rel.companies.length > 5) {
        relHTML += `<div class="tip-note">\uC678 ${rel.companies.length - 5}\uAC1C \uAE30\uC5C5</div>`;
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
      data.overall_label === '\uAE0D\uC815' ? 'var(--green)' :
      data.overall_label === '\uBD80\uC815' ? 'var(--red)' : 'var(--yellow)';

    summaryEl.innerHTML = `
      <span style="color:${sentColor}">${data.overall_label}</span>
      <span style="color:var(--text-muted)">
        (\uAE0D\uC815 ${data.positive_count} / \uBD80\uC815 ${data.negative_count} / \uC911\uB9BD ${data.neutral_count})
      </span>
    `;

    if (data.articles.length === 0) {
      listEl.innerHTML = '<div class="loading">\uAD00\uB828 \uB274\uC2A4\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4</div>';
      return;
    }

    listEl.innerHTML = data.articles
      .map((article) => {
        const sentClass =
          article.sentiment_label === '\uAE0D\uC815' ? 'positive' :
          article.sentiment_label === '\uBD80\uC815' ? 'negative' : 'neutral';
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

    countEl.textContent = `${data.total}\uAC1C \uAE30\uC5C5 \uBC1C\uACAC`;

    if (data.companies.length === 0) {
      gridEl.innerHTML = '<div class="loading">\uAD00\uB828\uAE30\uC5C5\uC744 \uCC3E\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4</div>';
      return;
    }

    gridEl.innerHTML = data.companies
      .map((c) => {
        const changeStr = c.change_pct !== null ? formatChange(c.change_pct) : '-';
        const changeClass = c.change_pct > 0 ? 'up' : c.change_pct < 0 ? 'down' : '';
        return `
        <div class="related-card" data-code="${c.code}">
          <div class="related-card-name">${escapeHTML(c.name)}</div>
          <div class="related-card-code">${c.code} \u00B7 ${c.market}</div>
          <div class="related-card-type">${escapeHTML(c.relation_type)}</div>
          <div class="related-card-change ${changeClass}" aria-label="10\uC77C \uBCC0\uB3D9\uB960 ${changeStr}"><span class="related-card-period">10\uC77C</span> ${changeStr}</div>
        </div>
      `;
      })
      .join('');

    gridEl.querySelectorAll('.related-card').forEach((card) => {
      card.addEventListener('click', () => {
        const code = card.dataset.code;
        document.getElementById('searchInput').value = card.querySelector('.related-card-name').textContent;
        this.load(code);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });
  },
};
