/**
 * AlphaLens 지정학 리스크 모듈
 * - _loadGeopolitical: 지정학 데이터 로드
 * - _renderGeopolitical: 지정학 대시보드 렌더링 (compact/full)
 */

const Geopolitical = {
  async load() {
    const section = document.getElementById('geopoliticalSection');
    section.style.display = '';

    // 로딩 상태 표시
    document.getElementById('geoRiskScore').textContent = '-';
    document.getElementById('geoRiskLabel').textContent = '분석 중...';
    document.getElementById('geoRiskLabel').className = 'geo-risk-label';
    document.getElementById('geoRiskBarFill').style.width = '0%';
    document.getElementById('geoEvents').innerHTML = '<div class="section-loading-msg">이벤트 분석 중</div>';
    document.getElementById('geoSectorImpacts').innerHTML = '';
    document.getElementById('geoTriggers').innerHTML = '';
    document.getElementById('geoHorizonGrid').innerHTML = '<div class="section-loading-msg">시간축 분석 중</div>';
    document.getElementById('geoHorizonSection').style.display = '';

    SectionProgress.start('#geopoliticalSection', 'geopolitical');
    try {
      const data = await API.getGeopolitical();
      if (!data || !data.risk_index) {
        SectionProgress.complete('geopolitical');
        document.getElementById('geoRiskLabel').textContent = '데이터 없음';
        document.getElementById('geoEvents').innerHTML = '<span class="geo-empty">분석 가능한 데이터가 없습니다</span>';
        document.getElementById('geoHorizonGrid').innerHTML = '';
        document.getElementById('geoHorizonSection').style.display = 'none';
        return;
      }
      const isCompact = Router.activeNav === 'home';
      this.render(data, isCompact);
      SectionProgress.complete('geopolitical');
    } catch (e) {
      console.warn('Geopolitical load failed:', e.message);
      SectionProgress.error('geopolitical');
      document.getElementById('geoRiskLabel').textContent = '로드 실패';
      document.getElementById('geoEvents').innerHTML = '<div class="section-error-msg">데이터를 불러올 수 없습니다</div>';
      document.getElementById('geoHorizonGrid').innerHTML = '';
      document.getElementById('geoHorizonSection').style.display = 'none';
    }
  },

  render(data, compact) {
    const ri = data.risk_index || {};
    const score = Number(ri.score) || 0;
    const SEVERITY_ALLOW = ['critical', 'high', 'medium', 'low'];
    const safeSeverity = (s) => SEVERITY_ALLOW.includes(s) ? s : 'low';

    // 리스크 점수
    const scoreEl = document.getElementById('geoRiskScore');
    scoreEl.textContent = score.toFixed(0);
    const scoreColor = score >= 70 ? 'var(--red)' : score >= 50 ? '#fb923c' : score >= 30 ? 'var(--yellow)' : 'var(--green)';
    scoreEl.style.color = scoreColor;

    // 리스크 라벨
    const labelEl = document.getElementById('geoRiskLabel');
    labelEl.textContent = ri.label || '분석 중';
    const labelClass = score >= 70 ? 'danger' : score >= 50 ? 'alert' : score >= 30 ? 'caution' : 'safe';
    labelEl.className = `geo-risk-label ${labelClass}`;

    // 리스크 바
    const barFill = document.getElementById('geoRiskBarFill');
    const barEl = document.getElementById('geoRiskBar');
    if (barEl) barEl.setAttribute('aria-valuenow', score.toFixed(0));
    barFill.style.width = `${Math.min(score, 100)}%`;
    barFill.style.background = score >= 70
      ? 'linear-gradient(90deg, #fb923c, var(--red))'
      : score >= 50
        ? 'linear-gradient(90deg, var(--yellow), #fb923c)'
        : score >= 30
          ? 'linear-gradient(90deg, var(--green), var(--yellow))'
          : 'var(--green)';

    // compact 모드: 우측 상세 칼럼 숨김
    const rightCol = document.querySelector('.geo-right-col');
    if (rightCol) rightCol.style.display = compact ? 'none' : '';

    // 감지된 이벤트
    const eventsEl = document.getElementById('geoEvents');
    const events = data.detected_events || {};
    const eventEntries = Object.entries(events);
    if (eventEntries.length > 0) {
      eventsEl.innerHTML = eventEntries.map(([, ev]) => {
        const sev = safeSeverity(ev.severity);
        const hitCount = Number(ev.hit_count) || 0;
        return `<div class="geo-event-chip">
          <span class="geo-event-icon">${escapeHTML(ev.icon || '')}</span>
          <span class="geo-event-label">${escapeHTML(ev.label || '')}</span>
          <span class="geo-event-severity ${sev}">${sev}</span>
          <span class="geo-event-count">${hitCount}건</span>
        </div>`;
      }).join('');
    } else {
      eventsEl.innerHTML = '<span class="geo-empty">감지된 이벤트 없음</span>';
    }

    // 섹터 영향
    const sectorEl = document.getElementById('geoSectorImpacts');
    const sectors = data.sector_impacts || {};
    const sectorEntries = Object.entries(sectors);
    if (sectorEntries.length > 0) {
      sectorEl.innerHTML = sectorEntries.slice(0, 12).map(([name, info]) => {
        const dir = info.direction || '';
        const cls = dir === '수혜' ? 'positive' : dir === '피해' ? 'negative' : 'neutral-impact';
        const impact = Number(info.total_impact) || 0;
        const sign = impact > 0 ? '+' : '';
        return `<span class="geo-sector-tag ${cls}">${dir === '수혜' ? '&#9650;' : dir === '피해' ? '&#9660;' : '&#9679;'} ${escapeHTML(name)} ${sign}${impact}</span>`;
      }).join('');
    } else {
      sectorEl.innerHTML = '<span class="geo-empty">영향 분석 데이터 없음</span>';
    }

    // 시나리오 트리거
    const triggersEl = document.getElementById('geoTriggers');
    const triggers = data.scenario_triggers || [];
    if (triggers.length > 0) {
      triggersEl.innerHTML = triggers.map((t) => {
        const sev = safeSeverity(t.severity);
        return `<div class="geo-trigger-item ${sev}">
          <span class="geo-trigger-signal">${escapeHTML(t.signal || '')}</span>
          <span class="geo-trigger-action">${escapeHTML(t.action || '')}</span>
        </div>`;
      }).join('');
    } else {
      triggersEl.innerHTML = '<span class="geo-empty">트리거 없음</span>';
    }

    // 시간축별 리스크
    const horizonSection = document.getElementById('geoHorizonSection');
    const horizonGrid = document.getElementById('geoHorizonGrid');
    const horizons = data.horizon_risks || {};
    const horizonOrder = ['short', 'mid', 'long'];
    const horizonIcons = { short: '⚡', mid: '📊', long: '🏗️' };

    if (Object.keys(horizons).length > 0) {
      horizonSection.style.display = '';
      horizonGrid.innerHTML = horizonOrder.map((key) => {
        const h = horizons[key];
        if (!h) return '';
        const hScore = Number(h.score) || 0;
        const hColor = hScore >= 70 ? 'var(--red)' : hScore >= 50 ? '#fb923c' : hScore >= 30 ? 'var(--yellow)' : 'var(--green)';
        const hClass = hScore >= 70 ? 'danger' : hScore >= 50 ? 'alert' : hScore >= 30 ? 'caution' : 'safe';

        // compact 모드: 점수+라벨+바만 표시
        if (compact) {
          return `<div class="geo-horizon-card ${hClass}">
            <div class="geo-hz-header">
              <span class="geo-hz-icon">${horizonIcons[key]}</span>
              <span class="geo-hz-title">${escapeHTML(h.horizon_label || '')}</span>
              <span class="geo-hz-period">${escapeHTML(h.period || '')}</span>
            </div>
            <div class="geo-hz-score-row">
              <span class="geo-hz-score" style="color:${hColor}">${hScore.toFixed(0)}</span>
              <span class="geo-hz-label ${hClass}">${escapeHTML(h.label || '')}</span>
            </div>
            <div class="geo-hz-bar">
              <div class="geo-hz-bar-fill" style="width:${Math.min(hScore, 100)}%;background:${hColor}"></div>
            </div>
          </div>`;
        }

        const eventsHtml = (h.key_events || []).map((ev) => {
          const sev = safeSeverity(ev.severity);
          const roleTag = ev.role === 'secondary' ? ' <span class="geo-hz-secondary">간접</span>' : '';
          return `<span class="geo-hz-event ${sev}">${escapeHTML(ev.icon || '')} ${escapeHTML(ev.label || '')}${roleTag}</span>`;
        }).join('');

        return `<div class="geo-horizon-card ${hClass}">
          <div class="geo-hz-header">
            <span class="geo-hz-icon">${horizonIcons[key]}</span>
            <span class="geo-hz-title">${escapeHTML(h.horizon_label || '')}</span>
            <span class="geo-hz-period">${escapeHTML(h.period || '')}</span>
          </div>
          <div class="geo-hz-score-row">
            <span class="geo-hz-score" style="color:${hColor}">${hScore.toFixed(0)}</span>
            <span class="geo-hz-label ${hClass}">${escapeHTML(h.label || '')}</span>
          </div>
          <div class="geo-hz-bar">
            <div class="geo-hz-bar-fill" style="width:${Math.min(hScore, 100)}%;background:${hColor}"></div>
          </div>
          <div class="geo-hz-desc">${escapeHTML(h.description || '')}</div>
          ${eventsHtml ? `<div class="geo-hz-events">${eventsHtml}</div>` : ''}
          <div class="geo-hz-guidance">${escapeHTML(h.guidance || '')}</div>
        </div>`;
      }).join('');
    } else {
      horizonSection.style.display = 'none';
    }

    // 업데이트 시간
    if (data.updated_at) {
      const t = new Date(data.updated_at);
      const articlesCount = Number(data.articles_analyzed) || 0;
      document.getElementById('geoUpdateTime').textContent =
        `${t.toLocaleTimeString('ko', { hour: '2-digit', minute: '2-digit' })} 기준 · ${articlesCount}건 분석`;
    }
  },
};
