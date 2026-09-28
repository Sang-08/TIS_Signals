/**
 * app.js — Dashboard logic: fetch data từ API, render panels, auto-refresh.
 *
 * API base: cùng host, port 8877 (mặc định)
 * Mỗi panel có refresh interval riêng (30s, 2m, 5m, 1h)
 */

const API_BASE = window.location.origin;

// ═══ Utility ═══

function formatNumber(num, decimals = 2) {
  if (num === null || num === undefined) return '—';
  return Number(num).toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatPrice(price, pair) {
  if (price === null || price === undefined) return '—';
  // Forex 5 decimals, crypto 2
  const decimals = price > 100 ? 2 : price > 10 ? 4 : 5;
  return formatNumber(price, decimals);
}

function formatChange(pct) {
  if (pct === null || pct === undefined) return '<span class="change-neutral">—</span>';
  const cls = pct > 0 ? 'change-positive' : pct < 0 ? 'change-negative' : 'change-neutral';
  const arrow = pct > 0 ? '▲' : pct < 0 ? '▼' : '→';
  return `<span class="${cls}">${arrow} ${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%</span>`;
}

function timeAgo(timestamp) {
  const now = Date.now() / 1000;
  const diff = now - timestamp;
  if (diff < 60) return 'vừa xong';
  if (diff < 3600) return `${Math.floor(diff / 60)}m trước`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h trước`;
  return `${Math.floor(diff / 86400)}d trước`;
}

function formatUTC(timestamp) {
  const d = new Date(timestamp * 1000);
  return d.toISOString().slice(11, 16) + ' UTC';
}

function formatDateShort(isoString) {
  try {
    const d = new Date(isoString);
    const dd = String(d.getDate()).padStart(2, '0');
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    return `${dd}/${mm} ${hh}:${min}`;
  } catch {
    return isoString;
  }
}

async function fetchJSON(endpoint) {
  try {
    const resp = await fetch(`${API_BASE}${endpoint}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.json();
  } catch (err) {
    console.warn(`Fetch ${endpoint} failed:`, err.message);
    return null;
  }
}

// ═══ Clock ═══

function updateClock() {
  const now = new Date();
  document.getElementById('clock').textContent =
    now.toISOString().slice(11, 19) + ' UTC';
}
setInterval(updateClock, 1000);
updateClock();

// ═══ Summary Banner ═══

async function updateSummary() {
  const data = await fetchJSON('/api/summary');
  if (!data) return;

  // Fear & Greed badge
  const fgBadge = document.getElementById('fearGreedBadge');
  const fg = data.fear_greed;
  if (fg !== null && fg !== undefined) {
    let bgColor, label;
    if (fg <= 25) { bgColor = '#ff6b6b20'; label = 'Extreme Fear'; }
    else if (fg <= 40) { bgColor = '#ff9f4320'; label = 'Fear'; }
    else if (fg <= 60) { bgColor = '#8892a420'; label = 'Neutral'; }
    else if (fg <= 75) { bgColor = '#00d4aa20'; label = 'Greed'; }
    else { bgColor = '#00d4aa40'; label = 'Extreme Greed'; }
    fgBadge.style.background = bgColor;
    fgBadge.style.color = fg <= 40 ? '#ff6b6b' : fg <= 60 ? '#8892a4' : '#00d4aa';
    fgBadge.textContent = `F&G: ${fg} ${label}`;
  }

  // Summary items
  const snapCount = Object.keys(data.snapshots || {}).length;
  document.getElementById('summaryStatus').textContent = snapCount > 0 ? `${snapCount} assets tracked` : 'Chưa có dữ liệu';
  document.getElementById('summaryDataPoints').textContent = snapCount > 0 ? `${snapCount} assets` : '—';
  document.getElementById('summaryLastUpdate').textContent = new Date().toISOString().slice(11, 19) + ' UTC';

  // Upcoming event
  if (data.upcoming_events && data.upcoming_events.length > 0) {
    const ev = data.upcoming_events[0];
    const hLeft = data.hours_to_next_event;
    let evText = `${ev.country} ${ev.title}`;
    if (hLeft) evText += ` (${hLeft.toFixed(1)}h)`;
    document.getElementById('summaryEvent').textContent = evText;
    document.getElementById('summaryEvent').style.color = ev.impact === 'High' ? '#ff6b6b' : '#ff9f43';
  }
}

// ═══ Forex Panel ═══

let previousForexPrices = {};

async function updateForex() {
  const data = await fetchJSON('/api/summary');
  if (!data || !data.snapshots) return;

  const tbody = document.getElementById('forexBody');
  const forexAssets = Object.entries(data.snapshots).filter(
    ([key]) => key.includes('_') && !key.includes('USDT')
  );

  if (forexAssets.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty-state">Chưa có dữ liệu forex. Bot cần thu thập trước.</td></tr>';
    return;
  }

  let html = '';
  for (const [asset, snap] of forexAssets) {
    const price = snap.price;
    const pair = asset.replace('_', '/');
    const flash = previousForexPrices[asset] && previousForexPrices[asset] !== price ? 'price-flash' : '';
    previousForexPrices[asset] = price;

    // Get changes from API
    const changeData = await fetchJSON(`/api/candles?asset=${asset}&hours=24`);
    let change1h = null, change24h = null;
    if (changeData && changeData.data && changeData.data.length > 1) {
      const latest = changeData.data[changeData.data.length - 1];
      // Find price ~1h ago and ~24h ago
      const now = latest.timestamp;
      const h1 = changeData.data.find(d => d.timestamp <= now - 3600);
      const h24 = changeData.data[0];
      if (h1 && h1.price) change1h = ((latest.price - h1.price) / h1.price) * 100;
      if (h24 && h24.price) change24h = ((latest.price - h24.price) / h24.price) * 100;
    }

    html += `<tr>
      <td class="pair">${pair}</td>
      <td class="price ${flash}">${formatPrice(price, pair)}</td>
      <td>${formatChange(change1h)}</td>
      <td>${formatChange(change24h)}</td>
    </tr>`;
  }
  tbody.innerHTML = html;
}

// ═══ Crypto Panel ═══

async function updateCrypto() {
  const data = await fetchJSON('/api/summary');
  if (!data || !data.snapshots) return;

  const container = document.getElementById('cryptoBody');
  const cryptoAssets = Object.entries(data.snapshots).filter(
    ([key]) => key.includes('USDT')
  );

  if (cryptoAssets.length === 0) {
    container.innerHTML = '<div class="empty-state">Chưa có dữ liệu crypto.</div>';
    return;
  }

  let html = '';
  for (const [asset, snap] of cryptoAssets) {
    const fr = snap.funding_rate;
    const oiChg = snap.oi_change_1h;
    const longR = snap.long_ratio;
    const shortR = snap.short_ratio;
    const price = snap.price;

    const frColor = fr > 0.03 ? 'var(--bearish)' : fr > 0 ? 'var(--bullish)' : fr < -0.03 ? 'var(--bullish)' : fr < 0 ? 'var(--bearish)' : 'var(--neutral)';
    const oiColor = oiChg > 0 ? 'var(--bullish)' : oiChg < 0 ? 'var(--bearish)' : 'var(--neutral)';

    const longPct = longR ? (longR * 100).toFixed(1) : '—';
    const shortPct = shortR ? (shortR * 100).toFixed(1) : '—';
    const longWidth = longR ? longR * 100 : 50;

    html += `
    <div class="crypto-card">
      <div class="crypto-header">
        <span class="crypto-symbol">${asset}</span>
        <span class="crypto-price" style="color:var(--text-primary)">${price ? '$' + formatNumber(price, 2) : '—'}</span>
      </div>
      <div class="crypto-metrics">
        <div class="metric-box">
          <div class="metric-label">Funding</div>
          <div class="metric-value" style="color:${frColor}">${fr !== null ? (fr >= 0 ? '+' : '') + fr.toFixed(4) + '%' : '—'}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">OI 1h</div>
          <div class="metric-value" style="color:${oiColor}">${oiChg !== null ? (oiChg >= 0 ? '+' : '') + oiChg.toFixed(2) + '%' : '—'}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">L/S Ratio</div>
          <div class="metric-value">${longPct}% / ${shortPct}%</div>
        </div>
      </div>
      <div class="ls-bar">
        <div class="long" style="width:${longWidth}%"></div>
        <div class="short" style="width:${100 - longWidth}%"></div>
      </div>
      <div class="ls-labels">
        <span class="change-positive">Long ${longPct}%</span>
        <span class="change-negative">Short ${shortPct}%</span>
      </div>
    </div>`;
  }
  container.innerHTML = html;
}

// ═══ News Panel ═══

async function updateNews() {
  const data = await fetchJSON('/api/news?limit=15');
  if (!data || !data.news) return;

  const container = document.getElementById('newsList');

  if (data.news.length === 0) {
    container.innerHTML = '<div class="empty-state"><span class="icon">📰</span>Chưa có tin tức.</div>';
    return;
  }

  let html = '';
  for (const item of data.news) {
    const url = item.url || '#';
    html += `
    <a href="${url}" target="_blank" class="news-item" style="text-decoration:none;display:block;">
      <div class="news-time">${timeAgo(item.timestamp)} · ${item.source || '?'}</div>
      <div class="news-headline">${item.headline || 'Không có tiêu đề'}</div>
    </a>`;
  }
  container.innerHTML = html;
}

// ═══ Whale Panel ═══

async function updateWhale() {
  const data = await fetchJSON('/api/whale?hours=4');
  if (!data) return;

  const container = document.getElementById('whaleList');
  const txs = data.transactions || [];

  if (txs.length === 0) {
    container.innerHTML = '<div class="empty-state"><span class="icon">🐳</span>Không có giao dịch whale gần đây.</div>';
    return;
  }

  let html = '';
  for (const tx of txs.slice(0, 15)) {
    html += `
    <div class="whale-item">
      <span class="whale-icon">🐳</span>
      <div>
        <div class="whale-amount">$${formatNumber(tx.amount_usd, 0)} ${tx.symbol}</div>
        <div class="whale-detail">${tx.from_type} → ${tx.to_type}</div>
      </div>
      <span class="whale-time">${timeAgo(tx.timestamp)}</span>
    </div>`;
  }
  container.innerHTML = html;
}

// ═══ Calendar Panel ═══

async function updateCalendar() {
  const data = await fetchJSON('/api/calendar?hours=72');
  if (!data) return;

  const container = document.getElementById('calendarList');
  const events = data.events || [];

  if (events.length === 0) {
    container.innerHTML = '<div class="empty-state"><span class="icon">📅</span>Không có sự kiện sắp tới.</div>';
    return;
  }

  let html = '';
  for (const ev of events.slice(0, 20)) {
    const impactClass = (ev.impact || 'Low').toLowerCase();
    html += `
    <div class="calendar-item">
      <div class="calendar-impact ${impactClass}"></div>
      <div class="calendar-content">
        <div class="calendar-time">${formatDateShort(ev.date)}</div>
        <div class="calendar-title">${ev.title}</div>
        <div class="calendar-data">
          <span class="calendar-country">${ev.country}</span>
          ${ev.forecast ? ` · Dự báo: ${ev.forecast}` : ''}
          ${ev.previous ? ` · Trước: ${ev.previous}` : ''}
        </div>
      </div>
    </div>`;
  }
  container.innerHTML = html;
}

// ═══ Charts ═══

let fundingChart = null;
let oiChart = null;

const chartDefaults = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 300 },
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: '#131a2a',
      borderColor: '#1e2a3f',
      borderWidth: 1,
      titleFont: { family: 'JetBrains Mono' },
      bodyFont: { family: 'JetBrains Mono', size: 11 },
    },
  },
  scales: {
    x: {
      ticks: { color: '#5a6478', font: { family: 'JetBrains Mono', size: 10 }, maxTicksLimit: 8 },
      grid: { color: '#1e2a3f22' },
    },
    y: {
      ticks: { color: '#5a6478', font: { family: 'JetBrains Mono', size: 10 } },
      grid: { color: '#1e2a3f44' },
    },
  },
};

async function updateFundingChart() {
  const asset = document.getElementById('fundingAssetSelect').value;
  const data = await fetchJSON(`/api/funding-history?asset=${asset}&hours=48`);
  if (!data || !data.data || data.data.length === 0) return;

  const labels = data.data.map(d => formatUTC(d.timestamp));
  const values = data.data.map(d => d.rate);

  const ctx = document.getElementById('fundingChart').getContext('2d');

  if (fundingChart) fundingChart.destroy();

  fundingChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: values,
        borderColor: '#00d4aa',
        backgroundColor: 'rgba(0, 212, 170, 0.08)',
        fill: true,
        borderWidth: 1.5,
        pointRadius: 0,
        pointHoverRadius: 4,
        tension: 0.3,
      }],
    },
    options: {
      ...chartDefaults,
      scales: {
        ...chartDefaults.scales,
        y: {
          ...chartDefaults.scales.y,
          ticks: {
            ...chartDefaults.scales.y.ticks,
            callback: v => v.toFixed(4) + '%',
          },
        },
      },
    },
  });
}

async function updateOIChart() {
  const asset = document.getElementById('oiAssetSelect').value;
  const data = await fetchJSON(`/api/oi-history?asset=${asset}&hours=48`);
  if (!data || !data.data || data.data.length === 0) return;

  const labels = data.data.map(d => formatUTC(d.timestamp));
  const values = data.data.map(d => d.oi);

  const ctx = document.getElementById('oiChart').getContext('2d');

  if (oiChart) oiChart.destroy();

  oiChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: values,
        borderColor: '#54a0ff',
        backgroundColor: 'rgba(84, 160, 255, 0.08)',
        fill: true,
        borderWidth: 1.5,
        pointRadius: 0,
        pointHoverRadius: 4,
        tension: 0.3,
      }],
    },
    options: {
      ...chartDefaults,
      scales: {
        ...chartDefaults.scales,
        y: {
          ...chartDefaults.scales.y,
          ticks: {
            ...chartDefaults.scales.y.ticks,
            callback: v => {
              if (v >= 1e9) return (v / 1e9).toFixed(1) + 'B';
              if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
              if (v >= 1e3) return (v / 1e3).toFixed(1) + 'K';
              return v;
            },
          },
        },
      },
    },
  });
}

// ═══ Signals & Accuracy ═══

async function updateSignals() {
  const container = document.getElementById('signalsBody');

  // Signals
  const sigData = await fetchJSON('/api/signals?limit=5');
  const accData = await fetchJSON('/api/accuracy');

  let html = '';

  // Accuracy section
  if (accData && accData.accuracy && Object.keys(accData.accuracy).length > 0) {
    html += '<div style="margin-bottom:12px;"><div style="font-size:0.78rem;color:var(--text-muted);text-transform:uppercase;margin-bottom:8px;">Accuracy</div>';
    for (const [asset, stats] of Object.entries(accData.accuracy)) {
      const wr7 = stats['7d'];
      const wr30 = stats['30d'];
      const color7 = wr7.win_rate >= 60 ? 'var(--bullish)' : wr7.win_rate >= 50 ? 'var(--warning)' : 'var(--bearish)';
      html += `<div class="accuracy-row">
        <span class="accuracy-asset">${asset}</span>
        <span class="accuracy-value" style="color:${color7}">7d: ${wr7.win_rate.toFixed(1)}% (${wr7.correct}/${wr7.total})</span>
      </div>`;
    }
    html += '</div>';
  }

  // Recent signals
  if (sigData && sigData.signals && sigData.signals.length > 0) {
    html += '<div style="font-size:0.78rem;color:var(--text-muted);text-transform:uppercase;margin-bottom:8px;">Recent Signals</div>';
    for (const sig of sigData.signals) {
      const cls = sig.direction === 'UP' ? 'bullish' : sig.direction === 'DOWN' ? 'bearish' : '';
      const icon = sig.direction === 'UP' ? '📈' : sig.direction === 'DOWN' ? '📉' : '➡️';
      const outcomeIcon = sig.outcome === 'CORRECT' ? ' ✅' : sig.outcome === 'WRONG' ? ' ❌' : '';
      html += `<div class="signal-card ${cls}">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span class="signal-direction">${icon} ${sig.asset} ${sig.direction}</span>
          <span class="signal-prob">${(sig.probability * 100).toFixed(1)}%${outcomeIcon}</span>
        </div>
        <div style="font-size:0.72rem;color:var(--text-muted);margin-top:4px;">${timeAgo(sig.timestamp)}</div>
      </div>`;
    }
  } else if (!html) {
    html = '<div class="empty-state"><span class="icon">🤖</span>Model cần thu thập dữ liệu trước khi tạo signal.<br>Chạy bot ít nhất 2-4 tuần.</div>';
  }

  container.innerHTML = html;
}

// ═══ Chart Asset Select Events ═══

document.getElementById('fundingAssetSelect').addEventListener('change', updateFundingChart);
document.getElementById('oiAssetSelect').addEventListener('change', updateOIChart);

// ═══ Init & Refresh Intervals ═══

async function initAll() {
  // First load
  await Promise.allSettled([
    updateSummary(),
    updateForex(),
    updateCrypto(),
    updateNews(),
    updateWhale(),
    updateCalendar(),
    updateFundingChart(),
    updateOIChart(),
    updateSignals(),
  ]);

  // Refresh intervals
  setInterval(() => { updateSummary(); updateForex(); updateCrypto(); }, 30000);   // 30s
  setInterval(updateWhale, 120000);                                                  // 2m
  setInterval(updateNews, 300000);                                                   // 5m
  setInterval(() => { updateFundingChart(); updateOIChart(); }, 300000);             // 5m
  setInterval(updateSignals, 60000);                                                 // 1m
  setInterval(updateCalendar, 3600000);                                              // 1h
}

// Start
initAll();
