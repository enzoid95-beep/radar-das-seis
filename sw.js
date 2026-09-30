// Radar das Seis: permite instalar o site como app.
// Não guarda nada em cache, para que os resultados sempre venham atualizados.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => { e.respondWith(fetch(e.request)); });
