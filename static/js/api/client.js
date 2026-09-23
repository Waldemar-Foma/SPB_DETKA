/**
 * Единственная точка сетевого взаимодействия.
 * Все модули получают данные только через этот клиент.
 */
const BASE = '/api/v1';

async function request(path, options = {}) {
  const response = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body?.error?.message || `HTTP ${response.status}`);
  }
  return response.json();
}

export const api = {
  get:  (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
};