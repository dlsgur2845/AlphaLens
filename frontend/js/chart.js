/**
 * AlphaLens 주가 차트 모듈
 * - 라인/캔들스틱 전환
 * - 이동평균선 (MA5/20/60) 오버레이
 * - 거래량 바 차트
 */

/* ── 캔들스틱 위크(꼬리) 커스텀 플러그인 ── */
const candleWickPlugin = {
  id: 'candleWick',
  beforeDatasetDraw(chart, args) {
    const dataset = chart.data.datasets[args.index];
    if (!dataset._prices) return;

    const { ctx } = chart;
    const meta = args.meta;
    const yScale = chart.scales.y;
    const prices = dataset._prices;

    ctx.save();
    ctx.lineWidth = 1;

    meta.data.forEach((bar, i) => {
      const p = prices[i];
      if (!p) return;

      const x = bar.x;
      const highY = yScale.getPixelForValue(p.high);
      const lowY = yScale.getPixelForValue(p.low);

      ctx.beginPath();
      ctx.strokeStyle = p.close >= p.open ? '#dc2626' : '#1173d4';
      ctx.moveTo(x, highY);
      ctx.lineTo(x, lowY);
      ctx.stroke();
    });

    ctx.restore();
  },
};

Chart.register(candleWickPlugin);

/* ── 메인 차트 모듈 ── */
const PriceChart = {
  chart: null,
  rsiChart: null,
  mode: 'line',
  showMA: { 5: false, 20: true, 60: false },
  showVolume: true,
  showBB: false,
  showRSI: false,
  _rawData: null,

  init() {
    const ctx = document.getElementById('priceChart');
    if (!ctx) return;

    this.chart = new Chart(ctx, {
      type: 'bar',
      data: { labels: [], datasets: [] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1e293b',
            titleColor: '#f1f5f9',
            bodyColor: '#94a3b8',
            borderColor: '#334155',
            borderWidth: 1,
            padding: 12,
            callbacks: {
              label(ctx) {
                const ds = ctx.dataset;
                if (ds.label === '거래량') {
                  const v = ctx.parsed.y;
                  if (v >= 1e6) return `거래량 ${(v / 1e6).toFixed(1)}M`;
                  if (v >= 1e3) return `거래량 ${(v / 1e3).toFixed(0)}K`;
                  return `거래량 ${v.toLocaleString()}`;
                }
                if (ds.label === 'OHLC') {
                  const p = ds._prices?.[ctx.dataIndex];
                  if (!p) return '';
                  return [
                    `시가 ${p.open.toLocaleString()}`,
                    `고가 ${p.high.toLocaleString()}`,
                    `저가 ${p.low.toLocaleString()}`,
                    `종가 ${p.close.toLocaleString()}`,
                  ];
                }
                if (ds.label?.startsWith('MA')) {
                  return ctx.parsed.y != null
                    ? `${ds.label} ${Math.round(ctx.parsed.y).toLocaleString()}`
                    : null;
                }
                if (ds.label?.startsWith('BB')) {
                  return ctx.parsed.y != null ? `${ds.label} ${Math.round(ctx.parsed.y).toLocaleString()}` : null;
                }
                return `${ctx.parsed.y.toLocaleString()}원`;
              },
            },
          },
        },
        scales: {
          x: {
            grid: { color: 'rgba(255,255,255,0.06)' },
            ticks: { color: '#94a3b8', maxTicksLimit: 8, font: { size: 11 } },
          },
          y: {
            position: 'left',
            grid: { color: 'rgba(255,255,255,0.06)' },
            ticks: {
              color: '#94a3b8',
              font: { size: 11 },
              callback(v) {
                if (v >= 1e6) return (v / 1e6).toFixed(0) + 'M';
                if (v >= 1e3) return (v / 1e3).toFixed(0) + 'K';
                return v;
              },
            },
          },
          y1: {
            position: 'right',
            display: false,
            beginAtZero: true,
            grid: { drawOnChartArea: false },
          },
        },
      },
    });

    const rsiCtx = document.getElementById('rsiChart');
    if (rsiCtx) {
      this.rsiChart = new Chart(rsiCtx, {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { intersect: false, mode: 'index' },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: '#1e293b', titleColor: '#f1f5f9',
              bodyColor: '#94a3b8', borderColor: '#334155', borderWidth: 1, padding: 8,
              callbacks: {
                label(ctx) {
                  if (ctx.dataset.label === 'RSI') return ctx.parsed.y != null ? `RSI ${ctx.parsed.y.toFixed(1)}` : null;
                  return null;
                },
              },
            },
          },
          scales: {
            x: { display: false },
            y: {
              min: 0, max: 100,
              grid: { color: 'rgba(255,255,255,0.06)' },
              ticks: {
                color: '#94a3b8', font: { size: 10 }, stepSize: 30,
                callback(v) { return v === 30 || v === 70 ? v : ''; },
              },
            },
          },
        },
      });
    }
  },

  update(priceData) {
    this._rawData = priceData;
    this._rebuild();
  },

  setMode(mode) {
    this.mode = mode;
    this._rebuild();
  },

  toggleMA(period) {
    this.showMA[period] = !this.showMA[period];
    this._rebuild();
    return this.showMA[period];
  },

  toggleVolume() {
    this.showVolume = !this.showVolume;
    this._rebuild();
    return this.showVolume;
  },

  toggleBB() {
    this.showBB = !this.showBB;
    this._rebuild();
    return this.showBB;
  },

  toggleRSI() {
    this.showRSI = !this.showRSI;
    const container = document.getElementById('rsiContainer');
    if (container) container.style.display = this.showRSI ? '' : 'none';
    this._rebuild();
    return this.showRSI;
  },

  _rebuild() {
    if (!this.chart || !this._rawData?.prices) return;

    const prices = this._rawData.prices;
    // 6개월 이상이면 연도 포함, 그 이하는 월-일만
    const showYear = prices.length > 120;
    const labels = prices.map((p) => {
      if (showYear) {
        // "2024-03-29" → "24.03"  (연도 2자리 + 월)
        const parts = p.date.split('-');
        return parts[0].slice(2) + '.' + parts[1];
      }
      return p.date.slice(5); // "03-29"
    });
    const closes = prices.map((p) => p.close);

    const datasets = [];

    // 가격 데이터셋
    if (this.mode === 'candle') {
      datasets.push(this._candleDataset(prices));
    } else {
      datasets.push(this._lineDataset(closes));
    }

    // 이동평균선
    for (const [period, active] of Object.entries(this.showMA)) {
      if (active) datasets.push(this._maDataset(closes, parseInt(period)));
    }

    // 볼린저 밴드
    if (this.showBB) {
      datasets.push(...this._bbDatasets(closes));
    }

    // 거래량
    if (this.showVolume) {
      datasets.push(this._volumeDataset(prices));
    }

    // y1 축 max 조정 (거래량이 차트 하단 25%만 차지하도록)
    const maxVol = Math.max(...prices.map((p) => p.volume));
    this.chart.options.scales.y1.display = this.showVolume;
    this.chart.options.scales.y1.max = maxVol * 4;

    this.chart.data.labels = labels;
    this.chart.data.datasets = datasets;
    this.chart.update('none');

    if (this.showRSI && this.rsiChart) {
      this._updateRSI(closes, labels);
    }
  },

  /* ── 데이터셋 빌더 ── */

  _lineDataset(closes) {
    const first = closes[0] || 0;
    const last = closes[closes.length - 1] || 0;
    const isUp = last >= first;
    const color = isUp ? '#dc2626' : '#1173d4';

    return {
      type: 'line',
      label: '종가',
      data: closes,
      borderColor: color,
      backgroundColor: isUp ? 'rgba(220,38,38,0.08)' : 'rgba(17,115,212,0.08)',
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 5,
      fill: true,
      tension: 0.3,
      yAxisID: 'y',
      order: 1,
    };
  },

  _candleDataset(prices) {
    const data = prices.map((p) => [Math.min(p.open, p.close), Math.max(p.open, p.close)]);
    const bgColors = prices.map((p) =>
      p.close >= p.open ? 'rgba(220,38,38,0.85)' : 'rgba(17,115,212,0.85)'
    );
    const borderColors = prices.map((p) => (p.close >= p.open ? '#dc2626' : '#1173d4'));

    return {
      type: 'bar',
      label: 'OHLC',
      data: data,
      backgroundColor: bgColors,
      borderColor: borderColors,
      borderWidth: 1,
      yAxisID: 'y',
      order: 1,
      barPercentage: 0.7,
      categoryPercentage: 0.95,
      _prices: prices,
    };
  },

  _maDataset(closes, period) {
    const ma = [];
    const minPoints = Math.min(period, 2);
    for (let i = 0; i < closes.length; i++) {
      if (i < minPoints - 1) {
        ma.push(null);
      } else {
        const windowSize = Math.min(period, i + 1);
        let sum = 0;
        for (let j = i - windowSize + 1; j <= i; j++) sum += closes[j];
        ma.push(sum / windowSize);
      }
    }

    const colors = { 5: '#d97706', 20: '#7c3aed', 60: '#db2777' };
    const dashes = { 5: [], 20: [6, 3], 60: [2, 2] };

    return {
      type: 'line',
      label: `MA${period}`,
      data: ma,
      borderColor: colors[period] || '#9ca3af',
      borderWidth: 1.5,
      borderDash: dashes[period] || [],
      pointRadius: 0,
      pointHoverRadius: 3,
      fill: false,
      tension: 0.3,
      yAxisID: 'y',
      order: 0,
      spanGaps: true,
    };
  },

  _bbDatasets(closes) {
    const period = 20;
    const numStd = 2;
    const upper = [];
    const lower = [];

    const minPoints = Math.min(period, 2);
    for (let i = 0; i < closes.length; i++) {
      if (i < minPoints - 1) {
        upper.push(null);
        lower.push(null);
      } else {
        const windowSize = Math.min(period, i + 1);
        const slice = closes.slice(i - windowSize + 1, i + 1);
        const avg = slice.reduce((a, b) => a + b, 0) / windowSize;
        const std = Math.sqrt(slice.reduce((s, v) => s + (v - avg) ** 2, 0) / windowSize);
        upper.push(avg + numStd * std);
        lower.push(avg - numStd * std);
      }
    }

    return [
      {
        type: 'line', label: 'BB Upper', data: upper,
        borderColor: 'rgba(156,163,175,0.5)', borderWidth: 1, borderDash: [4, 2],
        pointRadius: 0, fill: '+1', backgroundColor: 'rgba(156,163,175,0.06)',
        yAxisID: 'y', order: 0, spanGaps: true,
      },
      {
        type: 'line', label: 'BB Lower', data: lower,
        borderColor: 'rgba(156,163,175,0.5)', borderWidth: 1, borderDash: [4, 2],
        pointRadius: 0, fill: false,
        yAxisID: 'y', order: 0, spanGaps: true,
      },
    ];
  },

  _volumeDataset(prices) {
    const volumes = prices.map((p) => p.volume);
    const colors = prices.map((p, i) => {
      if (i === 0) return 'rgba(107,114,128,0.15)';
      return p.close >= prices[i - 1].close
        ? 'rgba(220,38,38,0.20)'
        : 'rgba(17,115,212,0.20)';
    });

    return {
      type: 'bar',
      label: '거래량',
      data: volumes,
      backgroundColor: colors,
      borderWidth: 0,
      yAxisID: 'y1',
      order: 2,
      barPercentage: 0.5,
      categoryPercentage: 0.9,
    };
  },

  _calcRSI(closes, period = 14) {
    const rsi = new Array(closes.length).fill(null);
    if (closes.length < period + 1) return rsi;

    let sumGain = 0;
    let sumLoss = 0;
    for (let i = 1; i <= period; i++) {
      const diff = closes[i] - closes[i - 1];
      if (diff > 0) sumGain += diff;
      else sumLoss += Math.abs(diff);
    }
    let avgGain = sumGain / period;
    let avgLoss = sumLoss / period;

    rsi[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);

    for (let i = period + 1; i < closes.length; i++) {
      const diff = closes[i] - closes[i - 1];
      avgGain = (avgGain * (period - 1) + (diff > 0 ? diff : 0)) / period;
      avgLoss = (avgLoss * (period - 1) + (diff < 0 ? Math.abs(diff) : 0)) / period;
      rsi[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
    }

    return rsi;
  },

  _updateRSI(closes, labels) {
    const rsi = this._calcRSI(closes);

    this.rsiChart.data.labels = labels;
    this.rsiChart.data.datasets = [
      {
        label: 'RSI', data: rsi,
        borderColor: '#7c3aed', borderWidth: 1.5,
        pointRadius: 0, pointHoverRadius: 3,
        fill: false, tension: 0.3, spanGaps: true,
      },
      {
        label: '과매수', data: new Array(labels.length).fill(70),
        borderColor: 'rgba(239,68,68,0.3)', borderWidth: 1,
        borderDash: [4, 4], pointRadius: 0, fill: false,
      },
      {
        label: '과매도', data: new Array(labels.length).fill(30),
        borderColor: 'rgba(59,130,246,0.3)', borderWidth: 1,
        borderDash: [4, 4], pointRadius: 0, fill: false,
      },
    ];
    this.rsiChart.update('none');
  },

  destroy() {
    if (this.chart) {
      this.chart.destroy();
      this.chart = null;
    }
    if (this.rsiChart) {
      this.rsiChart.destroy();
      this.rsiChart = null;
    }
  },
};
