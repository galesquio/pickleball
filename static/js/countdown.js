function formatCountdown(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [h, m, s].map(v => String(v).padStart(2, '0')).join(':');
}

function updateCountdowns() {
  document.querySelectorAll('.countdown').forEach(el => {
    let sec = parseInt(el.dataset.seconds, 10);
    if (isNaN(sec)) {
      const endsAt = el.closest('[data-ends-at]')?.dataset.endsAt;
      if (endsAt) {
        sec = Math.max(0, Math.floor((new Date(endsAt) - Date.now()) / 1000));
      }
    }
    if (sec <= 0) {
      el.textContent = '00:00:00';
      el.classList.add('text-red-600', 'animate-pulse');
      return;
    }
    el.textContent = formatCountdown(sec);
    el.dataset.seconds = sec - 1;
    if (sec < 900) {
      el.classList.add('text-red-600', 'animate-pulse');
      el.classList.remove('text-teal-800', 'text-amber-800');
    }
  });
}

async function pollStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const data = await res.json();
    updateGrid('courts-grid', data.courts, 'court');
    updateGrid('rackets-grid', data.rackets, 'racket');
  } catch (e) {
    console.warn('Status poll failed', e);
  }
}

function updateGrid(gridId, items, type) {
  const grid = document.getElementById(gridId);
  if (!grid) return;
  items.forEach(item => {
    const card = grid.querySelector(`[data-${type}-id="${item.id}"]`);
    if (!card) return;
    card.dataset.status = item.status;
    const countdown = card.querySelector('.countdown');
    if (item.rental && countdown) {
      card.dataset.rentalId = item.rental.rental_id;
      card.dataset.endsAt = item.rental.ends_at;
      countdown.dataset.seconds = item.rental.time_remaining_seconds;
    }
  });
}

setInterval(updateCountdowns, 1000);
setInterval(pollStatus, 10000);
updateCountdowns();
