import { api } from './client.js';

/** Распознаёт закупку по текстовому запросу. */
export const analyzeProcurement = (query) =>
  api.post('/procurement/analyze', { query });

/**
 * Возвращает ранжированный список контрагентов.
 * Поддерживает все query-параметры API: sort, limit, offset, фильтры.
 *
 * @param {string} procurementId
 * @param {Object} params — { sort?, limit?, offset?, company_type?, ... }
 * @returns {Promise<{items: Array, meta: Object}>}
 */
export const getSuppliersFor = (procurementId, params = {}) => {
  const clean = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  );
  const qs = new URLSearchParams(clean).toString();
  return api.get(`/procurement/${procurementId}/suppliers${qs ? '?' + qs : ''}`);
};