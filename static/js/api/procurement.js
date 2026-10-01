import { api } from './client.js';

export const analyzeProcurement = (query) =>
  api.post('/procurement/analyze', { query });

export const getProcurements = () => api.get('/procurement/list');

export const getSuppliersFor = (procurementId, params = {}) => {
  const clean = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  );
  const qs = new URLSearchParams(clean).toString();
  return api.get(`/procurement/${procurementId}/suppliers${qs ? '?' + qs : ''}`);
};

export const selectSupplier = (procurementId, supplierInn) =>
  api.post(`/procurement/${procurementId}/select`, { supplier_inn: supplierInn });
