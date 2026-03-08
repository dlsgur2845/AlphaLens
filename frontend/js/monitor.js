/**
 * AlphaLens 시스템 모니터링 모듈
 * - SystemMonitor: CPU/메모리 사이드바 모니터
 */

const SystemMonitor = {
  _interval: null,

  start() {
    this.fetch();
    this._interval = setInterval(() => this.fetch(), 1000);
  },

  async fetch() {
    try {
      const res = await fetch('/api/v1/system/stats');
      if (!res.ok) return;
      const data = await res.json();
      this.render(data);
    } catch { /* silent */ }
  },

  render(d) {
    const cpuEl = document.getElementById('statCpuValue');
    const memEl = document.getElementById('statMemValue');
    const memDetail = document.getElementById('statMemDetail');
    const cpuBar = document.getElementById('statCpuBar');
    const memBar = document.getElementById('statMemBar');
    if (!cpuEl) return;

    const cpu = d.cpu_percent ?? 0;
    const mem = d.memory_percent ?? 0;
    const memUsedGB = ((d.memory_used ?? 0) / (1024 ** 3)).toFixed(1);
    const memTotalGB = ((d.memory_total ?? 0) / (1024 ** 3)).toFixed(1);

    cpuEl.textContent = cpu.toFixed(1) + '%';
    memEl.textContent = mem.toFixed(1) + '%';
    if (memDetail) memDetail.textContent = `${memUsedGB} / ${memTotalGB} GB`;

    const cpuFill = cpuBar?.querySelector('.monitor-bar-fill');
    const memFill = memBar?.querySelector('.monitor-bar-fill');
    if (cpuFill) cpuFill.style.width = cpu + '%';
    if (memFill) memFill.style.width = mem + '%';
  },
};
