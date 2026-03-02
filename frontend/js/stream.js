/**
 * AlphaLens 실시간 스트리밍 클라이언트
 */
const AlphaStream = {
  _ws: null,
  _currentCode: null,
  _reconnectDelay: 1000,
  _maxReconnectDelay: 30000,
  _heartbeatTimer: null,
  _reconnectTimer: null,
  _intentionalClose: false,

  // ── 연결 관리 ─────────────────────────────

  connect() {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) return;

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${location.host}/api/v1/ws`;

    this._intentionalClose = false;
    this._ws = new WebSocket(url);

    this._ws.onopen = () => {
      console.log('[Stream] Connected');
      this._reconnectDelay = 1000;
      this._updateBadge(true);
      this._startHeartbeat();

      // 연결 복구 시 현재 종목 재구독
      if (this._currentCode) {
        this._send({ action: 'subscribe', code: this._currentCode });
      }
    };

    this._ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        this._handleMessage(msg);
      } catch (e) {
        console.warn('[Stream] Parse error:', e);
      }
    };

    this._ws.onclose = () => {
      console.log('[Stream] Disconnected');
      this._updateBadge(false);
      this._stopHeartbeat();
      if (!this._intentionalClose) {
        this._scheduleReconnect();
      }
    };

    this._ws.onerror = (err) => {
      console.warn('[Stream] Error:', err);
    };
  },

  disconnect() {
    this._intentionalClose = true;
    this._stopHeartbeat();
    clearTimeout(this._reconnectTimer);
    if (this._ws) {
      this._ws.close();
      this._ws = null;
    }
    this._updateBadge(false);
  },

  _scheduleReconnect() {
    clearTimeout(this._reconnectTimer);
    console.log(`[Stream] Reconnecting in ${this._reconnectDelay / 1000}s...`);
    this._reconnectTimer = setTimeout(() => {
      this._reconnectDelay = Math.min(this._reconnectDelay * 2, this._maxReconnectDelay);
      this.connect();
    }, this._reconnectDelay);
  },

  _send(obj) {
    if (this._ws && this._ws.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify(obj));
    }
  },

  // ── 하트비트 ──────────────────────────────

  _startHeartbeat() {
    this._stopHeartbeat();
    this._heartbeatTimer = setInterval(() => {
      this._send({ action: 'ping' });
    }, 30000);
  },

  _stopHeartbeat() {
    clearInterval(this._heartbeatTimer);
    this._heartbeatTimer = null;
  },

  // ── 구독 ──────────────────────────────────

  subscribe(code) {
    // 이전 종목 구독 해제
    if (this._currentCode && this._currentCode !== code) {
      this._send({ action: 'unsubscribe', code: this._currentCode });
    }
    this._currentCode = code;
    this._send({ action: 'subscribe', code: code });
    console.log(`[Stream] Subscribed to ${code}`);
  },

  // ── 메시지 핸들러 ─────────────────────────

  _handleMessage(msg) {
    switch (msg.type) {
      case 'price_update':
        this._onPriceUpdate(msg.data);
        break;
      case 'news_update':
        this._onNewsUpdate(msg.data);
        break;
      case 'scoring_update':
        this._onScoringUpdate(msg.data);
        break;
      case 'subscribed':
        console.log(`[Stream] Confirmed subscription: ${msg.data.code}`);
        break;
      case 'pong':
        break;
      default:
        console.log('[Stream] Unknown message:', msg);
    }
  },

  // ── 가격 업데이트 ─────────────────────────

  _onPriceUpdate(data) {
    if (data.code !== this._currentCode) return;

    const priceEl = document.getElementById('stockPrice');
    const changeEl = document.getElementById('stockChange');
    if (!priceEl) return;

    // 이전 값과 비교하여 flash
    const oldText = priceEl.textContent;
    const newText = data.price.toLocaleString() + '원';

    priceEl.textContent = newText;

    const sign = data.change >= 0 ? '+' : '';
    changeEl.textContent = `${sign}${data.change.toLocaleString()}원 (${sign}${data.change_pct}%)`;
    changeEl.className = `stock-change ${data.change >= 0 ? 'up' : 'down'}`;

    // 시장 상태 뱃지 갱신
    const labelEl = document.getElementById('priceLabel');
    if (labelEl) {
      const statusText = data.market_status === 'OPEN' ? '거래중' : '장마감';
      const statusClass = data.market_status === 'OPEN' ? 'open' : 'close';
      labelEl.innerHTML = `KRX 종가 <span class="market-status-badge ${statusClass}">${statusText}</span>`;
    }

    // Flash 애니메이션 (가격 변동 시)
    if (oldText !== newText) {
      const flashClass = data.price_direction === 'up' ? 'flash-up' : 'flash-down';
      priceEl.classList.remove('flash-up', 'flash-down');
      // reflow trigger
      void priceEl.offsetWidth;
      priceEl.classList.add(flashClass);
    }

    // 실시간 타임스탬프 갱신
    const tsEl = document.getElementById('liveTimestamp');
    if (tsEl) {
      const now = new Date(data.timestamp);
      tsEl.textContent = `실시간 · ${now.toLocaleTimeString('ko', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
    }
  },

  // ── 뉴스 업데이트 ─────────────────────────

  _onNewsUpdate(data) {
    if (data.code !== this._currentCode) return;
    if (!data.new_articles || data.new_articles.length === 0) return;

    const listEl = document.getElementById('newsList');
    const summaryEl = document.getElementById('newsSummary');
    if (!listEl) return;

    // 감성 요약 갱신
    if (summaryEl) {
      const sentColor =
        data.overall_label === '긍정' ? 'var(--green)' :
        data.overall_label === '부정' ? 'var(--red)' : 'var(--yellow)';

      summaryEl.innerHTML = `
        <span style="color:${sentColor}">${escapeHTML(data.overall_label)}</span>
        <span style="color:var(--text-muted)">
          (긍정 ${escapeHTML(data.positive_count)} / 부정 ${escapeHTML(data.negative_count)} / 중립 ${escapeHTML(data.neutral_count)})
        </span>
      `;
    }

    // 새 기사를 목록 상단에 삽입
    data.new_articles.forEach((article) => {
      const sentClass =
        article.sentiment_label === '긍정' ? 'positive' :
        article.sentiment_label === '부정' ? 'negative' : 'neutral';
      const scoreSign = article.sentiment_score > 0 ? '+' : '';

      const el = document.createElement('a');
      el.href = article.link;
      el.target = '_blank';
      el.rel = 'noopener noreferrer';
      el.className = 'news-item news-item-new';
      el.title = article.title;
      el.innerHTML = `
        <div class="news-sentiment-badge ${sentClass}">${escapeHTML(article.sentiment_label)}</div>
        <div class="news-item-content">
          <div class="news-item-title">
            <span class="news-new-badge">NEW</span>
            ${escapeHTML(article.title)}
          </div>
          <div class="news-item-meta">
            <span>${escapeHTML(article.source)}</span>
            <span>${escapeHTML(article.date)}</span>
            <span class="news-item-score ${sentClass}">${escapeHTML(scoreSign)}${escapeHTML(article.sentiment_score.toFixed(2))}</span>
          </div>
        </div>
      `;

      listEl.insertBefore(el, listEl.firstChild);

      // NEW 뱃지 5초 후 제거
      setTimeout(() => {
        const badge = el.querySelector('.news-new-badge');
        if (badge) badge.remove();
        el.classList.remove('news-item-new');
      }, 5000);
    });
  },

  // ── 스코어링 업데이트 ─────────────────────

  _onScoringUpdate(data) {
    if (data.code !== this._currentCode) return;

    // 게이지
    if (typeof ScoreGauge !== 'undefined') {
      ScoreGauge.draw('scoreGauge', data.total_score);
    }

    const scoreVal = document.getElementById('scoreValue');
    if (scoreVal) scoreVal.textContent = data.total_score.toFixed(1);

    // 7단계 시그널 라벨
    const label = data.action_label || data.signal;
    const signalEl = document.getElementById('scoreSignal');
    if (signalEl && typeof ScoreGauge !== 'undefined') {
      const riskSuffix = data.risk_grade ? ` · 리스크 ${data.risk_grade}` : '';
      signalEl.textContent = label + riskSuffix;
      signalEl.className = `score-signal ${ScoreGauge.getSignalClass(label)}`;
    }

    // 업데이트 시간
    const updatedEl = document.getElementById('scoreUpdated');
    if (updatedEl) {
      const updated = new Date(data.updated_at);
      updatedEl.textContent =
        `${updated.toLocaleDateString('ko')} ${updated.toLocaleTimeString('ko', { hour: '2-digit', minute: '2-digit' })} 기준`;
    }

    // 세부 점수 breakdown 바 (7팩터)
    if (data.breakdown && typeof ScoreGauge !== 'undefined') {
      ScoreGauge.updateBreakdown(data.breakdown);
    }
  },

  // ── LIVE 뱃지 상태 ────────────────────────

  _updateBadge(connected) {
    const badge = document.getElementById('liveBadge');
    if (!badge) return;

    if (connected) {
      badge.textContent = 'LIVE';
      badge.className = 'live-badge connected';
    } else {
      badge.textContent = 'OFFLINE';
      badge.className = 'live-badge disconnected';
    }
  },
};
