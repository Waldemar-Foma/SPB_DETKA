/**
 * Форматирование чисел для интерфейса.
 */

const LOCALE = 'ru-RU';

export const formatRub = (value) =>
  new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 }).format(value) + ' ₽';

export const formatMln = (value) => `${value.toFixed(0)} млн ₽`;
export const formatMrd = (value) => `${value.toFixed(1)} млрд ₽`;
export const formatNumber = (value) => new Intl.NumberFormat(LOCALE).format(value);