/**
 * AlphaLens API 통신 모듈
 * - 타임아웃 (10초)
 * - 1회 자동 재시도
 * - 오프라인 감지
 */

/* ── HTML 이스케이프 유틸리티 ── */
function escapeHTML(str) {
  if (typeof str !== 'string') return String(str ?? '');
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function safeURL(url) {
  if (typeof url !== 'string') return '#';
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  return '#';
}

const API = {
  BASE: '/api/v1',
  TIMEOUT: 10000,

  async _fetch(url, retries = 1) {
    if (!navigator.onLine) {
      Toast.show('네트워크 연결을 확인해주세요', 'error');
      throw new Error('오프라인 상태');
    }

    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.TIMEOUT);

        const res = await fetch(url, { signal: controller.signal });
        clearTimeout(timer);

        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(err.detail || '요청 실패');
        }
        return res.json();
      } catch (e) {
        if (e.name === 'AbortError') {
          if (attempt < retries) continue;
          throw new Error('요청 시간 초과');
        }
        if (attempt < retries && e.message !== '오프라인 상태') continue;
        throw e;
      }
    }
  },

  get(endpoint) {
    return this._fetch(`${this.BASE}${endpoint}`);
  },

  searchStocks(query) {
    return this.get(`/stocks/search?q=${encodeURIComponent(query)}&limit=15`);
  },

  getStockDetail(code) {
    return this.get(`/stocks/${code}`);
  },

  getPriceHistory(code, days = 90) {
    return this.get(`/stocks/${code}/price?days=${days}`);
  },

  getRelatedCompanies(code, depth = 2, max = 20) {
    return this.get(`/related/${code}?depth=${depth}&max=${max}`);
  },

  getNews(code, maxArticles = 20) {
    return this.get(`/news/${code}?max_articles=${maxArticles}`);
  },

  getScoring(code) {
    return this.get(`/scoring/${code}`);
  },

  getRecommendations() {
    return this.get('/recommendations');
  },

  getGeopolitical() {
    return this.get('/geopolitical');
  },
};

// 오프라인/온라인 전환 감지
window.addEventListener('online', () => Toast.show('네트워크 연결됨', 'success'));
window.addEventListener('offline', () => Toast.show('네트워크 연결 끊김', 'error'));
