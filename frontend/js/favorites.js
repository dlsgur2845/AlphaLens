/**
 * AlphaLens 관심종목 & 최근검색 모듈
 * - Welcome 화면 데이터 렌더링
 * - 즐겨찾기/최근검색 카드 관리
 */

const Favorites = {
  init() {
    document.getElementById('moreFavorites').addEventListener('click', () => {
      Router.navigate('favorites');
    });
    document.getElementById('moreRecent').addEventListener('click', () => {
      Router.navigate('favorites');
    });
  },

  render(opts) {
    const limit = (opts && opts.limit != null) ? opts.limit : 5;
    const favs = Storage.getFavorites();
    const recent = Storage.getRecent();
    const isFavPage = Router.activeNav === 'favorites';

    const favSection = document.getElementById('favoritesSection');
    const favGrid = document.getElementById('favoritesGrid');
    if (favs.length > 0) {
      favSection.style.display = '';
      const showFavs = limit ? favs.slice(0, limit) : favs;
      favGrid.innerHTML = showFavs.map((s) => this._cardHTML(s, 'favorite')).join('');
      this._bindCards(favGrid, 'favorite');
    } else {
      favSection.style.display = 'none';
    }

    const recentSection = document.getElementById('recentSection');
    const recentGrid = document.getElementById('recentGrid');
    if (recent.length > 0) {
      recentSection.style.display = '';
      const showRecent = limit ? recent.slice(0, limit) : recent;
      recentGrid.innerHTML = showRecent.map((s) => this._cardHTML(s, 'recent')).join('');
      this._bindCards(recentGrid, 'recent');
    } else {
      recentSection.style.display = 'none';
    }

    document.getElementById('moreFavorites').style.display = isFavPage ? 'none' : '';
    document.getElementById('moreRecent').style.display = isFavPage ? 'none' : '';
  },

  _cardHTML(stock, type) {
    const changePct = stock.change_pct != null ? stock.change_pct : 0;
    const changeClass = changePct > 0 ? 'up' : changePct < 0 ? 'down' : '';
    const changeStr = formatChange(changePct);
    const priceStr = stock.price != null ? stock.price.toLocaleString() + '\uC6D0' : '-';
    const ts = stock.timestamp || stock.addedAt;
    const timeStr = ts ? this._relativeTime(ts) : '';

    const actionBtn = type === 'favorite'
      ? `<button class="stock-card-action star" data-action="unfav" data-code="${stock.code}" title="\uC990\uACA8\uCC3E\uAE30 \uD574\uC81C">&#9733;</button>`
      : `<button class="stock-card-action" data-action="remove" data-code="${stock.code}" title="\uC0AD\uC81C">&#10005;</button>`;

    let overMarketHTML = '';
    const om = stock.over_market;
    if (om && om.price) {
      const omPct = om.change_pct != null ? om.change_pct : 0;
      const omClass = omPct > 0 ? 'up' : omPct < 0 ? 'down' : '';
      overMarketHTML = `
        <div class="stock-card-over">
          <span class="stock-card-over-label">\uC2DC\uAC04\uC678</span>
          <span class="stock-card-over-price">${om.price.toLocaleString()}\uC6D0</span>
          <span class="stock-card-over-change ${omClass}" aria-label="\uC2DC\uAC04\uC678 \uBCC0\uB3D9\uB960 ${formatChange(omPct)}">${formatChange(omPct)}</span>
        </div>`;
    }

    return `
      <div class="stock-card" data-code="${stock.code}" data-name="${escapeHTML(stock.name)}">
        ${actionBtn}
        <div class="stock-card-name">${escapeHTML(stock.name)}</div>
        <div class="stock-card-meta">${stock.code} \u00B7 ${stock.market || ''}</div>
        <div class="stock-card-price">${priceStr}</div>
        <div class="stock-card-change ${changeClass}" aria-label="\uBCC0\uB3D9\uB960 ${changeStr}">${changeStr}</div>
        ${overMarketHTML}
        ${timeStr ? `<div class="stock-card-time">${timeStr}</div>` : ''}
      </div>
    `;
  },

  _relativeTime(timestamp) {
    const diff = Date.now() - timestamp;
    const sec = Math.floor(diff / 1000);
    if (sec < 60) return '\uBC29\uAE08 \uC804';
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}\uBD84 \uC804`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}\uC2DC\uAC04 \uC804`;
    const day = Math.floor(hr / 24);
    if (day < 30) return `${day}\uC77C \uC804`;
    return `${Math.floor(day / 30)}\uB2EC \uC804`;
  },

  _bindCards(container, type) {
    container.querySelectorAll('.stock-card').forEach((card) => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('.stock-card-action')) return;
        const code = card.dataset.code;
        const name = card.dataset.name;
        document.getElementById('searchInput').value = name;
        StockDetail.load(code);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });

    container.querySelectorAll('.stock-card-action').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const code = btn.dataset.code;
        const action = btn.dataset.action;
        if (action === 'remove') {
          Storage.removeRecent(code);
          Toast.show('\uCD5C\uADFC \uAC80\uC0C9\uC5D0\uC11C \uC0AD\uC81C\uB428', 'info');
        } else if (action === 'unfav') {
          Storage.removeFavorite(code);
          Toast.show('\uC990\uACA8\uCC3E\uAE30 \uD574\uC81C\uB428', 'info');
        }
        this.render();
      });
    });
  },
};
