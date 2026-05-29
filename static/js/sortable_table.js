/** Sortable table helpers — client-side DOM sort + zebra striping. */
(function (global) {
  function applyZebra(tbody) {
    if (!tbody) return;
    tbody.querySelectorAll('tr:not(.empty-row)').forEach((row, i) => {
      row.classList.remove('bg-white', 'bg-gray-50', 'hover:bg-violet-50');
      row.classList.add(i % 2 === 0 ? 'bg-white' : 'bg-gray-50');
      row.classList.add('hover:bg-violet-50');
    });
  }

  function cellValue(row, colIndex, sortType) {
    const cell = row.children[colIndex];
    if (!cell) return sortType === 'number' ? 0 : '';
    const raw = cell.dataset.sortValue ?? cell.textContent.trim();
    if (sortType === 'number') {
      return parseFloat(String(raw).replace(/[^\d.-]/g, '')) || 0;
    }
    if (sortType === 'date') {
      return new Date(raw).getTime() || 0;
    }
    return String(raw).toLowerCase();
  }

  function initSortableTable(table, defaultSort) {
    if (!table || table.dataset.sortBound) return;
    table.dataset.sortBound = '1';

    const tbody = table.querySelector('tbody');
    const headers = [...table.querySelectorAll('th[data-sort-key]')];
    if (!tbody || !headers.length) return;

    let colIndex = headers.findIndex(h => h.dataset.sortKey === defaultSort?.key);
    if (colIndex < 0) colIndex = 0;
    let sortDir = defaultSort?.dir || (headers[colIndex].dataset.sortType === 'string' ? 'asc' : 'desc');

    function indicators() {
      headers.forEach((th, i) => {
        let indicator = th.querySelector('.sort-indicator');
        if (!indicator) {
          indicator = document.createElement('span');
          indicator.className = 'sort-indicator text-violet-500 text-[10px] ml-0.5';
          th.appendChild(indicator);
        }
        if (i === colIndex) {
          indicator.textContent = sortDir === 'asc' ? '▲' : '▼';
          th.classList.add('text-violet-700');
        } else {
          indicator.textContent = '';
          th.classList.remove('text-violet-700');
        }
      });
    }

    function sortRows() {
      const th = headers[colIndex];
      const sortType = th.dataset.sortType || 'string';
      const rows = [...tbody.querySelectorAll('tr:not(.empty-row)')];
      rows.sort((a, b) => {
        const av = cellValue(a, colIndex, sortType);
        const bv = cellValue(b, colIndex, sortType);
        const cmp = av < bv ? -1 : av > bv ? 1 : 0;
        return sortDir === 'asc' ? cmp : -cmp;
      });
      rows.forEach(r => tbody.appendChild(r));
      applyZebra(tbody);
      indicators();
    }

    headers.forEach((th, i) => {
      th.classList.add('cursor-pointer', 'select-none', 'hover:bg-gray-100', 'transition-colors');
      th.addEventListener('click', () => {
        if (colIndex === i) {
          sortDir = sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          colIndex = i;
          sortDir = th.dataset.sortType === 'string' ? 'asc' : 'desc';
        }
        sortRows();
      });
    });

    sortRows();
  }

  function bindServerSort(table, onSortChange, defaultSort) {
    if (!table || table.dataset.serverSortBound) return;
    table.dataset.serverSortBound = '1';

    const headers = [...table.querySelectorAll('th[data-sort-key]')];
    let sortKey = defaultSort?.key || headers[0]?.dataset.sortKey || 'datetime';
    let sortDir = defaultSort?.dir || 'desc';

    function indicators() {
      headers.forEach(th => {
        let indicator = th.querySelector('.sort-indicator');
        if (!indicator) {
          indicator = document.createElement('span');
          indicator.className = 'sort-indicator text-violet-500 text-[10px] ml-0.5';
          th.appendChild(indicator);
        }
        const active = th.dataset.sortKey === sortKey;
        indicator.textContent = active ? (sortDir === 'asc' ? '▲' : '▼') : '';
        th.classList.toggle('text-violet-700', active);
      });
    }

    headers.forEach(th => {
      th.classList.add('cursor-pointer', 'select-none', 'hover:bg-gray-100', 'transition-colors');
      th.addEventListener('click', () => {
        const key = th.dataset.sortKey;
        if (sortKey === key) {
          sortDir = sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          sortKey = key;
          sortDir = th.dataset.sortType === 'string' ? 'asc' : 'desc';
        }
        indicators();
        onSortChange(sortKey, sortDir);
      });
    });

    indicators();
    return () => ({ sortKey, sortDir });
  }

  global.MerchTable = { initSortableTable, bindServerSort, applyZebra };
})(window);
