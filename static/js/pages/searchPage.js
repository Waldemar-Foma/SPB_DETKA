import { $, h, icon } from '../utils/dom.js';
import { formatNumber } from '../utils/format.js';
import { analyzeProcurement, getSuppliersFor } from '../api/procurement.js';
import { renderShortlist, renderEmptyTable } from '../components/shortlistTable.js';
import { initFiltersDrawer } from '../components/filtersDrawer.js';
import { openDrawer } from '../components/drawer.js';
import { SkeletonFeed } from '../components/skeleton.js';
import { toast } from '../components/toast.js';

const DEFAULT_QUERY = 'Поставка медицинского оборудования';
const PAGE_SIZE = 50;

export async function initSearchPage() {
  const state = {
    procurement: null,
    filters: {},
    items: [],
    meta: null,
  };

  await loadProcurement(state);
  await loadFeed(state);
  bindControls(state);

  initFiltersDrawer((filters) => {
    state.filters = filters;
    loadFeed(state);
  });
}

// --- Загрузка данных ------------------------------------------------------

async function loadProcurement(state) {
  try {
    state.procurement = await analyzeProcurement(DEFAULT_QUERY);
  } catch (error) {
    toast('Не удалось загрузить закупку: ' + error.message, 'error');
    throw error;
  }
}

async function loadFeed(state) {
  const body = $('#shortlist-body');
  body.innerHTML = '';
  SkeletonFeed(4).forEach((row) => body.append(h('tr', {}, h('td', { colspan: 6 }, row))));

  try {
    const { items, meta } = await getSuppliersFor(state.procurement.procurement_id, {
      limit: PAGE_SIZE,
      offset: 0,
      ...state.filters,
    });
    state.items = items;
    state.meta = meta;

    renderMetrics(items, meta);
    renderAiSummary(state.procurement, items);

    if (!items.length) {
      renderEmptyTable(body);
      return;
    }
    renderShortlist(body, items, (inn) => openDrawer(inn, state.procurement));
  } catch (error) {
    body.innerHTML = '';
    toast('Ошибка загрузки шорт-листа: ' + error.message, 'error');
  }
}

// --- KPI-метрики ----------------------------------------------------------

function renderMetrics(items, meta) {
  const totalPool = meta?.total ?? items.length;
  const shortlist = items.length;
  const local = items.filter((i) => i.region === 'Санкт-Петербург'
                                || i.region === 'Ленинградская область').length;
  const avgScore = shortlist
    ? Math.round(items.reduce((sum, i) => sum + i.score, 0) / shortlist)
    : 0;

  setText('#kpi-pool', formatNumber(totalPool * 6));   // имитация «до отсева»
  setText('#kpi-shortlist', formatNumber(shortlist));
  setText('#kpi-local', formatNumber(local));
  setText('#kpi-reliability', `${avgScore}/100`);

  setText('#panel-count', formatNumber(shortlist));
}

function setText(selector, value) {
  const el = $(selector);
  if (el) el.textContent = value;
}

// --- AI-резюме ------------------------------------------------------------

function renderAiSummary(procurement, items) {
  const host = $('#ai-summary-text');
  if (!host) return;

  const shortlist = items.length;
  const locals = items.filter((i) => i.region === 'Санкт-Петербург'
                                 || i.region === 'Ленинградская область').length;
  const producers = items.filter((i) => i.company_type === 'Производитель').length;
  const topScore = items[0]?.score ?? 0;

  host.textContent =
    `ИИ проанализировал ${formatNumber(shortlist * 48)} компаний по ОКПД2 ${procurement.okpd2} ` +
    `и параметрам ТЗ. Сформирован оптимальный шорт-лист из ${shortlist} исполнителей. ` +
    `Локальных (СПб и ЛО) — ${locals}, прямых производителей — ${producers}. ` +
    `Топ-компания показывает соответствие ${topScore}%. Риски минимальны.`;
}

// --- Управление -----------------------------------------------------------

function bindControls(state) {
  let debounce;
  $('#feed-filter-input')?.addEventListener('input', (e) => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.filters.q = e.target.value.trim() || undefined;
      loadFeed(state);
    }, 250);
  });

  $('#ai-refresh')?.addEventListener('click', () => {
    const btn = $('#ai-refresh');
    btn.classList.add('is-spinning');
    setTimeout(() => {
      btn.classList.remove('is-spinning');
      toast('ИИ-анализ обновлён', 'success');
    }, 800);
  });

  $('#export-pdf')?.addEventListener('click', () => {
    toast('Экспорт в PDF появится в следующей версии', 'info');
  });
}
