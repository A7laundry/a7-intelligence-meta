/**
 * A7 Intelligence Dashboard v2
 * Interactive dashboard with Chart.js and Flask API backend
 */
(function () {
  'use strict';

  let currentRange = document.querySelector('.range-btn.active')?.getAttribute('data-range') || '7d';
  let trendChart = null;

  /* ─── Account Context ─── */
  let currentAccountId = null;

  function getAccountIdFromUrl() {
    return new URLSearchParams(window.location.search).get('account_id');
  }

  function setAccountIdInUrl(id) {
    const params = new URLSearchParams(window.location.search);
    params.set('account_id', id);
    window.history.replaceState({}, '', '?' + params.toString());
  }

  function acctParam() {
    return currentAccountId ? '&account_id=' + currentAccountId : '';
  }

  async function initAccountSelector() {
    try {
      const accounts = await fetchApi('/accounts');
      if (!accounts || accounts.length <= 1) return; // hide if only one account
      const select = $('#accountSelect');
      const wrap = $('#accountSelectorWrap');
      if (!select || !wrap) return;
      select.innerHTML = '';
      accounts.forEach(acc => {
        const opt = document.createElement('option');
        opt.value = acc.id;
        opt.textContent = acc.account_name;
        select.appendChild(opt);
      });
      // Restore from URL or localStorage
      const fromUrl = getAccountIdFromUrl();
      const fromStorage = localStorage.getItem('a7_account_id');
      const initial = fromUrl || fromStorage || (accounts[0] && accounts[0].id);
      if (initial) {
        select.value = initial;
        currentAccountId = parseInt(initial, 10);
      }
      wrap.style.display = 'flex';
      // Update badge for selected account platform
      const selected = accounts.find(a => a.id == currentAccountId);
      if (selected) {
        const badge = $('#accountPlatformBadge');
        if (badge) badge.textContent = selected.platform === 'google' ? 'Google' : 'Meta';
      }
      // Load status pill for initial account
      if (currentAccountId) loadAccountStatus(currentAccountId);
      // Listen for changes
      select.addEventListener('change', function () {
        currentAccountId = parseInt(this.value, 10);
        localStorage.setItem('a7_account_id', currentAccountId);
        setAccountIdInUrl(currentAccountId);
        const acc = accounts.find(a => a.id == currentAccountId);
        if (acc) {
          const badge = $('#accountPlatformBadge');
          if (badge) badge.textContent = acc.platform === 'google' ? 'Google' : 'Meta';
        }
        loadAccountStatus(currentAccountId);
        load(currentRange);
        loadAllSections();
      });
    } catch (e) {
      // silently skip if accounts endpoint unavailable
    }
  }

  function loadAllSections() {
    loadGrowthScore();
    loadBudget();
    loadAlerts();
    loadCoach();
    loadAutomation();
    loadAutoLogs();
    loadCreatives();
    loadAccountOverview();
  }

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  /* ─── Formatters ─── */
  function fmt(n) {
    if (n == null || isNaN(n)) return '\u2014';
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toLocaleString('en-US');
  }
  function fmtMoney(n) {
    if (n == null || isNaN(n)) return '\u2014';
    return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function fmtPct(n) {
    if (n == null || isNaN(n)) return '\u2014';
    return n.toFixed(2) + '%';
  }
  function statusClass(s) {
    s = (s || '').toLowerCase();
    if (s === 'active' || s === 'enabled') return 'status-active';
    if (s === 'paused') return 'status-paused';
    return 'status-removed';
  }
  function changeHtml(pct, invert) {
    if (pct == null || pct === 0) return '<span class="kpi-change neutral">\u2014</span>';
    const isGood = invert ? pct < 0 : pct > 0;
    const cls = isGood ? 'positive' : 'negative';
    const arrow = pct > 0 ? '\u25B2' : '\u25BC';
    return `<span class="kpi-change ${cls}">${arrow} ${Math.abs(pct).toFixed(1)}%</span>`;
  }

  /* ─── API ─── */
  async function fetchApi(path) {
    const resp = await fetch('/api' + path);
    if (!resp.ok) throw new Error(resp.status);
    return resp.json();
  }

  async function postApi(path, body) {
    const resp = await fetch('/api' + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(resp.status);
    return resp.json();
  }

  /* ─── Render KPIs ─── */
  function renderKPIs(data) {
    const t = data.summary.total;
    const m = data.summary.meta;
    const g = data.summary.google;
    const ch = (data.comparison && data.comparison.changes) || {};

    $('#kpiSpend').textContent = fmtMoney(t.spend);
    $('#kpiImpressions').textContent = fmt(t.impressions);
    $('#kpiClicks').textContent = fmt(t.clicks);
    $('#kpiCtr').textContent = fmtPct(t.ctr);
    $('#kpiConversions').textContent = fmt(t.conversions);
    $('#kpiCpa').textContent = fmtMoney(t.cpa);

    // Changes
    $('#kpiSpendChange').innerHTML = changeHtml(ch.spend, true);
    $('#kpiImpressionsChange').innerHTML = changeHtml(ch.impressions);
    $('#kpiClicksChange').innerHTML = changeHtml(ch.clicks);
    $('#kpiCtrChange').innerHTML = '';
    $('#kpiConversionsChange').innerHTML = changeHtml(ch.conversions);
    $('#kpiCpaChange').innerHTML = '';

    // Breakdown
    if ($('#kpiMetaSpend')) {
      $('#kpiMetaSpend').textContent = 'M: ' + fmtMoney(m.spend);
      $('#kpiGoogleSpend').textContent = 'G: ' + fmtMoney(g.spend);
      $('#kpiMetaImpressions').textContent = 'M: ' + fmt(m.impressions);
      $('#kpiGoogleImpressions').textContent = 'G: ' + fmt(g.impressions);
      $('#kpiMetaClicks').textContent = 'M: ' + fmt(m.clicks);
      $('#kpiGoogleClicks').textContent = 'G: ' + fmt(g.clicks);
    }
  }

  /* ─── Render Trend Chart ─── */
  function renderTrendChart(trend) {
    const canvas = $('#trendChart');
    if (!canvas) return;

    if (trendChart) trendChart.destroy();

    const labels = trend.map(d => {
      const parts = d.date.split('-');
      return parts[1] + '/' + parts[2];
    });
    const metaSpend = trend.map(d => d.meta_spend || 0);
    const googleSpend = trend.map(d => d.google_spend || 0);
    const metaConv = trend.map(d => d.meta_conversions || 0);
    const googleConv = trend.map(d => d.google_conversions || 0);

    trendChart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Meta Spend',
            data: metaSpend,
            backgroundColor: 'rgba(37, 99, 235, 0.8)',
            borderRadius: 3,
            order: 2,
          },
          {
            label: 'Google Spend',
            data: googleSpend,
            backgroundColor: 'rgba(245, 158, 11, 0.8)',
            borderRadius: 3,
            order: 3,
          },
          {
            label: 'Meta Conv.',
            data: metaConv,
            type: 'line',
            borderColor: '#2563eb',
            backgroundColor: 'transparent',
            borderWidth: 2,
            pointRadius: 3,
            pointBackgroundColor: '#2563eb',
            yAxisID: 'y1',
            order: 1,
          },
          {
            label: 'Google Conv.',
            data: googleConv,
            type: 'line',
            borderColor: '#f59e0b',
            backgroundColor: 'transparent',
            borderWidth: 2,
            pointRadius: 3,
            pointBackgroundColor: '#f59e0b',
            yAxisID: 'y1',
            order: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'bottom', labels: { usePointStyle: true, padding: 16, font: { size: 11, family: 'Inter' } } },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                if (ctx.dataset.yAxisID === 'y1') return ctx.dataset.label + ': ' + ctx.parsed.y;
                return ctx.dataset.label + ': $' + ctx.parsed.y.toFixed(2);
              }
            }
          }
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 11, family: 'Inter' } } },
          y: {
            position: 'left',
            title: { display: true, text: 'Spend ($)', font: { size: 11, family: 'Inter' } },
            grid: { color: '#f0f0f0' },
            ticks: { font: { size: 11 }, callback: v => '$' + v },
          },
          y1: {
            position: 'right',
            title: { display: true, text: 'Conversions', font: { size: 11, family: 'Inter' } },
            grid: { display: false },
            ticks: { font: { size: 11 }, stepSize: 1 },
          },
        },
      },
    });
  }

  /* ─── Render Campaign Table ─── */
  function renderCampaignTable(campaigns, tbodyId, showActions) {
    const tbody = document.getElementById(tbodyId);
    if (!campaigns || campaigns.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:20px">No campaigns</td></tr>';
      return;
    }
    let html = '';
    campaigns.forEach(c => {
      const sc = statusClass(c.status);
      const isActive = (c.status || '').toUpperCase() === 'ACTIVE';
      html += '<tr>' +
        '<td style="font-weight:600">' + c.name + '</td>' +
        '<td><span class="status-badge ' + sc + '">' + c.status + '</span></td>' +
        '<td>' + fmtMoney(c.spend) + '</td>' +
        '<td>' + fmt(c.clicks) + '</td>' +
        '<td>' + fmtPct(c.ctr) + '</td>' +
        '<td>' + fmt(c.conversions) + '</td>' +
        '<td>' + fmtMoney(c.cpa) + '</td>';
      if (showActions) {
        if (isActive) {
          html += '<td><button class="btn-action pause" onclick="toggleCampaign(\'' + c.id + '\',\'PAUSED\')" title="Pause">&#x23F8;</button></td>';
        } else {
          html += '<td><button class="btn-action activate" onclick="toggleCampaign(\'' + c.id + '\',\'ACTIVE\')" title="Activate">&#x25B6;</button></td>';
        }
      } else {
        html += '<td></td>';
      }
      html += '</tr>';
    });
    tbody.innerHTML = html;
  }

  /* ─── Toggle Campaign Status ─── */
  window.toggleCampaign = async function (campaignId, newStatus) {
    if (!confirm('Change campaign status to ' + newStatus + '?')) return;
    try {
      await postApi('/campaigns/' + campaignId + '/status', { status: newStatus });
      load(currentRange);
    } catch (e) {
      alert('Error: ' + e.message);
    }
  };

  /* ─── Platform Status ─── */
  async function loadPlatformStatus() {
    try {
      const data = await fetchApi('/platforms');
      const el = $('#platformStatus');
      el.innerHTML =
        '<span class="platform-dot ' + (data.meta ? 'connected' : 'disconnected') + '">&#x25CF; Meta</span>' +
        '<span class="platform-dot ' + (data.google ? 'connected' : 'disconnected') + '">&#x25CF; Google</span>';
    } catch (e) { /* ignore */ }
  }

  /* ─── Table Sorting ─── */
  function setupTableSort(tableId, campaigns, tbodyId, showActions) {
    const table = document.getElementById(tableId);
    if (!table) return;
    const headers = table.querySelectorAll('th[data-key]');
    let sortKey = null, sortAsc = true;
    headers.forEach(th => {
      th.addEventListener('click', () => {
        const key = th.getAttribute('data-key');
        if (sortKey === key) { sortAsc = !sortAsc; } else { sortKey = key; sortAsc = true; }
        headers.forEach(h => { h.classList.remove('sorted'); h.querySelector('.sort-arrow').textContent = '\u25B2'; });
        th.classList.add('sorted');
        th.querySelector('.sort-arrow').textContent = sortAsc ? '\u25B2' : '\u25BC';
        const sorted = campaigns.slice().sort((a, b) => {
          const va = a[key], vb = b[key];
          if (typeof va === 'string') return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
          return sortAsc ? (va - vb) : (vb - va);
        });
        renderCampaignTable(sorted, tbodyId, showActions);
      });
    });
  }

  /* ─── Master Render ─── */
  function render(data) {
    // Demo banner
    if (data.demo) { $('#demoBanner').classList.add('visible'); }
    else { $('#demoBanner').classList.remove('visible'); }

    // Hide Google section if no data
    const gs = $('#googleSection');
    if (gs) {
      const hasGoogle = data.campaigns.google && data.campaigns.google.length > 0;
      gs.style.display = hasGoogle ? '' : 'none';
    }

    // Show content
    $('#loadingState').style.display = 'none';
    $('#kpiGrid').style.display = '';
    $('#sectionsContainer').style.display = '';

    renderKPIs(data);
    renderTrendChart(data.daily_trend || []);
    renderCampaignTable(data.campaigns.meta, 'metaTableBody', true);
    renderCampaignTable(data.campaigns.google, 'googleTableBody', false);
    setupTableSort('metaTable', data.campaigns.meta, 'metaTableBody', true);
    setupTableSort('googleTable', data.campaigns.google, 'googleTableBody', false);

    // Footer
    const dt = data.generated_at ? new Date(data.generated_at) : new Date();
    $('#footer').textContent = 'Last updated: ' + dt.toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: 'numeric', minute: '2-digit', hour12: true
    }) + (data.demo ? ' (Demo Data)' : '') + (data.source === 'database' ? ' (Cached)' : '');
  }

  /* ─── Load Data ─── */
  async function load(range) {
    $('#loadingState').style.display = '';
    $('#kpiGrid').style.display = 'none';
    $('#sectionsContainer').style.display = 'none';

    try {
      const data = await fetchApi('/dashboard/' + range + (currentAccountId ? '?account_id=' + currentAccountId : ''));
      render(data);
    } catch (e) {
      $('#loadingState').innerHTML = 'Error loading data. Check if the server is running.';
    }
  }

  /* ─── Range Switcher ─── */
  $$('.range-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.range-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentRange = btn.getAttribute('data-range');
      load(currentRange);
    });
  });

  /* ─── Refresh Button ─── */
  const refreshBtn = $('#btnRefresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', async () => {
      refreshBtn.classList.add('spinning');
      try {
        await postApi('/dashboard/refresh', {});
        await load(currentRange);
      } finally {
        refreshBtn.classList.remove('spinning');
      }
    });
  }

  /* ─── Auto Refresh ─── */
  let autoRefreshTimer = null;
  const AUTO_REFRESH_MS = 5 * 60 * 1000; // 5 minutes

  function startAutoRefresh() {
    stopAutoRefresh();
    autoRefreshTimer = setInterval(() => load(currentRange), AUTO_REFRESH_MS);
  }

  function stopAutoRefresh() {
    if (autoRefreshTimer) {
      clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
    }
  }

  /* ─── Growth Score Strip ─── */
  async function loadGrowthScore() {
    try {
      var data = await fetchApi('/growth-score?days=7' + acctParam());
      var strip = document.getElementById('growthStrip');
      if (!strip) return;
      strip.style.display = '';

      var numEl = document.getElementById('growthScoreNum');
      numEl.textContent = data.score;
      numEl.className = 'growth-score-num ' + (data.label || 'stable');

      var badgeEl = document.getElementById('growthScoreBadge');
      badgeEl.textContent = (data.label || 'unknown').replace('_', ' ');
      badgeEl.className = 'growth-score-badge ' + (data.label || 'stable');

      document.getElementById('growthStripSummary').textContent = data.summary || '';

      // Signals
      var signals = document.getElementById('growthStripSignals');
      var html = '';

      // Critical alerts count
      var alertData = null;
      try { alertData = await fetchApi('/alerts?severity=critical&limit=100' + acctParam()); } catch(e) {}
      var critCount = alertData ? (alertData.alerts || []).length : 0;
      if (critCount > 0) {
        html += '<span class="growth-signal critical">' + critCount + ' Critical Alert' + (critCount > 1 ? 's' : '') + '</span>';
      }

      // Top drivers
      if (data.top_positive_driver) {
        html += '<span class="growth-signal opportunity">' + data.top_positive_driver.component.replace(/_/g, ' ') + ': ' + data.top_positive_driver.score + '</span>';
      }

      signals.innerHTML = html;
    } catch (e) {
      // Growth strip stays hidden
    }
  }

  /* ─── Budget Intelligence ─── */
  let budgetChart = null;

  async function loadBudget() {
    var loading = document.getElementById('budgetLoading');
    var content = document.getElementById('budgetContent');
    var empty = document.getElementById('budgetEmpty');
    if (!loading) return;

    loading.style.display = '';
    content.style.display = 'none';
    empty.style.display = 'none';

    try {
      var data = await fetchApi('/budget/summary?days=7' + acctParam());
      loading.style.display = 'none';

      if (data.error || data.total_spend === 0) {
        empty.style.display = '';
        return;
      }

      content.style.display = '';
      renderBudgetScore(data);
      renderBudgetChart(data);
      renderBudgetLists(data);
    } catch (e) {
      loading.style.display = 'none';
      empty.style.display = '';
    }
  }

  function renderBudgetScore(data) {
    var el = document.getElementById('budgetScoreValue');
    if (!el) return;
    var score = data.efficiency_score || 0;
    el.textContent = score;
    el.className = 'budget-score-value ' +
      (score >= 70 ? 'score-high' : (score >= 40 ? 'score-mid' : 'score-low'));
  }

  function renderBudgetChart(data) {
    var canvas = document.getElementById('budgetChart');
    if (!canvas) return;
    if (budgetChart) budgetChart.destroy();

    var ratios = data.ratios || {};
    budgetChart = new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: ['Efficient', 'Waste', 'Neutral'],
        datasets: [{
          data: [ratios.efficient_pct || 0, ratios.waste_pct || 0, ratios.neutral_pct || 0],
          backgroundColor: ['#10b981', '#ef4444', '#9ca3af'],
          borderWidth: 2,
          borderColor: '#fff',
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '60%',
        plugins: {
          legend: { position: 'right', labels: { font: { size: 11, family: 'Inter' }, padding: 12, usePointStyle: true } },
          tooltip: {
            callbacks: {
              label: function(ctx) { return ctx.label + ': ' + ctx.parsed.toFixed(1) + '%'; }
            }
          }
        }
      }
    });
  }

  function renderBudgetLists(data) {
    var el = document.getElementById('budgetLists');
    if (!el) return;
    var html = '';

    // Waste campaigns
    var waste = data.waste_campaigns || [];
    html += '<div class="budget-list"><div class="budget-list-header waste">Waste Spend ($' +
      (data.waste_spend || 0).toFixed(2) + ')</div>';
    if (waste.length === 0) {
      html += '<div class="budget-list-item" style="color:var(--text-muted)">No waste detected</div>';
    } else {
      waste.forEach(function(w) {
        html += '<div class="budget-list-item">' +
          '<div class="budget-list-item-name">' + w.name + '</div>' +
          '<div class="budget-list-item-spend">$' + (w.spend || 0).toFixed(2) + '</div>' +
          '<div class="budget-list-item-reason">' + (w.reason || '') + '</div>' +
        '</div>';
      });
    }
    html += '</div>';

    // Scaling opportunities
    var opps = data.efficient_campaigns || [];
    html += '<div class="budget-list"><div class="budget-list-header opportunity">Efficient Spend ($' +
      (data.efficient_spend || 0).toFixed(2) + ')</div>';
    if (opps.length === 0) {
      html += '<div class="budget-list-item" style="color:var(--text-muted)">No efficient campaigns yet</div>';
    } else {
      opps.forEach(function(o) {
        html += '<div class="budget-list-item">' +
          '<div class="budget-list-item-name">' + o.name + '</div>' +
          '<div class="budget-list-item-spend">$' + (o.spend || 0).toFixed(2) +
            (o.conversions ? ' | ' + o.conversions + ' conv' : '') + '</div>' +
          '<div class="budget-list-item-reason">' + (o.reason || '') + '</div>' +
        '</div>';
      });
    }
    html += '</div>';

    el.innerHTML = html;
  }

  /* ─── Alerts Center ─── */
  async function loadAlerts() {
    var list = document.getElementById('alertsList');
    var empty = document.getElementById('alertsEmpty');
    if (!list) return;

    try {
      var data = await fetchApi('/alerts?limit=20' + acctParam());
      var alerts = data.alerts || [];
      if (alerts.length === 0) {
        list.innerHTML = '';
        empty.style.display = '';
        return;
      }
      empty.style.display = 'none';
      renderAlerts(list, alerts);
    } catch (e) {
      list.innerHTML = '';
      empty.style.display = '';
    }
  }

  function renderAlerts(container, alerts) {
    var html = '<div class="alerts-list">';
    alerts.forEach(function(a) {
      var ts = a.created_at ? new Date(a.created_at).toLocaleString('en-US', {
        month:'short',day:'numeric',hour:'numeric',minute:'2-digit',hour12:true
      }) : '';
      html += '<div class="alert-card severity-' + a.severity + '">' +
        '<div class="alert-body">' +
          '<div class="alert-header">' +
            '<span class="alert-severity severity-badge-' + a.severity + '">' + a.severity + '</span>' +
            '<span class="alert-title">' + a.title + '</span>' +
          '</div>' +
          '<div class="alert-message">' + a.message + '</div>' +
          '<div class="alert-meta">' + (a.entity_type || '') + ': ' + (a.entity_name || '') + ' | ' + ts + '</div>' +
        '</div>' +
        '<button class="alert-resolve" onclick="resolveAlert(' + a.id + ')" title="Resolve">Resolve</button>' +
      '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  }

  window.resolveAlert = async function(id) {
    try {
      await postApi('/alerts/' + id + '/resolve', {});
      await loadAlerts();
    } catch (e) {
      alert('Error: ' + e.message);
    }
  };

  window.refreshAlerts = async function() {
    try {
      await postApi('/alerts/refresh', {});
      await loadAlerts();
    } catch (e) {
      alert('Error refreshing alerts: ' + e.message);
    }
  };

  /* ─── AI Coach ─── */
  async function loadCoach() {
    const loading = document.getElementById('coachLoading');
    const content = document.getElementById('coachContent');
    const empty = document.getElementById('coachEmpty');
    if (!loading) return;

    loading.style.display = '';
    content.style.display = 'none';
    empty.style.display = 'none';

    try {
      const [briefing, recsData, healthData] = await Promise.all([
        fetchApi('/ai-coach/briefing?days=7' + acctParam()),
        fetchApi('/ai-coach/recommendations?days=7' + acctParam()),
        fetchApi('/ai-coach/health?days=7' + acctParam()),
      ]);

      loading.style.display = 'none';

      if (briefing.error && !briefing.headline) {
        empty.style.display = '';
        return;
      }

      content.style.display = '';
      renderCoachHealth(healthData);
      renderCoachHeadline(briefing);
      renderCoachBullets(briefing.summary_bullets || []);
      renderCoachHighlights(briefing);
      renderCoachRecs(recsData.recommendations || []);
    } catch (e) {
      loading.style.display = 'none';
      empty.style.display = '';
    }
  }

  function renderCoachHealth(h) {
    const badge = document.getElementById('healthBadge');
    const label = document.getElementById('healthLabel');
    const score = document.getElementById('healthScore');
    if (!badge) return;

    badge.textContent = h.score;
    badge.className = 'health-badge ' + (h.label || 'stable');
    label.textContent = (h.label || 'unknown').replace('_', ' ');
    label.className = 'health-label ' + (h.label || 'stable');
    score.textContent = 'Health Score: ' + h.score + '/100';
  }

  function renderCoachHeadline(b) {
    var el = document.getElementById('coachHeadline');
    if (el) el.textContent = b.headline || '';
  }

  function renderCoachBullets(bullets) {
    var el = document.getElementById('coachBullets');
    if (!el) return;
    el.innerHTML = bullets.map(function(b) { return '<li>' + b + '</li>'; }).join('');
  }

  function renderCoachHighlights(b) {
    var el = document.getElementById('coachHighlights');
    if (!el) return;
    var html = '';

    var tc = b.top_campaign;
    if (tc) {
      html += '<div class="coach-highlight-card">' +
        '<div class="coach-highlight-label">Top Campaign</div>' +
        '<div class="coach-highlight-value">' + tc.name + '</div>' +
        '<div class="coach-highlight-sub">' + tc.conversions + ' conv | $' + (tc.cpa || 0).toFixed(2) + ' CPA</div>' +
      '</div>';
    }

    var tr = b.top_creative;
    if (tr) {
      html += '<div class="coach-highlight-card">' +
        '<div class="coach-highlight-label">Top Creative</div>' +
        '<div class="coach-highlight-value">' + tr.name + '</div>' +
        '<div class="coach-highlight-sub">Score: ' + tr.score + '/100 | ' + tr.conversions + ' conv</div>' +
      '</div>';
    }

    var opp = b.top_opportunity;
    if (opp) {
      html += '<div class="coach-highlight-card">' +
        '<div class="coach-highlight-label">Top Opportunity</div>' +
        '<div class="coach-highlight-value">' + opp.title + '</div>' +
        '<div class="coach-highlight-sub">' + (opp.entity_name || '') + '</div>' +
      '</div>';
    }

    var risk = b.top_risk;
    if (risk) {
      html += '<div class="coach-highlight-card">' +
        '<div class="coach-highlight-label">Top Risk</div>' +
        '<div class="coach-highlight-value">' + risk.title + '</div>' +
        '<div class="coach-highlight-sub">' + (risk.entity_name || '') + '</div>' +
      '</div>';
    }

    el.innerHTML = html;
  }

  function renderCoachRecs(recs) {
    var el = document.getElementById('coachRecs');
    if (!el) return;
    if (recs.length === 0) {
      el.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:12px;font-size:13px">No specific recommendations at this time.</div>';
      return;
    }

    // Show max 6 recommendations
    var shown = recs.slice(0, 6);
    var html = '';
    shown.forEach(function(r) {
      html += '<div class="coach-rec-card severity-' + r.severity + '">' +
        '<div class="coach-rec-header">' +
          '<span class="coach-rec-severity severity-badge-' + r.severity + '">' + r.severity + '</span>' +
          '<span class="coach-rec-title">' + r.title + '</span>' +
        '</div>' +
        '<div class="coach-rec-message">' + r.message + '</div>' +
        '<div class="coach-rec-action">' + r.recommendation + '</div>' +
        '<div class="coach-rec-entity">' + (r.entity_type || '') + ': ' + (r.entity_name || '') + '</div>' +
      '</div>';
    });
    el.innerHTML = html;
  }

  window.refreshCoach = async function() {
    try {
      await postApi('/ai-coach/refresh', {});
      await loadCoach();
    } catch (e) {
      alert('Error refreshing AI Coach: ' + e.message);
    }
  };

  /* ─── Forecast Panel ─── */
  async function loadForecast() {
    var loading = document.getElementById('forecastLoading');
    var content = document.getElementById('forecastContent');
    var empty = document.getElementById('forecastEmpty');
    if (!loading) return;

    loading.style.display = '';
    content.style.display = 'none';
    empty.style.display = 'none';

    try {
      var data = await fetchApi('/analytics/forecast?horizon=7' + acctParam());
      loading.style.display = 'none';

      var forecasts = data.forecasts || {};
      var hasData = false;
      for (var k in forecasts) {
        if (forecasts[k].trend_direction !== 'insufficient_data') { hasData = true; break; }
      }

      if (!hasData) {
        empty.style.display = '';
        return;
      }

      content.style.display = '';
      renderForecasts(forecasts);
    } catch (e) {
      loading.style.display = 'none';
      empty.style.display = '';
    }
  }

  function renderForecasts(forecasts) {
    var grid = document.getElementById('forecastGrid');
    if (!grid) return;
    var html = '';
    var metricLabels = { spend: 'Spend', conversions: 'Conversions', cpa: 'CPA', ctr: 'CTR' };
    var metricFormat = {
      spend: function(v) { return fmtMoney(v); },
      conversions: function(v) { return fmt(v); },
      cpa: function(v) { return fmtMoney(v); },
      ctr: function(v) { return fmtPct(v); }
    };

    for (var metric in forecasts) {
      var f = forecasts[metric];
      if (f.trend_direction === 'insufficient_data') continue;

      var label = metricLabels[metric] || metric;
      var formatter = metricFormat[metric] || function(v) { return v; };
      var arrowCls = f.trend_direction;
      var arrow = f.trend_direction === 'rising' ? '\u25B2' : (f.trend_direction === 'falling' ? '\u25BC' : '\u25CF');
      var sentiment = f.trend_sentiment || 'neutral';
      var changePct = f.expected_change_pct || 0;
      var changeStr = (changePct > 0 ? '+' : '') + changePct.toFixed(1) + '%';

      html += '<div class="forecast-card">' +
        '<div class="forecast-card-metric">' + label + ' Forecast (7d)</div>' +
        '<div class="forecast-card-values">' +
          '<span class="forecast-card-current">' + formatter(f.current_value) + '</span>' +
          '<span class="forecast-card-arrow ' + arrowCls + '">' + arrow + '</span>' +
          '<span class="forecast-card-predicted">' + formatter(f.forecast_end_value) + '</span>' +
        '</div>' +
        '<div class="forecast-card-trend ' + sentiment + '">' +
          f.trend_direction.charAt(0).toUpperCase() + f.trend_direction.slice(1) + ' (' + changeStr + ')' +
        '</div>' +
        '<span class="forecast-card-confidence">' + f.confidence + ' confidence</span>' +
      '</div>';
    }
    grid.innerHTML = html;
  }

  /* ─── Executive Reports ─── */
  async function loadReport() {
    var loading = document.getElementById('reportLoading');
    var content = document.getElementById('reportContent');
    var empty = document.getElementById('reportEmpty');
    if (!loading) return;

    loading.style.display = '';
    content.style.display = 'none';
    empty.style.display = 'none';

    try {
      var data = await fetchApi('/reports/latest?days=7' + acctParam());
      loading.style.display = 'none';

      if (!data.sections) {
        empty.style.display = '';
        return;
      }

      content.style.display = '';
      renderReportSummary(data.sections);
      renderReportAlerts(data.sections.alert_summary || {});
    } catch (e) {
      loading.style.display = 'none';
      empty.style.display = '';
    }
  }

  function renderReportSummary(sections) {
    var el = document.getElementById('reportSummary');
    if (!el) return;
    var s = sections.executive_summary || {};
    var gs = sections.growth_score || {};

    var spendChange = s.spend_change_pct || 0;
    var convChange = s.conversion_change_pct || 0;
    var spendCls = spendChange > 0 ? 'negative' : 'positive';
    var convCls = convChange > 0 ? 'positive' : 'negative';

    var html = '';
    html += '<div class="report-stat">' +
      '<div class="report-stat-value">' + fmtMoney(s.total_spend) + '</div>' +
      '<div class="report-stat-label">Total Spend</div>' +
      '<div class="report-stat-change ' + spendCls + '">' + (spendChange > 0 ? '+' : '') + spendChange.toFixed(1) + '% vs prior</div>' +
    '</div>';
    html += '<div class="report-stat">' +
      '<div class="report-stat-value">' + fmt(s.total_conversions) + '</div>' +
      '<div class="report-stat-label">Conversions</div>' +
      '<div class="report-stat-change ' + convCls + '">' + (convChange > 0 ? '+' : '') + convChange.toFixed(1) + '% vs prior</div>' +
    '</div>';
    html += '<div class="report-stat">' +
      '<div class="report-stat-value">' + fmtMoney(s.avg_cpa) + '</div>' +
      '<div class="report-stat-label">Avg CPA</div>' +
    '</div>';
    html += '<div class="report-stat">' +
      '<div class="report-stat-value">' + (gs.score || 0) + '/100</div>' +
      '<div class="report-stat-label">Growth Score (' + (gs.label || 'unknown') + ')</div>' +
    '</div>';

    var tc = sections.top_campaigns || {};
    html += '<div class="report-stat">' +
      '<div class="report-stat-value">' + (tc.total_campaigns || 0) + '</div>' +
      '<div class="report-stat-label">Campaigns Tracked</div>' +
    '</div>';

    var risks = sections.risks || {};
    var opps = sections.opportunities || {};
    html += '<div class="report-stat">' +
      '<div class="report-stat-value">' + (risks.total_risks || 0) + ' / ' + (opps.total_opportunities || 0) + '</div>' +
      '<div class="report-stat-label">Risks / Opportunities</div>' +
    '</div>';

    el.innerHTML = html;
  }

  function renderReportAlerts(alerts) {
    var el = document.getElementById('reportAlerts');
    if (!el) return;
    var total = alerts.unresolved_total || 0;
    var critical = alerts.unresolved_critical || 0;
    var warnings = alerts.unresolved_warnings || 0;

    var html = '';
    html += '<div class="report-alert-card">' +
      '<div class="report-alert-count ' + (critical > 0 ? 'critical' : 'clean') + '">' + critical + '</div>' +
      '<div class="report-alert-label">Critical Alerts</div>' +
    '</div>';
    html += '<div class="report-alert-card">' +
      '<div class="report-alert-count ' + (warnings > 0 ? 'warning' : 'clean') + '">' + warnings + '</div>' +
      '<div class="report-alert-label">Warnings</div>' +
    '</div>';
    html += '<div class="report-alert-card">' +
      '<div class="report-alert-count ' + (total === 0 ? 'clean' : '') + '">' + total + '</div>' +
      '<div class="report-alert-label">Total Unresolved</div>' +
    '</div>';

    el.innerHTML = html;
  }

  /* ─── Cross-Platform Intelligence ─── */
  let spendShareChart = null;

  async function loadCrossPlatform() {
    var loading = document.getElementById('crossPlatformLoading');
    var content = document.getElementById('crossPlatformContent');
    var empty = document.getElementById('crossPlatformEmpty');
    if (!loading) return;

    loading.style.display = '';
    content.style.display = 'none';
    empty.style.display = 'none';

    try {
      var [summaryData, effData, oppsData, shareData] = await Promise.all([
        fetchApi('/platforms/summary?days=7' + acctParam()),
        fetchApi('/platforms/efficiency?days=7' + acctParam()),
        fetchApi('/platforms/opportunities?days=7' + acctParam()),
        fetchApi('/platforms/spend-share?days=7' + acctParam()),
      ]);

      loading.style.display = 'none';

      var activePlatforms = (summaryData.platforms || []).filter(function(p) { return p.spend > 0; });
      if (activePlatforms.length === 0) {
        empty.style.display = '';
        return;
      }

      content.style.display = '';
      renderSpendShareChart(shareData);
      renderPlatformTable(summaryData, effData);
      renderCrossPlatformCards(effData, summaryData);
      renderCrossPlatformOpps(oppsData);
    } catch (e) {
      loading.style.display = 'none';
      empty.style.display = '';
    }
  }

  function renderSpendShareChart(data) {
    var canvas = document.getElementById('spendShareChart');
    if (!canvas) return;
    if (spendShareChart) spendShareChart.destroy();

    var colors = { 'Meta': 'rgba(37, 99, 235, 0.8)', 'Google': 'rgba(245, 158, 11, 0.8)' };
    var labels = data.labels || [];
    var values = data.values || [];
    var bgColors = labels.map(function(l) { return colors[l] || '#9ca3af'; });

    spendShareChart = new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: bgColors,
          borderWidth: 2,
          borderColor: '#fff',
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '55%',
        plugins: {
          legend: { position: 'bottom', labels: { font: { size: 11, family: 'Inter' }, padding: 10, usePointStyle: true } },
          tooltip: {
            callbacks: {
              label: function(ctx) {
                var pcts = data.percentages || [];
                return ctx.label + ': $' + ctx.parsed.toFixed(2) + ' (' + (pcts[ctx.dataIndex] || 0).toFixed(1) + '%)';
              }
            }
          }
        }
      }
    });
  }

  function renderPlatformTable(summary, efficiency) {
    var tbody = document.getElementById('platformTableBody');
    if (!tbody) return;
    var platforms = summary.platforms || [];
    var effMap = {};
    (efficiency.platforms || []).forEach(function(p) { effMap[p.platform] = p; });

    var html = '';
    platforms.forEach(function(p) {
      var eff = effMap[p.platform] || {};
      var effScore = eff.efficiency_score || 0;
      var scoreClass = effScore >= 60 ? 'score-high' : (effScore >= 30 ? 'score-mid' : 'score-low');
      html += '<tr>' +
        '<td style="font-weight:700;text-transform:capitalize">' + p.platform + '</td>' +
        '<td>' + fmtMoney(p.spend) + '</td>' +
        '<td>' + fmt(p.conversions) + '</td>' +
        '<td>' + fmtMoney(p.avg_cpa) + '</td>' +
        '<td>' + fmtPct(p.ctr) + '</td>' +
        '<td><span class="creative-score ' + scoreClass + '">' + effScore + '</span></td>' +
        '<td>' + p.share_of_spend.toFixed(1) + '%</td>' +
      '</tr>';
    });
    tbody.innerHTML = html;
  }

  function renderCrossPlatformCards(efficiency, summary) {
    var el = document.getElementById('crossPlatformCards');
    if (!el) return;
    var html = '';

    // Best Channel card
    var best = efficiency.best_channel;
    if (best) {
      var bestData = (efficiency.platforms || []).find(function(p) { return p.platform === best; });
      html += '<div class="cross-card">' +
        '<div class="cross-card-label">Best Channel</div>' +
        '<div class="cross-card-value" style="text-transform:capitalize">' + best + '</div>' +
        '<div class="cross-card-sub">Efficiency: ' + (bestData ? bestData.efficiency_score : 0) + '/100</div>' +
      '</div>';
    }

    // Total Spend
    html += '<div class="cross-card">' +
      '<div class="cross-card-label">Total Cross-Platform Spend</div>' +
      '<div class="cross-card-value">' + fmtMoney(summary.total_spend) + '</div>' +
      '<div class="cross-card-sub">' + summary.platforms_active + ' platform(s) active</div>' +
    '</div>';

    // Per-platform CPA comparison
    var platforms = summary.platforms || [];
    platforms.forEach(function(p) {
      if (p.spend > 0) {
        html += '<div class="cross-card">' +
          '<div class="cross-card-label" style="text-transform:capitalize">' + p.platform + ' CPA</div>' +
          '<div class="cross-card-value">' + fmtMoney(p.avg_cpa) + '</div>' +
          '<div class="cross-card-sub">' + p.conversions + ' conversions | ' + fmtPct(p.ctr) + ' CTR</div>' +
        '</div>';
      }
    });

    el.innerHTML = html;
  }

  function renderCrossPlatformOpps(data) {
    var el = document.getElementById('crossPlatformOpps');
    if (!el) return;
    var opps = data.opportunities || [];
    if (opps.length === 0) {
      el.innerHTML = '';
      return;
    }
    var html = '';
    opps.forEach(function(o) {
      html += '<div class="cross-opp-card severity-' + (o.severity || 'info') + '">' +
        '<div class="cross-opp-title">' + o.title + '</div>' +
        '<div class="cross-opp-message">' + o.message + '</div>' +
        '<div class="cross-opp-confidence">Confidence: ' + (o.confidence || 'medium') + '</div>' +
      '</div>';
    });
    el.innerHTML = html;
  }

  /* ─── Automation Control Center ─── */
  let currentAutoTab = 'pending';

  async function loadAutomation() {
    var loading = document.getElementById('automationLoading');
    var content = document.getElementById('automationContent');
    var empty = document.getElementById('automationEmpty');
    if (!loading) return;

    loading.style.display = '';
    content.style.display = 'none';
    empty.style.display = 'none';

    try {
      var data = await fetchApi('/automation/actions' + (currentAccountId ? '?account_id=' + currentAccountId : ''));
      loading.style.display = 'none';

      var actions = data.actions || [];
      var summary = data.summary || {};

      if (actions.length === 0 && (summary.total || 0) === 0) {
        empty.style.display = '';
        return;
      }

      content.style.display = '';
      renderAutoSummary(summary);
      renderAutoActions(actions, currentAutoTab);
    } catch (e) {
      loading.style.display = 'none';
      empty.style.display = '';
    }
  }

  function renderAutoSummary(s) {
    var el = document.getElementById('automationSummary');
    if (!el) return;
    var html = '';
    var statuses = ['proposed', 'approved', 'executed', 'rejected'];
    statuses.forEach(function(st) {
      html += '<div class="auto-stat">' +
        '<div class="auto-stat-value ' + st + '">' + (s[st] || 0) + '</div>' +
        '<div class="auto-stat-label">' + st + '</div>' +
      '</div>';
    });
    html += '<div class="auto-stat">' +
      '<div class="auto-stat-value">' + (s.total || 0) + '</div>' +
      '<div class="auto-stat-label">Total</div>' +
    '</div>';
    el.innerHTML = html;
  }

  function renderAutoActions(actions, tab) {
    var el = document.getElementById('automationList');
    if (!el) return;

    if (tab === 'logs') {
      loadAutoLogs();
      return;
    }
    if (tab === 'runs') {
      loadAutoRuns();
      return;
    }

    var filtered = actions.filter(function(a) { return a.status === tab; });
    if (filtered.length === 0) {
      el.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:20px;font-size:13px">No ' + tab + ' actions.</div>';
      return;
    }

    var html = '';
    filtered.forEach(function(a) {
      html += '<div class="auto-action-card">' +
        '<div class="action-info">' +
          '<div class="action-type">' + (a.action_type || '').replace(/_/g, ' ') + '</div>' +
          '<div class="action-entity">' + (a.entity_name || 'Unknown') + '</div>' +
          '<div class="action-reason">' + (a.reason || '') + '</div>' +
          '<div class="action-meta">' +
            '<span class="auto-confidence ' + (a.confidence || 'medium') + '">' + (a.confidence || 'medium') + '</span>' +
            '<span class="auto-status-badge ' + a.status + '">' + a.status + '</span>' +
            (a.suggested_change_pct ? '<span style="font-size:11px;color:var(--text-muted)">' + (a.suggested_change_pct > 0 ? '+' : '') + a.suggested_change_pct + '%</span>' : '') +
          '</div>' +
        '</div>' +
        '<div class="action-buttons">';
      if (a.status === 'proposed') {
        html += '<button class="btn-approve" onclick="approveAction(' + a.id + ')">Approve</button>';
        html += '<button class="btn-reject" onclick="rejectAction(' + a.id + ')">Reject</button>';
      } else if (a.status === 'approved') {
        html += '<button class="btn-execute" onclick="executeAction(' + a.id + ')">Execute</button>';
        html += '<button class="btn-reject" onclick="rejectAction(' + a.id + ')">Reject</button>';
      }
      html += '</div></div>';
    });
    el.innerHTML = html;
  }

  async function loadAutoLogs() {
    var el = document.getElementById('automationList');
    if (!el) return;
    try {
      var data = await fetchApi('/automation/logs?limit=30' + acctParam());
      var logs = data.logs || [];
      if (logs.length === 0) {
        el.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:20px;font-size:13px">No logs yet.</div>';
        return;
      }
      var html = '';
      logs.forEach(function(l) {
        var ts = l.created_at ? new Date(l.created_at).toLocaleString('en-US', {
          month:'short',day:'numeric',hour:'numeric',minute:'2-digit',hour12:true
        }) : '';
        html += '<div class="auto-log-row">' +
          '<span class="log-status ' + (l.status || '') + '">' + (l.status || '') + '</span>' +
          '<span class="log-message">' + (l.message || '') + '</span>' +
          '<span class="log-time">' + ts + '</span>' +
        '</div>';
      });
      el.innerHTML = html;
    } catch (e) {
      el.innerHTML = '<div style="color:var(--text-muted);padding:12px">Error loading logs.</div>';
    }
  }

  async function loadAutoRuns() {
    var el = document.getElementById('automationList');
    if (!el) return;
    try {
      var data = await fetchApi('/automation/runs?limit=20' + acctParam());
      var runs = data.runs || [];
      if (runs.length === 0) {
        el.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:20px;font-size:13px">No automation runs yet. Use <strong>Generate</strong> + <strong>Run</strong> to create a run.</div>';
        return;
      }
      var html = '<div class="auto-runs-list">';
      runs.forEach(function(r) {
        var started = r.started_at ? new Date(r.started_at).toLocaleString('en-US', {
          month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true
        }) : '';
        var duration = '';
        if (r.started_at && r.finished_at) {
          var ms = new Date(r.finished_at) - new Date(r.started_at);
          duration = ms >= 1000 ? (ms / 1000).toFixed(1) + 's' : ms + 'ms';
        }
        html += '<div class="auto-run-row">' +
          '<span class="run-status ' + (r.status || 'running') + '">' + (r.status || 'running') + '</span>' +
          '<span class="run-time">' + started + '</span>' +
          '<div class="run-stats">' +
            '<span>' + (r.proposals_generated || 0) + ' proposed</span>' +
            '<span>' + (r.actions_executed || 0) + ' executed</span>' +
            (r.actions_failed ? '<span class="run-failed">' + r.actions_failed + ' failed</span>' : '') +
          '</div>' +
          (duration ? '<span class="run-duration">' + duration + '</span>' : '') +
        '</div>';
      });
      html += '</div>';
      el.innerHTML = html;
    } catch (e) {
      el.innerHTML = '<div style="color:var(--text-muted);padding:12px">Error loading run history.</div>';
    }
  }

  window.switchAutoTab = function(tab) {
    currentAutoTab = tab;
    document.querySelectorAll('.auto-tab').forEach(function(b) { b.classList.remove('active'); });
    document.querySelector('.auto-tab[data-tab="' + tab + '"]').classList.add('active');
    loadAutomation();
  };

  window.approveAction = async function(id) {
    try {
      await postApi('/automation/' + id + '/approve', {});
      await loadAutomation();
    } catch (e) { alert('Error: ' + e.message); }
  };

  window.rejectAction = async function(id) {
    try {
      await postApi('/automation/' + id + '/reject', {});
      await loadAutomation();
    } catch (e) { alert('Error: ' + e.message); }
  };

  window.executeAction = async function(id) {
    if (!confirm('Execute this automation action?')) return;
    try {
      var result = await postApi('/automation/' + id + '/execute', {});
      alert(result.message || 'Action executed');
      await loadAutomation();
    } catch (e) { alert('Error: ' + e.message); }
  };

  window.generateAutomation = async function() {
    try {
      var result = await postApi('/automation/generate', {});
      alert('Generated ' + (result.queued_count || 0) + ' proposals (' + (result.blocked_count || 0) + ' blocked)');
      await loadAutomation();
    } catch (e) { alert('Error: ' + e.message); }
  };

  window.runAutomation = async function() {
    if (!confirm('Execute all approved automation actions?')) return;
    try {
      // Execute each approved action
      var pending = await fetchApi('/automation/actions?status=approved' + acctParam());
      var actions = pending.actions || [];
      var executed = 0;
      for (var i = 0; i < actions.length; i++) {
        await postApi('/automation/' + actions[i].id + '/execute', {});
        executed++;
      }
      alert('Executed ' + executed + ' actions');
      await loadAutomation();
    } catch (e) { alert('Error: ' + e.message); }
  };

  /* ─── Creative Intelligence ─── */
  async function loadCreatives() {
    try {
      const [summaryData, creativesData] = await Promise.all([
        fetchApi('/creatives/summary?days=7' + acctParam()),
        fetchApi('/creatives?days=7' + acctParam()),
      ]);

      renderCreativeSummary(summaryData);
      renderCreativeGrid(creativesData.creatives || []);
    } catch (e) {
      // Silently handle - creative section shows empty state
      const emptyEl = document.getElementById('creativeEmpty');
      if (emptyEl) emptyEl.style.display = '';
    }
  }

  function renderCreativeSummary(s) {
    const el = document.getElementById('creativeSummary');
    if (!el || s.total_creatives === 0) {
      if (el) el.style.display = 'none';
      const emptyEl = document.getElementById('creativeEmpty');
      if (emptyEl) emptyEl.style.display = '';
      return;
    }

    el.style.display = '';
    document.getElementById('creativeEmpty').style.display = 'none';

    el.innerHTML =
      '<div class="creative-stat"><div class="creative-stat-value">' + s.total_creatives + '</div><div class="creative-stat-label">Total Creatives</div></div>' +
      '<div class="creative-stat"><div class="creative-stat-value">' + s.avg_score + '</div><div class="creative-stat-label">Avg Score</div></div>' +
      '<div class="creative-stat"><div class="creative-stat-value">' + s.fatigued_count + '</div><div class="creative-stat-label">Fatigued</div></div>' +
      '<div class="creative-stat"><div class="creative-stat-value">' + fmtMoney(s.total_spend) + '</div><div class="creative-stat-label">Total Spend</div></div>';
  }

  function renderCreativeGrid(creatives) {
    const grid = document.getElementById('creativeGrid');
    if (!grid || creatives.length === 0) return;

    let html = '';
    creatives.forEach(c => {
      const scoreClass = c.score >= 70 ? 'score-high' : (c.score >= 40 ? 'score-mid' : 'score-low');
      const fatigueClass = 'fatigue-' + c.fatigue_status;
      const thumbHtml = c.thumbnail_url
        ? '<img src="' + c.thumbnail_url + '" alt="' + c.name + '">'
        : '<span>No preview</span>';

      html += '<div class="creative-card">' +
        '<div class="creative-card-thumb">' + thumbHtml + '</div>' +
        '<div class="creative-card-body">' +
          '<div class="creative-card-name">' + c.name + '</div>' +
          '<div class="creative-card-campaign">' + c.campaign + ' &rarr; ' + c.adset + '</div>' +
          '<div class="creative-card-metrics">' +
            '<div class="creative-metric"><div class="creative-metric-value">' + fmtPct(c.ctr) + '</div><div class="creative-metric-label">CTR</div></div>' +
            '<div class="creative-metric"><div class="creative-metric-value">' + c.conversions + '</div><div class="creative-metric-label">Conv</div></div>' +
            '<div class="creative-metric"><div class="creative-metric-value">' + fmtMoney(c.cpa) + '</div><div class="creative-metric-label">CPA</div></div>' +
          '</div>' +
        '</div>' +
        '<div class="creative-card-footer">' +
          '<span class="creative-score ' + scoreClass + '">' + c.score + '/100</span>' +
          '<span class="fatigue-badge ' + fatigueClass + '">' + c.fatigue_status + '</span>' +
        '</div>' +
      '</div>';
    });
    grid.innerHTML = html;
  }

  window.collectCreatives = async function () {
    try {
      await postApi('/creatives/collect', {});
      await loadCreatives();
    } catch (e) {
      alert('Error collecting creatives: ' + e.message);
    }
  };

  /* ─── Cross-Account Overview ─── */
  let accountSpendChart = null;

  async function loadAccountOverview() {
    var section = document.getElementById('crossAccountSection');
    var loading = document.getElementById('crossAccountLoading');
    var content = document.getElementById('crossAccountContent');
    var empty = document.getElementById('crossAccountEmpty');
    if (!section) return;

    try {
      var data = await fetchApi('/accounts/overview?days=7');
      var accounts = data.accounts || [];

      // Show section only when 2+ accounts
      if (accounts.length < 2) {
        section.style.display = 'none';
        return;
      }

      section.style.display = '';
      loading.style.display = 'none';
      content.style.display = '';

      var periodEl = document.getElementById('crossAccountPeriod');
      if (periodEl) periodEl.textContent = 'Last 7 days';

      renderCATotals(data.totals || {});
      renderCAInsights(data.insights || {});
      renderCAChart(data.spend_share || {});
      renderCATable(accounts);
      loadAccountHealth();
    } catch (e) {
      if (section) section.style.display = 'none';
    }
  }

  async function loadAccountHealth() {
    var wrap = document.getElementById('accountHealthWrap');
    var tbody = document.getElementById('accountHealthBody');
    if (!wrap || !tbody) return;
    try {
      var data = await fetchApi('/accounts/health');
      var accounts = data.accounts || [];
      if (accounts.length === 0) return;
      var html = '';
      accounts.forEach(function(a) {
        var scoreClass = a.growth_score >= 70 ? 'good' : a.growth_score >= 40 ? 'mid' : 'bad';
        var alertClass = a.active_alerts > 0 ? 'has-alerts' : '';
        html += '<tr>' +
          '<td><span class="ca-account-name">' + a.account_name + '</span></td>' +
          '<td><span class="health-score-badge ' + scoreClass + '">' + a.growth_score + ' <small>' + a.growth_label + '</small></span></td>' +
          '<td class="' + alertClass + '">' + a.active_alerts + '</td>' +
          '<td>' + fmtMoney(a.spend_last_7_days || 0) + '</td>' +
          '<td>' + fmt(a.conversions_last_7_days || 0) + '</td>' +
          '<td>' + (a.automation_actions_today || 0) + '</td>' +
        '</tr>';
      });
      tbody.innerHTML = html;
      wrap.style.display = '';
    } catch (e) {
      // silently skip if health endpoint unavailable
    }
  }

  function renderCATotals(t) {
    var el = document.getElementById('crossAccountTotals');
    if (!el) return;
    var cards = [
      { label: 'Total Spend',   value: fmtMoney(t.spend || 0) },
      { label: 'Conversions',   value: fmt(t.conversions || 0) },
      { label: 'Avg CPA',       value: fmtMoney(t.cpa || 0) },
      { label: 'Avg CTR',       value: fmtPct(t.ctr || 0) },
      { label: 'Active Alerts', value: t.alerts || 0 },
      { label: 'Accounts',      value: t.accounts || 0 },
    ];
    el.innerHTML = cards.map(function(c) {
      return '<div class="ca-total-card">' +
        '<div class="ca-total-value">' + c.value + '</div>' +
        '<div class="ca-total-label">' + c.label + '</div>' +
      '</div>';
    }).join('');
  }

  function renderCAInsights(ins) {
    var el = document.getElementById('crossAccountInsights');
    if (!el) return;
    var cards = [];
    if (ins.best_performing) {
      cards.push({ type: 'Best Performing', name: ins.best_performing.name,
        reason: ins.best_performing.reason, cls: 'best' });
    }
    if (ins.worst_cpa) {
      cards.push({ type: 'Worst CPA', name: ins.worst_cpa.name,
        reason: ins.worst_cpa.reason, cls: 'worst' });
    }
    if (ins.highest_alerts) {
      cards.push({ type: 'Alert Concentration', name: ins.highest_alerts.name,
        reason: ins.highest_alerts.reason, cls: 'alert' });
    }
    if (ins.opportunity) {
      cards.push({ type: 'Opportunity', name: ins.opportunity.name,
        reason: ins.opportunity.reason, cls: 'opportunity' });
    }
    el.innerHTML = cards.map(function(c) {
      return '<div class="ca-insight-card ' + c.cls + '">' +
        '<div class="ca-insight-type">' + c.type + '</div>' +
        '<div class="ca-insight-name">' + c.name + '</div>' +
        '<div class="ca-insight-reason">' + c.reason + '</div>' +
      '</div>';
    }).join('');
  }

  function renderCAChart(share) {
    var canvas = document.getElementById('accountSpendChart');
    if (!canvas) return;
    if (accountSpendChart) accountSpendChart.destroy();
    var labels = share.labels || [];
    var values = share.values || [];
    var pcts = share.percentages || [];
    var palette = ['#2563eb','#10b981','#f59e0b','#8b5cf6','#ef4444','#06b6d4'];
    var colors = labels.map(function(_, i) { return palette[i % palette.length]; });

    accountSpendChart = new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{ data: values, backgroundColor: colors, borderWidth: 2, borderColor: '#fff' }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '58%',
        plugins: {
          legend: { position: 'bottom', labels: { font: { size: 11, family: 'Inter' }, padding: 10, usePointStyle: true } },
          tooltip: {
            callbacks: {
              label: function(ctx) {
                return ctx.label + ': $' + (ctx.parsed || 0).toFixed(2) + ' (' + (pcts[ctx.dataIndex] || 0) + '%)';
              }
            }
          }
        }
      }
    });
  }

  function renderCATable(accounts) {
    var tbody = document.getElementById('crossAccountTableBody');
    if (!tbody) return;
    var html = '';
    accounts.forEach(function(a) {
      var effCls = a.efficiency_score >= 70 ? 'high' : (a.efficiency_score >= 40 ? 'mid' : 'low');
      var alertCls = a.alerts_count > 0 ? 'has-alerts' : 'no-alerts';
      var platCls = a.platform === 'google' ? 'google' : 'meta';
      html += '<tr>' +
        '<td><div class="ca-account-name">' + a.account_name + '</div>' +
          '<div class="ca-account-link" onclick="switchToAccount(' + a.id + ')">View account &rarr;</div></td>' +
        '<td><span class="ca-platform-badge ' + platCls + '">' + a.platform + '</span></td>' +
        '<td>' + fmtMoney(a.spend) + '</td>' +
        '<td>' + fmt(a.conversions) + '</td>' +
        '<td>' + fmtMoney(a.cpa) + '</td>' +
        '<td>' + fmtPct(a.ctr) + '</td>' +
        '<td><span class="ca-eff-badge ' + effCls + '">' + a.efficiency_score + '</span></td>' +
        '<td><span class="ca-alert-count ' + alertCls + '">' + a.alerts_count + '</span></td>' +
        '<td><span class="ca-growth-badge ' + (a.growth_label || 'unknown') + '">' + (a.growth_label || '—') + '</span></td>' +
      '</tr>';
    });
    tbody.innerHTML = html;
  }

  window.switchToAccount = function(id) {
    currentAccountId = id;
    localStorage.setItem('a7_account_id', id);
    setAccountIdInUrl(id);
    var select = $('#accountSelect');
    if (select) select.value = id;
    load(currentRange);
    loadAllSections();
  };

  /* ─── Account Status Pill ─── */
  async function loadAccountStatus(accountId) {
    if (!accountId) return;
    var pill = document.getElementById('accountStatusPill');
    var dot = document.getElementById('accountStatusDot');
    var text = document.getElementById('accountStatusText');
    if (!pill || !dot || !text) return;
    try {
      var data = await fetchApi('/accounts/' + accountId + '/status');
      var freshness = data.freshness || 'empty';
      dot.className = 'account-status-dot ' + freshness;
      var parts = [];
      if (data.spend_today > 0) parts.push('$' + data.spend_today.toFixed(0) + ' today');
      if (data.alerts_active > 0) parts.push(data.alerts_active + ' alert' + (data.alerts_active !== 1 ? 's' : ''));
      if (data.last_snapshot) parts.push('snap: ' + data.last_snapshot);
      text.textContent = parts.join(' · ');
      pill.style.display = parts.length > 0 ? 'flex' : 'none';
    } catch (e) {
      pill.style.display = 'none';
    }
  }

  /* ─── AI Marketing Copilot ─── */
  (function initCopilot() {
    var history = [];

    // Load suggestion chips
    fetchApi('/copilot/suggestions').then(function(qs) {
      var el = document.getElementById('copilotSuggestions');
      if (!el || !Array.isArray(qs)) return;
      el.innerHTML = qs.map(function(q) {
        return '<button class="copilot-chip" onclick="copilotAskQuestion(' +
          JSON.stringify(q) + ')">' + q + '</button>';
      }).join('');
    }).catch(function() {});

    // Enter key submits
    var input = document.getElementById('copilotInput');
    if (input) {
      input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') copilotAsk();
      });
    }

    window.copilotAskQuestion = function(q) {
      var inp = document.getElementById('copilotInput');
      if (inp) inp.value = q;
      copilotAsk();
    };

    window.copilotAsk = async function() {
      var inp = document.getElementById('copilotInput');
      var btn = document.getElementById('copilotSendBtn');
      if (!inp) return;
      var question = inp.value.trim();
      if (!question) return;

      inp.value = '';
      if (btn) { btn.disabled = true; btn.textContent = '…'; }

      var period = currentRange === 'today' ? 'today' : (currentRange === '30d' ? '30d' : '7d');
      var body = { question: question, period: period };
      if (currentAccountId) body.account_id = currentAccountId;

      // Optimistic: add loading entry
      var entryId = 'cop-' + Date.now();
      _appendCopilotEntry(entryId, question, null);

      try {
        var result = await postApi('/copilot/ask', body);
        _updateCopilotEntry(entryId, result);

        var provEl = document.getElementById('copilotProvider');
        if (provEl && result.provider) {
          provEl.textContent = 'via ' + result.provider.replace('_', ' ');
        }
      } catch (e) {
        _updateCopilotEntry(entryId, {
          answer: 'Error: ' + e.message,
          key_findings: [], suggested_actions: [], confidence: 'low'
        });
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Ask'; }
      }
    };

    function _appendCopilotEntry(id, question, result) {
      var histEl = document.getElementById('copilotHistory');
      if (!histEl) return;
      var div = document.createElement('div');
      div.className = 'copilot-entry';
      div.id = id;
      div.innerHTML = '<div class="cop-question">' + _esc(question) + '</div>' +
        '<div class="cop-answer cop-loading">Thinking…</div>';
      histEl.insertBefore(div, histEl.firstChild);
    }

    function _updateCopilotEntry(id, result) {
      var div = document.getElementById(id);
      if (!div) return;
      var confidence = result.confidence || 'medium';
      var confClass = confidence === 'high' ? 'good' : confidence === 'low' ? 'bad' : 'mid';

      var html = '<div class="cop-answer">' + _md(result.answer || '') + '</div>';

      if ((result.key_findings || []).length) {
        html += '<div class="cop-findings"><strong>Key findings:</strong><ul>' +
          result.key_findings.map(function(f) { return '<li>' + _esc(f) + '</li>'; }).join('') +
          '</ul></div>';
      }
      if ((result.suggested_actions || []).length) {
        html += '<div class="cop-actions"><strong>Suggested actions:</strong><ul>' +
          result.suggested_actions.map(function(a) { return '<li>' + _esc(a) + '</li>'; }).join('') +
          '</ul></div>';
      }
      html += '<div class="cop-meta">' +
        '<span class="cop-confidence ' + confClass + '">' + confidence + ' confidence</span>' +
        (result.sources && result.sources.length
          ? '<span class="cop-sources">Sources: ' + result.sources.join(', ') + '</span>'
          : '') +
      '</div>';

      div.querySelector('.cop-answer').outerHTML = html;

      // Remove old findings/actions if re-rendered
      div.querySelectorAll('.cop-findings, .cop-actions, .cop-meta').forEach(function(el) {
        if (el !== div.querySelector('.cop-meta')) {
          // keep only latest injected block
        }
      });
      // Actually replace entire inner content
      div.innerHTML = '<div class="cop-question">' + div.querySelector('.cop-question').innerHTML + '</div>' + html;
    }

    function _esc(s) {
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    function _md(s) {
      // Minimal markdown: **bold**, bullet lists, newlines
      return _esc(s)
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
    }
  })();

  /* ─── Init ─── */
  loadPlatformStatus();
  initAccountSelector();
  load(currentRange);
  loadGrowthScore();
  loadCoach();
  loadBudget();
  loadAlerts();
  loadForecast();
  loadReport();
  loadCrossPlatform();
  loadAutomation();
  loadCreatives();
  loadAccountOverview();
  startAutoRefresh();

})();
