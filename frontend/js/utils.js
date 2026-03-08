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

/* ── 캐시 상태 실시간 추적 ── */
const CacheTracker = {
  _entries: {},   // key → { el, loadedAt, cacheAge, ttl, onExpire }
  _timer: null,

  /**
   * 캐시 상태를 등록하고 실시간 업데이트 시작.
   * @param {string} key - 고유 키 (market, geopolitical, recommend)
   * @param {HTMLElement|string} el - 배지를 표시할 요소 또는 ID
   * @param {object} data - API 응답 (_cached, _cache_age 포함)
   * @param {number} ttl - 캐시 TTL(초). 만료 시 onExpire 호출
   * @param {function} onExpire - TTL 만료 시 실행할 콜백 (자동 갱신)
   */
  register(key, el, data, ttl, onExpire) {
    const target = typeof el === 'string' ? document.getElementById(el) : el;
    if (!target) return;

    const isCached = data && data._cached === true;
    const cacheAge = isCached ? (data._cache_age || 0) : 0;

    this._entries[key] = {
      el: target,
      loadedAt: Date.now(),
      cacheAge,
      isCached,
      ttl,
      onExpire,
      expired: false,
    };

    this._updateBadge(key);
    if (!this._timer) {
      this._timer = setInterval(() => this._tick(), 1000);
    }
  },

  unregister(key) {
    delete this._entries[key];
    if (Object.keys(this._entries).length === 0 && this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  },

  clear() {
    this._entries = {};
    if (this._timer) { clearInterval(this._timer); this._timer = null; }
  },

  _tick() {
    for (const key of Object.keys(this._entries)) {
      this._updateBadge(key);
    }
  },

  _updateBadge(key) {
    const entry = this._entries[key];
    if (!entry || !entry.el) return;

    const elapsed = (Date.now() - entry.loadedAt) / 1000;
    const totalAge = entry.cacheAge + elapsed;
    const remaining = entry.ttl - totalAge;

    if (remaining <= 0 && !entry.expired) {
      entry.expired = true;
      entry.el.innerHTML = '<span class="cache-badge expired">만료됨</span>';
      if (entry.onExpire) {
        Toast.show('데이터가 갱신됩니다', 'info', 2000);
        entry.onExpire();
      }
      return;
    }

    if (entry.expired) return;

    if (!entry.isCached && elapsed < 3) {
      entry.el.innerHTML = '<span class="cache-badge fresh">실시간</span>';
      return;
    }

    const ageDisplay = this._formatAge(totalAge);
    const remainDisplay = this._formatAge(Math.max(remaining, 0));
    entry.el.innerHTML =
      `<span class="cache-badge cached" title="만료까지 ${remainDisplay}">캐시 · ${ageDisplay} 경과</span>`;
  },

  _formatAge(seconds) {
    if (seconds < 60) return `${Math.round(seconds)}초`;
    return `${Math.floor(seconds / 60)}분 ${Math.round(seconds % 60)}초`;
  },
};

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
