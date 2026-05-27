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

async function completeCourt(rentalId) {
  try {
    await postJson(`/api/complete/court/${rentalId}`, {});
    showToast('Court rental completed');
    setTimeout(() => location.reload(), 500);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function completeRacket(rentalId) {
  try {
    await postJson(`/api/complete/racket/${rentalId}`, {});
    showToast('Racket rental completed');
    setTimeout(() => location.reload(), 500);
  } catch (err) {
    showToast(err.message, 'error');
  }
}
