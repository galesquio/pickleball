// Court Schedule Grid — with date navigation (today → today+7)
const HOUR_LABELS = [
  '12AM–1AM','1AM–2AM','2AM–3AM','3AM–4AM','4AM–5AM','5AM–6AM',
  '6AM–7AM','7AM–8AM','8AM–9AM','9AM–10AM','10AM–11AM','11AM–12PM',
  '12PM–1PM','1PM–2PM','2PM–3PM','3PM–4PM','4PM–5PM','5PM–6PM',
  '6PM–7PM','7PM–8PM','8PM–9PM','9PM–10PM','10PM–11PM','11PM–12AM',
];

let _schedData = null;
let _detailRental = null;
let _courtOptions = null; // cached time options for pricing
let _viewDate = null;     // 'YYYY-MM-DD'; null = today (set on first load)

// ── Booking modal state ────────────────────────────────────────────────────
let _bookCtx = { courtId: null, courtName: null, hour: null, durationHours: 1 };

// ── Utilities ──────────────────────────────────────────────────────────────
function _shortLabel(name) {
  const m = name.match(/(\d+)/);
  return m ? `PKL${m[1]}` : name.slice(0, 4).toUpperCase();
}

function _esc(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function _fmtTime(iso) {
  const d = new Date(iso);
  let h = d.getHours(), m = d.getMinutes();
  const ap = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  return `${h}:${String(m).padStart(2, '0')}${ap}`;
}

function _fmtHour(hour) {
  const ap = hour >= 12 ? 'PM' : 'AM';
  const h = hour % 12 || 12;
  return `${h}:00 ${ap}`;
}

function _money(n) {
  return '₱' + Math.round(Number(n) || 0).toLocaleString();
}

// ── Date navigation helpers ────────────────────────────────────────────────

function _phDateStr(d) {
  // Return YYYY-MM-DD string for a Date object (Philippines local)
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function _todayDateStr() {
  return _phDateStr(_facilityNow());
}

function _maxDateStr() {
  const d = _facilityNow();
  d.setDate(d.getDate() + 7);
  return _phDateStr(d);
}

function _addDays(dateStr, days) {
  const d = new Date(dateStr + 'T00:00:00');
  d.setDate(d.getDate() + days);
  return _phDateStr(d);
}

function _fmtNavDate(dateStr) {
  // "Saturday, May 31, 2026"
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  });
}

function _fmtShortDate(dateStr) {
  // "May 31"
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-US', {
    month: 'short', day: 'numeric',
  });
}

function _renderDateNav() {
  const nav = document.getElementById('schedule-date-nav');
  if (!nav) return;

  const today = _todayDateStr();
  const maxDate = _maxDateStr();
  if (!_viewDate) _viewDate = today;

  const isToday = _viewDate === today;
  const isMax = _viewDate === maxDate;
  const dayDiff = Math.round(
    (new Date(_viewDate + 'T00:00:00') - new Date(today + 'T00:00:00')) / 86400000
  );
  const aheadBadge = dayDiff > 0
    ? `<span class="text-[11px] font-semibold text-blue-600 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full">${dayDiff} day${dayDiff > 1 ? 's' : ''} ahead</span>`
    : '';

  nav.innerHTML = `
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div class="min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-sm font-bold text-gray-900">${isToday ? "Today's Schedule" : 'Court Schedule'}</span>
          ${aheadBadge}
        </div>
        <p class="text-xs text-gray-500 mt-0.5">
          ${isToday ? 'Click on open slots to book' : _fmtNavDate(_viewDate) + ' — advance booking'}
        </p>
      </div>
      <div class="flex items-center gap-1.5 shrink-0">
        <button id="date-nav-prev" ${isToday ? 'disabled' : ''}
          class="w-8 h-8 flex items-center justify-center rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/>
          </svg>
        </button>
        <div class="flex items-center gap-1.5 px-3 h-8 bg-white border border-gray-200 rounded-lg text-xs font-medium text-gray-700 select-none">
          <svg class="w-3.5 h-3.5 text-gray-400 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <rect x="3" y="4" width="18" height="18" rx="2"/><path stroke-linecap="round" d="M16 2v4M8 2v4M3 10h18"/>
          </svg>
          <span>${isToday ? 'Today' : _fmtShortDate(_viewDate)}</span>
        </div>
        ${!isToday ? `<button id="date-nav-today" class="px-3 h-8 text-xs font-semibold text-teal-700 bg-teal-50 border border-teal-200 rounded-lg hover:bg-teal-100 transition-colors">Today</button>` : ''}
        <button id="date-nav-next" ${isMax ? 'disabled' : ''}
          class="w-8 h-8 flex items-center justify-center rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/>
          </svg>
        </button>
      </div>
    </div>`;

  document.getElementById('date-nav-prev')?.addEventListener('click', () => {
    if (_viewDate > today) { _viewDate = _addDays(_viewDate, -1); loadCourtsSchedule(); }
  });
  document.getElementById('date-nav-today')?.addEventListener('click', () => {
    _viewDate = today; loadCourtsSchedule();
  });
  document.getElementById('date-nav-next')?.addEventListener('click', () => {
    if (_viewDate < maxDate) { _viewDate = _addDays(_viewDate, 1); loadCourtsSchedule(); }
  });
}

function _buildStartIso(hour) {
  const dateStr = _viewDate || _todayDateStr();
  const pad = n => String(n).padStart(2, '0');
  return `${dateStr}T${pad(hour)}:00:00`;
}

async function _fetchSchedulePrice(durationHours, startIso) {
  const params = new URLSearchParams({ duration_hours: String(durationHours) });
  if (startIso) params.set('start_time', startIso);
  const res = await fetch(`/api/schedule/courts/price?${params}`);
  if (!res.ok) return null;
  return res.json();
}

async function _ensureOptions() {
  if (_courtOptions) return _courtOptions;
  const res = await fetch('/api/time-options?type=court');
  const data = await res.json();
  _courtOptions = data.options || [];
  return _courtOptions;
}

// ── Schedule loading & rendering ───────────────────────────────────────────
async function loadCourtsSchedule() {
  if (!_viewDate) _viewDate = _todayDateStr();
  try {
    const res = await fetch(`/api/schedule/courts?view_date=${_viewDate}`);
    if (!res.ok) return;
    const data = await res.json();
    _schedData = data;
    renderCourtsSchedule(data);
  } catch (e) {
    console.error('Schedule load error:', e);
  }
}

function renderCourtsSchedule(data) {
  _renderDateNav(); // keep nav in sync with current _viewDate

  const container = document.getElementById('court-schedule-container');
  if (!container) return;

  const { courts, rentals, current_hour, is_today } = data;

  if (!courts.length) {
    container.innerHTML = '<p class="text-sm text-gray-400 py-6 text-center">No courts configured.</p>';
    return;
  }

  // Lookup: court_id → { start_hour: rental }
  const byStart = {};
  // Skip set: cells covered by a rowspan above
  const skip = new Set();

  for (const r of rentals) {
    if (!byStart[r.court_id]) byStart[r.court_id] = {};
    byStart[r.court_id][r.start_hour] = r;
    for (let h = r.start_hour + 1; h < r.end_hour && h < 24; h++) {
      skip.add(`${r.court_id}_${h}`);
    }
  }

  // ── Table header ──
  let html = `<div class="overflow-x-auto rounded-xl border border-gray-200 shadow-sm">
<table class="w-full border-collapse text-xs bg-white">
<thead>
<tr>
  <th class="sticky left-0 z-20 bg-gray-200 border-b-2 border-r border-gray-300 px-3 py-2.5 text-left text-[11px] font-semibold text-gray-600 min-w-[88px]">Time</th>`;

  for (const c of courts) {
    html += `
  <th class="bg-gray-200 border-b-2 border-r border-gray-300 px-2 py-2 text-center min-w-[110px]">
    <span class="hidden sm:block text-xs font-semibold text-gray-700">${_esc(c.name)}</span>
    <span class="sm:hidden text-[11px] font-semibold text-gray-700">${_esc(_shortLabel(c.name))}</span>
    <div class="text-[10px] font-normal text-gray-500 mt-0.5">Pickleball</div>
  </th>`;
  }
  html += `\n</tr>\n</thead>\n<tbody>`;

  // ── Rows ──
  for (let h = 0; h < 24; h++) {
    const isPast = h < current_hour;
    const isNow = h === current_hour;

    html += `\n<tr>`;

    // Time label (sticky)
    const timeBg = isPast ? 'bg-gray-50' : isNow ? 'bg-blue-50' : 'bg-white';
    html += `<td class="sticky left-0 z-10 ${timeBg} border-b border-r border-gray-200 px-3 py-0 font-medium text-gray-500 whitespace-nowrap text-[11px] h-9">${HOUR_LABELS[h]}</td>`;

    for (const c of courts) {
      const key = `${c.id}_${h}`;
      if (skip.has(key)) continue;

      const rental = byStart[c.id]?.[h];

      if (rental) {
        // ── Booked cell ──
        const span = Math.min(rental.span, 24 - h);
        const pendingCash = rental.payment_pending;
        const isPaid = rental.is_paid && !pendingCash;
        const isActive = rental.status === 'active';

        let cellBg;
        let nameColor;
        if (pendingCash) {
          cellBg = 'bg-orange-100 hover:bg-orange-200 border-l-2 border-orange-400';
          nameColor = 'text-orange-900';
        } else if (isPaid) {
          cellBg = 'bg-teal-100 hover:bg-teal-200';
          nameColor = 'text-teal-800';
        } else {
          cellBg = 'bg-amber-50 hover:bg-amber-100 border-l-2 border-amber-400';
          nameColor = 'text-amber-900';
        }

        let statusLabel;
        if (pendingCash) {
          const collectLabel = rental.auto_completed ? 'Collect cash (auto)' : 'Collect cash';
          statusLabel = `<span class="text-[10px] text-orange-700 font-bold">${collectLabel}</span>`;
        } else if (isActive) {
          statusLabel = isPaid
            ? '<span class="text-[10px] text-teal-600 font-medium">Paid</span>'
            : '<span class="text-[10px] text-amber-600 font-medium">Unpaid</span>';
        } else {
          const doneText = rental.auto_completed ? 'Done (auto)' : 'Done';
          statusLabel = `<span class="text-[10px] text-gray-400">${doneText}</span>`;
        }

        const balanceBadge = pendingCash
          ? `<span class="text-[10px] font-bold text-orange-800">${_money(rental.payment_pending_amount)}</span>`
          : (!isPaid && rental.balance_due > 0
            ? `<span class="text-[10px] font-bold text-amber-700">${_money(rental.balance_due)} due</span>`
            : '');

        const contLabel = rental.continued_from_previous
          ? '<span class="text-[9px] text-gray-500 font-medium">(continued)</span>'
          : '';

        html += `
      <td rowspan="${span}"
          class="border-b border-r border-gray-200 ${cellBg} align-middle text-center cursor-pointer transition-colors px-1"
          onclick="openScheduleDetail(${rental.id})">
        <div class="flex flex-col items-center gap-0.5 py-1">
          <span class="text-[11px] font-semibold ${nameColor} leading-tight truncate max-w-[90px]">${_esc(rental.customer_name)}</span>
          ${contLabel}
          ${statusLabel}
          ${balanceBadge}
        </div>
      </td>`;

      } else if (isPast) {
        // ── Past cell ──
        html += `<td class="border-b border-r border-gray-200 bg-gray-100 h-9"></td>`;

      } else {
        // ── Open cell ──
        html += `
      <td class="border-b border-r border-gray-200 bg-white h-9 text-center cursor-pointer hover:bg-emerald-50 transition-colors group"
          onclick="openScheduleBookModal(${c.id}, '${_esc(c.name)}', ${h})">
        <span class="text-[11px] text-emerald-600 font-medium opacity-0 group-hover:opacity-100 transition-opacity select-none">Open</span>
      </td>`;
      }
    }
    html += `\n</tr>`;
  }

  html += `\n</tbody>\n</table>\n</div>`;
  container.innerHTML = html;

  // Inject the current-time indicator after DOM is set
  requestAnimationFrame(_updateNowIndicator);
}

// ── Current-time indicator ─────────────────────────────────────────────────

function _facilityNow() {
  // Philippines Standard Time (UTC+8)
  const now = new Date();
  return new Date(now.getTime() + now.getTimezoneOffset() * 60000 + 8 * 3600000);
}

function _updateNowIndicator() {
  // Only show for today's view
  if (!_schedData?.is_today) {
    const old = document.getElementById('now-indicator');
    if (old) old.remove();
    return;
  }

  const container = document.getElementById('court-schedule-container');
  if (!container) return;
  const wrapper = container.querySelector('.overflow-x-auto');
  if (!wrapper) return;
  const tbody = wrapper.querySelector('tbody');
  if (!tbody) return;

  const fn = _facilityNow();
  const hour = fn.getHours();
  const minute = fn.getMinutes();
  const rows = tbody.querySelectorAll('tr');
  if (hour >= rows.length) return;

  const targetRow = rows[hour];
  const wrapperRect = wrapper.getBoundingClientRect();
  const rowRect = targetRow.getBoundingClientRect();
  const rowH = rowRect.height || 36;
  const top = (rowRect.top - wrapperRect.top) + rowH * (minute / 60);

  const hh = String(hour).padStart(2, '0');
  const mm = String(minute).padStart(2, '0');
  const timeStr = `${hh}:${mm}`;

  let ind = document.getElementById('now-indicator');
  if (!ind) {
    wrapper.style.position = 'relative';
    ind = document.createElement('div');
    ind.id = 'now-indicator';
    ind.style.cssText = 'position:absolute;left:0;right:0;pointer-events:none;z-index:25;transform:translateY(-50%)';
    wrapper.appendChild(ind);
  }

  ind.style.top = top + 'px';
  ind.innerHTML = `
    <div style="display:flex;align-items:center">
      <div style="width:88px;flex-shrink:0;display:flex;align-items:center;justify-content:flex-end;padding-right:5px">
        <span style="background:#f43f5e;color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:5px;font-family:ui-monospace,monospace;letter-spacing:0.04em;white-space:nowrap;box-shadow:0 1px 4px rgba(244,63,94,0.45)">${timeStr}</span>
      </div>
      <div style="width:9px;height:9px;border-radius:50%;background:#f43f5e;flex-shrink:0;margin-left:-1px;box-shadow:0 0 0 3px rgba(244,63,94,0.18)"></div>
      <div style="flex:1;height:2px;background:linear-gradient(to right,#f43f5e 0%,#fb7185 50%,rgba(251,113,133,0) 100%)"></div>
    </div>`;
}

// ── Booking modal ──────────────────────────────────────────────────────────
async function openScheduleBookModal(courtId, courtName, hour) {
  _bookCtx = { courtId, courtName, hour, durationHours: 1 };

  const today = _todayDateStr();
  const isToday = (_viewDate || today) === today;
  const dateTag = isToday ? '' : ` · ${_fmtShortDate(_viewDate)}`;
  document.getElementById('sb-court-label').textContent = courtName + dateTag;
  _refreshBookModal();

  // Ensure options are loaded (fire-and-forget, updates UI after load)
  _ensureOptions().then(() => _refreshBookModal());

  // Reset inputs
  document.getElementById('sb-customer').value = '';
  document.getElementById('sb-payment').value = '';
  delete document.getElementById('sb-payment').dataset.touched;

  openModal('modal-sched-book');
}

function _refreshBookModal() {
  const { courtName, hour, durationHours } = _bookCtx;
  const endHour = hour + durationHours;

  // Slot label
  document.getElementById('sb-slot-label').textContent =
    `${_fmtHour(hour)} → ${_fmtHour(endHour % 24)}`;
  document.getElementById('sb-dur-value').textContent = durationHours;
  document.getElementById('sb-end-label').textContent =
    `${_fmtHour(hour)} to ${_fmtHour(endHour % 24)}${endHour >= 24 ? ' (+1 day)' : ''}`;

  // Disable −/+ at limits
  document.getElementById('sb-dur-minus').disabled = durationHours <= 1;
  document.getElementById('sb-dur-plus').disabled = durationHours >= 12;

  const startIso = _buildStartIso(hour);
  document.getElementById('sb-breakdown').innerHTML = '<span class="text-gray-400 text-xs">Loading rates…</span>';
  document.getElementById('sb-total').textContent = '…';

  _fetchSchedulePrice(durationHours, startIso).then((data) => {
    if (!data || _bookCtx.durationHours !== durationHours) return;
    const total = data.total_amount || 0;
    let bdHtml = '';
    if (data.promo) {
      bdHtml = `<div class="flex justify-between text-violet-700"><span>🎉 ${data.promo.name}</span><span class="font-medium">${_esc(data.promo.summary)}</span></div>`;
      if (data.play_duration_hours && data.play_duration_hours !== durationHours) {
        bdHtml += `<div class="text-xs text-violet-600 mt-1">Play time: ${data.play_duration_hours}h (selected ${durationHours}h slot)</div>`;
      }
    }
    (data.breakdown || []).forEach((item) => {
      const label = item.count > 1 ? `${item.label} × ${item.count}` : item.label;
      const amt = _money(item.price * item.count);
      bdHtml += `<div class="flex justify-between"><span>${_esc(label)}</span><span class="font-medium text-gray-800">${amt}</span></div>`;
    });
    if (!bdHtml) {
      bdHtml = `<div class="flex justify-between"><span>${durationHours}h rental</span><span class="font-medium text-gray-800">${_money(total)}</span></div>`;
    }
    document.getElementById('sb-breakdown').innerHTML = bdHtml;
    document.getElementById('sb-total').textContent = _money(total);

    const payInput = document.getElementById('sb-payment');
    if (!payInput.dataset.touched) {
      payInput.value = total;
    }
    _updateBookBalance(total);
  });
}

function _updateBookBalance(total) {
  const payInput = document.getElementById('sb-payment');
  const payment = parseFloat(payInput.value) || 0;
  const balance = Math.max(0, (total || 0) - payment);
  document.getElementById('sb-balance').textContent = _money(balance);

  const btn = document.getElementById('sb-confirm-btn');
  const customerOk = (document.getElementById('sb-customer').value || '').trim().length > 0;
  const payOk = payment >= 0 && payment <= (total || 0) + 0.009;
  btn.disabled = !customerOk || !payOk;
  btn.classList.toggle('opacity-50', !customerOk || !payOk);
  btn.classList.toggle('cursor-not-allowed', !customerOk || !payOk);
}

// ── Detail modal ───────────────────────────────────────────────────────────
function openScheduleDetail(rentalId) {
  if (!_schedData) return;
  const rental = _schedData.rentals.find(r => r.id === rentalId);
  if (!rental) return;
  _detailRental = rental;

  document.getElementById('sd-customer').textContent = rental.customer_name;
  document.getElementById('sd-plan').textContent = rental.time_option_label;
  document.getElementById('sd-time').textContent =
    `${_fmtTime(rental.started_at)} – ${_fmtTime(rental.ends_at)}`;
  document.getElementById('sd-billed').textContent = _money(rental.amount_billed);
  document.getElementById('sd-paid').textContent = _money(rental.amount_paid);
  const pendingCash = rental.payment_pending;
  document.getElementById('sd-balance').textContent = pendingCash
    ? _money(rental.payment_pending_amount)
    : _money(rental.balance_due);

  const isActive = rental.status === 'active';
  const badge = document.getElementById('sd-status-badge');
  if (pendingCash) {
    badge.textContent = rental.auto_completed ? 'Collect cash (auto)' : 'Collect cash';
    badge.className = 'text-xs font-semibold px-2 py-0.5 rounded-full bg-orange-100 text-orange-800';
  } else if (rental.is_paid) {
    badge.textContent = 'Paid';
    badge.className = 'text-xs font-semibold px-2 py-0.5 rounded-full bg-teal-100 text-teal-700';
  } else if (isActive) {
    badge.textContent = 'Unpaid';
    badge.className = 'text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700';
  } else {
    badge.textContent = rental.auto_completed ? 'Done (auto)' : 'Completed';
    badge.className = 'text-xs font-semibold px-2 py-0.5 rounded-full bg-gray-100 text-gray-500';
  }

  const pendingBanner = document.getElementById('sd-pending-banner');
  const pendingAmt = document.getElementById('sd-pending-amount');
  if (pendingBanner) pendingBanner.classList.toggle('hidden', !pendingCash);
  if (pendingAmt && pendingCash) pendingAmt.textContent = _money(rental.payment_pending_amount);

  const payBtn = document.getElementById('sd-pay-btn');
  const completeBtn = document.getElementById('sd-complete-btn');
  const collectBtn = document.getElementById('sd-collect-btn');
  const cancelBtn = document.getElementById('sd-cancel-btn');
  const cancelHint = document.getElementById('sd-cancel-hint');
  if (payBtn) payBtn.style.display = (isActive && !rental.is_paid) ? '' : 'none';
  if (completeBtn) {
    completeBtn.style.display = (isActive && !rental.is_upcoming && !pendingCash) ? '' : 'none';
  }
  if (collectBtn) collectBtn.classList.toggle('hidden', !pendingCash);

  if (cancelBtn) {
    const showCancel = isActive && rental.is_upcoming && rental.can_cancel;
    cancelBtn.classList.toggle('hidden', !showCancel);
    cancelBtn.disabled = false;
  }
  if (cancelHint) {
    if (isActive && rental.is_upcoming && !rental.can_cancel && rental.cancel_blocked_reason) {
      cancelHint.textContent = rental.cancel_blocked_reason;
      cancelHint.classList.remove('hidden');
    } else {
      cancelHint.classList.add('hidden');
      cancelHint.textContent = '';
    }
  }

  openModal('modal-sched-detail');
}

// ── Init ───────────────────────────────────────────────────────────────────
(function initSchedule() {
  function setup() {
    loadCourtsSchedule();
    _ensureOptions(); // preload so modal opens instantly
    setInterval(loadCourtsSchedule, 30000);
    setInterval(_updateNowIndicator, 60000); // reposition every minute

    // Duration buttons
    document.getElementById('sb-dur-minus')?.addEventListener('click', () => {
      if (_bookCtx.durationHours > 1) {
        _bookCtx.durationHours--;
        delete document.getElementById('sb-payment').dataset.touched;
        _refreshBookModal();
      }
    });
    document.getElementById('sb-dur-plus')?.addEventListener('click', () => {
      if (_bookCtx.durationHours < 12) {
        _bookCtx.durationHours++;
        delete document.getElementById('sb-payment').dataset.touched;
        _refreshBookModal();
      }
    });

    // Payment input
    document.getElementById('sb-payment')?.addEventListener('input', (e) => {
      e.target.dataset.touched = '1';
      const totalText = document.getElementById('sb-total')?.textContent || '';
      const total = parseFloat(totalText.replace(/[^\d.]/g, '')) || 0;
      _updateBookBalance(total);
    });

    // Customer name → re-validate confirm button
    document.getElementById('sb-customer')?.addEventListener('input', () => {
      const totalText = document.getElementById('sb-total')?.textContent || '';
      const total = parseFloat(totalText.replace(/[^\d.]/g, '')) || 0;
      _updateBookBalance(total);
    });

    // Confirm booking
    document.getElementById('sb-confirm-btn')?.addEventListener('click', async () => {
      const { courtId, hour, durationHours } = _bookCtx;
      const customer = document.getElementById('sb-customer').value.trim();
      const payment = parseFloat(document.getElementById('sb-payment').value) || 0;
      if (!customer) { showToast('Please enter a customer name', 'error'); return; }

      const startIso = _buildStartIso(hour);
      try {
        const res = await fetch('/api/rent/court/schedule', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            court_id: courtId,
            customer_name: customer,
            start_time: startIso,
            duration_hours: durationHours,
            payment_received: payment,
          }),
        });
        const data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Booking failed');
        showToast(`Booked! Billed ${_money(data.amount_billed)}${data.balance_due > 0 ? ', balance ' + _money(data.balance_due) : ''}`);
        closeModal('modal-sched-book');
        await loadCourtsSchedule();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });

    // Detail modal action buttons
    document.getElementById('sd-pay-btn')?.addEventListener('click', () => {
      if (!_detailRental) return;
      closeModal('modal-sched-detail');
      openRecordPaymentModal('court', _detailRental.id);
    });
    document.getElementById('sd-complete-btn')?.addEventListener('click', () => {
      if (!_detailRental) return;
      closeModal('modal-sched-detail');
      openCompleteModal('court', _detailRental.id);
    });
    document.getElementById('sd-collect-btn')?.addEventListener('click', async () => {
      if (!_detailRental) return;
      try {
        const res = await fetch(`/api/payment/court/${_detailRental.id}/collect`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Failed');
        showToast('Cash collection recorded');
        closeModal('modal-sched-detail');
        await loadCourtsSchedule();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });

    document.getElementById('sd-cancel-btn')?.addEventListener('click', async () => {
      if (!_detailRental) return;
      const refundNote = _detailRental.is_paid && _detailRental.amount_paid > 0
        ? `\n\nPaid ${_money(_detailRental.amount_paid)} — refund manually if required.`
        : '';
      if (!confirm(
        `Cancel upcoming booking for ${_detailRental.customer_name}?\n` +
        `${_fmtTime(_detailRental.started_at)} – ${_fmtTime(_detailRental.ends_at)}${refundNote}`
      )) return;
      try {
        const res = await fetch(`/api/rent/court/${_detailRental.id}/cancel`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Cancellation failed');
        showToast('Booking cancelled');
        closeModal('modal-sched-detail');
        await loadCourtsSchedule();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setup);
  } else {
    setup();
  }
})();

window.openScheduleBookModal = openScheduleBookModal;
window.openScheduleDetail = openScheduleDetail;
