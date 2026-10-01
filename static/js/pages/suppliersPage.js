import { api } from '../api/client.js';
import { toast } from '../components/toast.js';

const esc = (v) => String(v ?? '').replace(/[&<>'"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

export async function initSuppliersPage() {
  const search = document.getElementById('registry-search');
  const role = document.getElementById('registry-role-filter');
  let timer;
  const reload = () => loadRegistry({q: search?.value.trim(), role: role?.value});
  search?.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(reload, 220); });
  role?.addEventListener('change', reload);
  await loadStatus();
  await reload();
}

async function loadStatus() {
  try {
    const data = await api.get('/suppliers/registry-status');
    const latest = data.latest;
    document.getElementById('registry-gisp-count').textContent = `ГИСП: ${data.gisp_manufacturers}`;
    document.getElementById('registry-enriched-count').textContent = `Обогащено: ${data.enriched_suppliers}`;
    const host = document.getElementById('registry-sync-text');
    if (!latest) {
      host.textContent = 'Обогащение реестрами ещё не запускалось. После enrich_gisp.py результат появится здесь автоматически.';
    } else {
      const dt = latest.finished_at ? new Date(latest.finished_at).toLocaleString('ru-RU') : '—';
      host.textContent = `${latest.source}: ${latest.status}; строк в реестре ${latest.rows_total}, совпадений с локальным пулом ${latest.matched_suppliers}. Последний запуск: ${dt}.`;
    }
  } catch (e) {
    console.warn(e);
  }
}

async function loadRegistry(params={}) {
  const tbody = document.getElementById('registry-body');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6">Загрузка…</td></tr>';
  try {
    const clean = Object.fromEntries(Object.entries(params).filter(([,v]) => v));
    const qs = new URLSearchParams({...clean, per_page: 100}).toString();
    const data = await api.get(`/suppliers/?${qs}`);
    tbody.innerHTML = data.items.map(row).join('') || '<tr><td colspan="6">Ничего не найдено.</td></tr>';
    document.getElementById('registry-meta').textContent = `Показано ${data.items.length} из ${data.meta.total} локальных компаний (Санкт-Петербург + Ленинградская область).`;
  } catch (e) {
    tbody.innerHTML = '<tr><td colspan="6">Ошибка загрузки реестра.</td></tr>';
    toast('Не удалось загрузить реестр: ' + e.message, 'error');
  }
}

function row(item) {
  const registries = [
    item.is_gisp_manufacturer ? '<span class="badge">ГИСП</span>' : '',
    item.is_sme ? '<span class="badge">МСП</span>' : '',
  ].filter(Boolean).join(' ') || '—';
  const updated = item.enrichment_updated_at ? new Date(item.enrichment_updated_at).toLocaleDateString('ru-RU') : '—';
  return `<tr>
    <td><strong>${esc(item.name)}</strong><br><small>ИНН ${esc(item.inn)} · ${esc(item.region)}</small></td>
    <td>${esc(item.company_type)}</td>
    <td>${registries}<br><small>обновлено: ${esc(updated)}</small></td>
    <td>${esc(item.primary_okved || '—')}</td>
    <td>${esc(item.wins_count)} побед / ${esc(item.participation_count)} участий</td>
    <td>${esc(item.data_source || '—')}</td>
  </tr>`;
}
