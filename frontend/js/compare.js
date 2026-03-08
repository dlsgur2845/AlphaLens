/**
 * AlphaLens 종목 비교 모듈
 */

const Compare = {
  init() {
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
                this._loadResult(slot, item.dataset.code);
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

  async _loadResult(slot, code) {
    const el = document.getElementById(`compareResult${slot}`);
    el.innerHTML = '<div class="skeleton-block"></div>';
    try {
      const scoring = await API.getScoring(code);
      const color = ScoreGauge.getColor(scoring.total_score);
      const signalClass = ScoreGauge.getSignalClass(scoring.signal);
      const compareLabel = scoring.action_label || scoring.signal;
      const riskBadge = scoring.risk_grade ? ` \u00B7 \uB9AC\uC2A4\uD06C ${scoring.risk_grade}` : '';
      el.innerHTML = `
        <div class="compare-name">${escapeHTML(scoring.name)}</div>
        <div class="compare-code">${scoring.code}</div>
        <div class="compare-score" style="color:${color}">${scoring.total_score.toFixed(1)}</div>
        <span class="compare-signal score-signal ${signalClass}">${compareLabel}${riskBadge}</span>
        <div class="compare-breakdown">
          <div class="compare-breakdown-row"><span>\uAE30\uC220\uC801 \uBD84\uC11D (23%)</span><span>${scoring.breakdown.technical.toFixed(1)}</span></div>
          <div class="compare-breakdown-row"><span>\uB9E4\uB9E4 \uC2DC\uADF8\uB110 (19%)</span><span>${(scoring.breakdown.signal || 50).toFixed(1)}</span></div>
          <div class="compare-breakdown-row"><span>\uD380\uB354\uBA58\uD0C8 (19%)</span><span>${scoring.breakdown.fundamental.toFixed(1)}</span></div>
          <div class="compare-breakdown-row"><span>\uAE00\uB85C\uBC8C \uB9E4\uD06C\uB85C (14%)</span><span>${(scoring.breakdown.macro || 50).toFixed(1)}</span></div>
          <div class="compare-breakdown-row"><span>\uB9AC\uC2A4\uD06C (15%)</span><span>${(scoring.breakdown.risk || 50).toFixed(1)}</span></div>
          <div class="compare-breakdown-row"><span>\uAD00\uB828\uAE30\uC5C5 (5%)</span><span>${scoring.breakdown.related_momentum.toFixed(1)}</span></div>
          <div class="compare-breakdown-row"><span>\uB274\uC2A4 \uAC10\uC131 (5%)</span><span>${scoring.breakdown.news_sentiment.toFixed(1)}</span></div>
        </div>
      `;
    } catch (e) {
      el.innerHTML = '<div style="color:var(--text-muted);padding:20px">\uB370\uC774\uD130\uB97C \uBD88\uB7EC\uC62C \uC218 \uC5C6\uC2B5\uB2C8\uB2E4</div>';
    }
  },
};
