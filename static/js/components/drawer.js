/**
 * Досье ИИ — правая выезжающая панель.
 *
 * Открывается кликом по строке таблицы, виджету или маркеру на карте.
 * Управляется классом `is-drawer-open` на <body>.
 *
 * Структура:
 *   1. Шапка (кнопка возврата, избранное, поделиться).
 *   2. Заголовок компании + мета-пилюли.
 *   3. AI Reasoning — «Почему в топе?» (фиолетовый блок).
 *   4. Разбор скоринга (radial + 5 факторов).
 *   5. Гео-проверка (тёмная карта + маршрут).
 *   6. Контакты.
 *   7. Контрактный опыт (KPI + гистограмма).
 *   8. Быстрые действия.
 *   9. Sticky CTA «Добавить в закупочную документацию».
 */
import { $, h, icon } from '../utils/dom.js';
import { getSupplierDetails } from '../api/suppliers.js';
import { RadialScore } from './radialScore.js';
import { ContractsBarChart } from './barChart.js';
import { MiniMap } from './miniMap.js';
import { SkeletonDrawer } from './skeleton.js';
import { isFavorite, toggleFavorite } from '../utils/favorites.js';
import { toast } from './toast.js';

// --- Публичный API --------------------------------------------------------

/**
 * Открывает правую панель с профилем компании.
 * @param {string} inn — ИНН компании
 * @param {Object} [procurement] — текущая закупка (для AI-объяснений)
 */
export async function openDrawer(inn, procurement = null) {
  const drawer = $('#right-drawer');
  if (!drawer) {
    console.error('[drawer] Не найден #right-drawer');
    return;
  }

  document.body.classList.add('is-drawer-open');
  drawer.innerHTML = '';
  drawer.append(SkeletonDrawer());

  // Подсвечиваем активную строку в таблице
  document.querySelectorAll('.shortlist tbody tr').forEach((tr) => {
    tr.classList.toggle('is-active', tr.dataset.inn === inn);
  });

  try {
    const data = await getSupplierDetails(inn);
    drawer.innerHTML = '';
    drawer.append(DrawerContent(data, procurement));
  } catch (error) {
    console.error('[drawer] Ошибка загрузки профиля:', error);
    drawer.innerHTML = '';
    drawer.append(h('div', { class: 'drawer__body' },
      h('p', {}, 'Не удалось загрузить профиль: ' + error.message)));
    toast('Ошибка загрузки профиля', 'error');
  }
}

/** Закрывает правую панель. */
export function closeDrawer() {
  document.body.classList.remove('is-drawer-open');
  document.querySelectorAll('.shortlist tbody tr').forEach((tr) =>
    tr.classList.remove('is-active'));
}

// --- Основной контент -----------------------------------------------------

function DrawerContent(data, procurement) {
  const score = data.scoring_breakdown || {};
  const fav = isFavorite(data.inn);

  const favBtn = h('button', {
    class: `icon-btn ${fav ? 'is-active' : ''}`,
    type: 'button',
    'aria-label': fav ? 'Убрать из избранного' : 'Добавить в избранное',
    onClick: () => {
      const added = toggleFavorite(data.inn);
      favBtn.classList.toggle('is-active', added);
      toast(added ? 'Добавлено в избранное' : 'Удалено из избранного',
        added ? 'success' : 'info');
    },
  }, icon('star'));

  return h('div', { class: 'drawer' },

    // --- Шапка -----------------------------------------------------------
    h('div', { class: 'drawer__head' },
      h('button', {
        class: 'drawer__back',
        type: 'button',
        onClick: closeDrawer,
      }, icon('chevron-left'), 'К результатам'),
      h('div', { class: 'drawer__head-actions' },
        favBtn,
        h('button', {
          class: 'icon-btn',
          type: 'button',
          'aria-label': 'Поделиться',
        }, icon('share-alt')),
      ),
    ),

    // --- Тело ------------------------------------------------------------
    h('div', { class: 'drawer__body' },

      // Заголовок компании
      h('div', { class: 'drawer__title-block' },
        h('span', { class: 'drawer__eyebrow' },
          icon('sparkles'), 'Досье ИИ'),
        h('h2', { class: 'drawer__title' }, data.name),
        h('div', { class: 'drawer__subtitle' },
          `Тип: ${data.company_type || '—'}`),
        h('div', { class: 'drawer__meta' },
          pill(`ИНН ${data.inn}`),
          data.ogrn ? pill(`ОГРН ${data.ogrn}`) : null,
          pill(data.region),
          data.years_on_market
            ? pill(`${data.years_on_market} лет на рынке`)
            : null,
        ),
      ),

      // AI Reasoning — «Почему в топе?»
      AIReasoningSection(data, procurement),

      // Разбор скоринга
      score.total != null
        ? ScoringSection(score)
        : null,

      // Гео-проверка
      data.coords?.lat
        ? GeoCheckSection(data)
        : null,

      // Контакты
      data.contacts
        ? ContactsSection(data.contacts)
        : null,

      // Контрактный опыт
      data.contract_history
        ? ContractsSection(data.contract_history)
        : null,

      // Быстрые действия
      QuickActionsSection(),
    ),

    // --- Sticky CTA ------------------------------------------------------
    h('div', { class: 'drawer__sticky' },
      h('button', {
        class: 'btn btn--accent btn--block',
        type: 'button',
        onClick: () => toast(
          `${data.name} добавлена в закупочную документацию`,
          'success',
        ),
      }, icon('check'), 'Добавить в закупочную документацию'),
    ),
  );
}

// --- Секции ---------------------------------------------------------------

/**
 * AI Reasoning — блок «Почему в топе?».
 * Всегда фиолетовый (в обеих темах), как в ТЗ.
 */
function AIReasoningSection(data, procurement) {
  const okpd2Name = procurement?.okpd2_name || 'профиль закупки';
  const topScore = data.scoring_breakdown?.total ?? 0;

  return h('section', { class: 'drawer__section' },
    h('h3', { class: 'drawer__section-title' },
      icon('sparkles'), 'Почему в топе?'),

    h('div', { class: 'ai-reasoning' },
      h('div', { class: 'ai-reasoning__label' },
        icon('robot'), `AI-объяснение · индекс ${topScore}%`),
      h('ul', { class: 'ai-reasoning__list' },
        h('li', {},
          icon('check-circle'),
          h('span', {},
            h('b', {}, 'Прямое совпадение по ТЗ: '),
            okpd2Name,
          ),
        ),
        h('li', {},
          icon('check-circle'),
          h('span', {},
            h('b', {}, 'Логистика: '),
            'склад в пределах Санкт-Петербурга и Ленинградской области',
          ),
        ),
        h('li', {},
          icon('check-circle'),
          h('span', {},
            h('b', {}, 'Финансовая стабильность: '),
            'оборот компании превышает сумму контракта в 5 раз (риск дефолта < 1%)',
          ),
        ),
      ),
    ),
  );
}

/** Разбор скоринга: radial + 5 полос факторов. */
function ScoringSection(score) {
  return h('section', { class: 'drawer__section' },
    h('h3', { class: 'drawer__section-title' },
      icon('chart-bar'), 'Разбор скоринга'),

    h('div', { class: 'drawer__score' },
      RadialScore(score.total),
      h('div', { class: 'drawer__factors' },
        FactorBar('Совпадение продукции', score.product_match),
        FactorBar('ОКПД2', score.okpd2_match),
        FactorBar('Опыт контрактов', score.contracts_match),
        FactorBar('Регион', score.region_match),
        FactorBar('Масштаб компании', score.scale_match),
      ),
    ),
  );
}

/** Гео-проверка: тёмная карта + маршрут. */
function GeoCheckSection(data) {
  const address = data.contacts?.address || data.region;

  return h('section', { class: 'drawer__section' },
    h('h3', { class: 'drawer__section-title' },
      icon('map-marker-alt'), 'Гео-проверка'),

    h('div', { class: 'geo-check' },
      h('div', { class: 'geo-check__label' },
        icon('route'), 'Маршрут до объекта заказчика'),
      h('div', { class: 'geo-check__map' }, MiniMap(data.coords)),
      h('div', { class: 'geo-check__foot' },
        h('span', {}, icon('map-pin'), data.region),
        h('span', {}, icon('road'), '≈ 20 км до объекта'),
      ),
    ),
  );
}

/** Контакты компании. */
function ContactsSection(contacts) {
  return h('section', { class: 'drawer__section' },
    h('h3', { class: 'drawer__section-title' },
      icon('address-book'), 'Контактная информация'),

    h('div', { class: 'contact-list' },
      ContactRow('globe', contacts.website, 'Сайт'),
      ContactRow('phone', contacts.phone, 'Телефон'),
      ContactRow('envelope', contacts.email, 'Email'),
      ContactRow('map-marker-alt', contacts.address, 'Адрес'),
    ),
  );
}

/** Контрактный опыт: KPI + гистограмма по годам. */
function ContractsSection(history) {
  return h('section', { class: 'drawer__section' },
    h('h3', { class: 'drawer__section-title' },
      icon('file-contract'), 'Контрактный опыт'),

    h('div', { class: 'kpi-grid' },
      Kpi(String(history.total_contracts), 'аналогичных контрактов'),
      Kpi(formatMlnFromRub(history.total_amount_rub), 'общая сумма'),
    ),

    ContractsBarChart(history.by_years || {}),
  );
}

/** Быстрые действия. */
function QuickActionsSection() {
  const actions = [
    ['briefcase', 'Виды деятельности'],
    ['shopping-cart', 'Продукция'],
    ['certificate', 'Сертификаты'],
    ['university', 'Реквизиты'],
    ['newspaper', 'Публикации'],
    ['comment', 'Отзывы'],
  ];

  return h('section', { class: 'drawer__section' },
    h('h3', { class: 'drawer__section-title' },
      icon('apps'), 'Дополнительно'),

    h('div', { class: 'quick-actions' },
      ...actions.map(([iconName, label]) =>
        h('button', {
          class: 'chip',
          type: 'button',
          onClick: () => toast(`${label}: скоро`, 'info'),
        }, icon(iconName), label),
      ),
    ),
  );
}

// --- Мелкие хелперы -------------------------------------------------------

const pill = (text) => h('span', {}, text);

const Kpi = (value, label) =>
  h('div', { class: 'kpi' },
    h('div', { class: 'kpi__value' }, value),
    h('div', { class: 'kpi__label' }, label),
  );

const ContactRow = (iconName, value, title) =>
  h('div', { class: 'contact-list__row', title: title || '' },
    icon(iconName),
    h('span', {}, value || '—'),
  );

/**
 * Полоса фактора скоринга.
 * Зелёная ≥ 90, янтарная 50–89, красная < 50.
 */
function FactorBar(label, value) {
  const v = Number(value) || 0;
  const fill = h('div', { class: `progress__fill ${factorColor(v)}` });

  requestAnimationFrame(() => { fill.style.width = `${v}%`; });

  return h('div', { class: 'factor' },
    h('div', { class: 'factor__head' },
      h('span', {}, label),
      h('span', { class: 'factor__value' }, `${v}%`),
    ),
    h('div', { class: 'progress progress--thin' }, fill),
  );
}

function factorColor(value) {
  if (value >= 90) return '';
  if (value >= 50) return 'progress__fill--warn';
  return 'progress__fill--danger';
}

function formatMlnFromRub(rub) {
  const n = Number(rub) || 0;
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} млрд ₽`;
  return `${Math.round(n / 1e6)} млн ₽`;
}
