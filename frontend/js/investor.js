/**
 * AlphaLens 투자자별 매매동향 모듈
 * - InvestorTrend: 외국인/기관/개인 매매동향 차트 & 테이블
 */

const InvestorTrend = {
  _chart: null,

  render(data) {
    const section = document.getElementById('investorSection');
    if (!data || !Array.isArray(data) || data.length === 0) {
      section.style.display = 'none';
      return;
    }
    section.style.display = '';

    // 최신순 -> 오래된순으로 정렬 (차트용)
    const sorted = [...data].reverse();
    const latest = data[0];

    // 기간 표시
    document.getElementById('investorPeriod').textContent =
      `${sorted[0].date} ~ ${sorted[sorted.length - 1].date} (${sorted.length}일)`;

    // 요약 카드: 최근 5일 누적
    const recent5 = data.slice(0, Math.min(5, data.length));
    const sum5 = { foreign: 0, institution: 0, individual: 0 };
    recent5.forEach((d) => {
      sum5.foreign += d.foreign;
      sum5.institution += d.institution;
      sum5.individual += d.individual;
    });

    const fmtQty = (v) => {
      const abs = Math.abs(v);
      const sign = v > 0 ? '+' : v < 0 ? '-' : '';
      if (abs >= 1000000) return `${sign}${(abs / 1000000).toFixed(1)}백만`;
      if (abs >= 10000) return `${sign}${(abs / 10000).toFixed(1)}만`;
      return `${sign}${abs.toLocaleString()}`;
    };
    const cls = (v) => v > 0 ? 'up' : v < 0 ? 'down' : '';

    document.getElementById('investorSummary').innerHTML = `
      <div class="investor-summary-grid">
        <div class="investor-stat">
          <span class="investor-stat-label">외국인 (5일)</span>
          <span class="investor-stat-value ${cls(sum5.foreign)}">${fmtQty(sum5.foreign)}주</span>
        </div>
        <div class="investor-stat">
          <span class="investor-stat-label">기관 (5일)</span>
          <span class="investor-stat-value ${cls(sum5.institution)}">${fmtQty(sum5.institution)}주</span>
        </div>
        <div class="investor-stat">
          <span class="investor-stat-label">개인 (5일)</span>
          <span class="investor-stat-value ${cls(sum5.individual)}">${fmtQty(sum5.individual)}주</span>
        </div>
        <div class="investor-stat">
          <span class="investor-stat-label">외국인 보유</span>
          <span class="investor-stat-value">${latest.foreign_hold_ratio.toFixed(2)}%</span>
        </div>
      </div>`;

    // 차트
    const ctx = document.getElementById('investorChart').getContext('2d');
    if (this._chart) this._chart.destroy();

    this._chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: sorted.map((d) => d.date.slice(5)),
        datasets: [
          {
            label: '외국인',
            data: sorted.map((d) => d.foreign),
            backgroundColor: sorted.map((d) => d.foreign >= 0 ? 'rgba(59,130,246,.7)' : 'rgba(59,130,246,.3)'),
            borderColor: 'rgb(59,130,246)',
            borderWidth: 1,
          },
          {
            label: '기관',
            data: sorted.map((d) => d.institution),
            backgroundColor: sorted.map((d) => d.institution >= 0 ? 'rgba(168,85,247,.7)' : 'rgba(168,85,247,.3)'),
            borderColor: 'rgb(168,85,247)',
            borderWidth: 1,
          },
          {
            label: '개인',
            data: sorted.map((d) => d.individual),
            backgroundColor: sorted.map((d) => d.individual >= 0 ? 'rgba(34,197,94,.7)' : 'rgba(34,197,94,.3)'),
            borderColor: 'rgb(34,197,94)',
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            labels: { color: '#94a3b8', font: { size: 11 } },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toLocaleString()}주`,
            },
          },
        },
        scales: {
          x: {
            ticks: { color: '#64748b', font: { size: 10 } },
            grid: { color: 'rgba(100,116,139,.15)' },
          },
          y: {
            ticks: {
              color: '#64748b',
              font: { size: 10 },
              callback: (v) => {
                const abs = Math.abs(v);
                if (abs >= 1000000) return (v / 1000000).toFixed(0) + 'M';
                if (abs >= 1000) return (v / 1000).toFixed(0) + 'K';
                return v;
              },
            },
            grid: { color: 'rgba(100,116,139,.15)' },
          },
        },
      },
    });

    // 테이블
    const tbody = document.getElementById('investorTableBody');
    tbody.innerHTML = data.slice(0, 10).map((d) => `
      <tr>
        <td>${d.date.slice(5)}</td>
        <td class="${cls(d.foreign)}">${fmtQty(d.foreign)}</td>
        <td class="${cls(d.institution)}">${fmtQty(d.institution)}</td>
        <td class="${cls(d.individual)}">${fmtQty(d.individual)}</td>
        <td>${d.foreign_hold_ratio.toFixed(2)}%</td>
      </tr>
    `).join('');
  },
};
