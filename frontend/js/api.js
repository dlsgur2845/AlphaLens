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
  // 무거운 엔드포인트용 확장 타임아웃 (추천: 80종목 스코어링, 지정학: 18개 RSS)
  LONG_TIMEOUT: 30000,
  _apiKey: '',

  setApiKey(key) {
    this._apiKey = key;
  },

  _getHeaders() {
    const headers = {};
    if (this._apiKey) {
      headers['X-API-Key'] = this._apiKey;
    }
    return headers;
  },

  async _fetch(url, retries = 1, timeout = null) {
    const reqTimeout = timeout || this.TIMEOUT;

    if (!navigator.onLine) {
      Toast.show('네트워크 연결을 확인해주세요', 'error');
      throw new Error('오프라인 상태');
    }

    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), reqTimeout);

        const res = await fetch(url, {
          signal: controller.signal,
          headers: this._getHeaders(),
        });
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

  get(endpoint, timeout = null) {
    return this._fetch(`${this.BASE}${endpoint}`, 1, timeout);
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

  getInvestorTrend(code, days = 20) {
    return this.get(`/stocks/${code}/investor?days=${days}`);
  },

  getRelatedCompanies(code, depth = 1, max = 10) {
    return this.get(`/related/${code}?depth=${depth}&max=${max}`, this.LONG_TIMEOUT);
  },

  getNews(code, maxArticles = 20) {
    return this.get(`/news/${code}?max_articles=${maxArticles}`);
  },

  getScoring(code) {
    return this.get(`/scoring/${code}`);
  },

  getRecommendations() {
    return this.get('/recommendations', this.LONG_TIMEOUT);
  },

  getMarketSummary() {
    return this.get('/recommendations/market-summary');
  },

  getGeopolitical() {
    return this.get('/geopolitical', this.LONG_TIMEOUT);
  },

  async _post(url, body, timeout = null) {
    const reqTimeout = timeout || this.TIMEOUT;
    if (!navigator.onLine) {
      Toast.show('네트워크 연결을 확인해주세요', 'error');
      throw new Error('오프라인 상태');
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), reqTimeout);
    try {
      const res = await fetch(url, {
        method: 'POST',
        signal: controller.signal,
        headers: { ...this._getHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      clearTimeout(timer);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || '요청 실패');
      }
      return res.json();
    } catch (e) {
      clearTimeout(timer);
      if (e.name === 'AbortError') throw new Error('요청 시간 초과');
      throw e;
    }
  },

  post(endpoint, body, timeout = null) {
    return this._post(`${this.BASE}${endpoint}`, body, timeout);
  },

  analyzePortfolio(holdings) {
    return this.post('/portfolio/analyze', { holdings }, 120000);
  },
};

// 오프라인/온라인 전환 감지
window.addEventListener('online', () => Toast.show('네트워크 연결됨', 'success'));
window.addEventListener('offline', () => Toast.show('네트워크 연결 끊김', 'error'));
