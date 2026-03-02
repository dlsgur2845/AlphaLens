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

    // 배경 원호 (그라데이션)
    const startAngle = 0.75 * Math.PI;
    const endAngle = 2.25 * Math.PI;
    const totalAngle = endAngle - startAngle;

    const bgGradient = ctx.createLinearGradient(0, h, w, 0);
    bgGradient.addColorStop(0, 'rgba(239,68,68,0.15)');
    bgGradient.addColorStop(0.25, 'rgba(245,158,11,0.15)');
    bgGradient.addColorStop(0.5, 'rgba(234,179,8,0.15)');
    bgGradient.addColorStop(0.75, 'rgba(34,197,94,0.15)');
    bgGradient.addColorStop(1, 'rgba(16,185,129,0.15)');

    ctx.beginPath();
    ctx.arc(cx, cy, r, startAngle, endAngle);
    ctx.strokeStyle = bgGradient;
    ctx.lineWidth = 12;
    ctx.lineCap = 'round';
    ctx.stroke();

    // 점수 원호
    const scoreAngle = startAngle + (score / 100) * totalAngle;

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
    if (score >= 70) return '#2dd4a0';
    if (score >= 55) return '#5eead4';
    if (score >= 45) return '#f0b429';
    if (score >= 30) return '#f9a8a8';
    return '#ef6b6b';
  },

  getSignalClass(signal) {
    const map = {
      '강력매수': 'strong-buy',
      '매수': 'buy',
      '관망(매수우위)': 'lean-buy',
      '중립': 'neutral',
      '관망(매도우위)': 'lean-sell',
      '매도': 'sell',
      '강력매도': 'strong-sell',
      // 하위 호환
      '강한상승': 'strong-buy',
      '상승': 'buy',
      '하락': 'sell',
      '강한하락': 'strong-sell',
    };
    return map[signal] || 'neutral';
  },

  updateBreakdown(breakdown) {
    const items = [
      { bar: 'barTechnical', val: 'valTechnical', score: breakdown.technical },
      { bar: 'barSignal', val: 'valSignal', score: breakdown.signal != null ? breakdown.signal : 50 },
      { bar: 'barFundamental', val: 'valFundamental', score: breakdown.fundamental },
      { bar: 'barMacro', val: 'valMacro', score: breakdown.macro != null ? breakdown.macro : 50 },
      { bar: 'barRisk', val: 'valRisk', score: breakdown.risk != null ? breakdown.risk : 50 },
      { bar: 'barRelated', val: 'valRelated', score: breakdown.related_momentum },
      { bar: 'barNews', val: 'valNews', score: breakdown.news_sentiment },
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
    const color = last >= first ? '#2dd4a0' : '#ef6b6b';

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
          backgroundColor: '#1e2438',
          titleColor: '#e6e8ec',
          bodyColor: '#8f96a3',
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
