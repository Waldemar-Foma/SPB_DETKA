import { $, h, icon } from '../utils/dom.js';
import { formatRub, formatNumber } from '../utils/format.js';
import { analyzeProcurement, getSuppliersFor } from '../api/procurement.js';
import { SupplierCard } from '../components/supplierCard.js';
import { openDrawer } from '../components/drawer.js';

const DEFAULT_QUERY = 'Поставка медицинского оборудования';

export async function initSearchPage() {
  const state = {
    procurement: null,
    sort: 'relevance_desc',
    filters: {},
  };

  await loadProcurement(state);
  await refreshFeed(state);
  bindControls(state);
}

async function loadProcurement(state) {
  state.procurement = await analyzeProcurement(DEFAULT_QUERY);
  renderProcurement(state.procurement);
}

async function refreshFeed(state) {
  const { items, total } = await getSuppliersFor(
    state.procurement.procurement_id,
    { sort: state.sort, ...state.filters },
  );
  $('#feed-count').textContent = formatNumber(total);
  renderFeed(items);
}

function renderProcurement(p) {
  const host = $('#procurement-card');
  host.innerHTML = '';

  host.append(
    h('a', { class: 'procurement-card__back', href: '#' },
      icon('chevron-left'), 'К поиску'),
    h('h1', { class: 'procurement-card__title' }, p.title),
    h('div', { class: 'procurement-card__attrs' },
      attr('calendar-alt', `№ ${p.procurement_id}`),
      attr('list-ol', `ОКПД2 ${p.okpd2} — ${p.okpd2_name}`),
      attr('map-marker-alt', p.region),
      h('div', { class: 'procurement-card__price' },
        h('div', { class: 'procurement-card__price-label' }, 'Начальная цена'),
        h('div', { class: 'procurement-card__price-value' }, formatRub(p.initial_price)),
      ),
    ),
  );
}

const attr = (iconName, text) =>
  h('div', { class: 'procurement-card__attr' }, icon(iconName), h('span', {}, text));

function renderFeed(items) {
  const host = $('#supplier-feed');
  host.innerHTML = '';
  items.forEach((item) => host.append(SupplierCard(item, openDrawer)));
}

function bindControls(state) {
  $('#feed-sort').addEventListener('change', (e) => {
    state.sort = e.target.value;
    refreshFeed(state);
  });

  let debounce;
  $('#feed-filter-input').addEventListener('input', (e) => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.filters.q = e.target.value.trim() || undefined;
      refreshFeed(state);
    }, 250);
  });

  $('#feed-filter-reset').addEventListener('click', () => {
    state.filters = {};
    $('#feed-filter-input').value = '';
    refreshFeed(state);
  });
}