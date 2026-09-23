import { h } from '../utils/dom.js';

/**
 * Мини-карта с меткой компании на Leaflet + OpenStreetMap.
 * Тёмный стиль за счёт CSS-фильтра, коралловые маркеры.
 */
export function MiniMap(coords) {
  const container = h('div', { style: 'width:100%;height:100%' });

  requestAnimationFrame(() => {
    if (!window.L || !coords?.lat) return;

    const map = window.L.map(container, {
      zoomControl: false,
      attributionControl: false,
      scrollWheelZoom: false,
    }).setView([coords.lat, coords.lon], 12);

    window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
    }).addTo(map);

    const spb = [59.9386, 30.3141];

    window.L.polyline([[coords.lat, coords.lon], spb], {
      color: '#ff4e64',
      weight: 2,
      dashArray: '4 6',
      opacity: .9,
    }).addTo(map);

    window.L.circleMarker([coords.lat, coords.lon], {
      radius: 8,
      color: '#ff4e64',
      fillColor: '#ff4e64',
      fillOpacity: 1,
      weight: 2,
    }).addTo(map);

    window.L.circleMarker(spb, {
      radius: 5,
      color: '#ffffff',
      fillColor: '#ffffff',
      fillOpacity: 1,
      weight: 2,
    }).addTo(map);
  });

  return container;
}
