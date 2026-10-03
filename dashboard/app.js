/* ===== CrypT Trading Intelligence Dashboard — Bento Edition ===== */
const API = '';
let detailChart = null;
let miniChart = null;
let selectedAsset = null;
let currentMiniTab = 'funding';
let previousPrices = {};

// ===== UTILS =====
const fmt = (n, d = 2) => n == null ? '--' : Number(n).toFixed(d);
const fmtPct = (n, d = 2) => {
  if (n == null || isNaN(n)) return '--';
  const v = Number(n);
  return (v > 0 ? '+' : '') + v.toFixed(d) + '%';
};
const fmtUSD = n => {
  if (n == null) return '--';
  n = Number(n);
  if (Math.abs(n) >= 1e12) return '$' + (n / 1e12).toFixed(2) + 'T';
  if (Math.abs(n) >= 1e9) return '$' + (n / 1e9).toFixed(2) + 'B';
  if (Math.abs(n) >= 1e6) return '$' + (n / 1e6).toFixed(1) + 'M';
  if (Math.abs(n) >= 1e3) return '$' + (n / 1e3).toFixed(1) + 'K';
  return n >= 1 ? '$' + n.toFixed(2) : '$' + n.toFixed(4);
};
const fmtPrice = n => {
  if (n == null) return '--';
  n = Number(n);
  if (n >= 1000) return '$' + n.toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (n >= 1) return '$' + n.toFixed(2);
  if (n >= 0.01) return '$' + n.toFixed(4);
  return '$' + n.toFixed(6);
};
const cls = n => n == null ? 'neutral' : n > 0 ? 'up' : n < 0 ? 'down' : 'neutral';
const clsBg = n => n == null ? '' : n > 0 ? 'up-bg' : n < 0 ? 'down-bg' : '';
const ago = ts => {
  if (!ts) return '';
  const d = Math.floor((Date.now() / 1000 - ts) / 60);
  if (d < 1) return 'just now';
  if (d < 60) return d + 'm ago';
  if (d < 1440) return Math.floor(d / 60) + 'h ago';
  return Math.floor(d / 1440) + 'd ago';
};
const gainLoss = n => n == null ? '' : n >= 0 ? 'gain' : 'loss';

// Clock
setInterval(() => {
  const d = new Date();
  document.getElementById('clock').textContent =
    d.toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
}, 1000);

// ===== FETCH =====
async function api(path) {
  try {
    const r = await fetch(API + path);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.json();
  } catch (e) {
    console.warn('API error:', path, e.message);
    return null;
  }
}

// ===== SPARKLINE (tiny canvas) =====
function drawSparkline(canvas, data, color) {
  if (!canvas || !data || data.length < 2) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width = canvas.offsetWidth * 2;
  const h = canvas.height = canvas.offsetHeight * 2;
  ctx.clearRect(0, 0, w, h);

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const step = w / (data.length - 1);

  ctx.beginPath();
  data.forEach((v, i) => {
    const x = i * step;
    const y = h - ((v - min) / range) * (h * 0.85) - h * 0.05;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.lineJoin = 'round';
  ctx.stroke();

  // Gradient fill
  const last = data[data.length - 1];
  const lastY = h - ((last - min) / range) * (h * 0.85) - h * 0.05;
  ctx.lineTo(w, h);
  ctx.lineTo(0, h);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, color + '30');
  grad.addColorStop(1, 'transparent');
  ctx.fillStyle = grad;
  ctx.fill();
}

// ===== FEAR & GREED GAUGE =====
function updateFGGauge(value) {
  if (value == null) return;
  const el = document.getElementById('fg-value');
  const labelEl = document.getElementById('fg-label');
  const arc = document.getElementById('fg-arc');
  el.textContent = value;

  const label = value <= 25 ? 'Extreme Fear'
    : value <= 45 ? 'Fear'
    : value <= 55 ? 'Neutral'
    : value <= 75 ? 'Greed'
    : 'Extreme Greed';
  labelEl.textContent = label;

  // SVG arc: total length ~157
  const pct = Math.min(value / 100, 1);
  const len = pct * 157;
  arc.setAttribute('stroke-dasharray', len + ' 157');

  // Color the value
  if (value <= 25) el.style.color = '#f85149';
  else if (value <= 45) el.style.color = '#f0883e';
  else if (value <= 55) el.style.color = '#e8ecf4';
  else if (value <= 75) el.style.color = '#2dd4a8';
  else el.style.color = '#2dd4a8';
}

// ===== RENDER CRYPTO CARDS =====
function renderCrypto(data) {
  const grid = document.getElementById('crypto-grid');
  if (!data || !data.crypto || !data.crypto.length) {
    grid.innerHTML = '<div class="empty-state"><div class="skeleton-block"></div><span>Waiting for crypto data...</span></div>';
    return;
  }

  grid.innerHTML = data.crypto.map((c, idx) => {
    const chg = c.change_24h;
    const fr = c.funding_rate;
    const frPct = fr != null ? (fr * 100) : null;
    const oi = c.oi_value;
    const lp = c.long_ratio != null ? (c.long_ratio * 100).toFixed(0) : null;
    const sp = c.short_ratio != null ? (c.short_ratio * 100).toFixed(0) : null;
    const shortName = c.symbol.replace('USDT', '').replace('BUSD', '');
    const act = selectedAsset === c.symbol ? ' active' : '';
    const gl = gainLoss(chg);

    // Flash detection
    const prevPrice = previousPrices[c.symbol];
    let flashClass = '';
    if (prevPrice != null && c.price != null) {
      if (c.price > prevPrice) flashClass = ' flash-up';
      else if (c.price < prevPrice) flashClass = ' flash-down';
    }
    previousPrices[c.symbol] = c.price;

    return '<div class="coin-card ' + gl + act + '" style="animation-delay:' + (idx * 0.06) + 's" onclick="openDetail(\'' + c.symbol + '\')">'
      + '<div class="cc-top">'
      + '<span class="cc-symbol">' + shortName + '</span>'
      + '<span class="cc-change ' + cls(chg) + ' ' + clsBg(chg) + '">' + fmtPct(chg) + '</span>'
      + '</div>'
      + '<div class="cc-price' + flashClass + '">' + fmtPrice(c.price) + '</div>'
      + '<canvas class="cc-spark" id="spark-' + c.symbol + '"></canvas>'
      + '<div class="cc-meta">'
      + '<span class="cc-tag ' + cls(frPct) + '">F:' + fmtPct(frPct, 3) + '</span>'
      + (lp != null ? '<span class="cc-tag">' + lp + '/' + sp + '</span>' : '')
      + '</div></div>';
  }).join('');

  // Draw sparklines (async)
  data.crypto.forEach(c => loadSparkline(c.symbol));
}

async function loadSparkline(symbol) {
  const canvas = document.getElementById('spark-' + symbol);
  if (!canvas) return;
  const data = await api('/api/candles?asset=' + symbol + '&hours=24');
  const candles = (data && data.candles) || [];
  if (candles.length < 2) return;
  const prices = candles.map(c => c.price);
  const color = prices[prices.length - 1] >= prices[0] ? '#2dd4a8' : '#f85149';
  drawSparkline(canvas, prices, color);
}

// ===== RENDER FOREX CARDS =====
function renderForex(data) {
  const grid = document.getElementById('forex-grid');
  const section = document.getElementById('forex-section');
  if (!data || !data.forex || Object.keys(data.forex).length === 0) {
    section.style.display = 'none';
    return;
  }
  section.style.display = 'block';
  const pairs = data.forex;
  const keys = Object.keys(pairs).filter(k => pairs[k] && !pairs[k].error);

  grid.innerHTML = keys.map((k, idx) => {
    const p = pairs[k];
    const chg = p.change_1h;
    const gl = gainLoss(chg);
    const displayName = k.replace('_', '/');
    const act = selectedAsset === k ? ' active' : '';

    return '<div class="coin-card small ' + gl + act + '" style="animation-delay:' + (idx * 0.06) + 's" onclick="openDetail(\'' + k + '\')">'
      + '<div class="cc-top">'
      + '<span class="cc-symbol">' + displayName + '</span>'
      + '<span class="cc-change ' + cls(chg) + ' ' + clsBg(chg) + '">' + fmtPct(chg) + '</span>'
      + '</div>'
      + '<div class="cc-price">' + fmt(p.price, p.price > 10 ? 3 : 5) + '</div>'
      + '</div>';
  }).join('');
}

// ===== DETAIL PANEL (BENTO) =====
async function openDetail(symbol) {
  selectedAsset = symbol;
  const panel = document.getElementById('bento-detail');
  panel.classList.remove('hidden');

  const displayName = symbol.replace('USDT', '').replace('BUSD', '').replace('_', '/');
  document.getElementById('detail-symbol').textContent = displayName;

  // Highlight active card
  document.querySelectorAll('.coin-card').forEach(c => c.classList.remove('active'));
  document.querySelectorAll('.coin-card').forEach(c => {
    if (c.onclick && c.onclick.toString().includes(symbol)) c.classList.add('active');
  });

  const [candles, deriv, crossEx] = await Promise.all([
    api('/api/candles?asset=' + symbol + '&hours=48'),
    api('/api/derivatives?asset=' + symbol),
    api('/api/cross-exchange?asset=' + symbol),
  ]);

  // Price & change
  if (deriv && deriv.derivatives) {
    const d = deriv.derivatives;
    const price = d.mark_price || d.price;
    document.getElementById('detail-price').textContent = fmtPrice(price);

    // Use price change from candles instead of funding rate
    const chartData = (candles && candles.candles) || [];
    let priceChg = null;
    if (chartData.length >= 2) {
      const firstP = chartData[0].price;
      const lastP = chartData[chartData.length - 1].price;
      priceChg = ((lastP - firstP) / firstP) * 100;
    }
    const chgEl = document.getElementById('detail-change');
    chgEl.textContent = fmtPct(priceChg);
    chgEl.className = 'tile-change ' + cls(priceChg) + ' ' + clsBg(priceChg);

    // Funding Rate tile
    const fr = d.funding_rate;
    const frPct = fr != null ? fr * 100 : null;
    const frEl = document.getElementById('d-funding');
    frEl.textContent = fmtPct(frPct, 4);
    frEl.className = 'tile-value ' + cls(frPct);

    // OI tile
    document.getElementById('d-oi').textContent = fmtUSD(d.open_interest);

    // OI Change tile
    const oiChgEl = document.getElementById('d-oi-chg');
    oiChgEl.textContent = fmtPct(d.oi_change_1h);
    oiChgEl.className = 'tile-value ' + cls(d.oi_change_1h);

    // Long/Short bar
    const ls = d.long_short_ratio;
    if (ls) {
      document.getElementById('ls-long-bar').style.width = ls.long_pct + '%';
      document.getElementById('d-long-pct').textContent = fmt(ls.long_pct, 1) + '%';
      document.getElementById('d-short-pct').textContent = fmt(ls.short_pct, 1) + '%';
    }
  } else if (deriv && deriv.snapshot) {
    const s = deriv.snapshot;
    document.getElementById('detail-price').textContent = fmtPrice(s.price);
    const frPct = s.funding_rate != null ? s.funding_rate * 100 : null;
    const frEl = document.getElementById('d-funding');
    frEl.textContent = fmtPct(frPct, 4);
    frEl.className = 'tile-value ' + cls(frPct);
    document.getElementById('d-oi').textContent = fmtUSD(s.oi_value);
    const oiChgEl = document.getElementById('d-oi-chg');
    oiChgEl.textContent = fmtPct(s.oi_change_1h);
    oiChgEl.className = 'tile-value ' + cls(s.oi_change_1h);
    if (s.long_ratio != null) {
      const lPct = s.long_ratio * 100;
      const sPct = s.short_ratio * 100;
      document.getElementById('ls-long-bar').style.width = lPct + '%';
      document.getElementById('d-long-pct').textContent = fmt(lPct, 1) + '%';
      document.getElementById('d-short-pct').textContent = fmt(sPct, 1) + '%';
    }
  }

  // Cross-exchange
  if (crossEx && crossEx.exchanges && crossEx.exchanges.length) {
    const bybit = crossEx.exchanges.find(e => e.exchange === 'bybit');
    if (bybit) {
      document.getElementById('d-bybit-fr').textContent = fmtPct(bybit.funding_rate ? bybit.funding_rate * 100 : null, 4);
      const binFR = deriv && deriv.derivatives ? deriv.derivatives.funding_rate : null;
      document.getElementById('d-binance-fr').textContent = fmtPct(binFR ? binFR * 100 : null, 4);
      if (binFR != null && bybit.funding_rate != null) {
        const spread = (binFR - bybit.funding_rate) * 100;
        document.getElementById('d-spread').textContent = fmtPct(spread, 4);
        document.getElementById('d-spread').className = 'mono ' + cls(spread);
      }
    }
  } else {
    document.getElementById('d-bybit-fr').textContent = '--';
    document.getElementById('d-binance-fr').textContent = '--';
    document.getElementById('d-spread').textContent = '--';
  }

  // Chart
  const chartData = (candles && candles.candles) || [];
  if (chartData.length) renderDetailChart(chartData);

  loadMiniChart(symbol, currentMiniTab);
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function closeDetail() {
  document.getElementById('bento-detail').classList.add('hidden');
  selectedAsset = null;
  document.querySelectorAll('.coin-card').forEach(c => c.classList.remove('active'));
}

// ===== CHARTS =====
const chartDefaults = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: 'rgba(15, 18, 35, 0.9)',
      borderColor: 'rgba(255,255,255,0.08)',
      borderWidth: 1,
      titleFont: { family: "'Inter', sans-serif", size: 11 },
      bodyFont: { family: "'JetBrains Mono', monospace", size: 12 },
      padding: 10,
      cornerRadius: 10,
      displayColors: false,
      mode: 'index',
      intersect: false,
    },
  },
  interaction: { intersect: false, mode: 'index' },
};

function renderDetailChart(candles) {
  const ctx = document.getElementById('detail-chart');
  if (detailChart) detailChart.destroy();

  const labels = candles.map(c => {
    const d = new Date(c.timestamp * 1000);
    return d.toLocaleString('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
  });
  const prices = candles.map(c => c.price);
  const isUp = prices[prices.length - 1] >= prices[0];
  const color = isUp ? '#2dd4a8' : '#f85149';
  const colorDim = isUp ? 'rgba(45,212,168,0.12)' : 'rgba(248,81,73,0.12)';

  detailChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: prices,
        borderColor: color,
        backgroundColor: (context) => {
          const chart = context.chart;
          const { ctx: c, chartArea } = chart;
          if (!chartArea) return colorDim;
          const grad = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
          grad.addColorStop(0, color + '25');
          grad.addColorStop(1, 'transparent');
          return grad;
        },
        fill: true,
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBackgroundColor: color,
        pointHoverBorderColor: '#fff',
        pointHoverBorderWidth: 2,
        tension: 0.4,
      }]
    },
    options: {
      ...chartDefaults,
      scales: {
        x: {
          display: true,
          ticks: {
            maxTicksLimit: 6, color: '#4a5068',
            font: { size: 10, family: "'JetBrains Mono', monospace" },
          },
          grid: { color: 'rgba(255,255,255,0.03)', drawBorder: false },
        },
        y: {
          position: 'right',
          ticks: {
            color: '#4a5068',
            font: { size: 10, family: "'JetBrains Mono', monospace" },
          },
          grid: { color: 'rgba(255,255,255,0.03)', drawBorder: false },
        },
      },
    },
  });
}

async function loadMiniChart(symbol, type) {
  const endpoint = type === 'funding'
    ? '/api/funding-history?asset=' + symbol + '&hours=72'
    : '/api/oi-history?asset=' + symbol + '&hours=72';
  const data = await api(endpoint);
  const ctx = document.getElementById('mini-chart');
  if (miniChart) miniChart.destroy();

  const history = (data && data.history) || (data && data.data) || [];
  if (!history.length) {
    miniChart = new Chart(ctx, {
      type: 'line',
      data: { labels: ['No data'], datasets: [{ data: [0], borderColor: '#4a5068', pointRadius: 0 }] },
      options: { ...chartDefaults, scales: { x: { display: false }, y: { display: false } } },
    });
    return;
  }

  const labels = history.map(h => {
    const d = new Date(h.timestamp * 1000);
    return d.toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit', hour12: false });
  });

  const values = history.map(h => {
    if (type === 'funding') return ((h.funding_rate || h.rate || 0) * 100);
    return h.open_interest || h.oi || 0;
  });

  const color = type === 'funding' ? '#bc8cff' : '#58a6ff';

  miniChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: values,
        borderColor: color,
        backgroundColor: color + '12',
        fill: true,
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.4,
      }]
    },
    options: {
      ...chartDefaults,
      scales: {
        x: { display: false },
        y: {
          position: 'right',
          ticks: { color: '#4a5068', font: { size: 9, family: "'JetBrains Mono', monospace" } },
          grid: { color: 'rgba(255,255,255,0.02)', drawBorder: false },
        },
      },
    },
  });
}

function switchMiniChart(type) {
  currentMiniTab = type;
  document.querySelectorAll('.mini-tab').forEach(b => b.classList.remove('active'));
  if (event && event.target) event.target.classList.add('active');
  if (selectedAsset) loadMiniChart(selectedAsset, type);
}

// ===== TABS =====
function switchTab(name, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(t => t.classList.remove('active'));
  if (btn) btn.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
  updateTabIndicator(btn);
}

function updateTabIndicator(btn) {
  const indicator = document.getElementById('tab-indicator');
  if (!btn || !indicator) return;
  indicator.style.left = btn.offsetLeft + 'px';
  indicator.style.width = btn.offsetWidth + 'px';
}

// Init tab indicator
requestAnimationFrame(() => {
  const firstTab = document.querySelector('.tab-btn.active');
  if (firstTab) updateTabIndicator(firstTab);
});

// ===== INFO TAB RENDERERS =====
function renderNews(data) {
  const el = document.getElementById('tab-news');
  if (!data || !data.news || !data.news.length) {
    el.innerHTML = '<div class="empty-state"><span>📰 No news available yet.</span></div>';
    return;
  }
  el.innerHTML = data.news.map(n => {
    const title = n.headline || n.title || '--';
    const url = n.url;
    const titleHtml = url
      ? '<a href="' + url + '" target="_blank" rel="noopener">' + title + '</a>'
      : title;
    return '<div class="news-item">'
      + '<div class="title">' + titleHtml + '</div>'
      + '<div class="source">' + (n.source || '') + ' · ' + (n.timestamp ? ago(n.timestamp) : '') + '</div>'
      + '</div>';
  }).join('');
}

function renderWhale(data) {
  const el = document.getElementById('tab-whale');
  if (!data || !data.transactions || !data.transactions.length) {
    el.innerHTML = '<div class="empty-state"><span>🐳 No whale transactions detected.<br><small>Requires Whale Alert API key in .env</small></span></div>';
    return;
  }
  el.innerHTML = data.transactions.map(t => {
    return '<div class="whale-item">'
      + '<span class="wh-sym">' + (t.symbol || 'BTC') + '</span>'
      + '<span class="wh-flow">' + (t.from_type || '?') + ' → ' + (t.to_type || '?') + '</span>'
      + '<span class="wh-amt">' + fmtUSD(t.amount_usd) + '</span>'
      + '<span class="wh-time">' + (t.timestamp ? ago(t.timestamp) : '') + '</span>'
      + '</div>';
  }).join('');
}

function renderCalendar(data) {
  const el = document.getElementById('tab-calendar');
  if (!data || !data.events || !data.events.length) {
    el.innerHTML = '<div class="empty-state"><span>📅 No upcoming economic events.</span></div>';
    return;
  }
  el.innerHTML = data.events.slice(0, 25).map(e => {
    const impact = (e.impact || '').toLowerCase();
    const icon = impact === 'high' ? '🔴' : impact === 'medium' ? '🟡' : '⚪';
    return '<div class="cal-item ' + impact + '">'
      + '<div class="ev-info">' + icon
      + ' <span class="ev-cur">' + (e.currency || '') + '</span>'
      + '<span class="ev-title">' + (e.title || e.event || '') + '</span></div>'
      + '<span class="ev-time">' + (e.date || '') + ' ' + (e.time || '') + '</span>'
      + '</div>';
  }).join('');
}

async function renderSignals() {
  const el = document.getElementById('tab-signals');
  const [accData, sigData] = await Promise.all([
    api('/api/accuracy'),
    api('/api/signals?limit=10'),
  ]);

  let html = '';
  if (sigData && sigData.signals && sigData.signals.length) {
    html += sigData.signals.map(s => {
      const isUp = s.direction === 'UP';
      const icon = isUp ? '▲' : '▼';
      const label = isUp ? 'LONG' : 'SHORT';
      const dirCls = isUp ? 'up' : 'down';
      return '<div class="signal-card">'
        + '<div style="display:flex;justify-content:space-between;align-items:center">'
        + '<span class="sig-dir ' + dirCls + '">' + icon + ' ' + label + ' ' + s.asset + '</span>'
        + '<span class="sig-prob ' + dirCls + '">' + fmt(s.probability) + '%</span>'
        + '</div>'
        + '<div class="sig-meta">'
        + (s.outcome ? 'Outcome: <strong>' + s.outcome + '</strong>' : 'Pending...')
        + (s.timestamp ? ' · ' + ago(s.timestamp) : '')
        + '</div></div>';
    }).join('');
  }

  if (accData && accData.accuracy && Object.keys(accData.accuracy).length) {
    html += '<div style="margin-top:14px"><div class="tile-label">Model Accuracy</div>';
    for (const asset of Object.keys(accData.accuracy)) {
      const acc = accData.accuracy[asset];
      const w7 = acc['7d'];
      const w30 = acc['30d'];
      const w7t = w7 && w7.total ? fmt(w7.win_rate, 1) + '% (' + w7.correct + '/' + w7.total + ')' : '--';
      const w30t = w30 && w30.total ? fmt(w30.win_rate, 1) + '% (' + w30.correct + '/' + w30.total + ')' : '--';
      html += '<div class="cross-row"><span>' + asset + '</span><span class="mono">7d: ' + w7t + ' · 30d: ' + w30t + '</span></div>';
    }
    html += '</div>';
  }

  if (!html) {
    html = '<div class="empty-state"><span>🤖 ML model needs 2–4 weeks of data.<br><small>Bot is collecting in background.</small></span></div>';
  }
  el.innerHTML = html;
}

async function renderDBStats() {
  const el = document.getElementById('tab-dbstats');
  const data = await api('/api/db-stats');
  if (!data || !data.stats) {
    el.innerHTML = '<div class="empty-state"><span>Cannot load database stats.</span></div>';
    return;
  }
  const s = data.stats;
  const icons = {
    snapshots: '📸', news_items: '📰', whale_transactions: '🐳',
    signals: '🤖', subscribers: '👥', economic_events: '📅',
    cross_exchange_funding: '🔄', db_size_mb: '💾',
  };
  let html = '<table class="stat-table">';
  for (const k of Object.keys(s)) {
    const icon = icons[k] || '📊';
    const label = k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    const val = k === 'db_size_mb' ? s[k] + ' MB' : Number(s[k]).toLocaleString();
    html += '<tr><td>' + icon + ' ' + label + '</td><td>' + val + '</td></tr>';
  }
  html += '</table>';
  el.innerHTML = html;
}

// ===== MAIN UPDATE =====
async function update() {
  console.log('[CrypT] update() called at', new Date().toLocaleTimeString());
  try {
    const data = await api('/api/summary');
    console.log('[CrypT] API response:', data ? 'OK (' + (data.crypto || []).length + ' crypto)' : 'NULL');
    if (!data) {
      const sb = document.getElementById('status-bar');
      if (sb) sb.textContent = '⚠ API unreachable';
      return;
    }

    // Fear & Greed Gauge
    updateFGGauge(data.fear_greed);

    // Status
    const assetCount = data.tracked_assets || 0;
    const lastTime = data.last_update ? new Date(data.last_update * 1000).toLocaleTimeString('en', {
      hour: '2-digit', minute: '2-digit', hour12: false
    }) : '--';
    const sb = document.getElementById('status-bar');
    if (sb) sb.textContent = assetCount + ' assets · Updated ' + lastTime;

    // Render grids
    renderCrypto(data);
    renderForex(data);

    // Tabs data (parallel, non-blocking)
    Promise.all([
      api('/api/news?limit=15'),
      api('/api/whale?hours=48'),
      api('/api/calendar?hours=72'),
    ]).then(([news, whale, cal]) => {
      renderNews(news);
      renderWhale(whale);
      renderCalendar(cal);
    }).catch(e => console.warn('[CrypT] Tab data error:', e));

    renderSignals().catch(e => console.warn('[CrypT] Signals error:', e));
    renderDBStats().catch(e => console.warn('[CrypT] DB stats error:', e));

    console.log('[CrypT] update() completed successfully');
  } catch (e) {
    console.error('[CrypT] Update error:', e);
    const sb = document.getElementById('status-bar');
    if (sb) sb.textContent = '⚠ Update failed';
  }
}

// Initial load
console.log('[CrypT] Dashboard initializing...');
update();
// Auto-refresh every 30s
setInterval(update, 30000);
