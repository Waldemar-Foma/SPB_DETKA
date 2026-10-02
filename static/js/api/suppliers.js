import { api } from './client.js';
export const getSupplierDetails = (inn, params = {}) => {
  const clean = Object.fromEntries(Object.entries(params).filter(([,v]) => v !== undefined && v !== null && v !== ''));
  const qs = new URLSearchParams(clean).toString();
  return api.get(`/suppliers/${inn}/details${qs ? '?' + qs : ''}`);
};
export const refreshExternalReputation = (inn) => api.post(`/suppliers/${inn}/external-reputation`, {});

export const getSupplierExplanation = (inn, params = {}) => {
  const clean = Object.fromEntries(Object.entries(params).filter(([,v]) => v !== undefined && v !== null && v !== ''));
  const qs = new URLSearchParams(clean).toString();
  return api.get(`/suppliers/${inn}/explanation${qs ? '?' + qs : ''}`);
};
