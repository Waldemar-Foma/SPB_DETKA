/**
 * Мелкие DOM-хелперы. Без зависимостей, только стандартный API.
 */

export const $  = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

/**
 * Создаёт DOM-элемент.
 * @param {string} tag
 * @param {Object} attrs — атрибуты; class/dataset/on<Event> обрабатываются отдельно
 * @param {...(Node|string|Array|null|false|undefined)} children
 */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);

  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;

    if (key === 'class') el.className = value;
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else {
      el.setAttribute(key, value);
    }
  }

  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

/**
 * Создаёт иконку Line Awesome.
 * @param {string} name       — имя иконки без префикса, например "search", "map-marker-alt"
 * @param {string} style      — "las" (solid) | "lar" (regular) | "lab" (brands)
 * @param {string} className  — дополнительные CSS-классы
 * @returns {HTMLElement}
 */
export function icon(name, style = 'las', className = '') {
  return h('i', { class: `${style} la-${name} ${className}`.trim() });
}