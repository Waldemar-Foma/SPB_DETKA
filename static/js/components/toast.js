import { h, icon } from '../utils/dom.js';

const HOST_ID = 'toast-host';
const DEFAULT_DURATION = 3200;

function host() {
  let el = document.getElementById(HOST_ID);
  if (!el) {
    el = h('div', { class: 'toast-host', id: HOST_ID, role: 'status', 'aria-live': 'polite' });
    document.body.append(el);
  }
  return el;
}

/**
 * Показывает уведомление.
 * @param {string} text
 * @param {'info'|'success'|'error'} [type]
 * @param {number} [duration]
 */
export function toast(text, type = 'info', duration = DEFAULT_DURATION) {
  const iconName = type === 'success' ? 'check-circle'
                 : type === 'error'   ? 'exclamation-circle'
                 : 'info-circle';

  const el = h('div', { class: `toast toast--${type}` },
    icon(iconName),
    h('span', { class: 'toast__text' }, text),
  );

  host().append(el);

  setTimeout(() => {
    el.style.transition = 'opacity 200ms ease';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 220);
  }, duration);
}