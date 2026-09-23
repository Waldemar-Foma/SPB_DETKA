import { $, h, icon } from '../utils/dom.js';
import { getSupplierDetails } from '../api/suppliers.js';
import { RadialScore } from './radialScore.js';
import { ContractsBarChart } from './barChart.js';
import { MiniMap } from './miniMap.js';

const FACTOR_LABELS = {
  product_match:   'Совпадение продукции',
  okpd2_match:     'ОКПД2',
  contracts_match: 'Опыт контрактов',
  region_match:    'Регион',
  scale_match:     'Масштаб компании',
};

const QUICK_ACTIONS = [
  ['briefcase',       'Виды деятельности'],
  ['shopping-cart',   'Продукция'],
  ['certificate',     'Сертификаты'],
  ['university',      'Реквизиты'],
  ['newspaper',       'Публикации'],
  ['comment',         'Отзывы'],
];

/** Открывает правую панель с профилем контрагента. */
export async function openDrawer(inn) {
  const drawer = $('#right-drawer');
  drawer.hidden = false;
  drawer.innerHTML = '';
  drawer.append(h('div', { class: 'drawer' }, h('p', {}, 'Загрузка профиля…')));

  try {
    const data = await getSupplierDetails(inn);
    drawer.innerHTML = '';
    drawer.append(renderDrawer(data));
  } catch (error) {
    drawer.innerHTML = '';
    drawer.append(h('div', { class: 'drawer' },
      h('p', {}, 'Не удалось загрузить профиль: ' + error.message)));
  }
}

export function closeDrawer() {
  const drawer = $('#right-drawer');
  drawer.hidden = true;
  drawer.innerHTML = '';
}

function renderDrawer(data) {
  const score = data.scoring_breakdown;

  return h('div', { class: 'drawer' },
    h('div', { class: 'drawer__head' },
      h('button', {
        class: 'drawer__back', type: 'button', onClick: closeDrawer,
      }, icon('chevron-left'), 'К результатам'),
      h('div', { class: 'drawer__head-actions' },
        h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'В избранное' },
          icon('star')),
        h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Поделиться' },
          icon('share-alt')),
      ),
    ),

    h('div', {},
      h('h2', { class: 'drawer__title' }, data.name),
      h('div', { class: 'drawer__subtitle' }, `Тип: ${data.company_type}`),
      h('div', { class: 'drawer__meta' },
        `ИНН ${data.inn}`,
        data.ogrn ? `ОГРН ${data.ogrn}` : null,
        data.region,
        `${data.years_on_market} лет на рынке`,
      ),
    ),

    section('Почему подходит?',
      h('div', { class: 'drawer__score' },
        RadialScore(score.total),
        h('div', { class: 'drawer__factors' },
          ...Object.entries(FACTOR_LABELS).map(([key, label]) =>
            factorBar(label, score[key])),
        ),
      ),
    ),

    section('Контактная информация',
      h('div', { class: 'contact-list' },
        contactRow('globe',     data.contacts.website),
        contactRow('phone',     data.contacts.phone),
        contactRow('envelope',  data.contacts.email),
        contactRow('map-marker-alt', data.contacts.address),
      ),
      MiniMap(data.coords),
    ),

    section('Контрактный опыт',
      h('div', { class: 'kpi-grid' },
        kpi(String(data.contract_history.total_contracts), 'аналогичных контрактов'),
        kpi(formatMlnFromRub(data.contract_history.total_amount_rub), 'общая сумма'),
      ),
      ContractsBarChart(data.contract_history.by_years),
    ),

    section('Дополнительно',
      h('div', { class: 'drawer__chips' },
        ...QUICK_ACTIONS.map(([iconName, label]) =>
          h('button', { class: 'chip', type: 'button' }, icon(iconName), label)),
      ),
    ),

    h('div', { class: 'drawer__sticky' },
      h('button', { class: 'btn btn--primary btn--block', type: 'button' },
        icon('download'), 'Скачать карточку компании'),
    ),
  );
}

const section = (title, ...children) =>
  h('section', { class: 'drawer__section' },
    h('h3', { class: 'drawer__section-title' }, title),
    ...children,
  );

const factorBar = (label, value) =>
  h('div', { class: 'factor' },
    h('div', { class: 'factor__head' },
      h('span', {}, label),
      h('span', { class: 'factor__value' }, `${value}%`),
    ),
    h('div', { class: 'factor__track' },
      h('div', {
        class: 'factor__fill' + (value < 90 ? ' factor__fill--accent' : ''),
        style: `width:${value}%`,
      }),
    ),
  );

const contactRow = (iconName, value) =>
  h('div', { class: 'contact-list__row' }, icon(iconName), h('span', {}, value || '—'));

const kpi = (value, label) =>
  h('div', { class: 'kpi' },
    h('div', { class: 'kpi__value' }, value),
    h('div', { class: 'kpi__label' }, label),
  );

const formatMlnFromRub = (rub) => `${Math.round(rub / 1e6)} млн ₽`;