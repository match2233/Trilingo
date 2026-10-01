/* Service Worker —— 让应用离线可用（地铁里、飞行模式下也能背单词）。
 *
 * 应用外壳走缓存优先（改版时把 CACHE 版本号加一即可失效重建）；
 * GitHub API 一律走网络、不缓存，避免读到过期的学习数据。
 */

const CACHE = 'trilingo-v1';

const SHELL = [
  './',
  './index.html',
  './app.js',
  './core.js',
  './gh.js',
  './style.css',
  './manifest.webmanifest',
  './icons/icon-180.png',
  './icons/icon-192.png',
  './icons/icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);

  // 同步接口必须实时, 不缓存
  if (url.hostname === 'api.github.com') return;

  if (e.request.method !== 'GET') return;

  // 同源资源: 缓存优先, 回落到网络并顺手更新缓存
  if (url.origin === location.origin) {
    e.respondWith(
      caches.match(e.request).then((hit) => {
        if (hit) return hit;
        return fetch(e.request).then((resp) => {
          if (resp && resp.status === 200) {
            const copy = resp.clone();
            caches.open(CACHE).then((c) => c.put(e.request, copy));
          }
          return resp;
        }).catch(() => caches.match('./index.html'));
      })
    );
  }
});
