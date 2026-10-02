import { toast } from '../components/toast.js';

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body?.error?.message || body?.message || `HTTP ${response.status}`);
  return body;
}

export function initAdminPage() {
  document.getElementById('admin-refresh')?.addEventListener('click', () => refresh(true));
  document.getElementById('admin-test-models')?.addEventListener('click', testModels);
  document.getElementById('admin-run-gisp')?.addEventListener('click', runGisp);
  document.getElementById('admin-enrich-gisp')?.addEventListener('click', enrichGisp);
  document.getElementById('admin-run-company-enrichment')?.addEventListener('click', runCompanyEnrichment);
  refresh(false);
  setInterval(() => refresh(false), 8000);
}

async function refresh(showToast = false) {
  const refreshBtn = document.getElementById('admin-refresh');
  if (showToast && refreshBtn) refreshBtn.disabled = true;
  try {
    const data = await jsonFetch('/admin/api/status');
    setText('admin-data-mode', data.database.mode);
    setText('admin-count-suppliers', data.database.suppliers);
    setText('admin-count-procurements', data.database.procurements);
    setText('admin-count-contracts', data.database.contracts);
    setText('admin-count-users', data.database.users);

    const candidate = data.models?.candidate_search || {};
    setHealth(
      'health-candidate',
      candidate.ok ? 'ok' : 'bad',
      candidate.ok
        ? `Доступно · ${candidate.model || 'all-minilm'} · ${candidate.indexed_suppliers || '—'} компаний в индексе`
        : `Недоступно · ${candidate.reason || candidate.error || 'проверьте Ollama и FAISS-индекс'}`,
    );

    const llm = data.models?.llm || {};
    setHealth(
      'health-llm',
      llm.ok ? 'ok' : 'bad',
      llm.ok
        ? `Доступно · ${llm.model}`
        : `Недоступно · ${llm.error || (llm.service_ok ? 'модель не загружена' : 'Ollama не отвечает')}`,
    );

    const parser = data.gisp?.parser || {};
    setHealth('health-gisp-parser', parser.ok ? 'ok' : 'bad', parser.ok ? `Доступен · ${parser.message || 'готов'}` : `Недоступен · ${parser.message || 'не готов'}`);

    const job = data.gisp?.job || {};
    const jobState = job.status === 'ok' ? 'ok' : job.status === 'error' ? 'bad' : job.status === 'running' ? 'warn' : 'idle';
    const jobLabel = job.status === 'ok' ? 'Успешно' : job.status === 'error' ? 'Ошибка' : job.status === 'running' ? 'Выполняется' : 'Не запускался';
    setHealth('health-gisp-job', jobState, `${jobLabel}${job.message ? ` · ${job.message}` : ''}`);

    const file = data.gisp?.file || {};
    setHealth(
      'health-gisp-file',
      file.exists ? 'ok' : 'idle',
      file.exists ? `Доступен · ${file.size_mb} МБ · ${formatDate(file.modified_at)}` : 'Файл ещё не скачан',
    );
    setText('gisp-log', data.gisp?.log_tail || 'Журнал пока пуст.');

    const enrichment = data.company_enrichment || {};
    const enrichmentJob = enrichment.job || {};
    const enrichmentState = enrichmentJob.status === 'ok' ? 'ok' : enrichmentJob.status === 'error' ? 'bad' : enrichmentJob.status === 'running' ? 'warn' : 'idle';
    setHealth('health-company-enrichment', enrichmentState, enrichmentJob.message || 'Ещё не запускалось');
    setHealth('health-dadata-config', enrichment.dadata_configured ? 'ok' : 'warn', enrichment.dadata_configured ? 'DADATA_TOKEN задан' : 'DADATA_TOKEN не задан: тестовая история загрузится, DaData будет пропущена');
    setText('company-enrichment-log', enrichment.log_tail || 'Журнал пока пуст.');
    if (showToast) toast('Статус обновлён', 'success');
  } catch (error) {
    setHealth('health-candidate', 'bad', 'Не удалось получить статус');
    setHealth('health-llm', 'bad', 'Не удалось получить статус');
    setHealth('health-gisp-parser', 'bad', 'Не удалось получить статус');
    toast('Не удалось обновить админ-статус: ' + error.message, 'error');
  } finally {
    if (showToast && refreshBtn) refreshBtn.disabled = false;
  }
}

async function testModels() {
  const button = document.getElementById('admin-test-models');
  const output = document.getElementById('model-test-output');
  if (button) button.disabled = true;
  if (output) output.textContent = 'Проверяем FAISS/all-minilm и Qwen…';
  try {
    const data = await jsonFetch('/admin/api/models/test', { method: 'POST', body: '{}' });
    if (output) output.textContent = JSON.stringify(data, null, 2);
    setHealth('health-candidate', data.candidate_search?.ok ? 'ok' : 'bad', data.candidate_search?.ok ? `Инференс успешен · ${data.candidate_search.sample?.length || 0} кандидата · ${data.candidate_search.latency_ms} мс` : `Ошибка · ${data.candidate_search?.error || 'поиск не прошёл'}`);
    setHealth('health-llm', data.llm?.ok ? 'ok' : 'bad', data.llm?.ok ? `Инференс успешен · ${data.llm.latency_ms} мс` : `Ошибка · ${data.llm?.error || 'Qwen не ответила'}`);
    toast(data.candidate_search?.ok && data.llm?.ok ? 'Обе модели доступны' : 'Часть AI-компонентов недоступна', data.candidate_search?.ok && data.llm?.ok ? 'success' : 'error');
  } catch (error) {
    if (output) output.textContent = error.message;
    toast('Тест моделей завершился ошибкой: ' + error.message, 'error');
  } finally {
    if (button) button.disabled = false;
  }
}

async function runGisp() {
  const button = document.getElementById('admin-run-gisp');
  if (button) button.disabled = true;
  setHealth('health-gisp-job', 'warn', 'Запускаем парсер…');
  try {
    const data = await jsonFetch('/admin/api/gisp/start', { method: 'POST', body: '{}' });
    toast(data.message || 'Синхронизация запущена', 'success');
    setTimeout(() => refresh(false), 1000);
  } catch (error) {
    setHealth('health-gisp-job', 'bad', 'Не удалось запустить');
    toast('ГИСП: ' + error.message, 'error');
  } finally {
    if (button) button.disabled = false;
  }
}

async function runCompanyEnrichment() {
  const button = document.getElementById('admin-run-company-enrichment');
  if (button) button.disabled = true;
  setHealth('health-company-enrichment', 'warn', 'Запускаем обогащение…');
  try {
    const data = await jsonFetch('/admin/api/enrichment/start', { method: 'POST', body: '{}' });
    toast(data.message || 'Обогащение запущено', 'success');
    setTimeout(() => refresh(false), 1000);
  } catch (error) {
    setHealth('health-company-enrichment', 'bad', 'Не удалось запустить');
    toast('Обогащение компаний: ' + error.message, 'error');
  } finally {
    if (button) button.disabled = false;
  }
}

async function enrichGisp() {
  const button = document.getElementById('admin-enrich-gisp');
  if (button) button.disabled = true;
  setHealth('health-gisp-job', 'warn', 'Применяем текущий XLSX…');
  try {
    const data = await jsonFetch('/admin/api/gisp/enrich-existing', { method: 'POST', body: '{}' });
    toast(data.message || 'Текущий registry.xlsx применён', 'success');
    await refresh(false);
  } catch (error) {
    toast('ГИСП: ' + error.message, 'error');
    await refresh(false);
  } finally {
    if (button) button.disabled = false;
  }
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value ?? '—';
}

function setHealth(id, state, text) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('is-ok', 'is-bad', 'is-warn', 'is-idle');
  el.classList.add(`is-${state || 'idle'}`);

  // Подробный технический статус не выводим внутри карточки: он ломал
  // вёрстку и превращался в вертикальный столбик символов. Состояние
  // видно по цвету индикатора, а подробность остаётся в tooltip/ARIA.
  const label = text || 'Статус не определён';
  el.title = label;
  el.setAttribute('aria-label', `${el.querySelector('strong')?.textContent || id}: ${label}`);
}

function formatDate(value) {
  if (!value) return '—';
  try { return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)); }
  catch { return value; }
}
