/**
 * AlphaLens 스코어 게이지 시각화 모듈
 */
const ScoreGauge = {
  draw(canvasId, score) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h / 2;
    const r = Math.min(cx, cy) - 15;

    ctx.clearRect(0, 0, w, h);

    // 배경 원호
    const startAngle = 0.75 * Math.PI;
    const endAngle = 2.25 * Math.PI;
    const totalAngle = endAngle - startAngle;

    ctx.beginPath();
    ctx.arc(cx, cy, r, startAngle, endAngle);
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth = 12;
    ctx.lineCap = 'round';
    ctx.stroke();

    // 점수 원호
    const scoreAngle = startAngle + (score / 100) * totalAngle;
    const gradient = ctx.createConicGradient(startAngle, cx, cy);

    if (score >= 70) {
      gradient.addColorStop(0, '#34d399');
      gradient.addColorStop(1, '#10b981');
    } else if (score >= 55) {
      gradient.addColorStop(0, '#6ee7b7');
      gradient.addColorStop(1, '#34d399');
    } else if (score >= 45) {
      gradient.addColorStop(0, '#fbbf24');
      gradient.addColorStop(1, '#f59e0b');
    } else if (score >= 30) {
      gradient.addColorStop(0, '#fca5a5');
      gradient.addColorStop(1, '#f87171');
    } else {
      gradient.addColorStop(0, '#f87171');
      gradient.addColorStop(1, '#ef4444');
    }

    ctx.beginPath();
    ctx.arc(cx, cy, r, startAngle, scoreAngle);
    ctx.strokeStyle = ScoreGauge.getColor(score);
    ctx.lineWidth = 12;
    ctx.lineCap = 'round';
    ctx.stroke();

    // 끝점 원
    const dotX = cx + r * Math.cos(scoreAngle);
    const dotY = cy + r * Math.sin(scoreAngle);
    ctx.beginPath();
    ctx.arc(dotX, dotY, 6, 0, 2 * Math.PI);
    ctx.fillStyle = ScoreGauge.getColor(score);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(dotX, dotY, 10, 0, 2 * Math.PI);
    ctx.fillStyle = ScoreGauge.getColor(score) + '30';
    ctx.fill();
  },

  getColor(score) {
    if (score >= 70) return '#34d399';
    if (score >= 55) return '#6ee7b7';
    if (score >= 45) return '#fbbf24';
    if (score >= 30) return '#fca5a5';
    return '#f87171';
  },

  getSignalClass(signal) {
    const map = {
      '강한상승': 'strong-up',
      '상승': 'up',
      '중립': 'neutral',
      '하락': 'down',
      '강한하락': 'strong-down',
    };
    return map[signal] || 'neutral';
  },

  updateBreakdown(breakdown) {
    const items = [
      { bar: 'barTechnical', val: 'valTechnical', score: breakdown.technical },
      { bar: 'barNews', val: 'valNews', score: breakdown.news_sentiment },
      { bar: 'barFundamental', val: 'valFundamental', score: breakdown.fundamental },
      { bar: 'barRelated', val: 'valRelated', score: breakdown.related_momentum },
    ];

    items.forEach(item => {
      const bar = document.getElementById(item.bar);
      const val = document.getElementById(item.val);
      if (bar) {
        bar.style.width = `${item.score}%`;
        bar.style.background = `linear-gradient(90deg, ${ScoreGauge.getColor(item.score)}, ${ScoreGauge.getColor(item.score)}90)`;
      }
      if (val) val.textContent = item.score.toFixed(1);
    });
  },

  // ── 스코어 히스토리 미니 차트 ──

  _historyChart: null,

  drawHistory(code) {
    const history = Storage.getScoreHistory(code);
    const wrap = document.getElementById('scoreHistoryWrap');
    if (!wrap) return;

    if (history.length < 2) {
      wrap.style.display = 'none';
      return;
    }

    wrap.style.display = '';
    const ctx = document.getElementById('scoreHistoryChart');
    if (!ctx) return;

    if (this._historyChart) {
      this._historyChart.destroy();
    }

    const labels = history.map(h => h.date.slice(5));
    const data = history.map(h => h.score);
    const first = data[0];
    const last = data[data.length - 1];
    const color = last >= first ? '#34d399' : '#f87171';

    this._historyChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          data,
          borderColor: color,
          backgroundColor: color + '15',
          borderWidth: 1.5,
          pointRadius: 0,
          pointHoverRadius: 3,
          fill: true,
          tension: 0.3,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: {
          backgroundColor: '#21253a',
          titleColor: '#e8eaed',
          bodyColor: '#9aa0a6',
          callbacks: {
            label(ctx) { return `점수: ${ctx.parsed.y.toFixed(1)}`; }
          }
        }},
        scales: {
          x: { display: false },
          y: { display: false, min: 0, max: 100 },
        },
      },
    });
  },
};
