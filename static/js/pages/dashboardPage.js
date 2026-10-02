import { $ } from '../utils/dom.js';
import { analyzeProcurement, getSuppliersFor } from '../api/procurement.js';
import { initMapView } from '../components/mapView.js';
import { openDrawer } from '../components/drawer.js';
import { renderRelevanceChart, renderRegionsChart, renderTypesChart } from '../components/relevanceWidgets.js';
import { renderShortlist, renderEmptyTable } from '../components/shortlistTable.js';
import { toast } from '../components/toast.js';

export async function initDashboardPage() {
  // Если пользователь вернулся кнопкой «Назад» после выбора исполнителя,
  // браузер может восстановить старую карту из bfcache. Принудительная
  // перезагрузка заставит сервер проверить актуальный статус заявки и
  // перенаправить на карточку заказа.
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) window.location.reload();
  }, { once: true });

  const params = new URLSearchParams(location.search);
  const procurementId = params.get('procurement');
  if (!procurementId) { location.replace('/contracts/'); return; }
  const state = { procurement: null, items: [], types: new Set(), query: '' };
  state.procurement = await analyzeProcurement(procurementId);
  if (!['matching', 'selected'].includes(state.procurement.status)) {
    window.location.replace(`/contracts/${encodeURIComponent(state.procurement.procurement_id)}`);
    return;
  }
  renderContext(state.procurement);
  bindFilters(state);
  bindSearch(state);
  bindSelection(state);
  await loadFeed(state);
}

async function loadFeed(state) {
  const typeParam = [...state.types].join(',');
  try {
    const payload = await getSuppliersFor(state.procurement.procurement_id, { company_types: typeParam });
    state.items = payload.items || [];
    state.procurement.selected_supplier_inn = payload.meta?.selected_supplier_inn || null;
    state.procurement.selected_supplier_name = payload.meta?.selected_supplier_name || null;
    renderMetrics(payload.meta, state.items);
    renderSummary(state);
    renderList(state);
    renderRelevanceChart(state.items); renderRegionsChart(state.items); renderTypesChart(state.items);
    initMapView(state.items, (inn) => openDrawer(inn, state.procurement), state.procurement.selected_supplier_inn);
    if (!state.items.length) toast('По выбранным типам компаний подходящих кандидатов не найдено.', 'info');
  } catch (e) { toast('Не удалось построить подбор: ' + e.message, 'error'); }
}

function renderContext(p) {
  $('#procurement-current-title').textContent = p.title || 'Заявка';
  const okpd = p.okpd2 && p.okpd2 !== 'AUTO' ? ` · ОКПД2 ${p.okpd2}` : '';
  $('#procurement-current-meta').textContent = `${p.delivery_region || p.region || ''}${okpd}`;
}

function renderMetrics(meta, items) {
  $('#kpi-pool').textContent = Number(meta?.full_pool || 0).toLocaleString('ru-RU');
  $('#kpi-shortlist').textContent = String(items.length);
  const avg = items.length ? Math.round(items.reduce((s,x)=>s+(x.score||0),0)/items.length) : 0;
  $('#kpi-reliability').textContent = `${avg}%`;
}

function renderSummary(state) {
  const host=$('#ai-summary-text'); if(!host)return;
  if(!state.items.length){ host.textContent='Измените фильтр типов компаний или уточните описание заявки.'; return; }
  const best=state.items[0];
  const filter=state.types.size ? ` с учётом фильтра «${[...state.types].join(', ')}»` : '';
  host.textContent=`Найден топ-${state.items.length}${filter}. Лучшее совпадение — ${best.score}%. Нажмите на компанию, чтобы увидеть простое объяснение, отзывы и возможные ограничения.`;
}

function renderList(state) {
  const tbody = $('#shortlist-body'); if (!tbody) return;
  const subtitle = $('#list-subtitle');
  const total = state.items.length;
  const q = state.query.trim().toLowerCase();
  const visible = q
    ? state.items.filter((x) => [x.name, x.inn, x.region, x.company_type].some((v) => String(v || '').toLowerCase().includes(q)))
    : state.items;
  if (subtitle) {
    subtitle.textContent = total
      ? `Топ-${total} компаний сформирован ИИ. Финальный выбор всегда за вами.`
      : 'Нет компаний для текущего фильтра.';
  }
  if (!visible.length) { renderEmptyTable(tbody); return; }
  renderShortlist(tbody, visible, (inn) => openDrawer(inn, state.procurement), state.procurement.selected_supplier_inn);
}

function bindSearch(state) {
  const input = $('#list-search');
  input?.addEventListener('input', () => { state.query = input.value; renderList(state); });
}

function bindFilters(state) {
  const modal=$('#match-filter');
  const open=()=>{ modal.hidden=false; };
  $('#feed-open-filters')?.addEventListener('click',open); $('#list-open-filters')?.addEventListener('click',open);
  $('#match-filter-close')?.addEventListener('click',()=>modal.hidden=true);
  $('#match-filter-all')?.addEventListener('click',async()=>{ modal.querySelectorAll('input[type=checkbox]').forEach(x=>x.checked=false); state.types.clear(); modal.hidden=true; await loadFeed(state); });
  $('#match-filter-apply')?.addEventListener('click',async()=>{ state.types=new Set([...modal.querySelectorAll('input[type=checkbox]:checked')].map(x=>x.value)); modal.hidden=true; await loadFeed(state); });
  modal?.addEventListener('click',(e)=>{if(e.target===modal)modal.hidden=true;});
}

function bindSelection(state) {
  document.addEventListener('procurement:selection-changed', async (event)=>{
    const d=event.detail||{}; if(d.procurement_id!==state.procurement.procurement_id)return;
    state.procurement.selected_supplier_inn=d.selected_supplier_inn; state.procurement.selected_supplier_name=d.selected_supplier_name;
    await loadFeed(state);
  });
}
