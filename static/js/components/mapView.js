import { $ } from '../utils/dom.js';
let mapInstance = null;
let currentItems = [];
let currentOnOpen = null;

export function initMapView(items, onOpen, selectedInn = null) {
  const host = $('#map-canvas');
  if (!host || !window.L) return;
  currentItems = items; currentOnOpen = onOpen;
  if (mapInstance) { mapInstance.remove(); mapInstance = null; }
  mapInstance = window.L.map(host, { zoomControl: true, attributionControl: false, scrollWheelZoom: true }).setView([57.5, 48.0], 4);
  window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(mapInstance);
  const points=[];
  items.forEach((item, index) => {
    const lat=item.coords?.lat, lon=item.coords?.lon; if (!lat || !lon) return;
    points.push([lat,lon]);
    const selected=selectedInn && String(selectedInn)===String(item.inn);
    const icon=window.L.divIcon({ className:'map-pulse-wrapper', html:`<div class="map-pulse ${selected?'map-pulse--selected':''}" data-inn="${item.inn}"><span>${index+1}</span></div>`, iconSize:[24,24], iconAnchor:[12,12] });
    window.L.marker([lat,lon],{icon}).addTo(mapInstance);
  });
  if (points.length === 1) mapInstance.setView(points[0], 8);
  else if (points.length > 1) mapInstance.fitBounds(points,{padding:[80,80],maxZoom:7});
  if (!host.dataset.clicksBound) { host.dataset.clicksBound='1'; host.addEventListener('click',handleMapClick); }
  bindClose();
}
function handleMapClick(e){ const pulse=e.target.closest('.map-pulse'); if(!pulse)return; const item=currentItems.find(i=>String(i.inn)===String(pulse.dataset.inn)); if(item){e.stopPropagation(); showPopup(item);} }
function showPopup(item){
  const popup=$('#map-popup'); if(!popup)return;
  $('#map-popup-name').textContent=item.name||'—';
  $('#map-popup-meta').textContent=`${item.company_type||''} · ${item.region||''}`;
  $('#map-popup-score').textContent=`${item.score??'—'}%`;
  popup.hidden=false;
  const old=$('#map-popup-open'); if(old){ const btn=old.cloneNode(true); old.replaceWith(btn); btn.addEventListener('click',()=>currentOnOpen?.(item.inn)); }
}
function bindClose(){ const close=$('#map-popup-close'), popup=$('#map-popup'); if(!close||!popup||close.dataset.bound)return; close.dataset.bound='1'; close.addEventListener('click',()=>popup.hidden=true); }
