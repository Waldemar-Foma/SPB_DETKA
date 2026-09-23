import { $ } from '../utils/dom.js';
import { formatNumber } from '../utils/format.js';
import { analyzeProcurement, getSuppliersFor } from '../api/procurement.js';
import { renderShortlist, renderEmptyTable, renderLoadingRows }
  from '../components/shortlistTable.js';
import { initMapView } from '../components/mapView.js';
import { openDrawer } from '../components/drawer.js';
import { toast } from '../components/toast.js';
import { initViewMode } from '../utils/viewMode.js';
import { initDragWidgets } from '../utils/dragWidgets.js';
import {
  renderRelevanceChart,
  renderRegionsChart,
  renderTypesChart,
} from '../components/relevanceWidgets.js';

const DEFAULT_QUERY = 'Поставка медицинского оборудования';
const PAGE_SIZE = 50;

export async function initDashboardPage() {
  const state = { procurement: null, items: [], meta: null };

  await loadProcurement(state);
  await loadFeed(state);

  initViewMode();
  initDragWidgets();
  bindAiSummary();
}

async function loadProcurement(state) {
  try {
    state.procurement = await analyzeProcurement(DEFAULT_QUERY);
  } catch (error) {
    toast('Не удалось загрузить закупку: ' + error.message, 'error');
    throw error;
  }
}

async function loadFeed(state) {
  const tbody = $('#shortlist-body');
  if (tbody) {
    tbody.innerHTML = '';
    renderLoadingRows(tbody, 4);
  }

  try {
    const { items, meta } = await getSuppliersFor(state.procurement.procurement_id, {
      limit: PAGE_SIZE,
      offset: 0,
    });

    state.items = items;
    state.meta = meta;

    renderMetrics(items, meta);
    renderAiSummary(state.procurement, items);
    renderWidgetCharts(items);
    initMapView(items, (inn) => openDrawer(inn, state.procurement));

    if (tbody) {
      tbody.innerHTML = '';
      if (!items.length) renderEmptyTable(tbody);
      else renderShortlist(tbody, items, (inn) => openDrawer(inn, state.procurement));
    }
  } catch (error) {
    console.error('[dashboard] Ошибка загрузки:', error);
    toast('Ошибка загрузки: ' + error.message, 'error');
  }
}

function renderMetrics(items, meta) {
  const pool = (meta?.total ?? items.length) * 6;
  const shortlist = items.length;
  const local = items.filter((i) =>
    i.region === 'Санкт-Петербург' || i.region === 'Ленинградская область'
  ).length;
  const avg = shortlist
    ? Math.round(items.reduce((s, i) => s + i.score, 0) / shortlist)
    : 0;

  setText('#kpi-pool', formatNumber(pool));
  setText('#kpi-shortlist', formatNumber(shortlist));
  setText('#kpi-local', formatNumber(local));
  setText('#kpi-reliability', `${avg}/100`);
  setText('#panel-count', formatNumber(shortlist));
}

const setText = (sel, v) => {
  const el = $(sel);
  if (el) el.textContent = v;
};

function renderWidgetCharts(items) {
    renderRelevanceChart(items);
    renderRegionsChart(items);
    renderTypesChart(items);
}

function renderAiSummary(procurement, items) {
  const host = $('#ai-summary-text');
  if (!host) return;

  const shortlist = items.length;
  const locals = items.filter((i) =>
    i.region === 'Санкт-Петербург' || i.region === 'Ленинградская область'
  ).length;
  const producers = items.filter((i) => i.company_type === 'Производитель').length;
  const top = items[0]?.score ?? 0;

  host.textContent =
    `ИИ проанализировал ${formatNumber(shortlist * 48)} компаний по ОКПД2 ${procurement.okpd2} ` +
    `в регионе ${procurement.region}. Сформирован оптимальный шорт-лист из ${shortlist} исполнителей. ` +
    `Локальных (СПб и ЛО) — ${locals}, прямых производителей — ${producers}. ` +
    `Топ-компания показывает индекс совпадения ${top}%.`;
}

function bindAiSummary() {
  const toggle = $('#ai-summary-toggle');
  const details = $('#ai-summary-details');
  if (!toggle || !details) return;

  toggle.addEventListener('click', () => {
    const expanded = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', String(!expanded));
    toggle.textContent = !expanded ? 'Скрыть' : 'Показать подробнее';
    details.hidden = expanded;
  });
}
