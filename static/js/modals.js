const CURRENCY = '₱';

let completeContext = { type: null, rentalId: null, preview: null };

function openModal(id) {
  document.getElementById(id).classList.remove('hidden');
}

function closeModal(id) {
  document.getElementById(id).classList.add('hidden');
}

function openRentCourtModal(courtId, courtName) {
  const select = document.getElementById('rent-court-select');
  if (select) select.value = courtId;
  document.getElementById('rent-court-id').value = courtId;
  openModal('modal-rent-court');
}

function openRentRacketModal(racketId, racketName) {
  const select = document.getElementById('rent-racket-select');
  if (select) select.value = racketId;
  document.getElementById('rent-racket-id').value = racketId;
  openModal('modal-rent-racket');
}

function openSwapModal(rentalId, customer, timeRemaining) {
  document.getElementById('swap-rental-id').value = rentalId;
  document.getElementById('swap-customer').textContent = customer;
  openModal('modal-swap-racket');
}

function money(n) {
  return CURRENCY + Math.round(Number(n) || 0);
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
  document.getElementById('complete-base').textContent = money(preview.base_amount_paid);

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

  document.getElementById('complete-due-now').textContent = money(preview.amount_due_now);
  const paymentInput = document.getElementById('complete-payment');
  paymentInput.value = preview.amount_due_now > 0 ? preview.amount_due_now : '';
  updateCompleteChange();
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
    try {
      await postJson('/api/rent/court', { court_id: courtId, customer_name: customer, time_option_id: timeOptionId });
      showToast('Court rented successfully');
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
    const timeOptionId = parseInt(form.querySelector('[name="time_option_id"]:checked').value);
    try {
      await postJson('/api/rent/racket', { racket_id: racketId, customer_name: customer, time_option_id: timeOptionId });
      showToast('Racket rented successfully');
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
window.openSwapModal = openSwapModal;
window.openCompleteModal = openCompleteModal;
