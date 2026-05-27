function formatCountdown(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [h, m, s].map(v => String(v).padStart(2, '0')).join(':');
}

function formatExcessLabel(minutes) {
  if (minutes < 60) return `+${minutes}m over`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `+${h}h ${m}m over` : `+${h}h over`;
}

function applyCardTiming(card) {
  if (!card || card.dataset.status !== 'rented') return;

  const countdown = card.querySelector('.countdown');
  const excessEl = card.querySelector('.excess-label');
  if (!countdown) return;

  let sec = parseInt(countdown.dataset.seconds, 10);
  if (isNaN(sec)) {
    const endsAt = card.dataset.endsAt;
    if (endsAt) {
      sec = Math.floor((new Date(endsAt) - Date.now()) / 1000);
    } else {
      sec = 0;
    }
  }

  card.classList.remove('ring-2', 'ring-amber-400', 'bg-amber-50', 'ring-red-500', 'bg-red-50', 'border-amber-300', 'border-red-300');

  if (sec > 0) {
    countdown.textContent = formatCountdown(sec);
    countdown.dataset.seconds = sec - 1;
    countdown.classList.remove('text-red-600', 'animate-pulse');
    if (card.dataset.cardType === 'court') {
      countdown.classList.add('text-teal-700');
      countdown.classList.remove('text-amber-700');
    } else {
      countdown.classList.add('text-amber-700');
      countdown.classList.remove('text-teal-700');
    }
    if (excessEl) {
      excessEl.classList.add('hidden');
      excessEl.textContent = '';
    }

    const warningMinutes = parseInt(document.body.dataset.warningMinutes || '15', 10);
    if (sec <= warningMinutes * 60) {
      card.classList.add('ring-2', 'ring-amber-400', 'bg-amber-50', 'border-amber-300');
      countdown.classList.add('text-amber-700', 'animate-pulse');
      countdown.classList.remove('text-teal-700');
    }
    return;
  }

  countdown.textContent = '00:00:00';
  countdown.classList.add('text-red-600', 'animate-pulse');
  countdown.classList.remove('text-teal-700', 'text-amber-700');
  card.classList.add('ring-2', 'ring-red-500', 'bg-red-50', 'border-red-300');

  const endsAt = card.dataset.endsAt;
  let excessMinutes = parseInt(card.dataset.excessMinutes || '0', 10);
  if (endsAt) {
    const excessSec = Math.max(0, Math.floor((Date.now() - new Date(endsAt)) / 1000));
    excessMinutes = Math.ceil(excessSec / 60) || 0;
    card.dataset.excessMinutes = excessMinutes;
  }
  if (excessEl && excessMinutes > 0) {
    excessEl.textContent = formatExcessLabel(excessMinutes);
    excessEl.classList.remove('hidden');
  }
}

function updateCountdowns() {
  document.querySelectorAll('.court-card, .racket-card').forEach(applyCardTiming);
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
      card.dataset.timingState = item.rental.timing_state;
      card.dataset.excessMinutes = item.rental.excess_minutes;
      countdown.dataset.seconds = item.rental.time_remaining_seconds;
    }
    applyCardTiming(card);
  });
}

setInterval(updateCountdowns, 1000);
setInterval(pollStatus, 10000);
updateCountdowns();
