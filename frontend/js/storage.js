/**
 * AlphaLens localStorage 영속화 모듈
 * - 최근 검색 (최대 20개, 최신순)
 * - 즐겨찾기 (제한 없음)
 */
const Storage = {
  KEYS: {
    RECENT: 'alphalens_recent',
    FAVORITES: 'alphalens_favorites',
    SCORE_HISTORY: 'alphalens_score_history',
    PORTFOLIO: 'alphalens_portfolio',
  },
  MAX_RECENT: 20,
  MAX_SCORE_HISTORY: 30,

  // ── Internal helpers ──

  _load(key) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : [];
    } catch {
      localStorage.removeItem(key);
      return [];
    }
  },

  _save(key, data) {
    try {
      localStorage.setItem(key, JSON.stringify(data));
    } catch (e) {
      console.warn('Storage save failed:', e);
    }
  },

  // ── Recent ──

  getRecent() {
    return this._load(this.KEYS.RECENT);
  },

  addRecent(stock) {
    const list = this.getRecent().filter((s) => s.code !== stock.code);
    list.unshift({
      code: stock.code,
      name: stock.name,
      market: stock.market,
      price: stock.price,
      change_pct: stock.change_pct,
      over_market: stock.over_market || null,
      timestamp: Date.now(),
    });
    this._save(this.KEYS.RECENT, list.slice(0, this.MAX_RECENT));
  },

  removeRecent(code) {
    const list = this.getRecent().filter((s) => s.code !== code);
    this._save(this.KEYS.RECENT, list);
  },

  clearRecent() {
    this._save(this.KEYS.RECENT, []);
  },

  // ── Favorites ──

  getFavorites() {
    return this._load(this.KEYS.FAVORITES);
  },

  isFavorite(code) {
    return this.getFavorites().some((s) => s.code === code);
  },

  toggleFavorite(stock) {
    const list = this.getFavorites();
    const idx = list.findIndex((s) => s.code === stock.code);
    if (idx >= 0) {
      list.splice(idx, 1);
      this._save(this.KEYS.FAVORITES, list);
      return false;
    }
    list.push({
      code: stock.code,
      name: stock.name,
      market: stock.market,
      price: stock.price,
      change_pct: stock.change_pct,
      over_market: stock.over_market || null,
      addedAt: Date.now(),
    });
    this._save(this.KEYS.FAVORITES, list);
    return true;
  },

  removeFavorite(code) {
    const list = this.getFavorites().filter((s) => s.code !== code);
    this._save(this.KEYS.FAVORITES, list);
  },

  updatePrice(stock) {
    // 즐겨찾기에 해당 종목이 있으면 시세 갱신
    const favs = this.getFavorites();
    const idx = favs.findIndex((s) => s.code === stock.code);
    if (idx >= 0) {
      favs[idx].price = stock.price;
      favs[idx].change_pct = stock.change_pct;
      favs[idx].over_market = stock.over_market || null;
      this._save(this.KEYS.FAVORITES, favs);
    }
  },

  // ── Portfolio ──

  getPortfolio() {
    return this._load(this.KEYS.PORTFOLIO);
  },

  addPortfolioHolding(holding) {
    const list = this.getPortfolio().filter((h) => h.code !== holding.code);
    list.push({
      code: holding.code,
      name: holding.name || holding.code,
      quantity: holding.quantity,
      avg_price: holding.avg_price,
      addedAt: Date.now(),
    });
    this._save(this.KEYS.PORTFOLIO, list);
  },

  updatePortfolioHolding(code, updates) {
    const list = this.getPortfolio();
    const idx = list.findIndex((h) => h.code === code);
    if (idx >= 0) {
      Object.assign(list[idx], updates);
      this._save(this.KEYS.PORTFOLIO, list);
    }
  },

  removePortfolioHolding(code) {
    const list = this.getPortfolio().filter((h) => h.code !== code);
    this._save(this.KEYS.PORTFOLIO, list);
  },

  clearPortfolio() {
    this._save(this.KEYS.PORTFOLIO, []);
  },

  // ── Score History ──

  getScoreHistory(code) {
    const all = this._load(this.KEYS.SCORE_HISTORY);
    return (all[code] || []).slice(-this.MAX_SCORE_HISTORY);
  },

  addScoreHistory(code, score, signal) {
    const all = this._load(this.KEYS.SCORE_HISTORY) || {};
    if (!Array.isArray(all[code])) all[code] = [];

    // 같은 날 중복 방지 (마지막 기록과 같은 날이면 업데이트)
    const today = new Date().toISOString().slice(0, 10);
    const last = all[code][all[code].length - 1];
    if (last && last.date === today) {
      last.score = score;
      last.signal = signal;
    } else {
      all[code].push({ date: today, score, signal, ts: Date.now() });
    }

    // 최대 개수 유지
    if (all[code].length > this.MAX_SCORE_HISTORY) {
      all[code] = all[code].slice(-this.MAX_SCORE_HISTORY);
    }

    try {
      localStorage.setItem(this.KEYS.SCORE_HISTORY, JSON.stringify(all));
    } catch (e) {
      console.warn('Score history save failed:', e);
    }
  },
};
