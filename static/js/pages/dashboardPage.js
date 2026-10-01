import { $, h, icon } from '../utils/dom.js';
import { analyzeProcurement, getSuppliersFor } from '../api/procurement.js';
import { initMapView } from '../components/mapView.js';
import { openDrawer } from '../components/drawer.js';
import { renderRelevanceChart, renderRegionsChart, renderTypesChart } from '../components/relevanceWidgets.js';
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
  const state = { procurement: null, items: [], types: new Set() };
  state.procurement = await analyzeProcurement(procurementId);
  if (state.procurement.selected_supplier_inn || state.procurement.status !== 'matching') {
    window.location.replace(`/contracts/${encodeURIComponent(state.procurement.procurement_id)}`);
    return;
  }
  renderContext(state.procurement);
  bindFilters(state);
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
  const host=$('#top5-list'); if(!host)return; host.innerHTML='';
  if(!state.items.length){ host.append(h('div',{class:'top5-empty'},'Нет компаний для текущего фильтра.')); return; }
  state.items.forEach((item,index)=>host.append(topCard(item,index+1,()=>openDrawer(item.inn,state.procurement),state.procurement.selected_supplier_inn)));
}

function topCard(item, n, open, selectedInn) {
  const m=item.metrics||{}; const selected=String(selectedInn||'')===String(item.inn);
  const rating=m.reviews_count ? `${m.rating}/5 · ${m.reviews_count} отзыв.` : 'Отзывов пока нет';
  const win=m.win_rate == null ? 'нет данных' : `${m.win_rate}%`;
  return h('article',{class:`top5-card ${selected?'is-selected':''}`,onClick:open},
    h('div',{class:'top5-card__rank'},String(n)),
    h('div',{class:'top5-card__main'},
      h('div',{class:'top5-card__title'},h('strong',{},item.name),selected?h('span',{class:'badge badge--local'},'Выбран'):null),
      h('div',{class:'top5-card__meta'},`${item.company_type} · ${item.region}`),
      h('div',{class:'top5-card__metrics'},
        miniMetric('Совпадение',`${item.score}%`), miniMetric('Win rate',win), miniMetric('Отзывы',rating), miniMetric('Логистика',`${m.geography??'—'}%`)
      ),
      item.workload_warning?h('div',{class:'top5-card__warning'},icon('exclamation-triangle'),item.workload_warning):null,
    ),
    h('button',{class:'btn btn--ghost btn--sm',type:'button',onClick:(e)=>{e.stopPropagation();open();}},'Подробнее')
  );
}
const miniMetric=(label,value)=>h('span',{class:'top5-metric'},h('small',{},label),h('b',{},value));

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
