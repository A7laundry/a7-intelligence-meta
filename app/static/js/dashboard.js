/**
 * A7 Intelligence Dashboard v2
 * Interactive dashboard with Chart.js and Flask API backend
 */
(function () {
  'use strict';

  let currentRange = document.querySelector('.range-btn.active')?.getAttribute('data-range') || '7d';
  let trendChart = null;

  // Command Center chart instances (destroyed/recreated on reload)
  let _ccSpendChart    = null;
  let _ccConvChart     = null;
  let _ccCtrCpcChart   = null;
  let _ccTopCampChart  = null;

  /* ─── Account Context ─── */
  let currentAccountId = null;
  let _accountsCache = [];

  /* ─── Toast Notification System ─── */
  function showToast(message, type) {
    type = type || 'info';
    var icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
    var container = document.getElementById('toastContainer');
    if (!container) return;

    var toast = document.createElement('div');
    toast.className = 'a7-toast ' + type;
    toast.innerHTML =
      '<span class="a7-toast-icon">' + (icons[type] || 'ℹ') + '</span>' +
      '<div class="a7-toast-body">' +
        '<span class="a7-toast-msg">' + String(message).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</span>' +
      '</div>' +
      '<button class="a7-toast-close" aria-label="Close">\u00D7</button>';

    toast.querySelector('.a7-toast-close').addEventListener('click', function() {
      _dismissToast(toast);
    });

    container.appendChild(toast);
    // Force reflow then animate in
    void toast.offsetWidth;
    toast.classList.add('a7-toast-visible');

    var timer = setTimeout(function() { _dismissToast(toast); }, 4000);
    toast._dismissTimer = timer;
  }

  function _dismissToast(toast) {
    if (toast._dismissTimer) clearTimeout(toast._dismissTimer);
    toast.classList.remove('a7-toast-visible');
    setTimeout(function() {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 300);
  }

  /* ─── Button Loading States ─── */
  function setButtonLoading(btn, loading, originalText) {
    if (!btn) return;
    if (loading) {
      btn._originalText = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<span class="btn-spinner"></span>' + (originalText || 'Loading...');
      btn.style.opacity = '0.75';
    } else {
      btn.disabled = false;
      btn.innerHTML = btn._originalText || originalText || btn.innerHTML;
      btn.style.opacity = '';
    }
  }

  /* ─── Number Animation ─── */
  function animateNumber(el, target, suffix, duration) {
    suffix = suffix || '';
    duration = duration || 600;
    var start = 0;
    var startTime = null;
    var isFloat = String(target).indexOf('.') !== -1;

    function step(timestamp) {
      if (!startTime) startTime = timestamp;
      var progress = Math.min((timestamp - startTime) / duration, 1);
      // Ease out cubic
      var eased = 1 - Math.pow(1 - progress, 3);
      var current = start + (target - start) * eased;
      el.textContent = (isFloat ? current.toFixed(2) : Math.floor(current)) + suffix;
      if (progress < 1) requestAnimationFrame(step);
      else el.textContent = target + suffix;
    }
    requestAnimationFrame(step);
  }

  /* ─── Confirmation Modal ─── */
  function confirmAction(message, onConfirm, options) {
    options = options || {};
    var modal = document.getElementById('confirmModal');
    var msgEl = document.getElementById('confirmMsg');
    var titleEl = document.getElementById('confirmTitle');
    var iconEl = document.getElementById('confirmIcon');
    var okBtn = document.getElementById('confirmOk');
    var cancelBtn = document.getElementById('confirmCancel');

    if (!modal) {
      if (window.confirm(message)) onConfirm();
      return;
    }

    if (titleEl) titleEl.textContent = options.title || 'Confirm Action';
    if (msgEl) msgEl.textContent = message;
    if (iconEl) iconEl.textContent = options.icon || '⚠️';
    if (okBtn) okBtn.textContent = options.okLabel || 'Confirm';

    // Destructive actions get red button styling
    if (okBtn) {
      if (options.destructive) {
        okBtn.style.background = 'linear-gradient(135deg, #f43f5e, #e11d48)';
        okBtn.style.boxShadow = '0 2px 8px rgba(244,63,94,.3)';
      } else {
        okBtn.style.background = '';
        okBtn.style.boxShadow = '';
      }
    }

    modal.style.display = 'flex';

    var cleanup = function() {
      modal.style.display = 'none';
      // Clone buttons to remove all listeners
      var newOk = okBtn ? okBtn.cloneNode(true) : null;
      var newCancel = cancelBtn ? cancelBtn.cloneNode(true) : null;
      if (okBtn && newOk) okBtn.parentNode.replaceChild(newOk, okBtn);
      if (cancelBtn && newCancel) cancelBtn.parentNode.replaceChild(newCancel, cancelBtn);
    };

    document.getElementById('confirmOk').addEventListener('click', function() {
      cleanup();
      onConfirm();
    }, { once: true });

    document.getElementById('confirmCancel').addEventListener('click', cleanup, { once: true });

    modal.addEventListener('click', function(e) {
      if (e.target === modal) cleanup();
    }, { once: true });
  }

  /* ─── Tab Cache ─── */
  var _tabCache = {};
  var _tabCacheTTL = 120000; // 2 minutes

  function _isTabCacheValid(tab) {
    return _tabCache[tab] && (Date.now() - _tabCache[tab].loadedAt < _tabCacheTTL);
  }

  function _markTabLoaded(tab) {
    _tabCache[tab] = { loadedAt: Date.now() };
  }

  function _invalidateTabCache(tab) {
    delete _tabCache[tab];
  }

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

  function _showEmptyState(el, reason) {
    if (!el) return;
    var acc = _accountsCache.find(function(a) { return a.id == currentAccountId; });
    var accLabel = acc ? acc.account_name : (currentAccountId ? 'Account #' + currentAccountId : 'All accounts');
    var rangeLabel = {'today': 'Today', '7d': 'Last 7 days', '30d': 'Last 30 days'}[currentRange] || currentRange;
    var hint = reason || 'No data available for this period.';
    el.innerHTML = '<div class="empty-state">' +
      '<p>' + hint + '</p>' +
      '<p class="empty-hint">' + accLabel + ' &bull; ' + rangeLabel + '</p>' +
      '</div>';
    el.style.display = '';
  }

  async function initAccountSelector() {
    try {
      const accounts = await fetchApi('/accounts');
      if (!accounts || accounts.length === 0) return;
      _accountsCache = accounts;
      const select = $('#accountSelect');
      const wrap = $('#accountSelectorWrap');
      if (!select || !wrap) return;

      function _populateSelect(list) {
        select.innerHTML = '';
        list.forEach(acc => {
          const opt = document.createElement('option');
          opt.value = acc.id;
          opt.textContent = acc.account_name;
          select.appendChild(opt);
        });
      }
      _populateSelect(accounts);

      // Restore from URL or localStorage
      const fromUrl = getAccountIdFromUrl();
      const fromStorage = localStorage.getItem('a7_account_id');
      const initial = fromUrl || fromStorage || (accounts[0] && accounts[0].id);
      if (initial) {
        select.value = initial;
        currentAccountId = parseInt(initial, 10);
      }

      if (accounts.length > 1) wrap.style.display = 'flex';

      // Update badge for selected account platform
      const selected = accounts.find(a => a.id == currentAccountId);
      if (selected) {
        const badge = $('#accountPlatformBadge');
        if (badge) badge.textContent = selected.platform === 'google' ? 'Google' : 'Meta';
      }

      // Show search input for 3+ accounts
      if (accounts.length >= 3) {
        var sw = document.getElementById('accountSearchWrap');
        if (sw) sw.classList.add('visible');
        var si = document.getElementById('accountSearchInput');
        if (si) {
          si.addEventListener('input', function() {
            var q = this.value.toLowerCase().trim();
            var filtered = q ? _accountsCache.filter(a => a.account_name.toLowerCase().includes(q)) : _accountsCache;
            _populateSelect(filtered);
            if (filtered.length > 0) {
              select.value = filtered.find(a => a.id == currentAccountId) ? currentAccountId : filtered[0].id;
            }
          });
        }
      }

      // Load context panel for initial account
      if (currentAccountId) loadAccountStatus(currentAccountId);

      // Listen for changes
      select.addEventListener('change', function () {
        currentAccountId = parseInt(this.value, 10);
        localStorage.setItem('a7_account_id', currentAccountId);
        setAccountIdInUrl(currentAccountId);
        const acc = _accountsCache.find(a => a.id == currentAccountId);
        if (acc) {
          const badge = $('#accountPlatformBadge');
          if (badge) badge.textContent = acc.platform === 'google' ? 'Google' : 'Meta';
          showToast('Switched to ' + acc.account_name, 'success');
        }
        // Brief visual transition: dim content area while loading
        document.body.classList.add('a7-account-switching');
        setTimeout(function() { document.body.classList.remove('a7-account-switching'); }, 400);
        loadAccountStatus(currentAccountId);
        load(currentRange);
        loadAllSections();
      });
    } catch (e) {
      // silently skip if accounts endpoint unavailable
    }
  }

  // Alt+A shortcut to focus account search
  document.addEventListener('keydown', function(e) {
    if (e.altKey && (e.key === 'a' || e.key === 'A')) {
      var si = document.getElementById('accountSearchInput');
      if (si && si.offsetParent !== null) { si.focus(); si.select(); e.preventDefault(); }
    }
  });

  function loadAllSections() {
    // Reset lazy-loader cache so account-specific pages reload fresh
    _calledLoaders.clear();
    loadGrowthScore();
    loadBudget();
    loadAlerts();
    loadCoach();
    loadAutomation();
    loadAutoLogs();
    loadCreatives();
    loadAccountOverview();
    // Re-run current page's lazy loaders (e.g. Command Center on overview)
    var activePage = document.querySelector('.page-section.active');
    if (activePage) {
      var pageId = activePage.id.replace('page-', '');
      _runPageLoaders(pageId);
    }
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
  function _animateKpiEl(el, rawValue, formatter) {
    if (!el || rawValue == null || isNaN(rawValue)) {
      if (el) el.textContent = '—';
      return;
    }
    // Use animateNumber for whole integers; set directly for formatted strings
    var num = parseFloat(rawValue);
    if (!isNaN(num)) {
      var isFloat = (num !== Math.floor(num)) || formatter === fmtMoney;
      animateNumber(el, num, '', 600);
      // After animation, set formatted value
      setTimeout(function() { el.textContent = formatter(num); }, 650);
    } else {
      el.textContent = formatter(rawValue);
    }
  }

  function renderKPIs(data) {
    const t = data.summary.total;
    const m = data.summary.meta;
    const g = data.summary.google;
    const ch = (data.comparison && data.comparison.changes) || {};

    _animateKpiEl($('#kpiSpend'),       t.spend,       fmtMoney);
    _animateKpiEl($('#kpiImpressions'), t.impressions, fmt);
    _animateKpiEl($('#kpiClicks'),      t.clicks,      fmt);
    _animateKpiEl($('#kpiCtr'),         t.ctr,         fmtPct);
    _animateKpiEl($('#kpiConversions'), t.conversions, fmt);
    _animateKpiEl($('#kpiCpa'),         t.cpa,         fmtMoney);

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

    // Extended KPIs
    _animateKpiEl($('#kpiRoas'), t.roas, function(v) { return (v || 0).toFixed(2) + 'x'; });
    $('#kpiRoasChange').innerHTML = '';

    const cs = data.campaign_stats || {};
    if ($('#kpiActiveCampaigns')) {
      $('#kpiActiveCampaigns').textContent = cs.active != null ? cs.active : '—';
      $('#kpiCampaignTotal').textContent = cs.total != null ? 'of ' + cs.total + ' total' : '';
    }
    if ($('#kpiTopCampaign')) {
      $('#kpiTopCampaign').textContent = cs.top_campaign || '—';
      $('#kpiWorstCampaign').textContent = cs.worst_campaign && cs.worst_campaign !== '—'
        ? 'Worst CPA: ' + cs.worst_campaign : '';
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
      tbody.innerHTML = '<tr><td colspan="20" style="text-align:center;padding:48px 24px">' +
        '<div style="color:#5d7499;font-size:14px;font-weight:600">No campaigns found.</div>' +
        '<div style="color:#2e4060;font-size:13px;margin-top:6px">Connect a Meta or Google Ads account to see campaigns.</div>' +
        '</td></tr>';
      return;
    }
    var platform = tbodyId === 'googleTableBody' ? 'google' : 'meta';
    let html = '';
    campaigns.forEach(c => {
      const sc = statusClass(c.status);
      const isActive = (c.status || '').toUpperCase() === 'ACTIVE';
      html += '<tr data-campaign-id="' + (c.campaign_id || c.id || '') + '" data-platform="' + platform + '">' +
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

    // Attach drill-down click handlers
    tbody.querySelectorAll('tr[data-campaign-id]').forEach(function(row, idx) {
      row.addEventListener('click', function(e) {
        if (e.target.closest('button')) return; // let action buttons work normally
        var camp = campaigns[idx];
        if (!camp) return;
        document.querySelectorAll('#metaTable tbody tr.selected, #googleTable tbody tr.selected').forEach(function(r) {
          r.classList.remove('selected');
        });
        row.classList.add('selected');
        _openCampaignDrill(camp, platform);
      });
    });
  }

  /* ─── Toggle Campaign Status ─── */
  window.toggleCampaign = function (campaignId, newStatus) {
    var isPause = newStatus === 'PAUSED';
    confirmAction(
      'Change campaign status to ' + newStatus + '?',
      async function() {
        var btn = document.querySelector('[onclick*="toggleCampaign(\'' + campaignId + '\'"]');
        setButtonLoading(btn, true);
        try {
          await postApi('/campaigns/' + campaignId + '/status', { status: newStatus });
          _invalidateTabCache('campaigns');
          load(currentRange);
          showToast('Campaign ' + (isPause ? 'paused' : 'activated'), isPause ? 'warning' : 'success');
        } catch (e) {
          showToast('Error: ' + e.message, 'error');
          setButtonLoading(btn, false);
        }
      },
      { destructive: isPause, title: isPause ? 'Pause Campaign' : 'Activate Campaign' }
    );
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
  /* ─── Data Source Badge ─── */
  function updateDataSourceBadge(data) {
    var badge = document.getElementById('dataSourceBadge');
    var icon = document.getElementById('dataSourceIcon');
    var label = document.getElementById('dataSourceLabel');
    if (!badge) return;

    badge.style.display = 'inline-flex';

    if (data.demo) {
      badge.className = 'data-source-badge demo';
      icon.textContent = '◉';
      label.textContent = 'Demo data';
    } else if (data.source === 'database') {
      badge.className = 'data-source-badge db';
      icon.textContent = '◎';
      label.textContent = 'Snapshot data';
      if (data.generated_at) {
        var ago = _timeAgo(data.generated_at);
        label.textContent = 'Snapshot · ' + ago;
      }
    } else if (data.partial) {
      badge.className = 'data-source-badge partial';
      icon.textContent = '◑';
      label.textContent = 'Partial live data';
    } else {
      badge.className = 'data-source-badge live';
      icon.textContent = '●';
      label.textContent = 'Live data';
    }
  }

  function _timeAgo(isoString) {
    try {
      var then = new Date(isoString);
      var mins = Math.floor((Date.now() - then.getTime()) / 60000);
      if (mins < 2) return 'just now';
      if (mins < 60) return mins + 'm ago';
      var hrs = Math.floor(mins / 60);
      if (hrs < 24) return hrs + 'h ago';
      return Math.floor(hrs / 24) + 'd ago';
    } catch(e) { return ''; }
  }

  function render(data) {
    // Demo banner
    if (data.demo) { $('#demoBanner').classList.add('visible'); }
    else { $('#demoBanner').classList.remove('visible'); }

    updateDataSourceBadge(data);

    // Hide Google section if no data
    const gs = $('#googleSection');
    if (gs) {
      const hasGoogle = data.campaigns.google && data.campaigns.google.length > 0;
      gs.style.display = hasGoogle ? '' : 'none';
    }

    // Show content
    $('#loadingState').style.display = 'none';
    $('#kpiGrid').style.display = '';

    renderKPIs(data);
    renderTrendChart(data.daily_trend || []);
    // Cache campaign data for filter system
    _campData.meta   = data.campaigns.meta   || [];
    _campData.google = data.campaigns.google || [];

    renderCampaignTable(data.campaigns.meta, 'metaTableBody', true);
    renderCampaignTable(data.campaigns.google, 'googleTableBody', false);
    setupTableSort('metaTable', data.campaigns.meta, 'metaTableBody', true);
    setupTableSort('googleTable', data.campaigns.google, 'googleTableBody', false);

    // Init filters + update count
    _initCampaignFilters();
    var countEl = document.getElementById('campFilterCount');
    var total   = _campData.meta.length + _campData.google.length;
    if (countEl) countEl.textContent = total + ' campaign' + (total !== 1 ? 's' : '');

    // Footer
    const dt = data.generated_at ? new Date(data.generated_at) : new Date();
    $('#footer').textContent = 'Last updated: ' + dt.toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: 'numeric', minute: '2-digit', hour12: true
    }) + (data.demo ? ' (Demo Data)' : '') + (data.source === 'database' ? ' (Cached)' : '');
  }

  /* ─── Skeleton Helpers ─── */
  function _showKpiSkeletons() {
    var grid = $('#kpiGrid');
    if (!grid) return;
    var skeletonCard = '<div class="kpi-card" style="pointer-events:none">' +
      '<div class="skeleton skeleton-text" style="width:50%;height:11px;margin-bottom:16px"></div>' +
      '<div class="skeleton" style="width:70%;height:32px;margin-bottom:8px"></div>' +
      '<div class="skeleton skeleton-text" style="width:40%;height:10px"></div>' +
    '</div>';
    grid.innerHTML = skeletonCard.repeat(6);
    grid.style.display = '';
  }

  function _showCoachSkeleton() {
    var loading = document.getElementById('coachLoading');
    if (!loading) return;
    loading.innerHTML =
      '<div class="skeleton skeleton-text" style="width:80%;margin:0 auto 8px"></div>' +
      '<div class="skeleton skeleton-card" style="margin:0 auto;max-width:400px"></div>';
  }

  /* ─── Status Indicator Helpers ─── */
  function _setSysStatus(state) {
    var dot   = document.getElementById('sysDot');
    var label = document.getElementById('sysLabel');
    if (state === 'live') {
      if (dot)   { dot.style.background   = '#10b981'; dot.style.boxShadow = '0 0 6px #10b981'; }
      if (label) { label.textContent = 'Live'; label.style.color = '#10b981'; }
    } else if (state === 'degraded') {
      if (dot)   { dot.style.background   = '#f59e0b'; dot.style.boxShadow = '0 0 6px #f59e0b'; }
      if (label) { label.textContent = 'Degraded'; label.style.color = '#f59e0b'; }
    } else {
      if (dot)   { dot.style.background   = '#5d7499'; dot.style.boxShadow = 'none'; }
      if (label) { label.textContent = 'Offline'; label.style.color = '#5d7499'; }
    }
  }

  /* ─── Load Data ─── */
  async function load(range) {
    $('#loadingState').style.display = '';
    _showKpiSkeletons();

    try {
      const data = await fetchApi('/dashboard/' + range + (currentAccountId ? '?account_id=' + currentAccountId : ''));
      render(data);
      _setSysStatus('live');
    } catch (e) {
      $('#loadingState').innerHTML = 'Error loading data. Check if the server is running.';
      $('#kpiGrid').style.display = 'none';
      _setSysStatus('degraded');
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
        await postApi('/dashboard/refresh' + (currentAccountId ? '?account_id=' + currentAccountId : ''), {});
        await load(currentRange);
        showToast('Data refreshed', 'success');
      } catch (e) {
        showToast('Refresh failed: ' + e.message, 'error');
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
        _showEmptyState(empty, 'No budget data found for this account and period.');
        return;
      }

      content.style.display = '';
      renderBudgetScore(data);
      renderBudgetChart(data);
      renderBudgetLists(data);
      renderBudgetPacing(data);
    } catch (e) {
      loading.style.display = 'none';
      _showEmptyState(empty, 'Could not load budget data.');
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

  function renderBudgetPacing(data) {
    var section = document.getElementById('budgetPacingSection');
    var list    = document.getElementById('budgetPacingList');
    if (!section || !list) return;

    var campaigns = (data.efficient_campaigns || []).concat(data.waste_campaigns || []);
    if (campaigns.length === 0) { section.style.display = 'none'; return; }

    // Build pacing from spend ratio (spend / (spend + remaining_budget))
    // Use total_spend and waste_spend ratios as proxy for pacing where direct data unavailable
    var totalSpend   = data.total_spend   || 0;
    var wasteSpend   = data.waste_spend   || 0;
    var effSpend     = data.efficient_spend || 0;
    var dayOfMonth   = new Date().getDate();
    var daysInMonth  = new Date(new Date().getFullYear(), new Date().getMonth()+1, 0).getDate();
    var expectedPct  = dayOfMonth / daysInMonth;

    var items = [];
    campaigns.slice(0, 6).forEach(function(c) {
      var spend = c.spend || 0;
      if (spend === 0) return;
      // Derive pacing: compare spend ratio to expected monthly percentage
      var spendRatio = totalSpend > 0 ? spend / totalSpend : 0;
      var barPct = Math.min(spendRatio * 100 * (1 / Math.max(expectedPct, 0.01)), 100).toFixed(0);
      var pacingDiff = spendRatio / Math.max(expectedPct, 0.01);
      var statusClass = pacingDiff > 1.2 ? 'overspend' : pacingDiff > 1.05 ? 'ahead' : pacingDiff > 0.9 ? 'on-pace' : 'behind';
      var statusLabel = statusClass === 'overspend' ? 'Over' : statusClass === 'ahead' ? 'Ahead' : statusClass === 'on-pace' ? 'On Pace' : 'Behind';
      items.push(
        '<div class="budget-pacing-item">' +
          '<div class="budget-pacing-name" title="' + c.name + '">' + c.name + '</div>' +
          '<div class="budget-pacing-bar-wrap"><div class="budget-pacing-bar ' + statusClass + '" style="width:' + barPct + '%"></div></div>' +
          '<div class="budget-pacing-val">$' + Number(spend).toFixed(0) + '</div>' +
          '<div class="budget-pacing-status ' + statusClass + '">' + statusLabel + '</div>' +
        '</div>'
      );
    });

    if (items.length === 0) { section.style.display = 'none'; return; }
    list.innerHTML = items.join('');
    section.style.display = '';
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
        _showEmptyState(empty, 'No active alerts. System is operating normally.');
        return;
      }
      if (empty) empty.style.display = 'none';
      renderAlerts(list, alerts);
    } catch (e) {
      list.innerHTML = '';
      _showEmptyState(empty, 'Could not load alerts.');
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
      _invalidateTabCache('alerts');
      await loadAlerts();
    } catch (e) {
      showToast('Error: ' + e.message, 'error');
    }
  };

  window.refreshAlerts = async function() {
    var btn = document.getElementById('btnRefreshAlerts') ||
              document.querySelector('[onclick*="refreshAlerts"]');
    setButtonLoading(btn, true, 'Refreshing...');
    try {
      await postApi('/alerts/refresh' + (currentAccountId ? '?account_id=' + currentAccountId : ''), {});
      _invalidateTabCache('alerts');
      await loadAlerts();
      showToast('Alerts refreshed', 'success');
    } catch (e) {
      showToast('Error refreshing alerts: ' + e.message, 'error');
    } finally {
      setButtonLoading(btn, false);
    }
  };

  /* ─── AI Coach ─── */
  async function loadCoach() {
    const loading = document.getElementById('coachLoading');
    const content = document.getElementById('coachContent');
    const empty = document.getElementById('coachEmpty');
    if (!loading) return;

    loading.style.display = '';
    loading.innerHTML =
      '<div class="skeleton skeleton-text" style="width:70%;margin:0 auto 8px"></div>' +
      '<div class="skeleton skeleton-card" style="margin:0 auto;max-width:500px"></div>' +
      '<div class="skeleton skeleton-card" style="margin:4px auto;max-width:500px"></div>';
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
        _showEmptyState(empty, 'No campaign data available to generate AI insights.');
        return;
      }

      content.style.display = '';
      renderCoachHealth(healthData);
      renderCoachHeadline(briefing);
      renderCoachBullets(briefing.summary_bullets || []);
      // Enrich briefing with risk recs for the risks column
      var allRecs = recsData.recommendations || [];
      var riskRecs = allRecs.filter(function(r) { return r.severity === 'critical' || r.severity === 'warning'; });
      if (!briefing.top_risk && riskRecs.length > 0) briefing.top_risk = riskRecs[0];
      renderCoachHighlights(briefing, riskRecs);
      renderCoachRecs(allRecs);
    } catch (e) {
      loading.style.display = 'none';
      empty.style.display = '';
    }
  }

  function renderCoachHealth(h) {
    var bar = document.getElementById('coachHealthBar');
    if (!bar) return;
    var score = Math.round(h.score || 0);
    var label = (h.label || 'unknown').replace('_', ' ');
    var tier  = score >= 80 ? 'elite' : score >= 65 ? 'strong' : score >= 50 ? 'stable' : score >= 35 ? 'weak' : 'critical';
    var tierLabel = { elite: 'Elite', strong: 'Strong', stable: 'Stable', weak: 'Needs Work', critical: 'Critical' }[tier] || label;
    var pct = Math.min(100, Math.max(0, score));

    bar.innerHTML = [
      '<div class="coach-hb-left">',
        '<div class="coach-hb-score ' + tier + '">' + score + '</div>',
        '<div class="coach-hb-meta">',
          '<div class="coach-hb-tier">' + tierLabel + '</div>',
          '<div class="coach-hb-label">Growth Score</div>',
        '</div>',
      '</div>',
      '<div class="coach-hb-bar-wrap">',
        '<div class="coach-hb-bar"><div class="coach-hb-fill ' + tier + '" style="width:' + pct + '%"></div></div>',
        '<div class="coach-hb-legend">',
          '<span>0</span><span>50</span><span>100</span>',
        '</div>',
      '</div>',
      '<button class="coach-hb-cta" onclick="window.a7Navigate&&window.a7Navigate(\'ai-coach\')">',
        'Full Analysis →',
      '</button>',
    ].join('');
  }

  function renderCoachHeadline(b) {
    var el = document.getElementById('coachHeadline');
    if (el) el.textContent = b.headline || '';
  }

  function renderCoachBullets(bullets) {
    var el = document.getElementById('coachBullets');
    if (!el) return;
    el.innerHTML = bullets.map(function(b) { return '<li>' + _escCC(b) + '</li>'; }).join('');
  }

  function renderCoachHighlights(b, riskRecs) {
    // Opportunities column
    var oppEl = document.getElementById('coachOpportunities');
    // Risks column
    var riskEl = document.getElementById('coachRisks');

    if (oppEl) {
      var oppHtml = '';
      var tc = b.top_campaign;
      if (tc) {
        oppHtml += '<div class="coach-intel-item opp" onclick="window.a7Navigate&&window.a7Navigate(\'campaigns\')">' +
          '<div class="coach-intel-item-icon">◫</div>' +
          '<div class="coach-intel-item-body">' +
            '<div class="coach-intel-item-title">' + _escCC(tc.name || '') + '</div>' +
            '<div class="coach-intel-item-sub">Top campaign · ' + (tc.conversions || 0) + ' conv · $' + (tc.cpa || 0).toFixed(2) + ' CPA</div>' +
          '</div>' +
          '<div class="coach-intel-item-arrow">›</div>' +
        '</div>';
      }
      var opp = b.top_opportunity;
      if (opp) {
        oppHtml += '<div class="coach-intel-item opp" onclick="window.a7Navigate&&window.a7Navigate(\'budget\')">' +
          '<div class="coach-intel-item-icon">◈</div>' +
          '<div class="coach-intel-item-body">' +
            '<div class="coach-intel-item-title">' + _escCC(opp.title || '') + '</div>' +
            '<div class="coach-intel-item-sub">' + _escCC(opp.entity_name || '') + '</div>' +
          '</div>' +
          '<div class="coach-intel-item-arrow">›</div>' +
        '</div>';
      }
      var tr = b.top_creative;
      if (tr) {
        oppHtml += '<div class="coach-intel-item opp" onclick="window.a7Navigate&&window.a7Navigate(\'creative\')">' +
          '<div class="coach-intel-item-icon">◱</div>' +
          '<div class="coach-intel-item-body">' +
            '<div class="coach-intel-item-title">' + _escCC(tr.name || '') + '</div>' +
            '<div class="coach-intel-item-sub">Top creative · Score: ' + (tr.score || 0) + '/100</div>' +
          '</div>' +
          '<div class="coach-intel-item-arrow">›</div>' +
        '</div>';
      }
      if (!oppHtml) oppHtml = '<div class="coach-intel-empty">No opportunities detected yet.</div>';
      oppEl.innerHTML = oppHtml;
    }

    if (riskEl) {
      var riskHtml = '';
      // Show top_risk from briefing + up to 2 more from riskRecs
      var riskList = [];
      if (b.top_risk) riskList.push(b.top_risk);
      if (riskRecs) {
        riskRecs.forEach(function(r) {
          if (riskList.length < 3 && (!b.top_risk || r.title !== b.top_risk.title)) riskList.push(r);
        });
      }
      riskList.forEach(function(risk) {
        var sev = risk.severity || 'warning';
        var destR = risk.entity_type ? ({'campaign': 'campaigns', 'creative': 'creative'}[risk.entity_type.toLowerCase()] || 'alerts') : 'alerts';
        riskHtml += '<div class="coach-intel-item risk sev-' + _escCC(sev) + '" onclick="window.a7Navigate&&window.a7Navigate(\'' + _escCC(destR) + '\')">' +
          '<div class="coach-intel-item-icon">◬</div>' +
          '<div class="coach-intel-item-body">' +
            '<div class="coach-intel-item-title">' + _escCC(risk.title || '') + '</div>' +
            '<div class="coach-intel-item-sub">' + _escCC(risk.entity_name || risk.message || '') + '</div>' +
          '</div>' +
          '<span class="coach-intel-sev-badge ' + _escCC(sev) + '">' + _escCC(sev) + '</span>' +
        '</div>';
      });
      if (!riskHtml) riskHtml = '<div class="coach-intel-empty">✓ No critical risks detected.</div>';
      riskEl.innerHTML = riskHtml;
    }
  }

  function renderCoachRecs(recs) {
    var el = document.getElementById('coachRecs');
    if (!el) return;
    if (recs.length === 0) {
      el.innerHTML = '<div class="coach-recs-empty">No specific recommendations at this time.</div>';
      return;
    }

    var destMap = {
      campaign:  'campaigns',
      creative:  'creative',
      budget:    'budget',
      alert:     'alerts',
      automation: 'automation',
    };

    var shown = recs.slice(0, 6);
    var html = '';
    shown.forEach(function(r) {
      var conf = (r.metrics && r.metrics.confidence) ? r.metrics.confidence : null;
      var dest = destMap[(r.entity_type || '').toLowerCase()] || 'ai-coach';
      var confHtml = conf
        ? '<span class="coach-rec-conf conf-' + _escCC(conf) + '">' + _escCC(conf) + ' confidence</span>'
        : '';
      var entityHtml = r.entity_name
        ? '<div class="coach-rec-entity">' + _escCC(r.entity_type || '') + ': <strong>' + _escCC(r.entity_name) + '</strong></div>'
        : '';
      html += [
        '<div class="coach-rec-card severity-' + _escCC(r.severity) + '">',
          '<div class="coach-rec-header">',
            '<span class="coach-rec-severity severity-badge-' + _escCC(r.severity) + '">' + _escCC(r.severity) + '</span>',
            '<span class="coach-rec-title">' + _escCC(r.title) + '</span>',
            confHtml,
          '</div>',
          '<div class="coach-rec-message">' + _escCC(r.message) + '</div>',
          '<div class="coach-rec-action">' + _escCC(r.recommendation) + '</div>',
          entityHtml,
          '<button class="coach-rec-nav-btn" onclick="window.a7Navigate&&window.a7Navigate(\'' + _escCC(dest) + '\')">',
            'Open ' + _escCC(dest.replace('-', ' ').replace(/\b\w/g, function(c){ return c.toUpperCase(); })) + ' →',
          '</button>',
        '</div>',
      ].join('');
    });
    el.innerHTML = html;
  }

  window.refreshCoach = async function() {
    var btn = document.getElementById('btnRefreshCoach') ||
              document.querySelector('[onclick*="refreshCoach"]');
    setButtonLoading(btn, true, 'Refreshing...');
    try {
      await postApi('/ai-coach/refresh' + (currentAccountId ? '?account_id=' + currentAccountId : ''), {});
      _invalidateTabCache('coach');
      await loadCoach();
      showToast('AI Coach refreshed', 'success');
    } catch (e) {
      showToast('Error refreshing AI Coach: ' + e.message, 'error');
    } finally {
      setButtonLoading(btn, false);
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
        _showEmptyState(empty, 'Not enough historical data to generate forecasts. Run more campaigns and check back later.');
        return;
      }

      content.style.display = '';
      renderForecasts(forecasts);
    } catch (e) {
      loading.style.display = 'none';
      _showEmptyState(empty, 'Could not load forecast data.');
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

    // Also populate the top stats bar
    var bar = document.getElementById('autoStatsBar');
    if (bar) {
      var pending  = document.getElementById('autoStPending');
      var approved = document.getElementById('autoStApproved');
      var executed = document.getElementById('autoStExecuted');
      var failed   = document.getElementById('autoStFailed');
      if (pending)  pending.textContent  = s.proposed  || 0;
      if (approved) approved.textContent = s.approved  || 0;
      if (executed) executed.textContent = s.executed  || 0;
      if (failed)   failed.textContent   = s.failed    || 0;
      bar.style.display = '';
    }
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
      _invalidateTabCache('automation');
      await loadAutomation();
      showToast('Action approved', 'success');
    } catch (e) { showToast('Error: ' + e.message, 'error'); }
  };

  window.rejectAction = async function(id) {
    try {
      await postApi('/automation/' + id + '/reject', {});
      _invalidateTabCache('automation');
      await loadAutomation();
      showToast('Action rejected', 'info');
    } catch (e) { showToast('Error: ' + e.message, 'error'); }
  };

  window.executeAction = function(id) {
    confirmAction(
      'Execute this automation action? This will apply real changes to the campaign.',
      async function() {
        try {
          var result = await postApi('/automation/' + id + '/execute', {});
          showToast(result.message || 'Action executed', 'success');
          _invalidateTabCache('automation');
          await loadAutomation();
        } catch (e) { showToast('Error: ' + e.message, 'error'); }
      },
      { destructive: true, title: 'Execute Action', okLabel: 'Execute' }
    );
  };

  window.generateAutomation = async function() {
    var btn = document.getElementById('btnGenerateAutomation') ||
              document.querySelector('[onclick*="generateAutomation"]');
    setButtonLoading(btn, true, 'Generating...');
    try {
      var result = await postApi('/automation/generate', {});
      showToast('Generated ' + (result.queued_count || 0) + ' proposals (' + (result.blocked_count || 0) + ' blocked)', 'info');
      _invalidateTabCache('automation');
      await loadAutomation();
    } catch (e) { showToast('Error: ' + e.message, 'error'); }
    finally { setButtonLoading(btn, false); }
  };

  window.runAutomation = function() {
    confirmAction(
      'Execute all approved automation actions? This will apply real changes to your campaigns.',
      async function() {
        try {
          // Execute each approved action
          var pending = await fetchApi('/automation/actions?status=approved' + acctParam());
          var actions = pending.actions || [];
          var executed = 0;
          for (var i = 0; i < actions.length; i++) {
            await postApi('/automation/' + actions[i].id + '/execute', {});
            executed++;
          }
          showToast('Executed ' + executed + ' actions', 'success');
          _invalidateTabCache('automation');
          await loadAutomation();
        } catch (e) { showToast('Error: ' + e.message, 'error'); }
      },
      { destructive: true, title: 'Run All Automation', okLabel: 'Run All' }
    );
  };

  /* ─── Creative Intelligence ─── */
  async function loadCreatives() {
    var emptyEl = document.getElementById('creativeEmpty');
    try {
      const [summaryData, creativesData] = await Promise.all([
        fetchApi('/creatives/summary?days=7' + acctParam()),
        fetchApi('/creatives?days=7' + acctParam()),
      ]);
      _creativeData = creativesData.creatives || [];
      renderCreativeHero(summaryData, _creativeData);
      _applyCreativeFilter('all');
      _initCreativeFilters();
    } catch (e) {
      _showEmptyState(emptyEl, 'Could not load creative data.');
    }
  }

  function renderCreativeHero(summary, creatives) {
    var heroEl  = document.getElementById('creativeHero');
    var emptyEl = document.getElementById('creativeEmpty');
    var gridEl  = document.getElementById('creativeGrid');
    var noResEl = document.getElementById('creativeNoResults');

    if (!summary || summary.total_creatives === 0) {
      if (heroEl)  heroEl.style.display  = 'none';
      _showEmptyState(emptyEl, 'No creatives found for this account and period.');
      if (gridEl)  gridEl.innerHTML      = '';
      if (noResEl) noResEl.style.display = 'none';
      return;
    }
    if (emptyEl) emptyEl.style.display = 'none';
    if (!heroEl)  return;
    heroEl.style.display = '';

    // ── Stats strip ──────────────────────────────────────────────────────────
    var warnClass = summary.fatigued_count > 0 ? ' cre-hero-stat-warn' : '';
    var statsHtml =
      '<div class="cre-hero-stats">' +
        '<div class="cre-hero-stat"><div class="cre-hero-stat-val">' + summary.total_creatives + '</div><div class="cre-hero-stat-lbl">Total</div></div>' +
        '<div class="cre-hero-stat"><div class="cre-hero-stat-val">' + (summary.active_creatives || 0) + '</div><div class="cre-hero-stat-lbl">Active</div></div>' +
        '<div class="cre-hero-stat"><div class="cre-hero-stat-val">' + summary.avg_score + '</div><div class="cre-hero-stat-lbl">Avg Score</div></div>' +
        '<div class="cre-hero-stat' + warnClass + '"><div class="cre-hero-stat-val">' + summary.fatigued_count + '</div><div class="cre-hero-stat-lbl">Fatigued</div></div>' +
      '</div>';

    // ── Top creative spotlight ────────────────────────────────────────────────
    var spotlightsHtml = '';
    var top = summary.top_performer;
    if (top) {
      var thumb = top.thumbnail_url
        ? '<img src="' + _escCC(top.thumbnail_url) + '" class="cre-hero-thumb" loading="lazy" onerror="this.style.display=\'none\'">'
        : '<div class="cre-hero-thumb cre-hero-thumb-empty">◻</div>';
      var sc = top.score >= 70 ? 'score-high' : (top.score >= 40 ? 'score-mid' : 'score-low');
      spotlightsHtml +=
        '<div class="cre-hero-spotlight">' +
          '<div class="cre-hero-spotlight-label cre-label-top">★ Top Creative</div>' +
          '<div class="cre-hero-spotlight-inner">' +
            thumb +
            '<div class="cre-hero-spotlight-meta">' +
              '<div class="cre-hero-spotlight-name" title="' + _escCC(top.name || '') + '">' + _escCC(top.name || 'Untitled') + '</div>' +
              '<div class="cre-hero-spotlight-camp">' + _escCC(top.campaign || '') + '</div>' +
              '<div class="cre-hero-spotlight-metrics">' +
                '<span>CTR ' + fmtPct(top.ctr) + '</span>' +
                '<span>Conv. ' + fmt(top.conversions) + '</span>' +
                '<span class="creative-score ' + sc + '">' + top.score + '/100</span>' +
              '</div>' +
            '</div>' +
          '</div>' +
        '</div>';
    }

    // ── Most fatigued ─────────────────────────────────────────────────────────
    var worst = creatives
      .filter(function(c) { return c.fatigue_status === 'fatigued' || c.fatigue_status === 'critical'; })
      .sort(function(a, b) { return (b.frequency || 0) - (a.frequency || 0); })[0];
    if (worst) {
      var fsc = 'fatigue-' + worst.fatigue_status;
      spotlightsHtml +=
        '<div class="cre-hero-spotlight">' +
          '<div class="cre-hero-spotlight-label cre-label-fatigue">⚠ Most Fatigued</div>' +
          '<div class="cre-hero-spotlight-inner">' +
            (worst.thumbnail_url
              ? '<img src="' + _escCC(worst.thumbnail_url) + '" class="cre-hero-thumb" loading="lazy" onerror="this.style.display=\'none\'">'
              : '<div class="cre-hero-thumb cre-hero-thumb-empty">◻</div>') +
            '<div class="cre-hero-spotlight-meta">' +
              '<div class="cre-hero-spotlight-name">' + _escCC(worst.name || 'Untitled') + '</div>' +
              '<div class="cre-hero-spotlight-camp">' + _escCC(worst.campaign || '') + '</div>' +
              '<div class="cre-hero-spotlight-metrics">' +
                '<span>Frequency ' + (worst.frequency || 0).toFixed(1) + 'x</span>' +
                '<span class="fatigue-badge ' + fsc + '">' + worst.fatigue_status + '</span>' +
              '</div>' +
            '</div>' +
          '</div>' +
        '</div>';
    }

    heroEl.innerHTML = statsHtml + (spotlightsHtml ? '<div class="cre-hero-spotlights">' + spotlightsHtml + '</div>' : '');
  }

  function renderCreativeGrid(creatives) {
    var grid = document.getElementById('creativeGrid');
    if (!grid) return;
    if (!creatives || creatives.length === 0) {
      grid.innerHTML = '';
      return;
    }
    var html = '';
    creatives.forEach(function(c) {
      var scoreClass  = c.score >= 70 ? 'score-high' : (c.score >= 40 ? 'score-mid' : 'score-low');
      var showFatigue = c.fatigue_status && c.fatigue_status !== 'healthy';
      var thumb = c.thumbnail_url
        ? '<img src="' + _escCC(c.thumbnail_url) + '" alt="" loading="lazy" onerror="this.parentNode.classList.add(\'cre-no-thumb\')">'
        : '';
      var stBadge = '<span class="status-badge ' + statusClass(c.status) + ' cre-status-overlay">' + (c.status || 'UNKNOWN') + '</span>';
      var campLine = _escCC(c.campaign || '—') + (c.adset ? ' <span class="cre-adset-sep">›</span> ' + _escCC(c.adset) : '');

      html +=
        '<div class="creative-card">' +
          '<div class="creative-card-thumb">' + thumb + stBadge + '</div>' +
          '<div class="creative-card-body">' +
            '<div class="creative-card-name" title="' + _escCC(c.name || '') + '">' + _escCC(c.name || 'Untitled') + '</div>' +
            '<div class="creative-card-campaign">' + campLine + '</div>' +
            '<div class="creative-card-metrics">' +
              '<div class="creative-metric"><div class="creative-metric-value">' + fmtPct(c.ctr) + '</div><div class="creative-metric-label">CTR</div></div>' +
              '<div class="creative-metric"><div class="creative-metric-value">' + fmt(c.conversions) + '</div><div class="creative-metric-label">Conv.</div></div>' +
              '<div class="creative-metric"><div class="creative-metric-value">' + fmtMoney(c.cpa) + '</div><div class="creative-metric-label">CPA</div></div>' +
            '</div>' +
          '</div>' +
          '<div class="creative-card-footer">' +
            '<span class="creative-score ' + scoreClass + '">' + c.score + '/100</span>' +
            (showFatigue ? '<span class="fatigue-badge fatigue-' + c.fatigue_status + '">' + c.fatigue_status + '</span>' : '') +
          '</div>' +
          '<div class="creative-card-actions">' +
            '<button class="cre-action-btn" onclick="window.a7Navigate(\'campaigns\')" title="View campaign">Campaign</button>' +
            '<button class="cre-action-btn" onclick="window.a7Navigate(\'content-studio\')" title="Send to Content Studio">Content Studio</button>' +
          '</div>' +
        '</div>';
    });
    grid.innerHTML = html;
  }

  function _initCreativeFilters() {
    var group = document.getElementById('creativeStatusFilter');
    if (!group || group.dataset.initialized) return;
    group.dataset.initialized = '1';
    group.querySelectorAll('[data-cre-filter]').forEach(function(btn) {
      btn.addEventListener('click', function() {
        group.querySelectorAll('[data-cre-filter]').forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
        _applyCreativeFilter(btn.getAttribute('data-cre-filter'));
      });
    });
  }

  function _applyCreativeFilter(filter) {
    var filtered;
    if (filter === 'active') {
      filtered = _creativeData.filter(function(c) { return (c.status || '').toUpperCase() === 'ACTIVE'; });
    } else if (filter === 'fatigue') {
      filtered = _creativeData.filter(function(c) { return c.fatigue_status && c.fatigue_status !== 'healthy'; });
    } else if (filter === 'top') {
      filtered = _creativeData.filter(function(c) { return c.score >= 70; });
      // Fallback: show top 20% if nothing scores ≥70
      if (filtered.length === 0 && _creativeData.length > 0) {
        var sorted = _creativeData.slice().sort(function(a, b) { return b.score - a.score; });
        filtered   = sorted.slice(0, Math.max(1, Math.ceil(sorted.length * 0.2)));
      }
    } else {
      filtered = _creativeData;
    }

    var countEl = document.getElementById('creativeFilterCount');
    if (countEl) countEl.textContent = filtered.length + ' creative' + (filtered.length !== 1 ? 's' : '');

    var noResEl = document.getElementById('creativeNoResults');
    if (filtered.length === 0) {
      renderCreativeGrid([]);
      if (noResEl) {
        var msgs = {
          active:  { icon: '◻', title: 'No Active Creatives',    hint: 'All creatives appear to be paused or archived.' },
          fatigue: { icon: '✓', title: 'No Fatigue Signals',      hint: 'All creatives look healthy — no frequency or CTR-decline warnings.' },
          top:     { icon: '◎', title: 'No Top Performers Yet',   hint: 'Keep running campaigns to build score data. Creatives scoring 70+ appear here.' },
        };
        var m = msgs[filter] || { icon: '◎', title: 'No Creatives Found', hint: '' };
        noResEl.innerHTML =
          '<div class="cre-no-results-icon">' + m.icon + '</div>' +
          '<div class="cre-no-results-title">' + m.title + '</div>' +
          (m.hint ? '<div class="cre-no-results-hint">' + m.hint + '</div>' : '');
        noResEl.style.display = '';
      }
    } else {
      if (noResEl) noResEl.style.display = 'none';
      renderCreativeGrid(filtered);
    }
  }

  window.collectCreatives = async function () {
    var btn = document.getElementById('btnCollectCreatives') ||
              document.querySelector('[onclick*="collectCreatives"]');
    setButtonLoading(btn, true, 'Syncing...');
    try {
      await postApi('/creatives/collect' + (currentAccountId ? '?account_id=' + currentAccountId : ''), {});
      _invalidateTabCache('creatives');
      await loadCreatives();
      showToast('Creatives synced', 'success');
    } catch (e) {
      showToast('Error collecting creatives: ' + e.message, 'error');
    } finally {
      setButtonLoading(btn, false);
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

      // With sidebar navigation, the page handles visibility.
      // Show empty state for single account, full content for 2+.
      if (accounts.length < 2) {
        loading.style.display = 'none';
        if (empty) empty.style.display = '';
        return;
      }

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
      if (loading) loading.style.display = 'none';
      if (empty) empty.style.display = '';
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
        var score = a.growth_score || 0;
        var ac = a.active_alerts || 0;
        var healthRowCls = (score < 40 || ac > 5) ? 'ca-health-red'
                         : (score >= 70 && ac <= 1) ? 'ca-health-green'
                         : 'ca-health-yellow';
        html += '<tr class="' + healthRowCls + '">' +
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

    // Identify best performer (highest growth_score) and highest alert account
    var bestId = null, alertId = null, maxScore = -1, maxAlerts = -1;
    accounts.forEach(function(a) {
      if ((a.growth_score || 0) > maxScore) { maxScore = a.growth_score || 0; bestId = a.id; }
      if ((a.alerts_count || 0) > maxAlerts) { maxAlerts = a.alerts_count || 0; alertId = a.id; }
    });

    var html = '';
    accounts.forEach(function(a) {
      var effCls = a.efficiency_score >= 70 ? 'high' : (a.efficiency_score >= 40 ? 'mid' : 'low');
      var alertCls = a.alerts_count > 0 ? 'has-alerts' : 'no-alerts';
      var platCls = a.platform === 'google' ? 'google' : 'meta';

      // Health color class: red > yellow > green (risk takes priority)
      var score = a.growth_score || 0;
      var ac = a.alerts_count || 0;
      var healthCls = (score < 40 || ac > 5) ? 'ca-health-red'
                    : (score >= 70 && ac <= 1) ? 'ca-health-green'
                    : 'ca-health-yellow';

      // Border highlight: red (most alerts) takes priority over green (best score)
      var borderStyle = '';
      if (a.id === alertId && maxAlerts > 0) borderStyle = ' ca-row-risky';
      else if (a.id === bestId) borderStyle = ' ca-row-best';

      html += '<tr class="' + healthCls + borderStyle + '">' +
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

  /* ─── Account Context Panel ─── */
  async function loadAccountStatus(accountId) {
    if (!accountId) return;
    var panel = document.getElementById('accountContextPanel');
    try {
      var data = await fetchApi('/accounts/' + accountId + '/status');
      if (panel) {
        var syncEl   = document.getElementById('acpSync');
        var spendEl  = document.getElementById('acpSpend');
        var alertsEl = document.getElementById('acpAlerts');
        if (syncEl)  syncEl.textContent  = data.last_sync ? 'Sync: ' + data.last_sync : 'No sync';
        if (spendEl) spendEl.textContent = data.spend_today > 0
          ? '$' + Number(data.spend_today).toFixed(0) + ' today'
          : '$0 today';
        var ac = data.alerts_count || data.alerts_active || 0;
        if (alertsEl) {
          alertsEl.textContent = ac > 0
            ? ac + ' alert' + (ac !== 1 ? 's' : '')
            : '0 alerts';
          alertsEl.className = 'acp-alerts' + (ac > 0 ? '' : ' none');
        }
        panel.style.display = 'flex';
      }
      renderAccountSummaryCards(data);
    } catch (e) {
      if (panel) panel.style.display = 'none';
    }
  }

  function renderAccountSummaryCards(data) {
    var wrap = document.getElementById('accountSummaryCards');
    if (!wrap) return;
    var spendToday = data.spend_today || 0;
    var convToday  = data.conversions_today || 0;
    var spend7d    = data.spend_7d || 0;
    var cpaToday   = (spendToday > 0 && convToday > 0) ? spendToday / convToday : 0;
    var cards = [
      { label: 'Spend Today',        value: fmtMoney(spendToday) },
      { label: 'Conversions Today',  value: fmt(convToday) },
      { label: 'CPA Today',          value: cpaToday > 0 ? fmtMoney(cpaToday) : '\u2014' },
      { label: 'Spend 7d',           value: fmtMoney(spend7d) },
    ];
    wrap.innerHTML = cards.map(function(c) {
      return '<div class="acct-summary-card">' +
        '<div class="asc-value">' + c.value + '</div>' +
        '<div class="asc-label">' + c.label + '</div>' +
      '</div>';
    }).join('');
    wrap.style.display = 'grid';
  }

  /* ─── AI Marketing Copilot ─── */
  (function initCopilot() {
    // Session history: last N Q&As sent as context to improve follow-ups
    var sessionHistory = [];
    var MAX_HISTORY = 5; // keep last 5 Q&As in memory; send last 3 to API

    // ── Suggestion chips ──────────────────────────────────────
    fetchApi('/copilot/suggestions').then(function(qs) {
      var el = document.getElementById('copilotSuggestions');
      if (!el || !Array.isArray(qs)) return;
      _renderChips(el, qs);
    }).catch(function() {});

    function _renderChips(container, questions) {
      container.innerHTML = questions.map(function(q) {
        return '<button class="copilot-chip" data-question="' + _esc(q) + '">' + _esc(q) + '</button>';
      }).join('');
    }

    // Delegated click on chips (initial suggestions + follow-up chips)
    document.addEventListener('click', function(e) {
      var chip = e.target.closest('.copilot-chip');
      if (chip && chip.dataset.question) {
        var inp = document.getElementById('copilotInput');
        if (inp) inp.value = chip.dataset.question;
        window.copilotAsk();
      }
    });

    // Enter key submits
    var input = document.getElementById('copilotInput');
    if (input) {
      input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') window.copilotAsk();
      });
    }

    // ── Ref-click delegation (scroll to section) ─────────────
    var histEl = document.getElementById('copilotHistory');
    if (histEl) {
      histEl.addEventListener('click', function(e) {
        // Ref links
        var ref = e.target.closest('.cop-ref');
        if (ref) {
          _handleRefClick(ref.dataset.refType, ref.dataset.refName, ref.dataset.refId);
          return;
        }
        // Propose buttons
        var propBtn = e.target.closest('.cop-propose-btn');
        if (propBtn && !propBtn.disabled) {
          _handlePropose(propBtn);
        }
      });
    }

    function _handleRefClick(refType, refName, refId) {
      var pageMap = {
        campaign: 'campaigns',
        alert: 'alerts',
        creative: 'creative',
        account: 'accounts',
      };
      var page = pageMap[refType] || null;
      if (page) {
        window.a7Navigate(page);
        if (refType === 'campaign') setTimeout(function() { _flashCampaignRow(refId || refName); }, 200);
      }
    }

    function _flashCampaignRow(campaignId) {
      if (!campaignId) return;
      var tbody = document.getElementById('metaTableBody');
      if (!tbody) return;
      // Try exact data-campaign-id match first
      var row = tbody.querySelector('tr[data-campaign-id="' + campaignId + '"]');
      // Fallback: find by campaign name in first cell
      if (!row) {
        var rows = tbody.querySelectorAll('tr');
        for (var i = 0; i < rows.length; i++) {
          var cell = rows[i].querySelector('td');
          if (cell && cell.textContent.trim() === campaignId) { row = rows[i]; break; }
        }
      }
      if (!row) return;
      row.classList.remove('ca-row-flash'); // reset if already animating
      void row.offsetWidth; // force reflow
      row.classList.add('ca-row-flash');
      setTimeout(function() { row.classList.remove('ca-row-flash'); }, 2000);
    }

    function _handlePropose(btn) {
      var d = btn.dataset;
      var confirmMsg = 'Create automation proposal?\n\nAction: ' + (d.actionType || '') +
        '\nCampaign: ' + (d.entityName || '') +
        '\n\nThis will be queued for your review in the Automation Center. No execution happens until you approve it there.';
      confirmAction(confirmMsg, function() { _doPropose(btn, d); });
    }

    async function _doPropose(btn, d) {
      btn.disabled = true;
      btn.textContent = '…';

      var body = {
        action_type: d.actionType,
        entity_name: d.entityName,
        entity_type: d.entityType || 'campaign',
        platform: d.platform || 'meta',
        reason: d.reason || '',
        confidence: d.confidence || 'medium',
      };
      if (currentAccountId) body.account_id = currentAccountId;

      try {
        var result = await postApi('/copilot/propose', body);
        if (result.success) {
          btn.textContent = '✓ Queued #' + result.action_id;
          btn.classList.add('cop-proposed');
        } else {
          btn.textContent = 'Blocked';
          btn.title = result.reason || 'Guardrail blocked this action';
          btn.classList.add('cop-blocked');
          btn.disabled = false;
        }
      } catch (e) {
        btn.textContent = 'Error';
        btn.disabled = false;
      }
    }

    // ── Public API ────────────────────────────────────────────
    window.copilotAsk = async function() {
      var inp = document.getElementById('copilotInput');
      var btn = document.getElementById('copilotSendBtn');
      if (!inp) return;
      var question = inp.value.trim();
      if (!question) return;

      inp.value = '';
      setButtonLoading(btn, true, '...');

      var period = currentRange === 'today' ? 'today' : (currentRange === '30d' ? '30d' : '7d');
      var body = {
        question: question,
        period: period,
        session_context: sessionHistory.slice(-3).map(function(h) {
          return { question: h.question, response_type: h.response_type,
                   answer: h.answer, summary: h.summary || '' };
        }),
      };
      if (currentAccountId) body.account_id = currentAccountId;

      var entryId = 'cop-' + Date.now();
      _appendCopilotEntry(entryId, question);

      try {
        var result = await postApi('/copilot/ask', body);
        _updateCopilotEntry(entryId, question, result);

        // Update session history (last 5 stored; last 3 sent as context)
        sessionHistory.push({
          question: question,
          response_type: result.response_type || 'analysis',
          summary: (result.summary || '').substring(0, 150),
          answer: (result.answer || '').substring(0, 200),
        });
        if (sessionHistory.length > MAX_HISTORY) sessionHistory.shift();

        // Update provider badge
        var provEl = document.getElementById('copilotProvider');
        if (provEl && result.provider) {
          provEl.textContent = 'via ' + result.provider.replace(/_/g, ' ');
        }
      } catch (e) {
        _updateCopilotEntry(entryId, question, {
          response_type: 'analysis',
          summary: 'Error: ' + e.message,
          answer: 'Error: ' + e.message,
          key_findings: [], recommended_actions: [], suggested_actions: [],
          follow_up_questions: [],
          confidence: 'low',
          confidence_reason: 'low — limited data or conflicting signals; request failed',
          sources: [],
        });
      } finally {
        setButtonLoading(btn, false);
      }
    };

    // ── Rendering ─────────────────────────────────────────────
    function _appendCopilotEntry(id, question) {
      var el = document.getElementById('copilotHistory');
      if (!el) return;
      var div = document.createElement('div');
      div.className = 'copilot-entry cop-loading';
      div.id = id;
      div.innerHTML =
        '<div class="cop-question">' + _esc(question) + '</div>' +
        '<div class="cop-answer">Analyzing data…</div>';
      el.insertBefore(div, el.firstChild);
    }

    function _updateCopilotEntry(id, question, result) {
      var div = document.getElementById(id);
      if (!div) return;
      div.classList.remove('cop-loading');

      var rtype = result.response_type || 'analysis';
      var confidence = result.confidence || 'medium';
      var confClass = confidence === 'high' ? 'good' : confidence === 'low' ? 'bad' : 'mid';
      var confReason = result.confidence_reason || '';

      var html = '<div class="cop-question">' + _esc(question) + '</div>';

      // Type badge row
      html += '<div class="cop-type-row">' +
        '<span class="cop-type-badge cop-type-' + _esc(rtype) + '">' + _esc(rtype) + '</span>' +
        '</div>';

      // Answer
      html += '<div class="cop-answer">' + _md(result.answer || '') + '</div>';

      // Key findings with clickable refs
      var findings = result.key_findings || [];
      if (findings.length) {
        html += '<div class="cop-findings"><strong>Key findings</strong><ul>';
        findings.forEach(function(f) { html += '<li>' + _renderFinding(f) + '</li>'; });
        html += '</ul></div>';
      }

      // Recommended actions (recommended_actions is canonical; suggested_actions is alias)
      var actions = result.recommended_actions || result.suggested_actions || [];
      if (actions.length) {
        html += '<div class="cop-actions"><strong>Recommended actions</strong><ul>';
        actions.forEach(function(a) { html += '<li>' + _renderAction(a) + '</li>'; });
        html += '</ul></div>';
      }

      // Follow-up chips
      var followUps = (result.follow_up_questions || []).slice(0, 3);
      if (followUps.length) {
        html += '<div class="cop-followups">';
        followUps.forEach(function(q) {
          html += '<button class="copilot-chip cop-followup-chip" data-question="' + _esc(q) + '">' +
            _esc(q) + '</button>';
        });
        html += '</div>';
      }

      // Meta row: confidence + sources
      html += '<div class="cop-meta">';
      html += '<span class="cop-confidence ' + confClass + '"' +
        (confReason ? ' title="' + _esc(confReason) + '"' : '') + '>' +
        _esc(confidence) + ' confidence' + (confReason ? ' ℹ' : '') + '</span>';
      if (result.sources && result.sources.length) {
        var srcText = result.sources.map(function(s) {
          if (typeof s === 'string') return s;
          return s.name ? (s.type + ':' + s.name) : s.type;
        }).join(', ');
        html += '<span class="cop-sources">Sources: ' + _esc(srcText) + '</span>';
      }
      html += '</div>';

      div.innerHTML = html;
    }

    function _renderFinding(f) {
      if (typeof f === 'string') return _esc(f);
      var text = _esc(f.text || '');
      if (f.ref_name && f.ref_type && f.ref_type !== 'null') {
        var dataAttrs = 'data-ref-type="' + _esc(f.ref_type) + '" ' +
          'data-ref-id="' + _esc(f.ref_id || '') + '" ' +
          'data-ref-name="' + _esc(f.ref_name) + '"';
        var badge =
          '<span class="cop-ref cop-ref-' + _esc(f.ref_type) + '" ' + dataAttrs +
          ' title="Click to navigate">' + _esc(f.ref_name) + '</span>' +
          '<span class="cop-nav-link cop-ref" ' + dataAttrs +
          ' title="View ' + _esc(f.ref_name) + '">View \u2192</span>';
        var escapedName = _esc(f.ref_name);
        text = text.includes(escapedName) ? text.replace(escapedName, badge) : text + ' ' + badge;
      }
      return text;
    }

    function _renderAction(a) {
      if (typeof a === 'string') return _esc(a);
      var text = _esc(a.text || '');
      if (a.suggested_change_pct !== undefined && a.suggested_change_pct !== null && a.suggested_change_pct !== 0) {
        var pct = a.suggested_change_pct;
        text += ' <span class="action-pct-hint">(' + (pct > 0 ? '+' : '') + pct + '%)</span>';
      }
      if (a.actionable && a.action_type && a.entity_name) {
        text += ' <button class="cop-propose-btn" ' +
          'data-action-type="' + _esc(a.action_type) + '" ' +
          'data-entity-name="' + _esc(a.entity_name) + '" ' +
          'data-entity-type="' + _esc(a.entity_type || 'campaign') + '" ' +
          'data-platform="' + _esc(a.platform || 'meta') + '" ' +
          'data-reason="' + _esc(a.reason || a.text || '') + '" ' +
          'data-confidence="' + _esc(a.confidence_for_action || 'medium') + '" ' +
          'title="Queue this action for human review in the Automation Center">' +
          '→ Propose</button>';
      }
      return text;
    }

    function _esc(s) {
      return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    function _md(s) {
      return _esc(s)
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
    }
  })();

  /* ─── Account Connection Wizard ─── */
  (function initAccountWizard() {
    var _activePlatform = null;

    window.openAccountWizard = function() {
      _showStep('wizardStep1');
      var overlay = document.getElementById('accountWizardOverlay');
      if (overlay) overlay.style.display = 'flex';
    };

    window.closeAccountWizard = function() {
      var overlay = document.getElementById('accountWizardOverlay');
      if (overlay) overlay.style.display = 'none';
      _clearForms();
    };

    window.wizardSelectPlatform = function(platform) {
      _activePlatform = platform;
      _showStep(platform === 'meta' ? 'wizardStepMeta' : 'wizardStepGoogle');
    };

    window.wizardGoBack = function() {
      _activePlatform = null;
      _showStep('wizardStep1');
    };

    window.wizardConnect = async function(platform) {
      // Collect form values
      var body = { platform: platform };
      if (platform === 'meta') {
        var extId = (document.getElementById('metaExtId') || {}).value || '';
        var token = (document.getElementById('metaToken') || {}).value || '';
        var name  = (document.getElementById('metaName')  || {}).value || '';
        if (!extId.trim() || !token.trim()) {
          _showError(platform, 'Account ID and Access Token are required.');
          return;
        }
        body.external_account_id = extId.trim();
        body.access_token        = token.trim();
        if (name.trim()) body.account_name = name.trim();
      } else {
        var cid     = (document.getElementById('googleCid')      || {}).value || '';
        var devTok  = (document.getElementById('googleDevToken') || {}).value || '';
        var refTok  = (document.getElementById('googleRefToken') || {}).value || '';
        var gName   = (document.getElementById('googleName')     || {}).value || '';
        if (!cid.trim() || !devTok.trim() || !refTok.trim()) {
          _showError(platform, 'Customer ID, Developer Token, and Refresh Token are required.');
          return;
        }
        body.customer_id      = cid.trim();
        body.developer_token  = devTok.trim();
        body.refresh_token    = refTok.trim();
        if (gName.trim()) body.account_name = gName.trim();
      }

      _showStep('wizardStepConnecting');

      try {
        var result = await postApi('/accounts/connect', body);
        if (result.success) {
          _showResult(true,
            '✓ Account Connected',
            'Your ' + platform.charAt(0).toUpperCase() + platform.slice(1) +
            ' account <strong>' + _wEsc(result.account && result.account.account_name || '') +
            '</strong> has been connected and initial sync started.',
            'Refresh Dashboard',
            function() { window.closeAccountWizard(); location.reload(); }
          );
        } else {
          _showResult(false, 'Connection Failed', result.error || 'Unknown error', 'Try Again',
            function() { _showStep(_activePlatform === 'meta' ? 'wizardStepMeta' : 'wizardStepGoogle'); });
        }
      } catch (err) {
        _showResult(false, 'Connection Failed', err.message || 'Request failed', 'Try Again',
          function() { _showStep(_activePlatform === 'meta' ? 'wizardStepMeta' : 'wizardStepGoogle'); });
      }
    };

    // ── Helpers ──────────────────────────────────────────────
    function _showStep(stepId) {
      var steps = ['wizardStep1', 'wizardStepMeta', 'wizardStepGoogle',
                   'wizardStepConnecting', 'wizardStepResult'];
      steps.forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.style.display = id === stepId ? 'block' : 'none';
      });
    }

    function _showError(platform, msg) {
      var elId = platform === 'meta' ? 'metaError' : 'googleError';
      var el = document.getElementById(elId);
      if (el) { el.textContent = msg; el.style.display = 'block'; }
    }

    function _showResult(success, title, msgHtml, btnLabel, btnAction) {
      _showStep('wizardStepResult');
      var icon  = document.getElementById('wizardResultIcon');
      var ttl   = document.getElementById('wizardResultTitle');
      var msg   = document.getElementById('wizardResultMsg');
      var btn   = document.getElementById('wizardResultPrimary');
      if (icon)  { icon.textContent = success ? '✓' : '✕'; icon.className = 'wizard-result-icon ' + (success ? 'wizard-result-ok' : 'wizard-result-err'); }
      if (ttl)   ttl.textContent = title;
      if (msg)   msg.innerHTML   = msgHtml;
      if (btn)   { btn.textContent = btnLabel; btn.onclick = btnAction || window.closeAccountWizard; }
    }

    function _clearForms() {
      ['metaExtId', 'metaToken', 'metaName', 'metaError',
       'googleCid', 'googleDevToken', 'googleRefToken', 'googleName', 'googleError']
        .forEach(function(id) {
          var el = document.getElementById(id);
          if (!el) return;
          if (el.tagName === 'INPUT') el.value = '';
          else { el.textContent = ''; el.style.display = 'none'; }
        });
      _activePlatform = null;
    }

    function _wEsc(s) {
      return String(s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
  })();

  /* ─── Plan Usage ─── */
  async function loadPlanUsage() {
    var section = document.getElementById('planUsageSection');
    var metersEl = document.getElementById('planUsageMeters');
    var badgeEl  = document.getElementById('planNameBadge');
    var priceEl  = document.getElementById('planPriceLabel');
    var periodEl = document.getElementById('planUsagePeriod');
    if (!section || !metersEl) return;
    try {
      var d = await fetchApi('/billing/usage');
      if (badgeEl) badgeEl.textContent = d.plan_name || 'Starter';
      if (priceEl) priceEl.textContent = (d.price > 0) ? '$' + d.price + '/mo' : 'Free';
      if (periodEl) periodEl.textContent = d.period || '';

      var meters = [
        { label: 'Ad Accounts',      data: d.accounts },
        { label: 'Automation Runs',  data: d.automation },
        { label: 'Copilot Queries',  data: d.copilot },
      ];

      metersEl.innerHTML = meters.map(function(m) {
        var u = m.data || {};
        if (u.unlimited) {
          return '<div class="plan-usage-meter">' +
            '<div class="pum-row"><span class="pum-label">' + m.label + '</span>' +
            '<span class="pum-unlimited">Unlimited</span></div>' +
          '</div>';
        }
        var pct = u.pct || 0;
        var barCls = pct >= 90 ? 'pum-bar danger' : pct >= 70 ? 'pum-bar warn' : 'pum-bar';
        return '<div class="plan-usage-meter">' +
          '<div class="pum-row">' +
            '<span class="pum-label">' + m.label + '</span>' +
            '<span class="pum-value">' + (u.used || 0) + ' / ' + (u.limit || 0) + '</span>' +
          '</div>' +
          '<div class="pum-bar-wrap"><div class="' + barCls + '" style="width:' + pct + '%"></div></div>' +
        '</div>';
      }).join('');

      // Upgrade CTA — only shown when not on Scale/Enterprise plan
      var ctaEl = document.getElementById('planUpgradeCta');
      if (ctaEl) {
        var planName = (d.plan_name || 'Starter').toLowerCase();
        if (planName === 'scale' || planName === 'enterprise') {
          ctaEl.style.display = 'none';
        } else {
          var showScale = (planName === 'growth');
          ctaEl.innerHTML =
            '<p class="puc-headline">You\'re on the <strong>' + (d.plan_name || 'Starter') + '</strong> plan.</p>' +
            '<p class="puc-subline">Unlock higher limits, priority support, and advanced automation.</p>' +
            '<div class="puc-btns">' +
              (!showScale ? '<button class="puc-btn puc-btn-growth" onclick="upgradePlan(\'growth\')">Upgrade to Growth &mdash; $99/mo</button>' : '') +
              '<button class="puc-btn puc-btn-scale" onclick="upgradePlan(\'scale\')">Upgrade to Scale &mdash; $299/mo</button>' +
            '</div>';
          ctaEl.style.display = '';
        }
      }

      section.style.display = '';
    } catch (e) {
      // silently skip if billing endpoint unavailable
    }
  }

  /* ─── Upgrade Plan (Stripe Checkout) ─── */
  window.upgradePlan = function(planName) {
    var btn = document.querySelector('.puc-btn-' + planName);
    if (btn) {
      btn._origText = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<span class="btn-spinner"></span>Redirecting...';
      btn.style.opacity = '0.75';
    }
    fetch('/api/billing/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan: planName }),
    })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.checkout_url) {
          window.location.href = data.checkout_url;
        } else {
          if (btn) {
            btn.disabled = false;
            btn.innerHTML = btn._origText || 'Upgrade';
            btn.style.opacity = '';
          }
          showToast('Upgrade unavailable: ' + (data.error || 'Unknown error'), 'error');
        }
      })
      .catch(function() {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = btn._origText || 'Upgrade';
          btn.style.opacity = '';
        }
        showToast('Could not connect to billing service', 'error');
      });
  };

  /* ─── Content Studio ─── */

  var _csActiveTab = 'ideas';

  function loadContentStudio() {
    var section = $('#contentStudioSection');
    if (!section) return;
    section.style.display = '';
    _renderCSTab(_csActiveTab);
    // Tab click handlers
    document.querySelectorAll('.cs-tab').forEach(function(btn) {
      btn.onclick = function() {
        document.querySelectorAll('.cs-tab').forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
        _csActiveTab = btn.getAttribute('data-cs-tab');
        _renderCSTab(_csActiveTab);
      };
    });
    // Generate button
    var genBtn = $('#csGenerateBtn');
    if (genBtn) {
      genBtn.onclick = function() { _csGenerateIdeas(); };
    }
  }

  function _renderCSTab(tab) {
    var panels = {
      ideas: 'csIdeasPanel',
      assets: 'csAssetsPanel',
      publishing: 'csPublishingPanel',
      brand: 'csBrandPanel',
      calendar: 'csCalendarPanel',
      intelligence: 'csIntelligencePanel',
    };
    Object.keys(panels).forEach(function(k) {
      var el = $(panels[k]);
      if (el) el.style.display = k === tab ? '' : 'none';
    });
    if (tab === 'ideas') _csLoadIdeas();
    if (tab === 'assets') _csLoadAssets();
    if (tab === 'publishing') { _pubLoad(); _schedLoad(); }
    if (tab === 'brand') _csLoadBrandKit();
    if (tab === 'calendar') _calLoad();
    if (tab === 'intelligence') _intelLoad();
  }

  async function _csLoadIdeas() {
    var tbody = $('#csIdeasBody');
    var empty = $('#csIdeasEmpty');
    if (!tbody) return;
    try {
      var ideas = await fetchApi('/content/ideas?' + _acctQs());
      if (!Array.isArray(ideas) || ideas.length === 0) {
        tbody.innerHTML = '';
        if (empty) empty.style.display = '';
        return;
      }
      if (empty) empty.style.display = 'none';
      tbody.innerHTML = ideas.map(function(i) {
        var statusCls = 'cs-badge cs-badge-' + (i.status || 'idea');
        return '<tr>' +
          '<td>' + _esc(i.title) + '<br><span style="font-size:11px;color:var(--text-muted)">' + _esc(i.description || '') + '</span></td>' +
          '<td><span class="cs-badge cs-badge-type">' + _esc(i.content_type || '') + '</span></td>' +
          '<td>' + _esc(i.platform_target || '') + '</td>' +
          '<td><span class="cs-badge cs-badge-src">' + _esc(i.source || '') + '</span></td>' +
          '<td><span class="' + statusCls + '">' + _esc(i.status || '') + '</span></td>' +
          '<td>' +
            '<button class="cs-action-btn" onclick="csApproveIdea(' + i.id + ')">Approve</button>' +
            '<button class="cs-action-btn" onclick="csRejectIdea(' + i.id + ')">Reject</button>' +
            '<button class="cs-action-btn cs-action-build" onclick="csBuildPrompt(' + i.id + ')" title="Build structured prompt from brand kit + idea">Prompt</button>' +
            '<button class="cs-action-btn cs-action-gen" onclick="csGenerateImage(' + i.id + ')" title="Generate image with AI">Image</button>' +
          '</td>' +
        '</tr>';
      }).join('');
    } catch (e) {
      if (tbody) tbody.innerHTML = '';
    }
  }

  async function _csLoadAssets() {
    var grid = $('#csAssetGrid');
    var empty = $('#csAssetsEmpty');
    if (!grid) return;
    try {
      var assets = await fetchApi('/content/assets?' + _acctQs());
      if (!Array.isArray(assets) || assets.length === 0) {
        grid.innerHTML = '';
        if (empty) empty.style.display = '';
        return;
      }
      if (empty) empty.style.display = 'none';
      var icons = { image: '🖼️', video: '🎬', design: '🎨', mockup: '📐' };
      grid.innerHTML = assets.map(function(a) {
        var icon = icons[a.asset_type] || '📄';
        var thumb = a.thumbnail_url
          ? '<img src="' + _esc(a.thumbnail_url) + '" style="width:100%;height:100%;object-fit:cover" loading="lazy">'
          : '<span style="font-size:2rem">' + icon + '</span>';
        var providerBadge = a.provider && a.provider !== 'mock'
          ? '<span class="cs-badge cs-badge-src" style="font-size:9px">' + _esc(a.provider) + '</span>'
          : '<span style="font-size:9px;color:var(--text-muted)">mock</span>';
        var costBadge = (a.generation_cost && a.generation_cost > 0)
          ? '<span style="font-size:9px;color:var(--text-muted)">$' + a.generation_cost.toFixed(3) + '</span>'
          : '';
        return '<div class="cs-asset-card">' +
          '<div class="cs-asset-thumb">' + thumb + '</div>' +
          '<div class="cs-asset-info">' +
            '<div class="cs-asset-type">' + _esc(a.asset_type || '') + ' ' + providerBadge + '</div>' +
            '<div class="cs-asset-status" style="color:var(--text-muted)">' + _esc(a.status || '') + ' ' + costBadge + '</div>' +
          '</div>' +
        '</div>';
      }).join('');
    } catch (e) {
      if (grid) grid.innerHTML = '';
    }
  }

  async function _csLoadBrandKit() {
    try {
      var kit = await fetchApi('/content/brand-kit?' + _acctQs());
      if (!kit) return;
      _setVal('csBrandName', kit.brand_name || '');
      _setVal('csBrandPrimary', kit.primary_color || '#000000');
      _setVal('csBrandSecondary', kit.secondary_color || '#ffffff');
      _setVal('csBrandAccent', kit.accent_color || '#3B82F6');
      _setVal('csBrandFont', kit.font_family || 'Inter');
      _setVal('csBrandLogo', kit.logo_url || '');
      _setVal('csBrandStyle', kit.style_description || '');
    } catch (e) { /* silently skip */ }
  }

  function _setVal(id, val) {
    var el = $(id);
    if (el) el.value = val;
  }

  window.saveBrandKit = async function() {
    var btn = document.getElementById('btnSaveBrandKit') ||
              document.querySelector('[onclick*="saveBrandKit"]');
    setButtonLoading(btn, true, 'Saving...');
    try {
      var payload = {
        account_id: currentAccountId || 1,
        brand_name: ($('#csBrandName') || {}).value || '',
        primary_color: ($('#csBrandPrimary') || {}).value || '#000000',
        secondary_color: ($('#csBrandSecondary') || {}).value || '#ffffff',
        accent_color: ($('#csBrandAccent') || {}).value || '#3B82F6',
        font_family: ($('#csBrandFont') || {}).value || 'Inter',
        logo_url: ($('#csBrandLogo') || {}).value || '',
        style_description: ($('#csBrandStyle') || {}).value || '',
      };
      await fetch('/api/content/brand-kit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      showToast('Brand kit saved', 'success');
    } catch (e) {
      showToast('Error saving brand kit', 'error');
    } finally {
      setButtonLoading(btn, false);
    }
  };

  window.csApproveIdea = async function(id) {
    try {
      await fetch('/api/content/ideas/' + id + '/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'approved' }),
      });
      _csLoadIdeas();
    } catch (e) { /* silently skip */ }
  };

  window.csRejectIdea = async function(id) {
    try {
      await fetch('/api/content/ideas/' + id + '/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'rejected' }),
      });
      _csLoadIdeas();
    } catch (e) { /* silently skip */ }
  };

  window.csBuildPrompt = async function(ideaId) {
    try {
      var res = await fetch('/api/content/prompts/build', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: currentAccountId || 1, content_idea_id: ideaId }),
      });
      var data = await res.json();
      if (data && data.prompt_text) {
        showToast('Prompt built and ready (' + data.prompt_text.length + ' chars)', 'success');
      }
    } catch (e) { /* silently skip */ }
  };

  window.csGenerateImage = function(ideaId) {
    confirmAction('Generate an AI image for this idea? (uses image generation credits)', async function() {
      try {
        var res = await fetch('/api/content/assets/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ account_id: currentAccountId || 1, content_idea_id: ideaId }),
        });
        var data = await res.json();
        if (data && data.asset) {
          _csActiveTab = 'assets';
          document.querySelectorAll('.cs-tab').forEach(function(b) {
            b.classList.toggle('active', b.getAttribute('data-cs-tab') === 'assets');
          });
          _renderCSTab('assets');
          showToast('Image generated successfully', 'success');
        }
      } catch (e) { /* silently skip */ }
    });
  };

  // ── Publishing Engine ─────────────────────────────────────────────────────

  async function _pubLoad() {
    await Promise.all([_pubLoadConnectors(), _pubLoadPosts(), _pubLoadJobs()]);
  }

  async function _pubLoadConnectors() {
    var container = $('#pubConnectorList');
    if (!container) return;
    try {
      var connectors = await fetchApi('/content/connectors?' + _acctQs());
      var PLATFORMS = ['instagram', 'facebook_page'];
      var connMap = {};
      if (Array.isArray(connectors)) {
        connectors.forEach(function(c) { connMap[c.platform] = c; });
      }
      container.innerHTML = PLATFORMS.map(function(p) {
        var c = connMap[p];
        var status = c ? c.status : 'none';
        var dotCls = 'pub-conn-' + status;
        var label = p.replace('_', ' ');
        var validated = c && c.last_validated_at ? c.last_validated_at.slice(0, 10) : '';
        var hint = validated ? ' · ' + validated : (c ? '' : ' · not configured');
        return '<div class="pub-connector-card">' +
          '<span class="pub-conn-dot ' + dotCls + '"></span>' +
          '<span style="font-weight:600;text-transform:capitalize">' + _esc(label) + '</span>' +
          '<span style="color:var(--text-muted)">' + _esc(status) + _esc(hint) + '</span>' +
        '</div>';
      }).join('');
    } catch (e) {
      if (container) container.innerHTML = '<span style="color:var(--text-muted);font-size:12px">Connector status unavailable</span>';
    }
  }

  window.pubSaveConnector = async function() {
    var platform = ($('#pubConnPlatform') || {}).value || 'instagram';
    var token    = ($('#pubConnToken')    || {}).value || '';
    var igUser   = ($('#pubConnIgUser')   || {}).value || '';
    var pageId   = ($('#pubConnPageId')   || {}).value || '';
    if (!token) { showToast('Access token is required.', 'warning'); return; }
    var btn = document.getElementById('btnPubSaveConnector') ||
              document.querySelector('[onclick*="pubSaveConnector"]');
    setButtonLoading(btn, true, 'Saving...');
    try {
      var resp = await fetch('/api/content/connectors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_id: currentAccountId || 1,
          platform: platform, access_token: token,
          ig_user_id: igUser, page_id: pageId,
        }),
      });
      var data = await resp.json();
      if (data && !data.error) {
        if ($('#pubConnToken')) $('#pubConnToken').value = '';
        await _pubLoadConnectors();
        showToast('Connector saved. Use "Validate" to test credentials.', 'success');
      } else {
        showToast('Error: ' + (data.error || 'Unknown'), 'error');
      }
    } catch (e) {
      showToast('Failed to save connector.', 'error');
    } finally {
      setButtonLoading(btn, false);
    }
  };

  window.pubValidateConnector = async function() {
    var platform = ($('#pubConnPlatform') || {}).value || 'instagram';
    var btn = document.getElementById('btnPubValidateConnector') ||
              document.querySelector('[onclick*="pubValidateConnector"]');
    setButtonLoading(btn, true, 'Validating...');
    try {
      var resp = await fetch('/api/content/connectors/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: currentAccountId || 1, platform: platform }),
      });
      var data = await resp.json();
      if (data.valid) {
        showToast('Credentials valid! Connected as: ' + (data.name || data.user_id || 'OK'), 'success');
      } else {
        showToast('Validation failed: ' + (data.error || 'Unknown error'), 'error');
      }
      await _pubLoadConnectors();
    } catch (e) {
      showToast('Validation request failed.', 'error');
    } finally {
      setButtonLoading(btn, false);
    }
  };

  async function _pubLoadPosts() {
    var tbody = $('#pubPostsBody');
    var empty = $('#pubPostsEmpty');
    var upcomingSection = $('#pubUpcomingSection');
    var upcomingList = $('#pubUpcomingList');
    if (!tbody) return;
    try {
      var posts = await fetchApi('/content/posts?' + _acctQs());
      if (!Array.isArray(posts) || posts.length === 0) {
        tbody.innerHTML = '';
        if (empty) empty.style.display = '';
        if (upcomingSection) upcomingSection.style.display = 'none';
        return;
      }
      if (empty) empty.style.display = 'none';

      // Upcoming scheduled posts
      var upcoming = posts.filter(function(p) {
        return p.status === 'scheduled' && p.scheduled_for;
      }).sort(function(a, b) { return a.scheduled_for < b.scheduled_for ? -1 : 1; });
      if (upcoming.length && upcomingSection && upcomingList) {
        upcomingSection.style.display = '';
        upcomingList.innerHTML = upcoming.slice(0, 5).map(function(p) {
          return '<div class="pub-upcoming-item">' +
            '<span class="pub-upcoming-time">' + _esc(p.scheduled_for || '') + '</span>' +
            '<span>' + _esc(p.title || '(untitled)') + '</span>' +
            '<span style="color:var(--text-muted);margin-left:auto">' + _esc(p.platform_target || '') + '</span>' +
          '</div>';
        }).join('');
      } else if (upcomingSection) {
        upcomingSection.style.display = 'none';
      }

      var statusColors = {
        draft: 'pub-status-draft', scheduled: 'pub-status-scheduled',
        publishing: 'pub-status-publishing', published: 'pub-status-published',
        failed: 'pub-status-failed', archived: 'pub-status-archived',
      };
      tbody.innerHTML = posts.map(function(p) {
        var sCls = statusColors[p.status] || 'pub-status-draft';
        var schedCell = p.scheduled_for
          ? '<span style="color:#f59e0b;font-size:11px">' + _esc(p.scheduled_for.slice(0,16)) + '</span>'
          : '—';
        return '<tr>' +
          '<td>' + _esc(p.title || '(untitled)') + '</td>' +
          '<td>' + _esc(p.platform_target || '') + '</td>' +
          '<td><span class="cs-badge cs-badge-type">' + _esc(p.post_type || '') + '</span></td>' +
          '<td><span class="' + sCls + '">' + _esc(p.status || '') + '</span></td>' +
          '<td>' + schedCell + '</td>' +
          '<td>' +
            '<button class="cs-action-btn cs-action-gen" onclick="pubPublishNow(' + p.id + ')" title="Publish now">Publish</button>' +
            '<button class="cs-action-btn cs-action-build" onclick="pubSchedule(' + p.id + ')" title="Schedule">Schedule</button>' +
            '<button class="cs-action-btn" onclick="pubArchive(' + p.id + ')" title="Archive">Archive</button>' +
          '</td>' +
        '</tr>';
      }).join('');
    } catch (e) {
      if (tbody) tbody.innerHTML = '';
    }
  }

  async function _pubLoadJobs() {
    var tbody = $('#pubJobsBody');
    var empty = $('#pubJobsEmpty');
    if (!tbody) return;
    try {
      var jobs = await fetchApi('/content/jobs?' + _acctQs());
      if (!Array.isArray(jobs) || jobs.length === 0) {
        tbody.innerHTML = '';
        if (empty) empty.style.display = '';
        return;
      }
      if (empty) empty.style.display = 'none';
      var jColors = {
        success: '#10b981', failed: 'var(--red)', running: '#6366f1',
        queued: 'var(--text-muted)', scheduled: '#f59e0b', cancelled: 'var(--text-muted)',
        uploading: '#6366f1', publishing: '#6366f1', retrying: '#f59e0b',
      };
      tbody.innerHTML = jobs.map(function(j) {
        var jColor = jColors[j.status] || 'var(--text-muted)';
        var retryBadge = (j.retry_count && j.retry_count > 0)
          ? '<span style="font-size:9px;color:#f59e0b;margin-left:4px">retry×' + j.retry_count + '</span>'
          : '';
        var nextRetry = (j.status === 'retrying' && j.next_retry_at)
          ? '<div style="font-size:9px;color:#f59e0b">next: ' + _esc(j.next_retry_at.slice(0,16)) + '</div>'
          : '';
        return '<tr>' +
          '<td><span class="cs-badge cs-badge-src">' + _esc(j.job_type || '') + '</span></td>' +
          '<td>' + _esc(j.platform_target || '') + '</td>' +
          '<td><span style="color:' + jColor + '">' + _esc(j.status || '') + '</span>' + retryBadge + nextRetry + '</td>' +
          '<td style="font-size:11px;color:#f59e0b">' + _esc((j.scheduled_for || '').slice(0,16) || '—') + '</td>' +
          '<td style="font-size:11px;color:var(--text-muted)">' + _esc((j.executed_at || '').slice(0,16) || '—') + '</td>' +
          '<td style="font-size:11px;color:var(--text-muted);max-width:200px;white-space:normal">' + _esc((j.result_message || '').slice(0, 120)) + '</td>' +
        '</tr>';
      }).join('');
    } catch (e) {
      if (tbody) tbody.innerHTML = '';
    }
  }

  window.pubCreatePost = async function() {
    var title = ($('#pubTitle') || {}).value || '';
    var platform = ($('#pubPlatform') || {}).value || 'instagram';
    var postType = ($('#pubPostType') || {}).value || 'image_post';
    if (!title.trim()) { showToast('Please enter a post title.', 'warning'); return; }
    try {
      await fetch('/api/content/posts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: currentAccountId || 1, title: title,
                               platform_target: platform, post_type: postType }),
      });
      if ($('#pubTitle')) $('#pubTitle').value = '';
      await _pubLoadPosts();
    } catch (e) { /* silently skip */ }
  };

  window.pubPublishNow = function(postId) {
    confirmAction(
      'Publish this post now? It will be immediately sent to the connected platform.',
      async function() {
        try {
          await fetch('/api/content/posts/' + postId + '/publish', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ account_id: currentAccountId || 1 }),
          });
          showToast('Post publishing started', 'success');
          await _pubLoad();
        } catch (e) { showToast('Publish failed: ' + e.message, 'error'); }
      },
      { title: 'Publish Post', okLabel: 'Publish Now' }
    );
  };

  window.pubSchedule = async function(postId) {
    var dt = prompt('Schedule for (ISO format, e.g. 2026-03-20T14:00:00):');
    if (!dt) return;
    try {
      await fetch('/api/content/posts/' + postId + '/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: currentAccountId || 1, scheduled_for: dt }),
      });
      await _pubLoadPosts();
    } catch (e) { /* silently skip */ }
  };

  window.pubArchive = function(postId) {
    confirmAction(
      'Archive this post draft? This cannot be undone.',
      async function() {
        try {
          await fetch('/api/content/posts/' + postId + '/status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ account_id: currentAccountId || 1, status: 'archived' }),
          });
          showToast('Post archived', 'info');
          await _pubLoadPosts();
        } catch (e) { /* silently skip */ }
      },
      { destructive: true, title: 'Archive Post', okLabel: 'Archive' }
    );
  };

  async function _csGenerateIdeas() {
    var btn = $('#csGenerateBtn');
    var loading = $('#csIdeasLoading');
    setButtonLoading(btn, true, 'Generating...');
    if (loading) loading.style.display = '';
    try {
      await fetch('/api/content/generate-ideas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: currentAccountId || 1 }),
      });
      await _csLoadIdeas();
      showToast('Ideas generated successfully', 'success');
    } catch (e) {
      showToast('Error generating ideas', 'error');
    } finally {
      setButtonLoading(btn, false);
      if (loading) loading.style.display = 'none';
    }
  }

  // ── Content Intelligence ──────────────────────────────────────────────────

  var _intelPlatformIcon = {
    instagram: '📸', facebook: '📘', facebook_page: '📘',
    tiktok: '🎵', linkedin: '💼', pinterest: '📌', google_display: '🎯',
  };
  var _intelInsightIcon = {
    top_performer: '🏆', reuse_opportunity: '♻️', paid_synergy: '🔗',
    low_engagement: '⚠️', format_winner: '🥇', best_time: '⏰',
  };

  async function _intelLoad() {
    await Promise.all([
      _intelLoadSummary(),
      _intelLoadTopPosts(),
      _intelLoadFormats(),
      _intelLoadBestTimes(),
      _intelLoadReuse(),
    ]);
  }

  async function _intelLoadSummary() {
    var row = $('#intelSummaryRow');
    if (!row) return;
    try {
      var d = await fetchApi('/content/intelligence/summary?' + _acctQs() + '&days=7');
      row.innerHTML =
        _intelKpi('Posts Published', d.posts_published, '(last 7 days)') +
        _intelKpi('Total Reach',     _intelFmt(d.total_reach), '') +
        _intelKpi('Engagement',      _intelFmt(d.total_engagement), '') +
        _intelKpi('Avg Score',       d.avg_score + '/100', '');
    } catch (e) { row.innerHTML = ''; }
  }

  function _intelKpi(label, value, sub) {
    return '<div class="intel-kpi-card">' +
      '<div class="intel-kpi-label">' + _esc(label) + '</div>' +
      '<div class="intel-kpi-value">' + _esc(String(value)) + '</div>' +
      (sub ? '<div class="intel-kpi-sub">' + _esc(sub) + '</div>' : '') +
    '</div>';
  }

  function _intelFmt(n) {
    if (!n && n !== 0) return '—';
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return String(n);
  }

  function _intelScoreCls(score) {
    if (score >= 60) return 'intel-score-high';
    if (score >= 30) return 'intel-score-medium';
    return 'intel-score-low';
  }

  async function _intelLoadTopPosts() {
    var container = $('#intelTopPosts');
    var empty = $('#intelTopPostsEmpty');
    if (!container) return;
    try {
      var posts = await fetchApi('/content/intelligence/top-posts?' + _acctQs() + '&days=30');
      if (!Array.isArray(posts) || posts.length === 0) {
        container.innerHTML = '';
        if (empty) empty.style.display = '';
        return;
      }
      if (empty) empty.style.display = 'none';
      container.innerHTML = posts.map(function(p) {
        var icon = _intelPlatformIcon[p.platform_target] || '📢';
        var thumb = p.thumbnail_url
          ? '<img src="' + _esc(p.thumbnail_url) + '" loading="lazy">'
          : icon;
        var score = p.score || 0;
        return '<div class="intel-post-row">' +
          '<div class="intel-post-thumb">' + thumb + '</div>' +
          '<div class="intel-post-info">' +
            '<div class="intel-post-title">' + _esc(p.title || '(untitled)') + '</div>' +
            '<div class="intel-post-meta">' +
              icon + ' ' + _esc(p.platform_target || '') + ' · ' +
              _esc(p.post_type || '') + ' · ' +
              'Reach: ' + _intelFmt(p.reach) + ' · Eng: ' + _intelFmt(p.engagement) +
            '</div>' +
          '</div>' +
          '<span class="intel-score-badge ' + _intelScoreCls(score) + '">' + score.toFixed(0) + '</span>' +
        '</div>';
      }).join('');
    } catch (e) { if (container) container.innerHTML = ''; }
  }

  async function _intelLoadFormats() {
    var container = $('#intelFormats');
    var empty = $('#intelFormatsEmpty');
    if (!container) return;
    try {
      var rows = await fetchApi('/content/intelligence/formats?' + _acctQs() + '&days=30');
      if (!Array.isArray(rows) || rows.length === 0) {
        container.innerHTML = '';
        if (empty) empty.style.display = '';
        return;
      }
      if (empty) empty.style.display = 'none';
      var html = '<table class="intel-format-table"><thead><tr>' +
        '<th>Format</th><th>Platform</th><th>Posts</th>' +
        '<th>Avg Engagement</th><th>Avg Reach</th><th>Avg CTR</th>' +
        '</tr></thead><tbody>';
      rows.forEach(function(r) {
        html += '<tr>' +
          '<td>' + _esc(r.post_type || '') + '</td>' +
          '<td>' + _esc(r.platform_target || '') + '</td>' +
          '<td>' + (r.post_count || 0) + '</td>' +
          '<td>' + _intelFmt(Math.round(r.avg_engagement || 0)) + '</td>' +
          '<td>' + _intelFmt(Math.round(r.avg_reach || 0)) + '</td>' +
          '<td>' + ((r.avg_ctr || 0) * 100).toFixed(2) + '%</td>' +
        '</tr>';
      });
      html += '</tbody></table>';
      container.innerHTML = html;
    } catch (e) { if (container) container.innerHTML = ''; }
  }

  async function _intelLoadBestTimes() {
    var container = $('#intelBestTimes');
    var empty = $('#intelBestTimesEmpty');
    if (!container) return;
    try {
      var times = await fetchApi('/content/intelligence/best-times?' + _acctQs() + '&days=30');
      if (!Array.isArray(times) || times.length === 0) {
        container.innerHTML = '';
        if (empty) empty.style.display = '';
        return;
      }
      if (empty) empty.style.display = 'none';
      container.innerHTML = '<div class="intel-times-grid">' +
        times.slice(0, 6).map(function(t) {
          return '<div class="intel-time-card">' +
            '<div class="intel-time-day">'  + _esc(t.weekday_label) + '</div>' +
            '<div class="intel-time-hour">' + _esc(t.hour_label) + '</div>' +
            '<div class="intel-time-eng">'  + _intelFmt(Math.round(t.avg_engagement)) + '</div>' +
            '<div class="intel-time-label">avg eng · ' + (t.post_count || 0) + ' posts</div>' +
          '</div>';
        }).join('') +
      '</div>';
    } catch (e) { if (container) container.innerHTML = ''; }
  }

  async function _intelLoadReuse() {
    var container = $('#intelReuse');
    var empty = $('#intelReuseEmpty');
    if (!container) return;
    try {
      var items = await fetchApi('/content/intelligence/reuse?' + _acctQs() + '&days=30');
      if (!Array.isArray(items) || items.length === 0) {
        container.innerHTML = '';
        if (empty) empty.style.display = '';
        return;
      }
      // Filter out error items
      items = items.filter(function(i) { return !i.error; });
      if (items.length === 0) {
        container.innerHTML = '';
        if (empty) empty.style.display = '';
        return;
      }
      if (empty) empty.style.display = 'none';
      container.innerHTML = items.map(function(ins) {
        var icon = _intelInsightIcon[ins.type] || '💡';
        return '<div class="intel-reuse-card">' +
          '<div class="intel-reuse-icon">' + icon + '</div>' +
          '<div class="intel-reuse-body">' +
            '<div class="intel-reuse-type ' + _esc(ins.type) + '">' +
              _esc((ins.type || '').replace(/_/g, ' ')) +
            '</div>' +
            '<div class="intel-reuse-title">' + _esc(ins.title || '') + '</div>' +
            '<div class="intel-reuse-msg">'   + _esc(ins.message || '') + '</div>' +
          '</div>' +
        '</div>';
      }).join('');
    } catch (e) { if (container) container.innerHTML = ''; }
  }

  window.intelSync = async function() {
    var status = $('#intelSyncStatus');
    if (status) status.textContent = 'Syncing…';
    try {
      var res  = await fetch('/api/content/intelligence/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: currentAccountId || 1 }),
      });
      var data = await res.json();
      if (data.error) {
        if (status) status.textContent = '✗ Error: ' + data.error;
        return;
      }
      if (status) {
        status.textContent = '✓ Synced ' + (data.synced || 0) +
          ' posts (' + (data.already_synced || 0) + ' already up to date)';
      }
      await _intelLoad();
    } catch (e) {
      if (status) status.textContent = '✗ Sync failed';
    }
  };

  // ── Publishing Monitor (Phase 8G) ─────────────────────────────────────────

  async function _schedLoad() {
    try {
      var res = await fetch('/api/content/scheduler/status');
      var data = await res.json();
      var badge = document.getElementById('schedBadge');
      var label = document.getElementById('schedLabel');
      if (badge) {
        badge.textContent = data.running ? 'Running' : 'Stopped';
        badge.className = 'sched-badge ' + (data.running ? 'running' : 'stopped');
      }
      if (label) {
        label.textContent = data.running
          ? ('Started ' + (data.started_at ? _schedFmt(data.started_at) : '—'))
          : 'Scheduler not running (started with web server)';
      }
      var el;
      el = document.getElementById('schedExec');   if (el) el.textContent = data.jobs_executed  != null ? data.jobs_executed  : '—';
      el = document.getElementById('schedFailed'); if (el) el.textContent = data.jobs_failed    != null ? data.jobs_failed    : '—';
      el = document.getElementById('schedStuck');  if (el) el.textContent = data.stuck_resolved != null ? data.stuck_resolved : '—';
      el = document.getElementById('schedLastRun'); if (el) el.textContent = data.last_run_at ? _schedFmt(data.last_run_at) : '—';
    } catch (e) { /* ignore */ }
  }

  function _schedFmt(ts) {
    try { return new Date(ts).toLocaleString(); } catch (e) { return ts; }
  }

  window.schedRefresh = function() { _schedLoad(); };

  window.schedRunNow = async function() {
    try {
      var btn = document.querySelector('.sched-run-btn');
      if (btn) { var orig = btn.textContent; btn.textContent = '…'; btn.disabled = true; }
      var res = await fetch('/api/content/scheduler/run', { method: 'POST' });
      var data = await res.json();
      if (btn) { btn.textContent = orig; btn.disabled = false; }
      showToast('Pass complete: ' + data.executed + ' executed, ' + data.failed + ' failed, ' + data.stuck_resolved + ' stuck resolved.', 'info');
      _schedLoad();
    } catch (e) {
      showToast('Scheduler run failed.', 'error');
    }
  };

  // ── Content Calendar ──────────────────────────────────────────────────────

  var _calView  = 'week';
  var _calStart = null;    // YYYY-MM-DD
  var _calRescheduleId = null;

  var _calPlatformIcon = {
    instagram: '📸', facebook: '📘', facebook_page: '📘',
    tiktok: '🎵', linkedin: '💼', pinterest: '📌', google_display: '🎯',
  };

  async function _calLoad() {
    var grid = $('#calGrid');
    if (!grid) return;
    if (!_calStart) {
      _calStart = new Date().toISOString().substring(0, 10);
    }
    var qs = 'view=' + _calView + '&start=' + _calStart + '&' + _acctQs();
    grid.innerHTML = '<div style="padding:20px;color:var(--text-muted);font-size:13px">Loading…</div>';
    try {
      var data = await fetchApi('/content/calendar?' + qs);
      _calRender(data);
      _calLoadUpcoming();
    } catch (e) {
      grid.innerHTML = '<div class="cs-empty">Failed to load calendar.</div>';
    }
  }

  function _calRender(data) {
    var grid = $('#calGrid');
    if (!grid) return;
    var label = $('#calPeriodLabel');
    if (label) {
      if (data.view === 'month') {
        var md = new Date(data.start + 'T00:00:00');
        label.textContent = md.toLocaleString('default', { month: 'long', year: 'numeric' });
      } else {
        label.textContent = _calFmtPeriod(data.start) + (data.view === 'week' ? ' – ' + _calFmtPeriod(data.end) : '');
      }
    }
    if (data.view === 'week' || data.view === 'day') {
      grid.innerHTML = _calBuildWeek(data);
    } else {
      grid.innerHTML = _calBuildMonth(data);
    }
  }

  function _calFmtPeriod(dateStr) {
    if (!dateStr) return '';
    try {
      var d = new Date(dateStr + 'T00:00:00');
      return d.toLocaleDateString('default', { month: 'short', day: 'numeric' });
    } catch (e) { return dateStr; }
  }

  function _calBuildWeek(data) {
    var html = '<div class="cal-week-grid">';
    data.days.forEach(function(day) {
      var todayCls = day.is_today ? ' cal-day-today' : '';
      html += '<div class="cal-day-col">' +
        '<div class="cal-day-header' + todayCls + '">' +
          '<span class="cal-day-label">' + _esc(day.label) + '</span>' +
          '<span class="cal-day-num">'  + day.day_num + '</span>' +
        '</div>' +
        '<div class="cal-day-body">';
      if (day.posts.length === 0) {
        html += '<div style="padding:6px;font-size:10px;color:var(--text-muted);text-align:center">—</div>';
      } else {
        day.posts.forEach(function(p) { html += _calPostCard(p); });
      }
      html += '</div></div>';
    });
    html += '</div>';
    return html;
  }

  function _calBuildMonth(data) {
    var html = '<div class="cal-month-grid">';
    ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].forEach(function(d) {
      html += '<div class="cal-month-header">' + d + '</div>';
    });
    var firstWeekday = data.days.length > 0 ? data.days[0].weekday : 0;
    for (var i = 0; i < firstWeekday; i++) {
      html += '<div class="cal-month-cell cal-month-empty"></div>';
    }
    data.days.forEach(function(day) {
      var todayCls = day.is_today ? ' cal-day-today' : '';
      html += '<div class="cal-month-cell' + todayCls + '">' +
        '<div class="cal-month-day-num">' + day.day_num + '</div>';
      day.posts.slice(0, 3).forEach(function(p) { html += _calPostPill(p); });
      if (day.posts.length > 3) {
        html += '<div class="cal-more">+' + (day.posts.length - 3) + ' more</div>';
      }
      html += '</div>';
    });
    html += '</div>';
    return html;
  }

  function _calPostCard(p) {
    var status  = p.status || 'draft';
    var icon    = _calPlatformIcon[p.platform_target] || '📢';
    var time    = '';
    var dtSrc   = status === 'published' ? p.published_at : p.scheduled_for;
    if (dtSrc) {
      try { time = new Date(dtSrc).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); } catch(e) {}
    }
    var thumb = p.thumbnail_url
      ? '<img class="cal-thumb" src="' + _esc(p.thumbnail_url) + '" loading="lazy">'
      : '';
    var canReschedule = status !== 'published' && status !== 'publishing';
    var reschedBtn = canReschedule
      ? '<button class="cal-action-btn" title="Reschedule" onclick="window.calOpenReschedule(' +
          p.id + ',\'' + _esc(p.scheduled_for || '') + '\',\'' + _esc(p.title || '') + '\')">⏰</button>'
      : '';
    return '<div class="cal-post-card cal-status-' + _esc(status) + '">' +
      (thumb ? '<div>' + thumb + '</div>' : '') +
      '<div class="cal-card-title">' + icon + ' ' + _esc((p.title || '(untitled)').substring(0, 28)) + '</div>' +
      (time ? '<div class="cal-card-time">' + _esc(time) + '</div>' : '') +
      '<div class="cal-card-footer">' +
        '<span class="cal-badge cal-badge-' + _esc(status) + '">' + _esc(status) + '</span>' +
        reschedBtn +
      '</div>' +
    '</div>';
  }

  function _calPostPill(p) {
    var status = p.status || 'draft';
    var icon   = _calPlatformIcon[p.platform_target] || '📢';
    var canReschedule = status !== 'published' && status !== 'publishing';
    var clickAttr = canReschedule
      ? 'onclick="window.calOpenReschedule(' + p.id + ',\'' + _esc(p.scheduled_for || '') +
        '\',\'' + _esc(p.title || '') + '\')"'
      : '';
    return '<div class="cal-post-pill cal-status-' + _esc(status) + '" ' + clickAttr +
      ' title="' + _esc(p.title || '') + '">' +
      icon + ' ' + _esc((p.title || '(untitled)').substring(0, 18)) +
      '</div>';
  }

  async function _calLoadUpcoming() {
    var list  = $('#calUpcomingList');
    var empty = $('#calUpcomingEmpty');
    if (!list) return;
    try {
      var items = await fetchApi('/content/calendar/upcoming?' + _acctQs());
      if (!Array.isArray(items) || items.length === 0) {
        list.innerHTML = '';
        if (empty) empty.style.display = '';
        return;
      }
      if (empty) empty.style.display = 'none';
      list.innerHTML = items.map(function(p) {
        var icon = _calPlatformIcon[p.platform_target] || '📢';
        var dt   = p.scheduled_for ? new Date(p.scheduled_for) : null;
        var ts   = dt
          ? dt.toLocaleDateString('default', { month: 'short', day: 'numeric' }) + ' ' +
            dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          : '';
        return '<div class="cal-upcoming-item">' +
          '<span class="cal-upcoming-icon">' + icon + '</span>' +
          '<div class="cal-upcoming-info">' +
            '<div class="cal-upcoming-title">' + _esc(p.title || '(untitled)') + '</div>' +
            '<div class="cal-upcoming-time">' + _esc(ts) + '</div>' +
          '</div>' +
          '<button class="cal-action-btn" onclick="window.calOpenReschedule(' +
            p.id + ',\'' + _esc(p.scheduled_for || '') + '\',\'' + _esc(p.title || '') +
          '\')">Reschedule</button>' +
        '</div>';
      }).join('');
    } catch (e) { /* silently skip */ }
  }

  // Navigation helpers
  function _calNav(delta, unit) {
    if (!_calStart) return;
    var d = new Date(_calStart + 'T00:00:00');
    if (unit === 'day')   d.setDate(d.getDate() + delta);
    if (unit === 'week')  d.setDate(d.getDate() + delta * 7);
    if (unit === 'month') { d.setMonth(d.getMonth() + delta); d.setDate(1); }
    _calStart = d.toISOString().substring(0, 10);
    _calLoad();
  }

  window.calPrev  = function() { _calNav(-1, _calView); };
  window.calNext  = function() { _calNav(+1, _calView); };
  window.calToday = function() {
    _calStart = new Date().toISOString().substring(0, 10);
    _calLoad();
  };
  window.calSetView = function(v) {
    _calView = v;
    var bw = $('#calBtnWeek');
    var bm = $('#calBtnMonth');
    if (bw) bw.classList.toggle('active', v === 'week');
    if (bm) bm.classList.toggle('active', v === 'month');
    _calLoad();
  };

  window.calOpenReschedule = function(postId, currentDt, title) {
    _calRescheduleId = postId;
    var modal = $('#calModal');
    var input = $('#calModalDate');
    var titleEl = $('#calModalTitle');
    if (titleEl) titleEl.textContent = title || '';
    if (modal) modal.style.display = '';
    if (input && currentDt) {
      try {
        var d = new Date(currentDt);
        input.value =
          d.getFullYear() + '-' +
          String(d.getMonth() + 1).padStart(2, '0') + '-' +
          String(d.getDate()).padStart(2, '0') + 'T' +
          String(d.getHours()).padStart(2, '0') + ':' +
          String(d.getMinutes()).padStart(2, '0');
      } catch (e) { input.value = ''; }
    }
  };

  window.calCloseModal = function() {
    var modal = $('#calModal');
    if (modal) modal.style.display = 'none';
    _calRescheduleId = null;
  };

  window.calReschedule = async function() {
    if (!_calRescheduleId) return;
    var input = $('#calModalDate');
    if (!input || !input.value) { showToast('Please select a date and time.', 'warning'); return; }
    try {
      var res  = await fetch('/api/content/calendar/reschedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          account_id: currentAccountId || 1,
          post_id: _calRescheduleId,
          scheduled_for: input.value,
        }),
      });
      var data = await res.json();
      if (data.error) { showToast('Error: ' + data.error, 'error'); return; }
      showToast('Post rescheduled', 'success');
      window.calCloseModal();
      _calLoad();
    } catch (e) { showToast('Failed to reschedule.', 'error'); }
  };

  function _acctQs() {
    return currentAccountId ? 'account_id=' + currentAccountId : '';
  }

  function _esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  /* ─── Page Metadata ─── */
  var _pageMeta = {
    'overview':       { title: 'Overview',              subtitle: 'Growth Command Center',             icon: '◈' },
    'accounts':       { title: 'Accounts',              subtitle: 'Cross-account performance',         icon: '⊞' },
    'campaigns':      { title: 'Campaigns',             subtitle: 'Active campaigns & performance',    icon: '◫' },
    'budget':         { title: 'Budget Intelligence',   subtitle: 'Allocation & efficiency analysis',  icon: '◎' },
    'automation':     { title: 'Automation',            subtitle: 'Proposals & execution history',     icon: '⊗' },
    'creative':       { title: 'Creative Intelligence', subtitle: 'Asset performance & insights',      icon: '◇' },
    'content-studio': { title: 'Content Studio',        subtitle: 'Ideas · Creatives · Publishing',   icon: '◱' },
    'ai-coach':       { title: 'AI Coach',              subtitle: 'AI-powered performance insights',   icon: '◉' },
    'insights':       { title: 'Insights',              subtitle: 'Forecasts & cross-platform data',   icon: '◈' },
    'alerts':         { title: 'Alerts',                subtitle: 'Active system alerts',              icon: '◬' },
    'reports':        { title: 'Reports',               subtitle: 'Executive reporting suite',         icon: '▤'  },
    'copilot':        { title: 'AI Marketing Copilot',  subtitle: 'Ask anything about performance',   icon: '◆' },
    'integrations':   { title: 'Integrations',          subtitle: 'Connected platforms & credentials', icon: '⊕' },
    'billing':        { title: 'Billing',               subtitle: 'Plan usage & limits',               icon: '◐' },
  };

  /* ─── Accounts Page ─── */
  async function loadAccountsPage() {
    var loading = document.getElementById('acctCardsLoading');
    var list    = document.getElementById('acctCardsList');
    var empty   = document.getElementById('acctCardsEmpty');
    if (!loading) return;

    try {
      var accounts = _accountsCache.length ? _accountsCache : await fetchApi('/accounts');
      if (!_accountsCache.length && accounts.length) _accountsCache = accounts;

      loading.style.display = 'none';

      if (!accounts || accounts.length === 0) {
        if (empty) empty.style.display = '';
        return;
      }

      // Fetch health data to get scores + alert counts
      var health = [];
      try { health = (await fetchApi('/accounts/health')).accounts || []; } catch(e) {}

      var html = accounts.map(function(acc) {
        var h = health.find(function(x) { return x.id == acc.id; }) || {};
        var score    = h.growth_score || 0;
        var alerts   = h.active_alerts || 0;
        var spend7d  = h.spend_last_7_days || 0;
        var scoreClass = score >= 70 ? 'good' : score >= 40 ? 'mid' : 'bad';
        var statusDot  = acc.status === 'active' ? 'active' : acc.status === 'paused' ? 'paused' : 'inactive';
        var platClass  = acc.platform === 'google' ? 'google' : '';
        var alertsClass = alerts > 0 ? '' : ' none';
        var syncText = acc.last_sync ? _relativeTime(acc.last_sync) : 'Never synced';

        return [
          '<div class="acct-card ' + platClass + '">',
            '<div class="acct-card-top">',
              '<span class="acct-card-plat ' + platClass + '">' + (acc.platform === 'google' ? 'Google' : 'Meta') + '</span>',
              '<span class="acct-card-name" title="' + _escCC(acc.account_name) + '">' + _escCC(acc.account_name) + '</span>',
              '<span class="acct-card-status-dot ' + statusDot + '"></span>',
            '</div>',
            '<div class="acct-card-stats">',
              '<div><div class="acct-card-stat-val">' + score + '</div><div class="acct-card-stat-key">Growth Score</div></div>',
              '<div><div class="acct-card-stat-val">' + alerts + '</div><div class="acct-card-stat-key">Active Alerts</div></div>',
              '<div><div class="acct-card-stat-val">' + _fmtCCMoney(spend7d) + '</div><div class="acct-card-stat-key">Spend 7d</div></div>',
              '<div><div class="acct-card-stat-val ' + scoreClass + '">' + (h.growth_label || '—') + '</div><div class="acct-card-stat-key">Status</div></div>',
            '</div>',
            '<div class="acct-card-footer">',
              '<span class="acct-card-sync">Synced: ' + syncText + '</span>',
              '<span class="acct-card-alerts' + alertsClass + '">' + alerts + ' alert' + (alerts !== 1 ? 's' : '') + '</span>',
            '</div>',
          '</div>',
        ].join('');
      }).join('');

      if (list) { list.innerHTML = html; list.style.display = ''; }
    } catch (e) {
      if (loading) loading.style.display = 'none';
      if (empty)   empty.style.display   = '';
    }
  }

  function _relativeTime(isoStr) {
    try {
      var dt    = new Date(isoStr);
      var now   = new Date();
      var secs  = Math.floor((now - dt) / 1000);
      if (secs < 60)   return secs + 's ago';
      if (secs < 3600) return Math.floor(secs / 60) + 'm ago';
      if (secs < 86400) return Math.floor(secs / 3600) + 'h ago';
      return Math.floor(secs / 86400) + 'd ago';
    } catch(e) { return isoStr; }
  }

  /* ─── Campaign Filters & Drill Panel ─── */
  var _campData            = { meta: [], google: [] }; // local cache of rendered campaign data
  var _creativeData        = [];                        // local cache for creative filter re-renders
  var _currentDrillCampaign = null;                    // campaign object currently open in drill

  /* Campaign Health Score — purely from campaign object fields, returns {score, tier, color} */
  function _campHealthScore(campaign) {
    var score = 0;
    // CTR contribution (0-30)
    var ctr = campaign.ctr || 0;
    if      (ctr >= 2.0) score += 30;
    else if (ctr >= 1.5) score += 24;
    else if (ctr >= 1.0) score += 18;
    else if (ctr >= 0.5) score += 10;
    else                 score += 0;
    // ROAS contribution (0-35)
    var roas = campaign.roas || 0;
    if      (roas >= 4.0) score += 35;
    else if (roas >= 3.0) score += 30;
    else if (roas >= 2.0) score += 22;
    else if (roas >= 1.0) score += 12;
    else                  score += 0;
    // Conversions contribution (0-20)
    var conv = campaign.conversions || 0;
    if      (conv >= 20) score += 20;
    else if (conv >= 5)  score += 14;
    else if (conv > 0)   score += 8;
    // Status contribution (0-15)
    var st = (campaign.status || '').toUpperCase();
    if      (st === 'ACTIVE') score += 15;
    else if (st === 'PAUSED') score += 5;

    score = Math.min(100, Math.max(0, score));
    var tier, color;
    if      (score >= 85) { tier = 'Elite';    color = '#10b981'; }
    else if (score >= 65) { tier = 'Strong';   color = '#3b82f6'; }
    else if (score >= 45) { tier = 'Stable';   color = '#f59e0b'; }
    else if (score >= 25) { tier = 'Weak';     color = '#f97316'; }
    else                  { tier = 'Critical'; color = '#ef4444'; }
    return { score: score, tier: tier, color: color };
  }

  function _initCampaignFilters() {
    var bar = document.getElementById('campFilterBar');
    if (!bar || bar.dataset.initialized) return;
    bar.dataset.initialized = '1';

    var activePlatform = 'all';
    var activeStatus   = 'all';

    function _updateClearBtn() {
      var clearBtn = document.getElementById('campFilterClear');
      var searchEl = document.getElementById('campSearch');
      if (!clearBtn) return;
      var hasFilter = activePlatform !== 'all' || activeStatus !== 'all' || (searchEl && searchEl.value.trim() !== '');
      clearBtn.style.display = hasFilter ? '' : 'none';
    }

    function _clear() {
      activePlatform = 'all';
      activeStatus   = 'all';
      var searchEl = document.getElementById('campSearch');
      if (searchEl) searchEl.value = '';
      bar.querySelectorAll('[data-camp-platform]').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-camp-platform') === 'all');
      });
      bar.querySelectorAll('[data-camp-status]').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-camp-status') === 'all');
      });
      _applyFilters('all', 'all', '');
      _updateClearBtn();
    }

    // Platform buttons
    bar.querySelectorAll('[data-camp-platform]').forEach(function(btn) {
      btn.addEventListener('click', function() {
        bar.querySelectorAll('[data-camp-platform]').forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
        activePlatform = btn.getAttribute('data-camp-platform');
        var searchEl = document.getElementById('campSearch');
        _applyFilters(activePlatform, activeStatus, searchEl ? searchEl.value.toLowerCase().trim() : '');
        _updateClearBtn();
      });
    });

    // Status buttons
    bar.querySelectorAll('[data-camp-status]').forEach(function(btn) {
      btn.addEventListener('click', function() {
        bar.querySelectorAll('[data-camp-status]').forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
        activeStatus = btn.getAttribute('data-camp-status');
        var searchEl = document.getElementById('campSearch');
        _applyFilters(activePlatform, activeStatus, searchEl ? searchEl.value.toLowerCase().trim() : '');
        _updateClearBtn();
      });
    });

    // Search
    var search = document.getElementById('campSearch');
    if (search) {
      search.addEventListener('input', function() {
        _applyFilters(activePlatform, activeStatus, this.value.toLowerCase().trim());
        _updateClearBtn();
      });
    }

    // Clear button
    var clearBtn = document.getElementById('campFilterClear');
    if (clearBtn) clearBtn.addEventListener('click', _clear);

    // Expose globally so no-results CTA can call it
    window._clearCampaignFilters = _clear;
  }

  function _applyFilters(platform, status, q) {
    var googleSection = document.getElementById('googleSection');
    var countEl       = document.getElementById('campFilterCount');
    var noResults     = document.getElementById('campNoResults');
    q = q || '';

    function filterAndRender(data, tbodyId, showActions) {
      var filtered = data.filter(function(c) {
        var matchStatus = status === 'all' || (c.status || '').toUpperCase() === status;
        var matchSearch = !q || c.name.toLowerCase().includes(q);
        return matchStatus && matchSearch;
      });
      renderCampaignTable(filtered, tbodyId, showActions);
      return filtered.length;
    }

    var metaCount   = 0;
    var googleCount = 0;

    if (platform === 'all' || platform === 'meta') {
      metaCount = filterAndRender(_campData.meta, 'metaTableBody', true);
    } else {
      var metaTbody = document.getElementById('metaTableBody');
      if (metaTbody) metaTbody.innerHTML = '';
    }

    if (platform === 'all' || platform === 'google') {
      googleCount = filterAndRender(_campData.google, 'googleTableBody', false);
      if (googleSection) googleSection.style.display = googleCount > 0 ? '' : 'none';
    } else {
      if (googleSection) googleSection.style.display = 'none';
    }

    var total = metaCount + googleCount;
    if (countEl) countEl.textContent = total + ' campaign' + (total !== 1 ? 's' : '');
    if (noResults) noResults.style.display = total === 0 ? '' : 'none';
  }

  // Expose drill close globally
  window._closeCampaignDrill = function() {
    var panel = document.getElementById('campDrillPanel');
    if (panel) panel.style.display = 'none';
    document.querySelectorAll('#metaTable tbody tr.selected, #googleTable tbody tr.selected').forEach(function(r) {
      r.classList.remove('selected');
    });
  };

  function _openCampaignDrill(campaign, platform) {
    var panel = document.getElementById('campDrillPanel');
    if (!panel) return;

    // Store for lazy tab loads
    _currentDrillCampaign = campaign;

    // ── Header ────────────────────────────────────────────────────────────────
    var platEl   = document.getElementById('campDrillPlatform');
    var statusEl = document.getElementById('campDrillStatus');
    var title    = document.getElementById('campDrillTitle');

    if (platEl) {
      platEl.textContent = platform === 'google' ? 'Google' : 'Meta';
      platEl.className   = 'camp-drill-platform camp-drill-platform-' + platform;
    }
    if (statusEl) {
      statusEl.textContent = (campaign.status || 'UNKNOWN').toUpperCase();
      statusEl.className   = 'camp-drill-status-badge status-badge ' + statusClass(campaign.status);
    }
    if (title) title.textContent = campaign.name;

    // ── Quick-action buttons ──────────────────────────────────────────────────
    var coachBtn = document.getElementById('campDrillCoachBtn');
    var autoBtn  = document.getElementById('campDrillAutoBtn');
    if (coachBtn) coachBtn.onclick = function() { window.a7Navigate('ai-coach'); };
    if (autoBtn)  autoBtn.onclick  = function() { window.a7Navigate('automation'); };

    // ── KPI stats row ─────────────────────────────────────────────────────────
    var stats = document.getElementById('campDrillStats');
    if (stats) {
      var roasVal = (campaign.roas != null && campaign.roas > 0)
        ? campaign.roas.toFixed(2) + 'x' : '—';
      stats.innerHTML = [
        '<div class="camp-drill-stat"><div class="camp-drill-stat-val">' + fmtMoney(campaign.spend)  + '</div><div class="camp-drill-stat-key">Spend</div></div>',
        '<div class="camp-drill-stat"><div class="camp-drill-stat-val">' + fmtPct(campaign.ctr)      + '</div><div class="camp-drill-stat-key">CTR</div></div>',
        '<div class="camp-drill-stat"><div class="camp-drill-stat-val">' + fmt(campaign.conversions) + '</div><div class="camp-drill-stat-key">Conv.</div></div>',
        '<div class="camp-drill-stat"><div class="camp-drill-stat-val">' + fmtMoney(campaign.cpa)    + '</div><div class="camp-drill-stat-key">CPA</div></div>',
        '<div class="camp-drill-stat"><div class="camp-drill-stat-val">' + roasVal                   + '</div><div class="camp-drill-stat-key">ROAS</div></div>',
      ].join('');
    }

    // ── Campaign Health Score band (initial — signal penalties applied later) ─
    _renderDrillHealth(_campHealthScore(campaign), null, null);

    // ── Recommended Actions block ─────────────────────────────────────────────
    _renderDrillActions(campaign);

    // ── Tab switching (bound once; depth tab triggers lazy load) ─────────────
    var tabsEl   = document.getElementById('campDrillTabs');
    var depthEl  = document.getElementById('campDrillDepth');
    if (tabsEl && !tabsEl.dataset.bound) {
      tabsEl.dataset.bound = '1';
      tabsEl.querySelectorAll('.camp-drill-tab').forEach(function(tab) {
        tab.addEventListener('click', function() {
          tabsEl.querySelectorAll('.camp-drill-tab').forEach(function(t) { t.classList.remove('active'); });
          tab.classList.add('active');
          var target = tab.getAttribute('data-drill-tab');
          document.querySelectorAll('.camp-drill-tab-body').forEach(function(b) {
            b.classList.toggle('active', b.id === 'campDrill' + target.charAt(0).toUpperCase() + target.slice(1));
          });
          // Lazy-load Ad Depth on first click
          if (target === 'depth') {
            var de = document.getElementById('campDrillDepth');
            if (de && !de.dataset.loaded && _currentDrillCampaign) {
              _loadDrillDepth(_currentDrillCampaign);
            }
          }
        });
      });
    }

    // Reset to Signals tab; mark depth as unloaded for new campaign
    if (tabsEl) {
      tabsEl.querySelectorAll('.camp-drill-tab').forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-drill-tab') === 'signals');
      });
      document.querySelectorAll('.camp-drill-tab-body').forEach(function(b) {
        b.classList.toggle('active', b.id === 'campDrillSignals');
      });
    }
    if (depthEl) {
      delete depthEl.dataset.loaded;
      depthEl.innerHTML =
        '<div class="camp-drill-depth-placeholder">' +
          '<div class="camp-drill-depth-icon">◈</div>' +
          '<div class="camp-drill-depth-title">Ad Sets &amp; Creatives</div>' +
          '<div class="camp-drill-depth-note">Click this tab to load ad depth data.</div>' +
        '</div>';
    }

    // ── Show panel ────────────────────────────────────────────────────────────
    panel.style.display = '';
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // ── Signals ───────────────────────────────────────────────────────────────
    _loadDrillSignals(campaign);
  }

  /* Render health band — called once immediately (no signals) then again after signals load */
  function _renderDrillHealth(hs, alertCount, proposalCount) {
    var el = document.getElementById('campDrillHealth');
    if (!el) return;

    var pillsHtml = '';
    if (alertCount !== null) {
      var ac = alertCount > 0 ? '#ef4444' : '#10b981';
      pillsHtml += '<span class="camp-drill-health-pill" style="background:' + ac + '1a;color:' + ac + '">' +
        alertCount + ' alert' + (alertCount !== 1 ? 's' : '') + '</span>';
    }
    if (proposalCount !== null) {
      var pc = proposalCount > 0 ? '#f59e0b' : '#5d7499';
      pillsHtml += '<span class="camp-drill-health-pill" style="background:' + pc + '1a;color:' + pc + '">' +
        proposalCount + ' proposal' + (proposalCount !== 1 ? 's' : '') + '</span>';
    }

    el.innerHTML =
      '<div class="camp-drill-health-inner">' +
        '<div class="camp-drill-health-left">' +
          '<span class="camp-drill-health-score" style="color:' + hs.color + '">' + hs.score + '</span>' +
          '<span class="camp-drill-health-label">/ 100</span>' +
          '<span class="camp-drill-health-tier" style="background:' + hs.color + '22;color:' + hs.color + '">' + hs.tier + '</span>' +
        '</div>' +
        '<div class="camp-drill-health-bar-wrap">' +
          '<div class="camp-drill-health-bar-track">' +
            '<div class="camp-drill-health-bar-fill" style="width:' + hs.score + '%;background:' + hs.color + '"></div>' +
          '</div>' +
          '<div class="camp-drill-health-bar-footer">' +
            '<span class="camp-drill-health-desc">Campaign Health</span>' +
            pillsHtml +
          '</div>' +
        '</div>' +
      '</div>';
  }

  /* Health score recalculated after signals are known */
  function _campHealthScoreWithSignals(campaign, alerts, proposals) {
    var hs    = _campHealthScore(campaign);
    var score = hs.score;
    // Alert penalties
    alerts.forEach(function(a) {
      if      (a.severity === 'critical') score -= 15;
      else if (a.severity === 'warning')  score -= 8;
      else if (a.severity === 'info')     score -= 3;
    });
    // Approved proposals mean action is already being taken — small boost
    var approved = proposals.filter(function(p) { return p.status === 'approved'; }).length;
    if (approved > 0) score += 5;
    score = Math.min(100, Math.max(0, score));

    var tier, color;
    if      (score >= 85) { tier = 'Elite';    color = '#10b981'; }
    else if (score >= 65) { tier = 'Strong';   color = '#3b82f6'; }
    else if (score >= 45) { tier = 'Stable';   color = '#f59e0b'; }
    else if (score >= 25) { tier = 'Weak';     color = '#f97316'; }
    else                  { tier = 'Critical'; color = '#ef4444'; }
    return { score: score, tier: tier, color: color };
  }

  /* Recommended Actions block */
  function _renderDrillActions(campaign) {
    var el = document.getElementById('campDrillActions');
    if (!el) return;

    var actions = [
      { icon: '◎', label: 'AI Coach',             desc: 'Get AI-powered optimisation recommendations', page: 'ai-coach' },
      { icon: '⚡', label: 'Automation Proposals', desc: 'View or create proposals for this campaign',  page: 'automation' },
      { icon: '◇', label: 'Content Studio',        desc: 'Create content inspired by this campaign',   page: 'content-studio' },
      { icon: '▲',  label: 'Budget Intelligence',  desc: 'Analyse budget efficiency and pacing',        page: 'budget' },
      { icon: '◈', label: 'Alerts',                desc: 'Review all active alerts for this account',  page: 'alerts' },
    ];

    var html = '<div class="camp-drill-actions-header">Recommended Actions</div><div class="camp-drill-actions-list">';
    actions.forEach(function(a) {
      html +=
        '<button class="camp-drill-action-item" onclick="window._drillNav(\'' + a.page + '\')">' +
          '<span class="camp-drill-action-icon">' + a.icon + '</span>' +
          '<span class="camp-drill-action-text">' +
            '<span class="camp-drill-action-label">' + a.label + '</span>' +
            '<span class="camp-drill-action-desc">' + a.desc + '</span>' +
          '</span>' +
        '</button>';
    });
    html += '</div>';
    el.innerHTML = html;
  }

  window._drillNav = function(page) { window.a7Navigate && window.a7Navigate(page); };

  function _loadDrillSignals(campaign) {
    var sigEl = document.getElementById('campDrillSignals');
    var loadEl = document.getElementById('campDrillSigLoading');
    if (!sigEl) return;

    if (loadEl) loadEl.style.display = '';

    var qs = acctParam();
    Promise.all([
      fetchApi('/alerts?limit=100' + qs).catch(function() { return { alerts: [] }; }),
      fetchApi('/automation/actions?limit=100' + qs).catch(function() { return { actions: [] }; }),
    ]).then(function(results) {
      var allAlerts  = (results[0].alerts  || []).filter(function(a) {
        return (a.entity_name || '').toLowerCase() === (campaign.name || '').toLowerCase();
      });
      var allActions = (results[1].actions || []).filter(function(a) {
        return (a.entity_name || '').toLowerCase() === (campaign.name || '').toLowerCase();
      });

      // Re-render health score with signal penalties and pill counts
      _renderDrillHealth(
        _campHealthScoreWithSignals(campaign, allAlerts, allActions),
        allAlerts.length,
        allActions.length
      );

      var html = '';

      // Alerts section
      html += '<div class="camp-drill-sig-section">';
      html += '<div class="camp-drill-sig-header">Active Alerts <span class="camp-drill-sig-count">' + allAlerts.length + '</span></div>';
      if (allAlerts.length === 0) {
        html += '<div class="camp-drill-sig-empty">No active alerts for this campaign.</div>';
      } else {
        allAlerts.forEach(function(a) {
          html += '<div class="camp-drill-sig-item sev-' + (a.severity || 'info') + '">' +
            '<span class="camp-drill-sig-sev">' + (a.severity || 'info') + '</span>' +
            '<div class="camp-drill-sig-content">' +
              '<div class="camp-drill-sig-title">' + _escCC(a.title || '') + '</div>' +
              '<div class="camp-drill-sig-msg">' + _escCC(a.message || '') + '</div>' +
            '</div></div>';
        });
      }
      html += '</div>';

      // Automation proposals section
      html += '<div class="camp-drill-sig-section">';
      html += '<div class="camp-drill-sig-header">Automation Proposals <span class="camp-drill-sig-count">' + allActions.length + '</span></div>';
      if (allActions.length === 0) {
        html += '<div class="camp-drill-sig-empty">No pending proposals for this campaign.</div>';
      } else {
        allActions.forEach(function(a) {
          var pct  = a.suggested_change_pct ? (a.suggested_change_pct > 0 ? '+' : '') + a.suggested_change_pct + '%' : '';
          var conf = a.confidence ? Math.round(a.confidence * 100) + '%' : '';
          html += '<div class="camp-drill-sig-item auto-' + (a.status || 'proposed') + '">' +
            '<span class="camp-drill-sig-sev auto">' + (a.status || 'proposed') + '</span>' +
            '<div class="camp-drill-sig-content">' +
              '<div class="camp-drill-sig-title">' + _escCC(a.action_type || '') + (pct ? ' <span class="camp-drill-sig-pct">' + pct + '</span>' : '') + '</div>' +
              '<div class="camp-drill-sig-msg">' + _escCC(a.reason || '') + (conf ? ' <span class="camp-drill-sig-conf">confidence: ' + conf + '</span>' : '') + '</div>' +
            '</div></div>';
        });
      }
      html += '</div>';

      if (loadEl) loadEl.style.display = 'none';
      sigEl.innerHTML = html;
    });
  }

  function _loadDrillDepth(campaign) {
    var depthEl = document.getElementById('campDrillDepth');
    if (!depthEl) return;

    depthEl.dataset.loaded = '1';
    depthEl.innerHTML = '<div class="camp-drill-sig-loading">Loading ad depth…</div>';

    var campId = campaign.id || '';
    var qs     = acctParam();

    Promise.all([
      fetchApi('/campaigns/' + encodeURIComponent(campId) + '/adsets').catch(function() { return { ad_sets: [] }; }),
      fetchApi('/creatives?campaign=' + encodeURIComponent(campId) + '&days=7' + qs).catch(function() { return { creatives: [] }; }),
    ]).then(function(results) {
      var adSets    = results[0].ad_sets  || [];
      var creatives = results[1].creatives || [];

      if (adSets.length === 0 && creatives.length === 0) {
        depthEl.innerHTML =
          '<div class="camp-drill-depth-placeholder">' +
            '<div class="camp-drill-depth-icon">◈</div>' +
            '<div class="camp-drill-depth-title">No Ad Depth Data</div>' +
            '<div class="camp-drill-depth-note">Connect a live Meta Ads account to unlock ad set performance, creative thumbnails, and per-ad analytics.</div>' +
            '<button class="camp-drill-depth-cta" onclick="window._drillNav(\'accounts\')">Connect Account →</button>' +
          '</div>';
        return;
      }

      // ── Helpers ─────────────────────────────────────────────────────────────
      function _adsetScore(a) {
        // Higher is better: weigh conversions first, then CTR
        return (a.conversions || 0) * 100 + (a.ctr || 0);
      }
      function _crScore(cr) {
        return (cr.total_conversions || 0) * 100 + (cr.avg_ctr || cr.ctr || 0);
      }
      function _isFatigued(cr) {
        return (cr.avg_frequency || 0) > 3 || (cr.max_frequency || 0) > 5;
      }
      function _renderCreativeCard(cr, isBest) {
        var thumb = cr.thumbnail_url
          ? '<img src="' + _escCC(cr.thumbnail_url) + '" class="camp-drill-creative-thumb" loading="lazy" onerror="this.style.display=\'none\'">'
          : '<div class="camp-drill-creative-thumb-empty">◻</div>';
        var badges = '';
        if (isBest)         badges += '<span class="camp-drill-badge camp-drill-badge-best">Best</span>';
        if (_isFatigued(cr)) badges += '<span class="camp-drill-badge camp-drill-badge-fatigue">Fatigue</span>';
        return '<div class="camp-drill-creative-card' + (isBest ? ' camp-drill-creative-card-best' : '') + '">' +
          thumb +
          '<div class="camp-drill-creative-meta">' +
            (badges ? '<div class="camp-drill-creative-badges">' + badges + '</div>' : '') +
            '<div class="camp-drill-creative-name" title="' + _escCC(cr.creative_name || '') + '">' + _escCC(cr.creative_name || 'Untitled') + '</div>' +
            '<div class="camp-drill-creative-stats">' +
              '<span>CTR ' + fmtPct(cr.avg_ctr || cr.ctr || 0) + '</span>' +
              '<span>Conv. ' + fmt(cr.total_conversions || 0) + '</span>' +
              '<span>CPA ' + (cr.cpa ? fmtMoney(cr.cpa) : '—') + '</span>' +
            '</div>' +
          '</div>' +
        '</div>';
      }

      var html = '';

      // ── Ad Sets section ──────────────────────────────────────────────────────
      if (adSets.length > 0) {
        // Find best ad set (by score)
        var bestAdsetIdx = 0;
        adSets.forEach(function(a, i) { if (_adsetScore(a) > _adsetScore(adSets[bestAdsetIdx])) bestAdsetIdx = i; });

        // Build creative lookup by adset_id, sorted by score desc
        var creativesByAdset = {};
        creatives.forEach(function(c) {
          var aid = c.adset_id || '';
          if (!creativesByAdset[aid]) creativesByAdset[aid] = [];
          creativesByAdset[aid].push(c);
        });
        Object.keys(creativesByAdset).forEach(function(aid) {
          creativesByAdset[aid].sort(function(a, b) { return _crScore(b) - _crScore(a); });
        });

        html += '<div class="camp-drill-sig-section">';
        html += '<div class="camp-drill-sig-header">Ad Sets <span class="camp-drill-sig-count">' + adSets.length + '</span></div>';

        adSets.forEach(function(a, idx) {
          var isTop = idx === bestAdsetIdx && adSets.length > 1;
          var sc    = statusClass(a.status);
          html +=
            '<div class="camp-drill-adset-card' + (isTop ? ' camp-drill-adset-card-top' : '') + '">' +
              '<div class="camp-drill-adset-header">' +
                '<span class="status-dot ' + sc + '"></span>' +
                '<span class="camp-drill-adset-name">' + _escCC(a.name || '—') + '</span>' +
                (isTop ? '<span class="camp-drill-badge camp-drill-badge-top">Top</span>' : '') +
              '</div>' +
              '<div class="camp-drill-adset-kpis">' +
                '<div class="camp-drill-adset-kpi"><span class="camp-drill-adset-kv">' + fmtMoney(a.spend || 0) + '</span><span class="camp-drill-adset-kl">Spend</span></div>' +
                '<div class="camp-drill-adset-kpi"><span class="camp-drill-adset-kv">' + fmtPct(a.ctr || 0)    + '</span><span class="camp-drill-adset-kl">CTR</span></div>' +
                '<div class="camp-drill-adset-kpi"><span class="camp-drill-adset-kv">' + fmt(a.conversions || 0) + '</span><span class="camp-drill-adset-kl">Conv.</span></div>' +
                '<div class="camp-drill-adset-kpi"><span class="camp-drill-adset-kv">' + (a.cpa ? fmtMoney(a.cpa) : '—') + '</span><span class="camp-drill-adset-kl">CPA</span></div>' +
              '</div>';

          // Nested creatives
          var ads = creativesByAdset[a.id] || [];
          if (ads.length > 0) {
            html += '<div class="camp-drill-creative-grid">';
            ads.forEach(function(cr, ci) {
              html += _renderCreativeCard(cr, ci === 0 && ads.length > 1);
            });
            html += '</div>';
          }
          html += '</div>'; // close adset-card
        });
        html += '</div>'; // close sig-section
      }

      // ── Flat creatives (no adset data from live API) ─────────────────────────
      if (adSets.length === 0 && creatives.length > 0) {
        var sortedCrs = creatives.slice().sort(function(a, b) { return _crScore(b) - _crScore(a); });
        html += '<div class="camp-drill-sig-section">';
        html += '<div class="camp-drill-sig-header">Creatives (Cached) <span class="camp-drill-sig-count">' + sortedCrs.length + '</span></div>';
        html += '<div class="camp-drill-creative-grid">';
        sortedCrs.forEach(function(cr, ci) {
          html += _renderCreativeCard(cr, ci === 0 && sortedCrs.length > 1);
        });
        html += '</div></div>';
      }

      depthEl.innerHTML = html || '<div class="camp-drill-sig-empty">No ad depth data available.</div>';
    });
  }

  /* ─── Command Center ─── */
  async function loadCommandCenter() {
    var loadWrap = document.getElementById('ccLoading');
    var content  = document.getElementById('ccContent');
    if (!loadWrap || !content) return;
    loadWrap.style.display = '';
    content.style.display  = 'none';

    try {
      var qs  = currentAccountId ? '?account_id=' + encodeURIComponent(currentAccountId) : '';
      var res = await fetch('/api/command-center' + qs);
      var data = await res.json();
      if (!res.ok) throw new Error(data.error || 'API error');

      _renderCCPulse(data.insights || [], data.period_comparison || null);
      _renderCCKpis(data.kpis, data.kpi_source, data.trend_days_available);
      _renderCCTrends(data.trend || []);
      _renderCCTopCamps(data.top_campaigns || []);
      _renderCCWorst(data.worst_campaigns || []);
      _renderCCDist(data.campaign_distribution || {});
      _renderCCAlertCluster(data.alert_severity || {});
      _renderCCAttention(data.attention);
      _renderCCOpps(data.opportunities || []);
      _renderCCHealth(data.health);

      loadWrap.style.display = 'none';
      content.style.display  = '';
    } catch (e) {
      loadWrap.innerHTML = '<div class="cc-empty">Failed to load command center — ' + _escCC(String(e.message)) + '</div>';
    }
  }

  /* ─── Command Center: Performance Pulse Strip ─── */

  var _PULSE_ICONS = {
    critical: '●',
    negative: '▼',
    warning:  '◬',
    positive: '▲',
    neutral:  '◆',
  };

  function _pulseDir(ch) {
    if (ch === null || ch === undefined) return 'flat';
    return ch > 0 ? 'up' : ch < 0 ? 'down' : 'flat';
  }

  function _pulseFmt(ch, invertSign) {
    // invertSign=true for metrics where up is bad (CPA, CPC)
    if (ch === null || ch === undefined) return null;
    var sign = ch > 0 ? '+' : '';
    var dir  = invertSign ? (ch > 0 ? 'down' : ch < 0 ? 'up' : 'flat') : _pulseDir(ch);
    return { text: sign + ch.toFixed(1) + '%', dir: dir };
  }

  function _renderCCPulse(insights, comparison) {
    var strip   = document.getElementById('ccPulseStrip');
    var deltas  = document.getElementById('ccPulseDeltas');
    var list    = document.getElementById('ccPulseList');
    if (!strip) return;

    // Hide strip when there's nothing to show
    if (!insights.length && !comparison) { strip.style.display = 'none'; return; }
    strip.style.display = '';

    // ── Period delta summary (compact badges) ──────────────────────────────
    if (deltas && comparison && comparison.changes) {
      var ch = comparison.changes;
      var badges = [
        { label: 'Spend',  fmt: _pulseFmt(ch.spend, false) },
        { label: 'Conv',   fmt: _pulseFmt(ch.conversions, false) },
        { label: 'CPA',    fmt: _pulseFmt(ch.cpa, true) },
        { label: 'CTR',    fmt: _pulseFmt(ch.ctr, false) },
        { label: 'CPC',    fmt: _pulseFmt(ch.cpc, true) },
      ].filter(function(b) { return b.fmt !== null; });

      deltas.innerHTML = badges.map(function(b) {
        if (!b.fmt) return '';
        return (
          '<span class="cc-pulse-delta ' + b.fmt.dir + '">' +
            b.label + ' ' + b.fmt.text +
          '</span>'
        );
      }).join('');
    }

    // ── Insight rows ──────────────────────────────────────────────────────
    if (!list) return;
    if (!insights.length) {
      list.innerHTML = '<div class="cc-pulse-empty">No significant changes detected vs. prior period.</div>';
      return;
    }

    var _STATE_LABELS = { 'new': 'NEW', persistent: 'Persistent', reviewed: 'Reviewed', resolved: 'Resolved', recovered: 'Recovered' };
    var _STATE_CSS    = { 'new': 'state-new', persistent: 'state-persistent', reviewed: 'state-reviewed', resolved: 'state-resolved', recovered: 'state-recovered' };

    list.innerHTML = insights.map(function(ins) {
      var icon    = _PULSE_ICONS[ins.signal] || '◆';
      var destMap = { budget: 'budget', campaigns: 'campaigns', creative: 'creative', 'ai-coach': 'ai-coach', alerts: 'alerts' };
      var dest    = destMap[ins.action_page] || ins.action_page || 'overview';

      var state   = ins._state || null;
      var dbId    = ins._db_id || null;
      var occ     = ins._occurrence_count || 1;
      var daysAct = ins._days_active || 0;

      var stateBadge = state
        ? '<span class="cc-pulse-state-badge ' + _escCC(_STATE_CSS[state] || '') + '">' + _escCC(_STATE_LABELS[state] || state) + '</span>'
        : '';

      var metaParts = [];
      if (daysAct > 0) metaParts.push('Active ' + daysAct + 'd');
      if (occ > 1)     metaParts.push(occ + 'x seen');
      var meta = metaParts.length
        ? '<span class="cc-pulse-meta">' + metaParts.join(' · ') + '</span>'
        : '';

      var stateActions = '';
      if (dbId && state && state !== 'resolved') {
        var acctId = currentAccountId || 1;
        stateActions = (
          (state !== 'reviewed'
            ? '<button class="cc-pulse-state-btn reviewed" onclick="ccPulseMarkReviewed(' + dbId + ',' + acctId + ',this)">Mark Reviewed</button>'
            : '') +
          '<button class="cc-pulse-state-btn resolved" onclick="ccPulseMarkResolved(' + dbId + ',' + acctId + ',this)">Resolve</button>'
        );
      }

      var histToggle = (dbId && occ > 1)
        ? '<button class="cc-pulse-history-btn" onclick="ccPulseToggleHistory(this,' + dbId + ',' + (currentAccountId || 1) + ')">History ▾</button>'
        : '';

      return [
        '<div class="cc-pulse-row" data-signal="' + _escCC(ins.signal) + '" data-db-id="' + (dbId || '') + '">',
          '<span class="cc-pulse-sig-bar"></span>',
          '<span class="cc-pulse-icon ' + _escCC(ins.signal) + '">' + icon + '</span>',
          '<div class="cc-pulse-text">',
            '<div class="cc-pulse-title-row">',
              '<span class="cc-pulse-title">' + _escCC(ins.title) + '</span>',
              stateBadge,
              meta,
            '</div>',
            '<div class="cc-pulse-body">' + _escCC(ins.body) + '</div>',
            stateActions ? '<div class="cc-pulse-state-actions">' + stateActions + '</div>' : '',
            '<div class="cc-pulse-history-drawer" style="display:none"></div>',
          '</div>',
          ins.metric
            ? '<span class="cc-pulse-metric ' + _escCC(ins.signal) + '">' + _escCC(ins.metric) + '</span>'
            : '',
          '<div class="cc-pulse-right-actions">',
            histToggle,
            '<button class="cc-pulse-action" onclick="window.a7Navigate&&window.a7Navigate(\'' + _escCC(dest) + '\')">' +
              _escCC(ins.action_label) + ' →' +
            '</button>',
          '</div>',
        '</div>',
      ].join('');
    }).join('');
  }

  window.ccPulseMarkReviewed = function(id, accountId, btn) {
    var row = btn.closest && btn.closest('.cc-pulse-row');
    fetch('/api/insights/' + id + '/reviewed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_id: accountId }),
    }).then(function(r) { return r.json(); }).then(function(data) {
      if (data.status === 'reviewed' && row) {
        var badge = row.querySelector('.cc-pulse-state-badge');
        if (badge) { badge.className = 'cc-pulse-state-badge state-reviewed'; badge.textContent = 'Reviewed'; }
        var rb = row.querySelector('.cc-pulse-state-btn.reviewed');
        if (rb) rb.remove();
      }
    }).catch(function() {});
  };

  window.ccPulseMarkResolved = function(id, accountId, btn) {
    var row = btn.closest && btn.closest('.cc-pulse-row');
    fetch('/api/insights/' + id + '/resolved', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_id: accountId }),
    }).then(function(r) { return r.json(); }).then(function(data) {
      if (data.status === 'resolved' && row) {
        row.style.opacity = '0.45';
        var badge = row.querySelector('.cc-pulse-state-badge');
        if (badge) { badge.className = 'cc-pulse-state-badge state-resolved'; badge.textContent = 'Resolved'; }
        var sa = row.querySelector('.cc-pulse-state-actions');
        if (sa) sa.remove();
      }
    }).catch(function() {});
  };

  window.ccPulseToggleHistory = function(btn, id, accountId) {
    var row    = btn.closest && btn.closest('.cc-pulse-row');
    var drawer = row && row.querySelector('.cc-pulse-history-drawer');
    if (!drawer) return;
    if (drawer.style.display !== 'none') {
      drawer.style.display = 'none';
      btn.textContent = 'History ▾';
      return;
    }
    btn.textContent = 'Loading…';
    fetch('/api/insights/' + id + '/history?account_id=' + accountId)
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var entries = data.history || [];
        if (!entries.length) {
          drawer.innerHTML = '<div class="cc-history-empty">No prior occurrences recorded.</div>';
        } else {
          drawer.innerHTML = entries.slice().reverse().map(function(e) {
            return (
              '<div class="cc-history-entry">' +
                '<span class="cc-history-ts">' + _escCC((e.ts || '—').slice(0, 16)) + '</span>' +
                (e.metric ? '<span class="cc-history-metric">' + _escCC(e.metric) + '</span>' : '') +
                '<span class="cc-history-sig ' + _escCC(e.signal || '') + '">' + _escCC(e.signal || 'neutral') + '</span>' +
              '</div>'
            );
          }).join('');
        }
        drawer.style.display = '';
        btn.textContent = 'History ▴';
      })
      .catch(function() {
        drawer.innerHTML = '<div class="cc-history-empty">Failed to load history.</div>';
        drawer.style.display = '';
        btn.textContent = 'History ▴';
      });
  };

  function _escCC(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function _fmtCCMoney(v) {
    if (v === null || v === undefined) return '—';
    if (v >= 1000000) return '$' + (v / 1000000).toFixed(1) + 'M';
    if (v >= 1000)    return '$' + (v / 1000).toFixed(1) + 'K';
    return '$' + Number(v).toFixed(0);
  }

  function _renderCCKpis(kpis, kpiSource, trendDays) {
    var row = document.getElementById('ccKpiRow');
    if (!row || !kpis) return;

    // Data-source honesty badge
    var srcBadge = document.getElementById('ccKpiSourceBadge');
    if (srcBadge) {
      if (kpiSource === 'live') {
        srcBadge.textContent = 'Live API';
        srcBadge.title = 'KPIs sourced live from Meta API (less than 3 days of snapshots)';
        srcBadge.className = 'cc-kpi-src-badge live';
      } else if (kpiSource === 'snapshots') {
        srcBadge.textContent = (trendDays || 0) + 'd cached';
        srcBadge.title = 'KPIs from stored daily snapshots — ' + (trendDays || 0) + ' days available';
        srcBadge.className = 'cc-kpi-src-badge cached';
      } else {
        srcBadge.textContent = '';
        srcBadge.className = 'cc-kpi-src-badge';
      }
    }
    var gs = kpis.growth_score;
    var gsLabel = kpis.growth_label || null;
    var gsTier = gs !== null && gs !== undefined
      ? (gs >= 80 ? 'elite' : gs >= 65 ? 'strong' : gs >= 50 ? 'stable' : gs >= 35 ? 'weak' : 'critical')
      : '';

    // Today's data (primary); 7d as secondary reference
    var hasTodaySpend = kpis.spend_today !== null && kpis.spend_today !== undefined;
    var hasTodayConv  = kpis.conv_today  !== null && kpis.conv_today  !== undefined;
    var hasTodayCpa   = kpis.cpa_today   !== null && kpis.cpa_today   !== undefined;

    row.innerHTML = [
      '<div class="cc-kpi-card spend">',
        '<div class="cc-kpi-label">Spend Today</div>',
        '<div class="cc-kpi-value">' + (hasTodaySpend ? _fmtCCMoney(kpis.spend_today) : '—') + '</div>',
        '<div class="cc-kpi-sub">' + _fmtCCMoney(kpis.spend_7d) + ' last 7d</div>',
      '</div>',
      '<div class="cc-kpi-card conv">',
        '<div class="cc-kpi-label">Conversions Today</div>',
        '<div class="cc-kpi-value">' + (hasTodayConv ? kpis.conv_today : '—') + '</div>',
        '<div class="cc-kpi-sub">' + (kpis.conv_7d || 0) + ' last 7d</div>',
      '</div>',
      '<div class="cc-kpi-card cpa">',
        '<div class="cc-kpi-label">CPA Today</div>',
        '<div class="cc-kpi-value">' + (hasTodayCpa ? _fmtCCMoney(kpis.cpa_today) : '—') + '</div>',
        '<div class="cc-kpi-sub">' + (kpis.cpa_7d !== null && kpis.cpa_7d !== undefined ? _fmtCCMoney(kpis.cpa_7d) + ' 7d avg' : 'no data 7d') + '</div>',
      '</div>',
      '<div class="cc-kpi-card growth ' + gsTier + '">',
        '<div class="cc-kpi-label">Growth Score</div>',
        '<div class="cc-kpi-value">' + (gs !== null && gs !== undefined ? Math.round(gs) : '—') + '</div>',
        '<div class="cc-kpi-sub">' + (gsLabel || 'AI performance index') + '</div>',
      '</div>',
    ].join('');
  }

  function _renderCCAttention(attention) {
    var body    = document.getElementById('ccAttentionBody');
    var countEl = document.getElementById('ccAttentionCount');
    if (!body || !attention) return;

    var items = [];
    var total = 0;

    (attention.alerts || []).forEach(function(a) {
      total++;
      items.push([
        '<div class="cc-attention-item" onclick="window.a7Navigate&&window.a7Navigate(\'alerts\')" title="View alerts">',
          '<span class="cc-sev-dot ' + _escCC(a.severity) + '"></span>',
          '<div class="cc-attn-text">',
            '<div class="cc-attn-title">' + _escCC(a.title) + '</div>',
            '<div class="cc-attn-msg">'  + _escCC(a.message || a.alert_type) + '</div>',
          '</div>',
        '</div>',
      ].join(''));
    });

    if (attention.pending_auto > 0) {
      total += attention.pending_auto;
      items.push([
        '<div class="cc-sys-row" style="cursor:pointer" onclick="window.a7Navigate&&window.a7Navigate(\'automation\')">',
          '<span class="cc-sys-icon">⊗</span>',
          '<span class="cc-sys-text"><strong>' + attention.pending_auto + '</strong> automation action' + (attention.pending_auto !== 1 ? 's' : '') + ' pending approval</span>',
        '</div>',
      ].join(''));
    }

    if (attention.stale_accounts > 0) {
      total += attention.stale_accounts;
      items.push([
        '<div class="cc-sys-row" style="cursor:pointer" onclick="window.a7Navigate&&window.a7Navigate(\'integrations\')">',
          '<span class="cc-sys-icon">⚠</span>',
          '<span class="cc-sys-text"><strong>' + attention.stale_accounts + '</strong> account' + (attention.stale_accounts !== 1 ? 's' : '') + ' need re-sync</span>',
        '</div>',
      ].join(''));
    }

    if (items.length === 0) {
      items.push('<div class="cc-empty">✓ All systems healthy</div>');
    }

    if (countEl) {
      countEl.textContent = total > 0 ? total : '✓';
      countEl.className   = 'cc-block-count' + (total === 0 ? ' zero' : '');
    }

    body.innerHTML = items.join('');
  }

  function _renderCCOpps(opps) {
    var body = document.getElementById('ccOppsBody');
    if (!body) return;
    if (!opps || opps.length === 0) {
      body.innerHTML = '<div class="cc-empty">No opportunities detected yet.</div>';
      return;
    }
    var destMap = { budget: 'budget', scale: 'campaigns', content: 'content-studio', info: 'ai-coach' };
    body.innerHTML = opps.map(function(o) {
      var dest = destMap[o.type] || 'ai-coach';
      return [
        '<div class="cc-opp-item" onclick="window.a7Navigate&&window.a7Navigate(\'' + _escCC(dest) + '\')" title="' + _escCC(o.title) + '">',
          '<div class="cc-opp-icon ' + _escCC(o.type) + '">' + _escCC(o.icon) + '</div>',
          '<div class="cc-opp-text">',
            '<div class="cc-opp-title">' + _escCC(o.title) + '</div>',
            '<div class="cc-opp-desc">'  + _escCC(o.desc)  + '</div>',
          '</div>',
          '<div class="cc-opp-arrow">›</div>',
        '</div>',
      ].join('');
    }).join('');
  }

  function _renderCCHealth(health) {
    var body = document.getElementById('ccHealthBody');
    if (!body) return;
    if (!health) {
      body.innerHTML = '<div class="cc-no-health">Connect an ad account to see health metrics.</div>';
      return;
    }
    var labelClass = { 'Excellent': 'excellent', 'Good': 'good', 'Fair': 'fair', 'Needs Work': 'needswork' }[health.label] || 'fair';
    var platformBadge = health.platform
      ? '<span class="cc-platform-badge ' + _escCC(health.platform.toLowerCase()) + '">' + _escCC(health.platform) + '</span>'
      : '';
    var syncOk = health.last_sync && health.last_sync !== 'Never' && !health.last_sync.startsWith('Never');
    var syncClass = syncOk ? 'ok' : 'stale';
    var alertDot = health.alert_count > 0
      ? '<span class="cc-alert-dot"></span>'
      : '';
    body.innerHTML = [
      '<div class="cc-health-acct-row">',
        '<div class="cc-health-name">' + _escCC(health.account_name) + '</div>',
        platformBadge,
      '</div>',
      '<div class="cc-health-score-row">',
        '<div class="cc-health-score-num">' + Math.round(health.score || 0) + '</div>',
        '<span class="cc-health-label ' + labelClass + '">' + _escCC(health.label) + '</span>',
      '</div>',
      '<div class="cc-health-stats">',
        '<div class="cc-health-stat">',
          '<div class="cc-health-stat-val">' + _fmtCCMoney(health.spend_7d) + '</div>',
          '<div class="cc-health-stat-key">Spend 7d</div>',
        '</div>',
        '<div class="cc-health-stat">',
          '<div class="cc-health-stat-val">' + (health.conv_7d || 0) + '</div>',
          '<div class="cc-health-stat-key">Conv. 7d</div>',
        '</div>',
        '<div class="cc-health-stat">',
          '<div class="cc-health-stat-val cc-sync-val ' + syncClass + '">' + _escCC(health.last_sync) + '</div>',
          '<div class="cc-health-stat-key">Last Sync</div>',
        '</div>',
        '<div class="cc-health-stat">',
          '<div class="cc-health-stat-val">' + alertDot + (health.alert_count || 0) + '</div>',
          '<div class="cc-health-stat-key">Active Alerts</div>',
        '</div>',
      '</div>',
    ].join('');
  }

  /* ─── Command Center: Trend Charts ─── */

  function _ccChartDefaults() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { mode: 'index', intersect: false } },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,.04)' }, ticks: { color: '#5d7499', font: { size: 10 } } },
        y: { grid: { color: 'rgba(255,255,255,.04)' }, ticks: { color: '#5d7499', font: { size: 10 } } },
      },
      elements: { point: { radius: 2, hoverRadius: 4 } },
    };
  }

  function _ccShortDate(iso) {
    var p = iso.split('-');
    return p[1] + '/' + p[2];
  }

  function _renderCCTrends(trend) {
    var labels = trend.map(function(d) { return _ccShortDate(d.date); });

    // Spend chart
    var cSpend = document.getElementById('ccSpendChart');
    if (cSpend) {
      if (_ccSpendChart) _ccSpendChart.destroy();
      _ccSpendChart = new Chart(cSpend, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            data: trend.map(function(d) { return d.spend; }),
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59,130,246,.12)',
            fill: true,
            tension: 0.4,
            borderWidth: 2,
          }],
        },
        options: _ccChartDefaults(),
      });
    }

    // Conversions chart
    var cConv = document.getElementById('ccConvChart');
    if (cConv) {
      if (_ccConvChart) _ccConvChart.destroy();
      _ccConvChart = new Chart(cConv, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            data: trend.map(function(d) { return d.conversions; }),
            borderColor: '#10b981',
            backgroundColor: 'rgba(16,185,129,.12)',
            fill: true,
            tension: 0.4,
            borderWidth: 2,
          }],
        },
        options: _ccChartDefaults(),
      });
    }

    // CTR + CPC dual-axis chart
    var cCtrCpc = document.getElementById('ccCtrCpcChart');
    if (cCtrCpc) {
      if (_ccCtrCpcChart) _ccCtrCpcChart.destroy();
      var opts = _ccChartDefaults();
      opts.scales.yCtr = { type: 'linear', position: 'left',  grid: { color: 'rgba(255,255,255,.04)' }, ticks: { color: '#5d7499', font: { size: 10 }, callback: function(v) { return v + '%'; } } };
      opts.scales.yCpc = { type: 'linear', position: 'right', grid: { display: false }, ticks: { color: '#5d7499', font: { size: 10 }, callback: function(v) { return '$' + v; } } };
      delete opts.scales.y;
      _ccCtrCpcChart = new Chart(cCtrCpc, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [
            {
              label: 'CTR %',
              data: trend.map(function(d) { return d.ctr; }),
              borderColor: '#f59e0b',
              backgroundColor: 'transparent',
              yAxisID: 'yCtr',
              tension: 0.4,
              borderWidth: 2,
            },
            {
              label: 'CPC $',
              data: trend.map(function(d) { return d.cpc; }),
              borderColor: '#a855f7',
              backgroundColor: 'transparent',
              yAxisID: 'yCpc',
              tension: 0.4,
              borderWidth: 2,
              borderDash: [4, 3],
            },
          ],
        },
        options: Object.assign({}, opts, {
          plugins: {
            legend: { display: true, labels: { color: '#8ba3c2', font: { size: 10 }, boxWidth: 10, padding: 8 } },
            tooltip: { mode: 'index', intersect: false },
          },
        }),
      });
    }
  }

  /* ─── Command Center: Top Campaigns Bar ─── */

  function _renderCCTopCamps(camps) {
    var canvas = document.getElementById('ccTopCampChart');
    if (!canvas) return;
    if (_ccTopCampChart) _ccTopCampChart.destroy();

    if (!camps.length) {
      canvas.parentElement.innerHTML = '<div class="cc-empty" style="padding:24px 0">No campaign data yet.</div>';
      return;
    }

    // Truncate long names
    function _short(name, max) {
      return name.length > max ? name.slice(0, max - 1) + '…' : name;
    }

    var labels  = camps.map(function(c) { return _short(c.name, 28); });
    var spends  = camps.map(function(c) { return c.spend; });
    var colors  = ['rgba(59,130,246,.8)', 'rgba(99,102,241,.8)', 'rgba(168,85,247,.8)', 'rgba(6,182,212,.8)', 'rgba(16,185,129,.8)'];

    _ccTopCampChart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          data: spends,
          backgroundColor: colors.slice(0, camps.length),
          borderRadius: 4,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: function(ctx) {
                var c = camps[ctx.dataIndex];
                var parts = ['$' + ctx.raw.toFixed(2) + ' spend'];
                if (c.conv > 0) parts.push(c.conv + ' conv • $' + c.cpa + ' CPA');
                return parts;
              },
            },
          },
        },
        scales: {
          x: {
            grid: { color: 'rgba(255,255,255,.04)' },
            ticks: { color: '#5d7499', font: { size: 10 }, callback: function(v) { return '$' + v; } },
          },
          y: {
            grid: { display: false },
            ticks: { color: '#e8eeff', font: { size: 11 } },
          },
        },
      },
    });
  }

  /* ─── Command Center: Worst Performers ─── */

  function _renderCCWorst(camps) {
    var body = document.getElementById('ccWorstBody');
    if (!body) return;
    if (!camps.length) {
      body.innerHTML = '<div class="cc-empty">No conversion data yet.</div>';
      return;
    }
    body.innerHTML = camps.map(function(c, i) {
      var rank = i === 0 ? 'worst' : i === 1 ? 'bad' : '';
      return [
        '<div class="cc-worst-row ' + rank + '">',
          '<div class="cc-worst-name">' + _escCC(c.name) + '</div>',
          '<div class="cc-worst-stats">',
            '<span class="cc-worst-cpa">$' + c.cpa + ' CPA</span>',
            '<span class="cc-worst-meta">' + c.conv + ' conv • $' + c.spend.toFixed(0) + '</span>',
          '</div>',
        '</div>',
      ].join('');
    }).join('');
  }

  /* ─── Command Center: Campaign Distribution ─── */

  function _renderCCDist(dist) {
    var body = document.getElementById('ccDistSummary');
    if (!body) return;
    var active = dist.active || 0;
    var paused = dist.paused || 0;
    var total  = dist.total  || 0;
    var activePct = total > 0 ? Math.round(active / total * 100) : 0;
    body.innerHTML = [
      '<div class="cc-dist-row">',
        '<div class="cc-dist-item cc-dist-active">',
          '<div class="cc-dist-num">' + active + '</div>',
          '<div class="cc-dist-lbl">Active</div>',
        '</div>',
        '<div class="cc-dist-bar-wrap">',
          '<div class="cc-dist-bar-track">',
            '<div class="cc-dist-bar-fill" style="width:' + activePct + '%"></div>',
          '</div>',
          '<div class="cc-dist-pct">' + activePct + '% running</div>',
        '</div>',
        '<div class="cc-dist-item cc-dist-paused">',
          '<div class="cc-dist-num">' + paused + '</div>',
          '<div class="cc-dist-lbl">Paused</div>',
        '</div>',
      '</div>',
      '<div class="cc-dist-total">' + total + ' total campaigns tracked (7d)</div>',
    ].join('');
  }

  /* ─── Command Center: Alert Severity Cluster ─── */

  function _renderCCAlertCluster(sevMap) {
    var body = document.getElementById('ccAlertCluster');
    if (!body) return;
    var critical = sevMap.critical || 0;
    var warning  = sevMap.warning  || 0;
    var info     = sevMap.info     || 0;
    var total    = critical + warning + info;
    if (total === 0) {
      body.innerHTML = '<div class="cc-cluster-ok">✓ No active alerts</div>';
      return;
    }
    var items = [];
    if (critical > 0) items.push('<div class="cc-cluster-badge critical">' + critical + ' Critical</div>');
    if (warning  > 0) items.push('<div class="cc-cluster-badge warning">'  + warning  + ' Warning</div>');
    if (info     > 0) items.push('<div class="cc-cluster-badge info">'     + info     + ' Info</div>');
    body.innerHTML = items.join('') +
      '<div class="cc-cluster-link" onclick="window.a7Navigate&&window.a7Navigate(\'alerts\')">View all →</div>';
  }

  /* ─── Lazy Load Registry ─── */
  // Maps page → load function names to call on first visit
  var _pageLoaders = {
    'overview':       ['loadCommandCenter'],
    'accounts':       ['loadAccountsPage', 'loadAccountOverview'],
    'campaigns':      [],   // data loaded by main load() which runs for overview
    'budget':         ['loadBudget'],
    'automation':     ['loadAutomation'],
    'creative':       ['loadCreatives'],
    'content-studio': ['loadContentStudio'],
    'ai-coach':       ['loadCoach'],
    'insights':       ['loadForecast', 'loadCrossPlatform'],
    'alerts':         ['loadAlerts'],
    'reports':        ['loadReport'],
    'copilot':        [],
    'integrations':   [],
    'billing':        ['loadPlanUsage'],
  };
  var _calledLoaders = new Set();

  // Map function name strings to actual functions (set up after functions are defined, in init)
  var _loaderFnMap = {};

  function _runPageLoaders(page) {
    var loaders = _pageLoaders[page] || [];
    loaders.forEach(function(fnName) {
      if (!_calledLoaders.has(fnName) && typeof _loaderFnMap[fnName] === 'function') {
        _calledLoaders.add(fnName);
        _loaderFnMap[fnName]();
      }
    });
  }

  /* ─── Workspace Header Update ─── */
  function _updateWorkspaceHeader(page) {
    var meta = _pageMeta[page] || { title: page, subtitle: '', icon: '◈' };

    var iconEl  = document.getElementById('wsPageIcon');
    var titleEl = document.getElementById('wsPageTitle');
    var subEl   = document.getElementById('wsPageSubtitle');
    if (iconEl)  iconEl.textContent  = meta.icon;
    if (titleEl) titleEl.textContent = meta.title;
    if (subEl)   subEl.textContent   = meta.subtitle;
  }

  /* ─── Sidebar Router ─── */
  function _navigateTo(page) {
    if (!page) page = 'overview';

    // Hide all page sections
    document.querySelectorAll('.page-section').forEach(function(p) {
      p.classList.remove('active');
    });

    // Show target page
    var target = document.getElementById('page-' + page);
    if (!target) {
      page = 'overview';
      target = document.getElementById('page-overview');
    }
    if (target) target.classList.add('active');

    // Update sidebar active state
    document.querySelectorAll('.nav-item[data-page]').forEach(function(item) {
      item.classList.remove('active');
    });
    var activeNav = document.querySelector('.nav-item[data-page="' + page + '"]');
    if (activeNav) activeNav.classList.add('active');

    // Update workspace header
    _updateWorkspaceHeader(page);

    // Lazy-load this page's data (first visit only)
    _runPageLoaders(page);

    // Update URL hash without scroll
    history.replaceState(null, null, '#' + page);
  }

  // Expose for external calls
  window.a7Navigate = _navigateTo;

  function _initRouter() {
    // Sidebar click handler
    document.addEventListener('click', function(e) {
      var navItem = e.target.closest('.nav-item[data-page]');
      if (navItem) {
        e.preventDefault();
        _navigateTo(navItem.getAttribute('data-page'));
      }
    });

    // Handle browser back/forward
    window.addEventListener('hashchange', function() {
      var hash = window.location.hash.replace('#', '').trim();
      if (hash) _navigateTo(hash);
    });

    // Activate initial page from URL hash or default to overview
    var initialPage = window.location.hash.replace('#', '').trim() || 'overview';
    _navigateTo(initialPage);
  }

  /* ─── Sidebar Collapse Toggle ─── */
  (function initSidebarToggle() {
    var btn = document.getElementById('sidebarToggleBtn');
    if (!btn) return;

    // Restore saved state
    if (localStorage.getItem('a7_sidebar_collapsed') === '1') {
      document.body.classList.add('sidebar-collapsed');
    }

    btn.addEventListener('click', function() {
      var collapsed = document.body.classList.toggle('sidebar-collapsed');
      localStorage.setItem('a7_sidebar_collapsed', collapsed ? '1' : '0');
    });
  })();

  /* ─── Workspace Status Mirror ─── */
  // Keep workspace header status in sync with global status indicator
  var _origSetSysStatus = window._setSysStatus;
  function _syncWsStatus(state) {
    var dot   = document.getElementById('wsStatusDot2');
    var label = document.getElementById('wsStatusLabel2');
    var pill  = document.getElementById('wsStatusPill');
    if (!dot || !label) return;

    dot.className   = 'ws-status-dot'   + (state !== 'live' ? ' ' + state : '');
    label.className = 'ws-status-label' + (state !== 'live' ? ' ' + state : '');
    label.textContent = state === 'live' ? 'Live' : state === 'degraded' ? 'Degraded' : 'Offline';

    if (pill) {
      pill.style.background     = state === 'live' ? 'rgba(16,185,129,.07)' : state === 'degraded' ? 'rgba(245,158,11,.07)' : 'rgba(93,116,153,.07)';
      pill.style.borderColor    = state === 'live' ? 'rgba(16,185,129,.18)' : state === 'degraded' ? 'rgba(245,158,11,.18)' : 'rgba(93,116,153,.18)';
    }
  }

  /* ─── Workspace Account Badge ─── */
  function _updateWsAccountBadge() {
    var badge = document.getElementById('wsAccountBadge');
    var dot   = document.getElementById('wsPlatformDot');
    var name  = document.getElementById('wsAcctName');
    if (!badge) return;

    if (!currentAccountId || !_accountsCache.length) {
      badge.style.display = 'none';
      return;
    }
    var acc = _accountsCache.find(function(a) { return a.id == currentAccountId; });
    if (!acc) { badge.style.display = 'none'; return; }

    badge.style.display = 'flex';
    if (dot) {
      dot.className = 'ws-platform-dot' + (acc.platform === 'google' ? ' google' : '');
    }
    if (name) name.textContent = acc.account_name;
  }

  /* ─── Init ─── */
  // Wire loader function map (after all functions are declared)
  _loaderFnMap = {
    loadCommandCenter:  loadCommandCenter,
    loadAccountsPage:   loadAccountsPage,
    loadGrowthScore:    loadGrowthScore,
    loadAccountOverview: loadAccountOverview,
    loadBudget:         loadBudget,
    loadAutomation:     loadAutomation,
    loadCreatives:      loadCreatives,
    loadContentStudio:  loadContentStudio,
    loadCoach:          loadCoach,
    loadForecast:       loadForecast,
    loadCrossPlatform:  loadCrossPlatform,
    loadAlerts:         loadAlerts,
    loadReport:         loadReport,
    loadPlanUsage:      loadPlanUsage,
  };

  // load() covers KPIs + campaigns; mark so lazy system doesn't re-run it
  _calledLoaders.add('load');

  // _initRouter() navigates to initial page and triggers its lazy loaders
  // (loadCommandCenter runs via _pageLoaders['overview'] on first visit)
  _initRouter();
  loadPlatformStatus();
  // Wait for account selector to resolve currentAccountId BEFORE the first data load,
  // so the correct account is used from the very first request.
  initAccountSelector().then(function() {
    load(currentRange);
    startAutoRefresh();
  }).catch(function() {
    // If account selector fails (e.g. endpoint unavailable), still load with default account
    load(currentRange);
    startAutoRefresh();
  });
  setTimeout(_updateWsAccountBadge, 800);

  // Patch account change to update workspace badge
  var _origAccountChange = null;
  (function patchAccountBadge() {
    var sel = document.getElementById('accountSelect');
    if (sel) {
      sel.addEventListener('change', function() {
        setTimeout(_updateWsAccountBadge, 50);
      });
    }
  })();

  // Patch _setSysStatus to also sync workspace header
  var _origGlobalSysStatus = _setSysStatus;
  _setSysStatus = function(state) {
    _origGlobalSysStatus(state);
    _syncWsStatus(state);
  };

})();
