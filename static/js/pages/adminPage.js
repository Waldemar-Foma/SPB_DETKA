import { toast } from '../components/toast.js';

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body?.error?.message || body?.message || `HTTP ${response.status}`);
  return body;
}

export function initAdminPage() {
  document.getElementById('admin-refresh')?.addEventListener('click', refresh);
  document.getElementById('admin-test-models')?.addEventListener('click', testModels);
  document.getElementById('admin-run-gisp')?.addEventListener('click', runGisp);
  document.getElementById('admin-enrich-gisp')?.addEventListener('click', enrichGisp);
  refresh();
  setInterval(refresh, 8000);
}

async function refresh() {
  try {
    const data = await jsonFetch('/admin/api/status');
    setText('admin-data-mode', data.database.mode);
    setText('admin-count-suppliers', data.database.suppliers);
    setText('admin-count-procurements', data.database.procurements);
    setText('admin-count-contracts', data.database.contracts);
    setText('admin-count-users', data.database.users);
    const candidate = data.models.candidate_search || {};
    const candidateText = candidate.ok
      ? `готов · ${candidate.model || 'all-minilm'} · индекс ${candidate.indexed_suppliers || '—'}`
      : (candidate.index_ok ? 'индекс есть, all-minilm не готова' : 'индекс/модель не готовы');
    setHealth('health-candidate', candidate.ok, candidateText);
    setHealth('health-embeddings', data.models.embeddings.ok, data.models.embeddings.ok ? `доступна · ${data.models.embeddings.model}` : 'не отвечает');
    const llmLoaded = data.models.llm.loaded;
    setHealth('health-llm', data.models.llm.ok && llmLoaded !== false, data.models.llm.ok ? (llmLoaded === false ? 'Ollama доступна, модель не загружена' : `доступна · ${data.models.llm.model}`) : 'не отвечает');

    const job = data.gisp.job || {};
    setHealth('health-gisp-job', job.status === 'ok' || job.status === 'idle', `${job.status || 'idle'} · ${job.message || ''}`);
    setHealth('health-gisp-file', Boolean(data.gisp.file?.exists), data.gisp.file?.exists ? `${data.gisp.file.size_mb} МБ · ${formatDate(data.gisp.file.modified_at)}` : 'файл не скачан');
    setText('gisp-log', data.gisp.log_tail || 'Журнал пока пуст.');
  } catch (error) {
    toast('Не удалось обновить админ-статус: ' + error.message, 'error');
  }
}

async function testModels() {
  const button = document.getElementById('admin-test-models');
  const output = document.getElementById('model-test-output');
  if (button) button.disabled = true;
  if (output) output.textContent = 'Выполняется реальный локальный запрос…';
  try {
    const data = await jsonFetch('/admin/api/models/test', { method: 'POST', body: '{}' });
    if (output) output.textContent = JSON.stringify(data, null, 2);
    setHealth('health-candidate', data.candidate_search?.ok, data.candidate_search?.ok ? `поиск OK · ${data.candidate_search.sample?.length || 0} кандидата · ${data.candidate_search.latency_ms} мс` : 'поиск не прошёл');
    setHealth('health-embeddings', data.embeddings.ok, data.embeddings.ok ? `инференс OK · ${data.embeddings.dimensions} измерений · ${data.embeddings.latency_ms} мс` : 'инференс не прошёл');
    setHealth('health-llm', data.llm.ok, data.llm.ok ? `инференс OK · ${data.llm.latency_ms} мс` : 'инференс не прошёл');
  } catch (error) {
    if (output) output.textContent = error.message;
    toast('Тест моделей завершился ошибкой', 'error');
  } finally {
    if (button) button.disabled = false;
  }
}

async function runGisp() {
  const button = document.getElementById('admin-run-gisp');
  if (button) button.disabled = true;
  try {
    const data = await jsonFetch('/admin/api/gisp/start', { method: 'POST', body: '{}' });
    toast(data.message || 'Синхронизация запущена', 'success');
    setTimeout(refresh, 1200);
  } catch (error) {
    toast('ГИСП: ' + error.message, 'error');
  } finally {
    if (button) button.disabled = false;
  }
}

async function enrichGisp() {
  const button = document.getElementById('admin-enrich-gisp');
  if (button) button.disabled = true;
  try {
    const data = await jsonFetch('/admin/api/gisp/enrich-existing', { method: 'POST', body: '{}' });
    toast(data.message || 'Текущий registry.xlsx применён', 'success');
    await refresh();
  } catch (error) {
    toast('ГИСП: ' + error.message, 'error');
    await refresh();
  } finally {
    if (button) button.disabled = false;
  }
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value ?? '—';
}
function setHealth(id, ok, text) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle('is-ok', Boolean(ok));
  el.classList.toggle('is-bad', !ok);
  const span = el.querySelector('div span');
  if (span) span.textContent = text || '—';
}
function formatDate(value) {
  if (!value) return '—';
  try { return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)); }
  catch { return value; }
}
