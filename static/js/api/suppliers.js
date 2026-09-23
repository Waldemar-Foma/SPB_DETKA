import { api } from './client.js';

/** Детальный профиль контрагента по ИНН. */
export const getSupplierDetails = (inn) => api.get(`/suppliers/${inn}/details`);