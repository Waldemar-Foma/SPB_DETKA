import { $, h, icon } from '../utils/dom.js';
import { getSupplierDetails, refreshExternalReputation } from '../api/suppliers.js';
import { selectSupplier } from '../api/procurement.js';
import { toast } from './toast.js';

export async function openDrawer(inn, procurement) {
  const drawer=$('#right-drawer'); if(!drawer)return;
  document.body.classList.add('is-drawer-open'); drawer.innerHTML='<div class="drawer__body"><div class="skeleton" style="height:240px"></div></div>';
  try { const data=await getSupplierDetails(inn,{procurement_id:procurement?.procurement_id}); drawer.innerHTML=''; drawer.append(content(data,procurement)); }
  catch(e){drawer.innerHTML=`<div class="drawer__body"><p>Не удалось загрузить компанию: ${escapeHtml(e.message)}</p></div>`;}
}
export function closeDrawer(){ document.body.classList.remove('is-drawer-open'); }

function content(data, procurement){
  const root=h('div',{class:'drawer'},
    h('div',{class:'drawer__head'},h('button',{class:'drawer__back',type:'button',onClick:closeDrawer},icon('chevron-left'),'К результатам')),
    h('div',{class:'drawer__body'},
      h('div',{class:'drawer__title-block'},h('span',{class:'drawer__eyebrow'},'Кандидат'),h('h2',{class:'drawer__title'},data.name),h('div',{class:'drawer__subtitle'},`${data.company_type} · ${data.region}`),h('div',{class:'drawer__meta'},pill(`ИНН ${data.inn}`),data.is_gisp_manufacturer?pill('Производитель ГИСП'):null)),
      explanation(data), metrics(data), warning(data), reviews(data), external(data), contacts(data),
    ),
    selection(data,procurement)
  );
  return root;
}

function explanation(data){
  const ai=data.ai_explanation||{};
  const isQwen=ai.source==='qwen2.5:3b';
  return h('section',{class:'drawer__section'},
    h('h3',{class:'drawer__section-title'},icon('sparkles'),'Почему подходит'),
    h('div',{class:`ai-explanation-source ${isQwen?'is-ai':'is-fallback'}`},isQwen?'Объяснение сформировано локальной Qwen':'Показано объяснение по рассчитанным метрикам'),
    h('p',{class:'drawer-simple-text'},ai.text||'Объяснение недоступно.')
  );
}
function metrics(data){ const m=data.metrics||{}, s=data.scoring_breakdown||{}; return h('section',{class:'drawer__section'},h('h3',{class:'drawer__section-title'},icon('chart-bar'),'Главное'),h('div',{class:'simple-metrics'},
  metric('Совпадение',`${s.total??0}%`), metric('По смыслу',`${s.semantic??0}%`), metric('Опыт в категории',`${s.category_experience??0}%`), metric('Win rate',m.win_rate==null?'Нет данных':`${m.win_rate}%`), metric('Отзывы',m.reviews_count?`${m.rating}/5 (${m.reviews_count})`:'Пока нет'), metric('Логистика',m.logistics?`${m.logistics.score}%`:'—')
),m.logistics?h('p',{class:'drawer-hint'},m.logistics.note):null); }
function warning(data){ const w=data.metrics?.workload; if(!w)return null; return h('section',{class:'drawer__section'},h('h3',{class:'drawer__section-title'},icon('clock'),'Текущая нагрузка'),h('div',{class:`workload-note workload-note--${w.level}`},h('strong',{},w.label),w.warning?h('p',{},w.warning):h('p',{},'Сервис не видит полную загрузку компании вне собственных заявок, поэтому отсутствие сигнала не является гарантией свободных ресурсов.'))); }
function reviews(data){ const rows=data.reviews||[]; return h('section',{class:'drawer__section'},h('h3',{class:'drawer__section-title'},icon('star'),'Отзывы заказчиков'),rows.length?h('div',{class:'review-list'},rows.slice(0,3).map(r=>h('div',{class:'review-item'},h('strong',{},`${r.rating}/5`),h('p',{},r.comment||'Без комментария')))):h('p',{class:'drawer-hint'},'Отзывов внутри сервиса пока нет. Оставить отзыв можно только после завершения заказа.')); }
function external(data){
  const wrap=h('div',{class:'external-mentions'}); renderExternal(wrap,data.external_mentions||[]);
  const btn=h('button',{class:'btn btn--ghost btn--sm',type:'button',onClick:async()=>{btn.disabled=true;btn.textContent='Ищем…';try{const result=await refreshExternalReputation(data.inn);renderExternal(wrap,result.items||[]);btn.textContent='Обновить поиск';}catch(e){toast('Не удалось выполнить внешний поиск: '+e.message,'error');btn.textContent='Повторить';}finally{btn.disabled=false;}}},'Проверить отзывы в интернете');
  return h('section',{class:'drawer__section'},h('h3',{class:'drawer__section-title'},icon('globe'),'Внешние упоминания'),h('p',{class:'drawer-hint'},'Показываем только реальные ссылки и сниппеты поиска. Внешний рейтинг не придумываем и не смешиваем с отзывами сервиса.'),wrap,btn);
}
function renderExternal(host,items){host.innerHTML='';if(!items.length){host.append(h('p',{class:'drawer-hint'},'Внешние упоминания ещё не загружены.'));return;}items.forEach(x=>host.append(h('a',{class:'external-mention',href:x.url,target:'_blank',rel:'noopener'},h('strong',{},x.title||x.source),h('span',{},x.snippet||x.source))));}
function contacts(data){ if(data.contacts_locked)return h('section',{class:'drawer__section contacts-locked'},h('h3',{class:'drawer__section-title'},icon('address-book'),'Контакты'),h('p',{},'Контактная информация откроется после выбора этой компании исполнителем.')); const c=data.contacts||{}; return h('section',{class:'drawer__section'},h('h3',{class:'drawer__section-title'},icon('address-book'),'Контакты исполнителя'),h('div',{class:'contact-list'},row('phone',c.phone),row('envelope',c.email),row('globe',c.website),row('map-marker-alt',c.address||data.region))); }
function selection(data,procurement){
  const locked=Boolean(procurement?.selected_supplier_inn)||procurement?.status!=='matching';
  const selected=String(procurement?.selected_supplier_inn||'')===String(data.inn);
  const btn=h('button',{class:'btn btn--accent btn--block',type:'button',disabled:locked,onClick:async()=>{btn.disabled=true;btn.textContent='Сохраняем…';try{const result=await selectSupplier(procurement.procurement_id,data.inn);procurement.selected_supplier_inn=result.selected_supplier_inn;procurement.status='selected';toast('Исполнитель выбран. Контакты открыты в заявке.','success');window.location.replace(result.details_url);}catch(e){btn.disabled=false;btn.textContent='Выбрать исполнителя';toast(e.message,'error');}}},selected?'Исполнитель выбран':(locked?'Выбор по заявке закрыт':'Выбрать исполнителя'));
  return h('div',{class:'drawer__sticky'},h('p',{class:'drawer-selection-note'},locked?'После выбора вернуться к подбору по этой заявке нельзя.':'Система рекомендует, но решение принимаете вы.'),btn);
}
const pill=t=>h('span',{},t); const metric=(l,v)=>h('div',{class:'simple-metric'},h('small',{},l),h('strong',{},v)); const row=(i,v)=>h('div',{class:'contact-list__row'},icon(i),h('span',{},v||'Не найдено в открытых данных'));
function escapeHtml(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));}
