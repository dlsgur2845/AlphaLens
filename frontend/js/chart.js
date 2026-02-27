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
      ctx.strokeStyle = p.close >= p.open ? '#ef4444' : '#3b82f6';
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
  mode: 'line',
  showMA: { 5: false, 20: true, 60: false },
  showVolume: true,
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
            backgroundColor: '#21253a',
            titleColor: '#e8eaed',
            bodyColor: '#9aa0a6',
            borderColor: '#2d3348',
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
                return `${ctx.parsed.y.toLocaleString()}원`;
              },
            },
          },
        },
        scales: {
          x: {
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: { color: '#6b7280', maxTicksLimit: 8, font: { size: 11 } },
          },
          y: {
            position: 'left',
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: {
              color: '#6b7280',
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

  _rebuild() {
    if (!this.chart || !this._rawData?.prices) return;

    const prices = this._rawData.prices;
    const labels = prices.map((p) => p.date.slice(5));
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
  },

  /* ── 데이터셋 빌더 ── */

  _lineDataset(closes) {
    const first = closes[0] || 0;
    const last = closes[closes.length - 1] || 0;
    const isUp = last >= first;
    const color = isUp ? '#f87171' : '#4f8cff';

    return {
      type: 'line',
      label: '종가',
      data: closes,
      borderColor: color,
      backgroundColor: isUp ? 'rgba(248,113,113,0.08)' : 'rgba(79,140,255,0.08)',
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
      p.close >= p.open ? 'rgba(239,68,68,0.85)' : 'rgba(59,130,246,0.85)'
    );
    const borderColors = prices.map((p) => (p.close >= p.open ? '#ef4444' : '#3b82f6'));

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
    for (let i = 0; i < closes.length; i++) {
      if (i < period - 1) {
        ma.push(null);
      } else {
        let sum = 0;
        for (let j = i - period + 1; j <= i; j++) sum += closes[j];
        ma.push(sum / period);
      }
    }

    const colors = { 5: '#fbbf24', 20: '#a78bfa', 60: '#f472b6' };
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

  _volumeDataset(prices) {
    const volumes = prices.map((p) => p.volume);
    const colors = prices.map((p, i) => {
      if (i === 0) return 'rgba(107,114,128,0.25)';
      return p.close >= prices[i - 1].close
        ? 'rgba(248,113,113,0.25)'
        : 'rgba(79,140,255,0.25)';
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

  destroy() {
    if (this.chart) {
      this.chart.destroy();
      this.chart = null;
    }
  },
};
