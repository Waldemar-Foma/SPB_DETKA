import { h } from '../utils/dom.js';
import { toast } from '../components/toast.js';

const RATING = {
  fast:  { label: 'Быстро',  badge: 'badge--producer' },
  ok:    { label: 'Нормально', badge: 'badge--supplier' },
  slow:  { label: 'Медленно', badge: 'badge--local' },
  error: { label: 'Ошибка',  badge: 'badge--local' },
};

const $id = (id) => document.getElementById(id);
const fmtMs = (v) => (v == null ? '—' : `${Number(v).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} мс`);
const fmtDate = (v) => {
  if (!v) return '—';
  try { return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(v)); }
  catch { return v; }
};

async function jsonFetch(url, options = {}) {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' }, cache: 'no-store', ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body?.error?.message || body?.message || `HTTP ${response.status}`);
  return body;
}

export function initApiTestsPage() {
  $id('apitest-run')?.addEventListener('click', runTest);
  loadHistory();
}

async function loadHistory() {
  try {
    const data = await jsonFetch('/admin/api/speed-test/history');
    renderHistory(data.history || []);
    if (data.latest) {
      $id('apitest-status').textContent = 'Показаны итоги последнего запуска. Запустите тест заново, чтобы увидеть подробности по каждому API.';
      renderSummary(data.latest.summary, data.latest.total_ms);
      $id('apitest-when').textContent = `Последний запуск: ${fmtDate(data.latest.started_at)}`;
    }
  } catch (error) {
    toast('Не удалось загрузить историю тестов: ' + error.message, 'error');
  }
}

async function runTest() {
  const button = $id('apitest-run');
  const runs = Number($id('apitest-runs')?.value || 3);
  const includeAi = Boolean($id('apitest-ai')?.checked);
  button.disabled = true;
  $id('apitest-status').textContent = includeAi
    ? 'Тест выполняется… проверка ИИ может занять до нескольких секунд.'
    : 'Тест выполняется…';
  try {
    const data = await jsonFetch('/admin/api/speed-test', { method: 'POST', body: JSON.stringify({ runs, include_ai: includeAi }) });
    renderResults(data.results || []);
    renderSummary(data.summary, data.total_ms);
    renderHistory(data.history || []);
    $id('apitest-when').textContent = `Последний запуск: ${fmtDate(data.started_at)} · повторов: ${data.runs}`;
    $id('apitest-status').textContent = data.ok
      ? `Готово: все ${data.summary.checks} проверок прошли успешно.`
      : `Готово: ошибки в ${data.summary.failed} из ${data.summary.checks} проверок. Подробности в таблице.`;
    toast(data.ok ? 'Тест API завершён' : 'Часть проверок завершилась с ошибкой', data.ok ? 'success' : 'error');
  } catch (error) {
    $id('apitest-status').textContent = 'Не удалось выполнить тест: ' + error.message;
    toast('Тест API: ' + error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

function renderSummary(summary, totalMs) {
  if (!summary) return;
  $id('apitest-kpis').hidden = false;
  $id('apitest-passed').textContent = `${summary.passed} из ${summary.checks}`;
  $id('apitest-avg').textContent = fmtMs(summary.avg_ms);
  $id('apitest-slowest').textContent = summary.slowest ? `${summary.slowest.label} · ${fmtMs(summary.slowest.avg_ms)}` : '—';
  $id('apitest-total').textContent = totalMs == null ? '—' : fmtMs(totalMs);
}

function renderResults(results) {
  const tbody = $id('apitest-body');
  tbody.innerHTML = '';
  const maxAvg = Math.max(1, ...results.map((r) => Number(r.avg_ms) || 0));
  let group = null;
  for (const r of results) {
    if (r.group !== group) {
      group = r.group;
      tbody.append(h('tr', { class: 'apitest-group' }, h('td', { colspan: 7 }, group)));
    }
    const rating = RATING[r.rating] || RATING.error;
    const width = Math.max(3, Math.round(((Number(r.avg_ms) || 0) / maxAvg) * 100));
    tbody.append(h('tr', { class: r.ok ? '' : 'apitest-failed' },
      h('td', {}, h('div', { class: 'company-meta' },
        h('span', { class: 'company-name' }, r.label),
        r.error ? h('span', { class: 'apitest-error' }, r.error) : null,
      )),
      h('td', {}, h('code', { class: 'apitest-path' }, `${r.method} ${r.path}`)),
      h('td', {}, r.status == null ? '—' : String(r.status)),
      h('td', { class: 'apitest-num' }, fmtMs(r.min_ms)),
      h('td', { class: 'apitest-num' }, h('b', {}, fmtMs(r.avg_ms))),
      h('td', { class: 'apitest-num' }, fmtMs(r.max_ms)),
      h('td', {},
        h('div', { class: 'apitest-speed' },
          h('span', { class: `badge ${rating.badge}` }, rating.label),
          h('div', { class: 'progress progress--thin' },
            h('div', { class: `progress__fill ${r.rating === 'fast' ? '' : r.rating === 'ok' ? 'progress__fill--warn' : 'progress__fill--danger'}`, style: `width:${width}%` }),
          ),
        ),
      ),
    ));
  }
}

function renderHistory(history) {
  const tbody = $id('apitest-history');
  tbody.innerHTML = '';
  if (!history.length) {
    tbody.append(h('tr', {}, h('td', { colspan: 6 }, h('div', { class: 'table-empty' }, h('p', {}, 'История пуста.')))));
    return;
  }
  for (const item of history) {
    const s = item.summary || {};
    tbody.append(h('tr', {},
      h('td', {}, fmtDate(item.started_at)),
      h('td', {}, `${item.runs}${item.include_ai ? ' · с ИИ' : ''}`),
      h('td', {}, `${s.passed ?? '—'} из ${s.checks ?? '—'}`),
      h('td', { class: 'apitest-num' }, fmtMs(s.avg_ms)),
      h('td', {}, s.slowest ? `${s.slowest.label} · ${fmtMs(s.slowest.avg_ms)}` : '—'),
      h('td', { class: 'apitest-num' }, fmtMs(item.total_ms)),
    ));
  }
}
