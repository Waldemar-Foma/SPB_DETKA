/**
 * Режим «Карта»: Leaflet + пульсирующие маркеры + всплывающий виджет.
 *
 * Обработчик клика — делегирование на #map-canvas.
 * Клик по любому .map-pulse всплывает к контейнеру и ловится там.
 * Такой подход не зависит от того, когда Leaflet вставил иконку в DOM.
 */
import { $ } from '../utils/dom.js';

let mapInstance = null;
let markers = [];
let currentItems = [];
let currentOnOpen = null;

export function initMapView(items, onOpen) {
  const host = $('#map-canvas');
  if (!host || !window.L) {
    console.warn('[mapView] init skipped:', { host: !!host, L: !!window.L });
    return;
  }

  // Сохраняем контекст — понадобится в обработчике кликов
  currentItems = items;
  currentOnOpen = onOpen;

  // Пересоздаём карту при обновлении данных
  if (mapInstance) {
    mapInstance.remove();
    mapInstance = null;
    markers = [];
  }

  mapInstance = window.L.map(host, {
    zoomControl: true,
    zoomControlPosition: 'bottomright',
    attributionControl: false,
    scrollWheelZoom: true,
  }).setView([59.86, 30.30], 9);

  window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
  }).addTo(mapInstance);

  items.slice(0, 30).forEach((item) => addMarker(item));

  // Делегирование: один обработчик на контейнер карты
  // Клик по .map-pulse (внутри divIcon) всплывает сюда.
  if (!host.dataset.clicksBound) {
    host.dataset.clicksBound = '1';
    host.addEventListener('click', handleMapClick);
  }

  bindPopupClose();
}

function handleMapClick(e) {
  const pulse = e.target.closest('.map-pulse');
  if (!pulse) return;

  const inn = pulse.dataset.inn;
  if (!inn) return;

  const item = currentItems.find((i) => i.inn === inn);
  if (!item) {
    console.warn('[mapView] Компания не найдена:', inn);
    return;
  }

  e.stopPropagation();
  showPopup(item);
}

function addMarker(item) {
  const lat = item.coords?.lat;
  const lon = item.coords?.lon;
  if (!lat || !lon) return;

  const isHigh = item.score >= 85;
  const className = isHigh ? 'map-pulse' : 'map-pulse map-pulse--mid';

  const icon = window.L.divIcon({
    className: 'map-pulse-wrapper',
    html: `<div class="${className}" data-inn="${item.inn}"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });

  const marker = window.L.marker([lat, lon], { icon }).addTo(mapInstance);
  markers.push(marker);
}

function showPopup(item) {
  const popup = $('#map-popup');
  if (!popup) {
    console.warn('[mapView] #map-popup не найден в DOM');
    return;
  }

  const nameEl = $('#map-popup-name');
  const metaEl = $('#map-popup-meta');
  const scoreEl = $('#map-popup-score');

  if (nameEl) nameEl.textContent = item.name || '—';
  if (metaEl) {
    metaEl.textContent =
      `${item.company_type || ''} · ${item.region || ''}`.replace(/^ · | · $/g, '');
  }
  if (scoreEl) scoreEl.textContent = `${item.score ?? '—'}%`;

  popup.hidden = false;

  // Пересоздаём кнопку, чтобы старые обработчики не накапливались
  const oldBtn = $('#map-popup-open');
  if (oldBtn) {
    const newBtn = oldBtn.cloneNode(true);
    oldBtn.replaceWith(newBtn);
    newBtn.addEventListener('click', () => {
      if (typeof currentOnOpen === 'function') {
        currentOnOpen(item.inn);
      }
    });
  }

  if (mapInstance && item.coords?.lat) {
    mapInstance.panTo([item.coords.lat, item.coords.lon], { animate: true });
  }
}

function bindPopupClose() {
    const close = $('#map-popup-close');
    const popup = $('#map-popup');
    if (!close || !popup) return;

    const newClose = close.cloneNode(true);
    newClose.classList.add('map-popup__close');
    close.replaceWith(newClose);
    newClose.addEventListener('click', () => { popup.hidden = true; });
  }
