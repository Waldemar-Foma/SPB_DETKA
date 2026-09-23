import { $, $$ } from '../utils/dom.js';

/**
 * Панель фильтров.
 *
 * Вся логика — на одном делегированном обработчике document.
 * Открытие/закрытие через класс .is-filters-open на <body>.
 *
 * Клик по любому из перечисленных элементов закрывает панель:
 *   - #filters-close       (крестик в шапке)
 *   - #filters-overlay     (тёмный фон)
 *   - #filters-cancel      (кнопка «Отмена», если есть)
 *
 * Плюс — клавиша Escape.
 */
export function initFiltersDrawer(onApply) {
  // Защита от повторной инициализации: если уже навешано — выходим.
  if (document.body.dataset.filtersBound === '1') {
    _updateApplyHandler(onApply);
    return;
  }
  document.body.dataset.filtersBound = '1';

  // Единственный обработчик кликов на весь документ.
  document.addEventListener('click', (e) => {
    // Открыть
    if (e.target.closest('#feed-open-filters')) {
      e.preventDefault();
      _open();
      return;
    }
    // Закрыть — крестик, overlay, отмена
    if (
      e.target.closest('#filters-close') ||
      e.target.closest('#filters-cancel') ||
      e.target.id === 'filters-overlay'
    ) {
      e.preventDefault();
      _close();
      return;
    }
    // Применить
    if (e.target.closest('#filters-apply')) {
      e.preventDefault();
      const apply = _state.apply;
      if (apply) apply(_collectValues());
      _close();
      return;
    }
    // Сбросить
    if (e.target.closest('#filters-reset')) {
      e.preventDefault();
      _resetForm();
      const apply = _state.apply;
      if (apply) apply({});
      _close();
      return;
    }
  });

  // Escape закрывает
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && _isOpen()) _close();
  });

  _updateApplyHandler(onApply);
}

// --- Состояние модуля ----------------------------------------------------

const _state = { apply: null };

function _updateApplyHandler(onApply) {
  _state.apply = onApply;
}

// --- Открытие / закрытие -------------------------------------------------

function _open() {
  document.body.classList.add('is-filters-open');
}

function _close() {
  document.body.classList.remove('is-filters-open');
}

function _isOpen() {
  return document.body.classList.contains('is-filters-open');
}

// --- Сбор и сброс значений -----------------------------------------------

function _collectValues() {
  const values = {};

  const types = $$('input[name="company_type"]:checked').map((el) => el.value);
  if (types.length) values.company_type = types[0];

  const regions = $$('input[name="region"]:checked').map((el) => el.value);
  if (regions.length) values.region = regions[0];

  const exp = $('input[name="min_experience"]:checked');
  if (exp && exp.value) values.min_experience = exp.value;

  const rev = $('input[name="min_revenue"]');
  if (rev && rev.value) values.min_revenue = rev.value;

  return values;
}

function _resetForm() {
  $$('#filters-drawer input[type="checkbox"]').forEach((el) => { el.checked = false; });
  $$('#filters-drawer input[type="radio"]').forEach((el) => { el.checked = false; });
  const rev = $('input[name="min_revenue"]');
  if (rev) rev.value = '';
}
