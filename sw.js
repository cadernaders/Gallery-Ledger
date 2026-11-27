/* Gallery Ledger service worker: serves photos from on-device storage, and keeps the app available offline. */
var APP_CACHE = 'gl-app-v1';
var SHELL = ['./', 'index.html', 'manifest.webmanifest', 'icon-192.png', 'apple-touch-icon.png'];

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(APP_CACHE).then(function (c) { return c.addAll(SHELL); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });

function readPhoto(id) {
  return new Promise(function (res) {
    var r = indexedDB.open('gallery-ledger-photos', 1);
    r.onupgradeneeded = function () { r.result.createObjectStore('photos'); };
    r.onerror = function () { res(null); };
    r.onsuccess = function () {
      var g = r.result.transaction('photos').objectStore('photos').get(id);
      g.onsuccess = function () { res(g.result || null); };
      g.onerror = function () { res(null); };
    };
  });
}

self.addEventListener('fetch', function (e) {
  var req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;
  var i = url.pathname.indexOf('/_blob/');
  if (i >= 0) {
    var id = decodeURIComponent(url.pathname.slice(i + 7));
    e.respondWith(readPhoto(id).then(function (b) {
      return b ? new Response(b, { headers: { 'Content-Type': b.type || 'image/jpeg', 'Cache-Control': 'no-store' } })
               : new Response('', { status: 404 });
    }));
    return;
  }
  /* the app itself: newest copy when online, last copy when offline */
  e.respondWith(fetch(req).then(function (r) {
    var copy = r.clone();
    caches.open(APP_CACHE).then(function (c) { c.put(req, copy); });
    return r;
  }).catch(function () { return caches.match(req).then(function (m) { return m || caches.match('./'); }); }));
});
