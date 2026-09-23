import { h } from '../utils/dom.js';

/**
 * Мини-карта с меткой компании на Leaflet + OpenStreetMap.
 * @param {{lat:number, lon:number}} coords
 */
export function MiniMap(coords) {
  const container = h('div', { class: 'mini-map' });

  requestAnimationFrame(() => {
    if (!window.L || !coords?.lat) return;

    const map = window.L.map(container, {
      zoomControl: false,
      attributionControl: false,
      scrollWheelZoom: false,
    }).setView([coords.lat, coords.lon], 13);

    window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
    }).addTo(map);

    window.L.circleMarker([coords.lat, coords.lon], {
      radius: 8,
      color: '#2563EB',
      fillColor: '#2563EB',
      fillOpacity: 1,
      weight: 2,
    }).addTo(map);
  });

  return container;
}