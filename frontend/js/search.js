/**
 * AlphaLens 검색 + 자동완성 + Quick Access + 키보드 네비게이션
 */
const Search = {
  debounceTimer: null,
  _selectedIndex: -1,

  init() {
    this._initSearchPair('searchInput', 'searchResults');
    this._initSearchPair('heroSearchInput', 'heroSearchResults');

    document.addEventListener('click', (e) => {
      if (!e.target.closest('.search-container') && !e.target.closest('.hero-search-container')) {
        document.getElementById('searchResults').classList.remove('active');
        const heroDD = document.getElementById('heroSearchResults');
        if (heroDD) heroDD.classList.remove('active');
        this._selectedIndex = -1;
      }
    });
  },

  _initSearchPair(inputId, dropdownId) {
    const input = document.getElementById(inputId);
    const dropdown = document.getElementById(dropdownId);
    if (!input || !dropdown) return;

    input.addEventListener('input', () => {
      clearTimeout(this.debounceTimer);
      this._selectedIndex = -1;
      const q = input.value.trim();

      if (q.length === 0) {
        this._showQuickAccessFor(dropdown);
        return;
      }

      this.debounceTimer = setTimeout(() => this._searchFor(q, dropdown), 300);
    });

    input.addEventListener('focus', () => {
      const q = input.value.trim();
      if (q.length === 0) {
        this._showQuickAccessFor(dropdown);
      } else if (dropdown.children.length > 0) {
        dropdown.classList.add('active');
      }
    });

    input.addEventListener('keydown', (e) => {
      const items = dropdown.querySelectorAll('.search-item[data-code]');
      if (!items.length && !dropdown.classList.contains('active')) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        this._selectedIndex = Math.min(this._selectedIndex + 1, items.length - 1);
        this._updateSelection(items);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        this._selectedIndex = Math.max(this._selectedIndex - 1, -1);
        this._updateSelection(items);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (this._selectedIndex >= 0 && items[this._selectedIndex]) {
          items[this._selectedIndex].click();
        } else if (items.length > 0) {
          items[0].click();
        }
      } else if (e.key === 'Escape') {
        dropdown.classList.remove('active');
        this._selectedIndex = -1;
        input.blur();
      }
    });
  },

  _updateSelection(items) {
    items.forEach((item, i) => {
      item.classList.toggle('selected', i === this._selectedIndex);
    });
    // 선택된 항목이 보이도록 스크롤
    if (this._selectedIndex >= 0 && items[this._selectedIndex]) {
      items[this._selectedIndex].scrollIntoView({ block: 'nearest' });
    }
  },

  showQuickAccess() {
    this._showQuickAccessFor(document.getElementById('searchResults'));
  },

  _showQuickAccessFor(dropdown) {
    const favs = Storage.getFavorites().slice(0, 5);
    const recent = Storage.getRecent().slice(0, 8);

    if (favs.length === 0 && recent.length === 0) {
      dropdown.classList.remove('active');
      return;
    }

    let html = '';

    if (favs.length > 0) {
      html += '<div class="search-section-label">즐겨찾기</div>';
      html += favs.map((s) => this._quickItemHTML(s)).join('');
    }

    if (recent.length > 0) {
      html += '<div class="search-section-label">최근 검색</div>';
      html += recent.map((s) => this._quickItemHTML(s)).join('');
    }

    dropdown.innerHTML = html;
    this._bindDropdownItems(dropdown);
    this._selectedIndex = -1;
    dropdown.classList.add('active');
  },

  _quickItemHTML(stock) {
    const changePct = stock.change_pct != null ? stock.change_pct : 0;
    const changeColor = changePct > 0 ? 'var(--red)' : changePct < 0 ? 'var(--accent)' : 'var(--text-muted)';
    const changeStr = changePct > 0 ? `+${changePct}%` : `${changePct}%`;

    return `
      <div class="search-item" data-code="${stock.code}" data-name="${escapeHTML(stock.name)}">
        <div>
          <span class="search-item-name">${escapeHTML(stock.name)}</span>
          <span class="search-item-code">${stock.code}</span>
        </div>
        <span style="font-size:13px;font-weight:600;color:${changeColor}">${changeStr}</span>
      </div>
    `;
  },

  async search(query) {
    return this._searchFor(query, document.getElementById('searchResults'));
  },

  async _searchFor(query, dropdown) {
    try {
      const results = await API.searchStocks(query);

      if (results.length === 0) {
        dropdown.innerHTML = '<div class="search-empty-state">검색 결과가 없습니다</div>';
        dropdown.classList.add('active');
        this._selectedIndex = -1;
        return;
      }

      dropdown.innerHTML = results
        .map(
          (s) => `
        <div class="search-item" data-code="${s.code}" data-name="${escapeHTML(s.name)}">
          <div>
            <span class="search-item-name">${escapeHTML(s.name)}</span>
            <span class="search-item-code">${s.code}</span>
          </div>
          <span class="search-item-market">${escapeHTML(s.market)}</span>
        </div>
      `
        )
        .join('');

      this._bindDropdownItems(dropdown);
      this._selectedIndex = -1;
      dropdown.classList.add('active');
    } catch (err) {
      console.error('검색 오류:', err);
    }
  },

  _bindDropdownItems(dropdown) {
    dropdown.querySelectorAll('.search-item[data-code]').forEach((item) => {
      item.addEventListener('click', () => {
        const code = item.dataset.code;
        const name = item.dataset.name;
        document.getElementById('searchInput').value = name;
        dropdown.classList.remove('active');
        this._selectedIndex = -1;
        App.loadStock(code);
      });
    });
  },
};
