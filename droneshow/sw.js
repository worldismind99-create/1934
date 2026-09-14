// ドローンショー サウンド - Service Worker
// アプリ本体とアイコンをキャッシュし、会場で回線が混んでいても開けるようにする。
// show.json(開始時刻)と ping.txt(時刻合わせ)は常にネットワークへ取りに行く。

var CACHE = 'droneshow-sound-v3';
var ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-maskable-512.png',
  './icons/apple-touch-icon.png'
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) { return c.addAll(ASSETS); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) { return k === CACHE ? null : caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET' && req.method !== 'HEAD') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // 時刻合わせと開始時刻は絶対にキャッシュしない(Dateヘッダの鮮度が命)
  if (/\/(ping\.txt|show\.json)$/.test(url.pathname) || req.method === 'HEAD') return;

  // 音源はキャッシュ優先(一度落とせば会場で回線不要)
  if (/\.(mp3|m4a|aac|ogg|opus|wav)$/i.test(url.pathname)) {
    e.respondWith(
      caches.match(req).then(function (hit) {
        return hit || fetch(req).then(function (res) {
          if (res && res.ok) { var copy = res.clone(); caches.open(CACHE).then(function (c) { c.put(req, copy); }); }
          return res;
        });
      })
    );
    return;
  }

  // 本体はネットワーク優先、つながらなければキャッシュ
  e.respondWith(
    fetch(req).then(function (res) {
      if (res && res.ok) { var copy = res.clone(); caches.open(CACHE).then(function (c) { c.put(req, copy); }); }
      return res;
    }).catch(function () {
      return caches.match(req).then(function (hit) { return hit || caches.match('./index.html'); });
    })
  );
});
