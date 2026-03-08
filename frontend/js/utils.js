/**
 * AlphaLens 공통 유틸리티
 * - formatChange: 변동률 포맷
 * - Toast: 알림 토스트
 * - SectionProgress: 섹션별 프로그레스 바
 */

/* ── WCAG 1.4.1 접근성: 변동률 포맷 헬퍼 ── */
function formatChange(value, suffix = '%') {
  if (value == null) return '-';
  const num = parseFloat(value);
  if (num > 0) return `▲ +${num.toFixed(2)}${suffix}`;
  if (num < 0) return `▼ ${num.toFixed(2)}${suffix}`;
  return `- 0.00${suffix}`;
}

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

/* ── 섹션 프로그레스 바 ── */
const SectionProgress = {
  _bars: {},

  start(selector, key) {
    this.remove(key);
    const el = document.querySelector(selector);
    if (!el) return;
    const bar = document.createElement('div');
    bar.className = 'section-progress';
    bar.setAttribute('role', 'progressbar');
    bar.setAttribute('aria-label', `${key} 로딩 중`);
    bar.innerHTML = '<div class="section-progress-bar"></div>';
    el.prepend(bar);
    this._bars[key] = bar;
  },

  complete(key) {
    const bar = this._bars[key];
    if (!bar) return;
    bar.classList.add('completing');
    setTimeout(() => {
      bar.classList.add('completed');
      bar.addEventListener('transitionend', () => bar.remove(), { once: true });
      setTimeout(() => bar.remove(), 800);
    }, 300);
    delete this._bars[key];
  },

  error(key) {
    const bar = this._bars[key];
    if (!bar) return;
    bar.classList.add('error');
    setTimeout(() => {
      bar.classList.add('completed');
      bar.addEventListener('transitionend', () => bar.remove(), { once: true });
      setTimeout(() => bar.remove(), 800);
    }, 1500);
    delete this._bars[key];
  },

  remove(key) {
    const bar = this._bars[key];
    if (bar) { bar.remove(); delete this._bars[key]; }
  },

  clear() {
    Object.keys(this._bars).forEach((k) => {
      this._bars[k].remove();
      delete this._bars[k];
    });
  },
};
