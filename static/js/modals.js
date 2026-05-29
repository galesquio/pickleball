const CURRENCY = '₱';

let completeContext = { type: null, rentalId: null, preview: null };
let paymentContext = { type: null, rentalId: null, preview: null };
let _racketOptions = null;
let _racketDurationHours = 1;
let _racketPriceQuote = null;

function computeGreedyDuration(durationHours, options) {
  if (!options?.length) {
    return { total: 0, breakdown: [] };
  }
  const opts = [...options].sort((a, b) => b.duration_minutes - a.duration_minutes);
  let remaining = durationHours * 60;
  let total = 0;
  const breakdown = [];

  while (remaining > 0) {
    const best = opts.find((o) => o.duration_minutes <= remaining) || opts[opts.length - 1];
    total += best.price;
    const last = breakdown[breakdown.length - 1];
    if (last && last.id === best.id) {
      last.count += 1;
    } else {
      breakdown.push({ id: best.id, label: best.label, price: best.price, count: 1 });
    }
    remaining = Math.max(0, remaining - best.duration_minutes);
  }
  return { total, breakdown };
}

function loadRacketOptionsFromDom() {
  const el = document.getElementById('racket-time-options-data');
  if (!el) return [];
  try {
    const parsed = JSON.parse(el.textContent);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function ensureRacketOptions() {
  if (_racketOptions?.length) return _racketOptions;
  const fromDom = loadRacketOptionsFromDom();
  if (fromDom.length) {
    _racketOptions = fromDom;
    return _racketOptions;
  }
  try {
    const res = await fetch('/api/time-options?type=racket');
    const data = await res.json();
    _racketOptions = data.options || [];
  } catch {
    _racketOptions = [];
  }
  return _racketOptions;
}

function adjustRacketRentHours(delta) {
  const next = _racketDurationHours + delta;
  if (next < 1 || next > 12) return;
  _racketDurationHours = next;
  const paymentInput = document.getElementById('rent-racket-payment');
  if (paymentInput) delete paymentInput.dataset.touched;
  refreshRacketRentDuration();
}

function openModal(id) {
  document.getElementById(id).classList.remove('hidden');
}

function closeModal(id) {
  document.getElementById(id).classList.add('hidden');
}

function resetRentPaymentTouched(kind) {
  const input = document.getElementById(`rent-${kind}-payment`);
  if (input) delete input.dataset.touched;
}

function openRentCourtModal(courtId, courtName) {
  const select = document.getElementById('rent-court-select');
  if (select) select.value = courtId;
  document.getElementById('rent-court-id').value = courtId;
  resetRentPaymentTouched('court');
  openModal('modal-rent-court');
  updateRentPayment('court');
}

function openRentRacketModal(racketId, racketName) {
  const select = document.getElementById('rent-racket-select');
  if (select) select.value = racketId;
  document.getElementById('rent-racket-id').value = racketId;
  _racketDurationHours = 1;
  _racketPriceQuote = null;
  _racketOptions = loadRacketOptionsFromDom();
  resetRentPaymentTouched('racket');
  openModal('modal-rent-racket');
  ensureRacketOptions().then(() => refreshRacketRentDuration());
  refreshRacketRentDuration();
}

function openSwapModal(rentalId, customer, timeRemaining) {
  document.getElementById('swap-rental-id').value = rentalId;
  document.getElementById('swap-customer').textContent = customer;
  openModal('modal-swap-racket');
}

function money(n) {
  return CURRENCY + Math.round(Number(n) || 0);
}

function selectedBilledAmount(kind) {
  if (kind === 'racket') {
    if (_racketPriceQuote != null) return _racketPriceQuote.total_amount || 0;
    if (!_racketOptions?.length) return 0;
    return computeGreedyDuration(_racketDurationHours, _racketOptions).total;
  }
  const radio = document.querySelector('.rent-court-option:checked');
  return radio ? parseFloat(radio.dataset.billed) || 0 : 0;
}

async function fetchRacketPriceQuote(durationHours) {
  try {
    const res = await fetch(`/api/rent/racket/price?duration_hours=${durationHours}`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

function refreshRacketRentDuration() {
  const durEl = document.getElementById('rent-racket-dur-value');
  const endEl = document.getElementById('rent-racket-end-label');
  const breakdownEl = document.getElementById('rent-racket-breakdown');
  const minusBtn = document.getElementById('rent-racket-dur-minus');
  const plusBtn = document.getElementById('rent-racket-dur-plus');
  if (!durEl) return;

  const hours = _racketDurationHours;
  durEl.textContent = hours;
  if (minusBtn) minusBtn.disabled = hours <= 1;
  if (plusBtn) plusBtn.disabled = hours >= 12;

  const now = new Date();
  const playHours = (_racketPriceQuote?.play_duration_minutes || hours * 60) / 60;
  const end = new Date(now.getTime() + playHours * 60 * 60 * 1000);
  if (endEl) {
    endEl.textContent = `Ends around ${end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  }

  if (breakdownEl) {
    breakdownEl.innerHTML = '<span class="text-gray-400 text-xs">Loading rates…</span>';
    delete breakdownEl.dataset.total;
  }

  fetchRacketPriceQuote(hours).then((data) => {
    if (!data || _racketDurationHours !== hours) return;
    _racketPriceQuote = data;
    const total = data.total_amount || 0;
    const playMins = data.play_duration_minutes || hours * 60;
    if (endEl) {
      const end = new Date(Date.now() + playMins * 60 * 1000);
      endEl.textContent = `Ends around ${end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    }
    if (!breakdownEl) {
      updateRentPayment('racket');
      return;
    }
    let html = '';
    if (data.promo) {
      html += `<div class="flex justify-between text-violet-700"><span>🎉 ${data.promo.name}</span><span class="text-xs font-medium">${data.promo.summary}</span></div>`;
    }
    (data.breakdown || []).forEach((item) => {
      const label = item.count > 1 ? `${item.label} ×${item.count}` : item.label;
      html += `<div class="flex justify-between"><span>${label}</span><span>${money(item.price * item.count)}</span></div>`;
    });
    if (!html) {
      html = `<div class="flex justify-between"><span>${hours}h rental</span><span>${money(total)}</span></div>`;
    }
    breakdownEl.innerHTML = html;
    breakdownEl.dataset.total = String(total);
    updateRentPayment('racket');
  });
}

function updateRentPayment(kind) {
  const billed = selectedBilledAmount(kind);
  const billedEl = document.getElementById(`rent-${kind}-billed`);
  const balanceEl = document.getElementById(`rent-${kind}-balance`);
  const paymentInput = document.getElementById(`rent-${kind}-payment`);
  const submitBtn = document.getElementById(`rent-${kind}-submit`);
  if (!billedEl || !balanceEl || !paymentInput) return;

  billedEl.textContent = money(billed);
  if (!paymentInput.dataset.touched && billed > 0) {
    paymentInput.value = billed;
  }
  const payment = parseFloat(paymentInput.value) || 0;
  const balance = Math.max(0, billed - payment);
  balanceEl.textContent = money(balance);

  let invalid = billed <= 0;
  if (payment > billed + 0.009) invalid = true;
  if (submitBtn) {
    submitBtn.disabled = invalid;
    submitBtn.classList.toggle('opacity-50', invalid);
    submitBtn.classList.toggle('cursor-not-allowed', invalid);
  }
}

function initRentPayment(kind) {
  const formId = kind === 'court' ? 'form-rent-court' : 'form-rent-racket';
  const form = document.getElementById(formId);
  if (!form) return;
  if (kind === 'court') {
    form.querySelectorAll('.rent-court-option').forEach((radio) => {
      radio.addEventListener('change', () => updateRentPayment(kind));
    });
  }
  document.getElementById(`rent-${kind}-payment`)?.addEventListener('input', (e) => {
    e.target.dataset.touched = '1';
    updateRentPayment(kind);
  });
  updateRentPayment(kind);
}

function updateCompleteChange() {
  const preview = completeContext.preview;
  if (!preview) return;
  const payment = parseFloat(document.getElementById('complete-payment').value) || 0;
  const due = preview.amount_due_now || 0;
  const change = Math.max(0, payment - due);
  document.getElementById('complete-change').textContent = money(change);
  const btn = document.getElementById('complete-submit-btn');
  if (due > 0 && payment < due - 0.009) {
    btn.disabled = true;
    btn.classList.add('opacity-50', 'cursor-not-allowed');
  } else {
    btn.disabled = false;
    btn.classList.remove('opacity-50', 'cursor-not-allowed');
  }
}

function renderCompletePreview(preview) {
  document.getElementById('complete-loading').classList.add('hidden');
  document.getElementById('complete-body').classList.remove('hidden');

  document.getElementById('complete-item-name').textContent = preview.item_name;
  document.getElementById('complete-customer').textContent = preview.customer;
  document.getElementById('complete-plan').textContent = preview.time_option_label;
  document.getElementById('complete-base-billed').textContent = money(preview.base_amount_billed);
  document.getElementById('complete-base-paid').textContent = money(preview.base_amount_paid);

  const balanceRow = document.getElementById('complete-balance-row');
  if (preview.balance_due > 0) {
    balanceRow.classList.remove('hidden');
    balanceRow.classList.add('flex');
    document.getElementById('complete-balance').textContent = money(preview.balance_due);
  } else {
    balanceRow.classList.add('hidden');
    balanceRow.classList.remove('flex');
  }

  const overtimeRow = document.getElementById('complete-overtime-row');
  const excessNote = document.getElementById('complete-excess-note');
  if (preview.overtime_charge > 0) {
    overtimeRow.classList.remove('hidden');
    overtimeRow.classList.add('flex');
    document.getElementById('complete-overtime-label').textContent =
      `Overtime (${preview.overtime_hours_charged}h × ${money(preview.rate_per_hour)})`;
    document.getElementById('complete-overtime-amount').textContent = money(preview.overtime_charge);
    excessNote.classList.remove('hidden');
    excessNote.textContent = `Late by ${preview.excess_label} (grace ${preview.grace_minutes} min)`;
  } else if (preview.excess_minutes > 0) {
    overtimeRow.classList.add('hidden');
    overtimeRow.classList.remove('flex');
    excessNote.classList.remove('hidden');
    excessNote.textContent = `Late by ${preview.excess_label} — within ${preview.grace_minutes} min grace, no overtime charge`;
  } else {
    overtimeRow.classList.add('hidden');
    overtimeRow.classList.remove('flex');
    excessNote.classList.add('hidden');
  }

  const paidNote = document.getElementById('complete-paid-note');
  const dueLabel = document.getElementById('complete-due-label');
  if (preview.balance_due <= 0 && preview.overtime_charge <= 0) {
    paidNote.classList.remove('hidden');
    dueLabel.textContent = 'Nothing due';
  } else if (preview.balance_due <= 0) {
    paidNote.classList.remove('hidden');
    dueLabel.textContent = 'Collect now (overtime only)';
  } else {
    paidNote.classList.add('hidden');
    dueLabel.textContent = 'Collect now';
  }

  document.getElementById('complete-due-now').textContent = money(preview.amount_due_now);
  const paymentInput = document.getElementById('complete-payment');
  paymentInput.value = preview.amount_due_now > 0 ? preview.amount_due_now : '';
  updateCompleteChange();
}

function updatePaymentSubmit() {
  const preview = paymentContext.preview;
  if (!preview) return;
  const payment = parseFloat(document.getElementById('payment-amount').value) || 0;
  const balance = preview.balance_due || 0;
  const btn = document.getElementById('payment-submit-btn');
  const invalid = balance <= 0 || payment <= 0 || payment > balance + 0.009;
  btn.disabled = invalid;
  btn.classList.toggle('opacity-50', invalid);
  btn.classList.toggle('cursor-not-allowed', invalid);
}

function renderPaymentPreview(preview) {
  document.getElementById('payment-loading').classList.add('hidden');
  document.getElementById('payment-body').classList.remove('hidden');
  document.getElementById('payment-item-name').textContent = preview.item_name;
  document.getElementById('payment-customer').textContent = preview.customer;
  document.getElementById('payment-billed').textContent = money(preview.base_amount_billed);
  document.getElementById('payment-paid').textContent = money(preview.base_amount_paid);
  document.getElementById('payment-balance').textContent = money(preview.balance_due);
  const input = document.getElementById('payment-amount');
  input.value = preview.balance_due > 0 ? preview.balance_due : '';
  updatePaymentSubmit();
}

async function openRecordPaymentModal(type, rentalId) {
  paymentContext = { type, rentalId, preview: null };
  openModal('modal-record-payment');
  document.getElementById('payment-loading').classList.remove('hidden');
  document.getElementById('payment-body').classList.add('hidden');

  try {
    const res = await fetch(`/api/payment/${type}/${rentalId}/preview`);
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Failed to load payment');
    if (data.paid_in_full) throw new Error('Base rental is already paid in full');
    paymentContext.preview = data;
    renderPaymentPreview(data);
  } catch (err) {
    closeModal('modal-record-payment');
    showToast(err.message, 'error');
  }
}

async function openCompleteModal(type, rentalId) {
  completeContext = { type, rentalId, preview: null };
  openModal('modal-complete-rental');
  document.getElementById('complete-loading').classList.remove('hidden');
  document.getElementById('complete-body').classList.add('hidden');

  try {
    const res = await fetch(`/api/complete/${type}/${rentalId}/preview`);
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Failed to load checkout');
    completeContext.preview = data;
    renderCompletePreview(data);
  } catch (err) {
    closeModal('modal-complete-rental');
    showToast(err.message, 'error');
  }
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok || data.error) {
    throw new Error(data.error || 'Request failed');
  }
  return data;
}

function initModalForms() {
  initRentPayment('court');
  initRentPayment('racket');

  document.getElementById('payment-amount')?.addEventListener('input', updatePaymentSubmit);

  document.getElementById('payment-submit-btn')?.addEventListener('click', async () => {
    const { type, rentalId, preview } = paymentContext;
    if (!type || !rentalId || !preview) return;
    const payment = parseFloat(document.getElementById('payment-amount').value) || 0;
    try {
      const data = await postJson(`/api/payment/${type}/${rentalId}`, { payment_received: payment });
      let msg = `Payment recorded — ${money(data.amount_paid)} of ${money(data.amount_billed)}`;
      if (data.balance_due > 0) msg += `, balance ${money(data.balance_due)}`;
      else msg += ', paid in full';
      showToast(msg);
      closeModal('modal-record-payment');
      setTimeout(() => location.reload(), 500);
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  document.getElementById('complete-payment')?.addEventListener('input', updateCompleteChange);

  document.getElementById('complete-submit-btn')?.addEventListener('click', async () => {
    const { type, rentalId, preview } = completeContext;
    if (!type || !rentalId || !preview) return;
    const payment = parseFloat(document.getElementById('complete-payment').value) || 0;
    try {
      const data = await postJson(`/api/complete/${type}/${rentalId}`, { payment_received: payment });
      let msg = 'Rental completed';
      if (data.overtime_charge > 0) {
        msg += ` — overtime ${money(data.overtime_charge)}, change ${money(data.checkout_change)}`;
      } else if (preview.balance_due > 0) {
        msg += ` — change ${money(data.checkout_change)}`;
      }
      showToast(msg);
      closeModal('modal-complete-rental');
      setTimeout(() => location.reload(), 500);
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  document.getElementById('form-rent-court')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const courtId = parseInt(form.querySelector('[name="court_id"]').value || form.court_id?.value);
    const customer = form.querySelector('[name="customer_name"]').value;
    const timeOptionId = parseInt(form.querySelector('[name="time_option_id"]:checked').value);
    const payment = parseFloat(document.getElementById('rent-court-payment').value) || 0;
    try {
      const data = await postJson('/api/rent/court', {
        court_id: courtId,
        customer_name: customer,
        time_option_id: timeOptionId,
        payment_received: payment,
      });
      let msg = `Court rented — billed ${money(data.amount_billed)}`;
      if (data.balance_due > 0) msg += `, balance ${money(data.balance_due)}`;
      showToast(msg);
      closeModal('modal-rent-court');
      setTimeout(() => location.reload(), 500);
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  document.getElementById('form-rent-racket')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const racketId = parseInt(form.querySelector('[name="racket_id"]').value);
    const customer = form.querySelector('[name="customer_name"]').value;
    const payment = parseFloat(document.getElementById('rent-racket-payment').value) || 0;
    try {
      const data = await postJson('/api/rent/racket', {
        racket_id: racketId,
        customer_name: customer,
        duration_hours: _racketDurationHours,
        payment_received: payment,
      });
      let msg = `Racket rented — billed ${money(data.amount_billed)}`;
      if (data.balance_due > 0) msg += `, balance ${money(data.balance_due)}`;
      showToast(msg);
      closeModal('modal-rent-racket');
      setTimeout(() => location.reload(), 500);
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  document.getElementById('form-swap-racket')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    try {
      await postJson('/api/swap/racket', {
        rental_id: parseInt(document.getElementById('swap-rental-id').value),
        new_racket_id: parseInt(form.querySelector('[name="new_racket_id"]').value),
        reason: form.querySelector('[name="reason"]').value,
      });
      showToast('Racket swapped successfully');
      closeModal('modal-swap-racket');
      setTimeout(() => location.reload(), 500);
    } catch (err) {
      showToast(err.message, 'error');
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initModalForms);
} else {
  initModalForms();
}

// Expose for inline onclick handlers
window.openModal = openModal;
window.closeModal = closeModal;
window.openRentCourtModal = openRentCourtModal;
window.openRentRacketModal = openRentRacketModal;
window.adjustRacketRentHours = adjustRacketRentHours;
window.openSwapModal = openSwapModal;
window.openCompleteModal = openCompleteModal;
window.openRecordPaymentModal = openRecordPaymentModal;
