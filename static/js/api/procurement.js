import { api } from './client.js';

/** Распознаёт закупку по текстовому запросу. */
export const analyzeProcurement = (query) =>
  api.post('/procurement/analyze', { query });

/** Возвращает ранжированный список контрагентов. */
export const getSuppliersFor = (procurementId, params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return api.get(`/procurement/${procurementId}/suppliers${qs ? '?' + qs : ''}`);
};