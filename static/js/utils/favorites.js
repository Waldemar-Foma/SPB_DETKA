const KEY = 'spb-favorites';

export function getFavorites() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '[]');
  } catch {
    return [];
  }
}

export function isFavorite(inn) {
  return getFavorites().includes(inn);
}

export function toggleFavorite(inn) {
  const list = getFavorites();
  const idx = list.indexOf(inn);
  if (idx >= 0) list.splice(idx, 1);
  else list.push(inn);
  localStorage.setItem(KEY, JSON.stringify(list));
  return idx < 0;
}

export function getFavoritesCount() {
  return getFavorites().length;
}