import { $, $$ } from '../utils/dom.js';

export function initFiltersDrawer(onApply) {
  if (document.body.dataset.filtersBound === '1') {
    _state.apply = onApply;
    return;
  }
  document.body.dataset.filtersBound = '1';
  _state.apply = onApply;

  document.addEventListener('click', (e) => {
    if (e.target.closest('#feed-open-filters')) { e.preventDefault(); _open(); return; }
    if (e.target.closest('#filters-close') || e.target.id === 'filters-overlay') {
      e.preventDefault(); _close(); return;
    }
    if (e.target.closest('#filters-apply')) {
      e.preventDefault(); _state.apply?.(_collectValues()); _close(); return;
    }
    if (e.target.closest('#filters-reset')) {
      e.preventDefault(); _resetForm(); _state.apply?.({}); _close();
    }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') _close();
  });
}

const _state = { apply: null };
const _open = () => document.body.classList.add('is-filters-open');
const _close = () => document.body.classList.remove('is-filters-open');

function _collectValues() {
  const values = {};
  const type = $('input[name="company_type"]:checked');
  if (type?.value) values.company_type = type.value;
  const region = $('input[name="region"]:checked');
  if (region?.value) values.region = region.value;
  const exp = $('input[name="min_experience"]:checked');
  if (exp?.value) values.min_experience = exp.value;
  return values;
}

function _resetForm() {
  $$('#filters-drawer input').forEach((el) => { el.checked = false; });
}
