/* ===========================================================================
 *  NEXUS Mobile - service worker
 * ===========================================================================
 *  Estrategia deliberada, e vale entender a diferenca:
 *
 *  ARQUIVOS DO APP (html, css, js, icones) -> cache primeiro.
 *      Abrem instantaneamente e funcionam sem rede. Sao pequenos e mudam so
 *      quando voce publica uma versao nova.
 *
 *  DADOS DO FIREBASE -> NUNCA passam por aqui.
 *      Um cache de dados de tarefas produziria o pior tipo de bug: o app
 *      mostrando uma tarefa que voce ja concluiu no computador, com aparencia
 *      de estar correto. Quem guarda dado offline e o localStorage, no app,
 *      com carimbo de tempo e resolucao de conflito.
 *
 *  Para publicar uma versao nova: mude VERSAO_CACHE. O activate abaixo apaga
 *  os caches antigos, e o proximo carregamento pega os arquivos novos.
 * ======================================================================== */

const VERSAO_CACHE = 'nexus-mobile-v1.0.1';

const ARQUIVOS = [
  './',
  './index.html',
  './styles.css',
  './nexus-sync.js',
  './app.js',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png'
];

// Hosts cujas respostas jamais devem ser cacheadas.
const NUNCA_CACHEAR = [
  'firebaseio.com',
  'identitytoolkit.googleapis.com',
  'securetoken.googleapis.com'
];

self.addEventListener('install', (evento) => {
  evento.waitUntil(
    caches.open(VERSAO_CACHE)
      .then((c) => c.addAll(ARQUIVOS))
      // skipWaiting: a versao nova assume no proximo carregamento em vez de
      // esperar todas as abas fecharem. Num app de uma aba so, e o esperado.
      .then(() => self.skipWaiting())
      .catch(() => { /* falha de cache nao pode impedir a instalacao */ })
  );
});

self.addEventListener('activate', (evento) => {
  evento.waitUntil(
    caches.keys()
      .then((chaves) => Promise.all(
        chaves.filter((k) => k !== VERSAO_CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (evento) => {
  const req = evento.request;

  // So interceptamos GET. POST/PUT do Firebase passam direto.
  if (req.method !== 'GET') return;

  const url = req.url;
  if (NUNCA_CACHEAR.some((h) => url.indexOf(h) !== -1)) return;

  // Requisicoes para outra origem tambem passam direto.
  if (new URL(url).origin !== self.location.origin) return;

  evento.respondWith(
    caches.match(req).then((cacheada) => {
      if (cacheada) {
        // Atualiza em segundo plano para a proxima abertura ja vir nova.
        fetch(req).then((resp) => {
          if (resp && resp.ok) {
            caches.open(VERSAO_CACHE).then((c) => c.put(req, resp.clone()));
          }
        }).catch(() => {});
        return cacheada;
      }

      return fetch(req).then((resp) => {
        if (resp && resp.ok && resp.type === 'basic') {
          const copia = resp.clone();
          caches.open(VERSAO_CACHE).then((c) => c.put(req, copia));
        }
        return resp;
      }).catch(() => {
        // Sem rede e sem cache: para navegacao, devolve a pagina principal
        // para o app abrir e mostrar os dados locais.
        if (req.mode === 'navigate') return caches.match('./index.html');
        return new Response('', { status: 504, statusText: 'Sem conexao' });
      });
    })
  );
});
