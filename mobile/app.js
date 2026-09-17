/* ===========================================================================
 *  NEXUS Mobile - aplicacao
 * ===========================================================================
 *  Escopo: apenas TAREFAS. O Vault nao vem para o celular, por decisao de
 *  seguranca - mas o app PRESERVA o campo `notepad` em toda gravacao. Ver
 *  preservarNaoEditados() em nexus-sync.js: sem isso, o primeiro envio do
 *  celular apagaria o Vault do desktop, em todos os dispositivos.
 * ======================================================================== */
'use strict';

const VERSAO = '1.0.1';

const sync = new NexusSync();
const E = window.NexusEstado;

let estado = E.vazio();
let filtro = 'myday';       // myday | planned | all | cat:<id> | proj:<id>
let aberta = null;          // id da tarefa aberta na folha
let sincronizando = false;
let cronoGravar = null;

/* ------------------------------------------------------------------ util */
const $  = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function hoje() {
  const d = new Date();
  return d.getFullYear() + '-' +
         String(d.getMonth() + 1).padStart(2, '0') + '-' +
         String(d.getDate()).padStart(2, '0');
}

function dataBR(iso) {
  if (!iso) return '';
  const p = String(iso).split('-');
  return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : iso;
}

function atrasada(t) {
  return t.dueDate && t.dueDate < hoje() && (Number(t.progress) || 0) < 100;
}

function avisar(msg, tipo) {
  const d = document.createElement('div');
  d.className = 'aviso' + (tipo ? ' ' + tipo : '');
  d.textContent = msg;
  $('#avisos').appendChild(d);
  setTimeout(() => {
    d.style.opacity = '0';
    setTimeout(() => d.remove(), 250);
  }, 3400);
}

function vibrar(ms) {
  try { if (navigator.vibrate) navigator.vibrate(ms || 8); } catch (e) {}
}

/* Prioridade -> classe CSS.
 *
 * Um mapa explicito, em vez de normalizar acento com regex. A versao com
 * regex precisaria de um intervalo de marcas diacriticas combinantes, que sao
 * caracteres INVISIVEIS no codigo. Este projeto ja perdeu tempo duas vezes com
 * caracteres invisiveis (um byte nulo e um travessao mal decodificado); um
 * mapa de cinco linhas resolve o mesmo problema e da para conferir batendo o
 * olho. */
const CLASSE_PRI = {
  'Baixa': 'p-Baixa',
  'Média': 'p-Media',
  'Media': 'p-Media',
  'Alta': 'p-Alta',
  'Urgente': 'p-Urgente'
};
function classePri(p) {
  return CLASSE_PRI[p] || 'p-Media';
}

/* ==========================================================================
 *  SINCRONIZACAO
 * ======================================================================= */
function pintarStatus(cor, texto) {
  const p = $('#ponto');
  p.className = 'ponto' + (cor ? ' ' + cor : '');
  $('#txt-sync').textContent = texto;
}

async function sincronizar(silencioso) {
  if (sincronizando) return;
  if (!navigator.onLine) {
    pintarStatus('offline', 'Offline');
    return;
  }
  sincronizando = true;
  pintarStatus('girando', 'Sincronizando');

  try {
    const r = await sync.baixar();

    if (r.estado === 'auth_error') {
      pintarStatus('erro', 'Sessao');
      avisar(r.msg || 'Sessao expirada. Entre novamente.', 'mau');
      mostrarLogin();
      return;
    }
    if (r.estado === 'erro') {
      pintarStatus('erro', 'Erro');
      if (!silencioso) avisar(r.msg || 'Falha ao sincronizar.', 'mau');
      return;
    }

    const remoto = r.estado === 'ok' ? E.normalizar(r.dados) : null;
    const decisao = E.decidir(remoto, estado);

    if (decisao.acao === 'adotar') {
      estado = decisao.usar;
      E.Local.gravar(estado);
      E.Local.marcarPendente(false);
      render();
      pintarStatus('', 'Atualizado');
    } else if (decisao.acao === 'enviar' || E.Local.temPendente()) {
      await enviarAgora(remoto);
    } else if (decisao.acao === 'conflito') {
      pintarStatus('pendente', 'Conflito');
      avisar('A nuvem tem ' + decisao.remoto + ' itens e este aparelho tem ' +
             decisao.local + '. Nada foi sobrescrito. Resolva no computador.', 'mau');
    } else {
      pintarStatus('', 'Atualizado');
    }
  } catch (e) {
    pintarStatus('erro', 'Erro');
    if (!silencioso) avisar('Falha inesperada: ' + e.message, 'mau');
  } finally {
    sincronizando = false;
  }
}

/**
 * Envia o estado local, preservando o que o celular nao edita.
 *
 * `remoto` e o snapshot que acabou de vir da nuvem. Dele vem o `notepad` e o
 * avatar. Se nao tivermos snapshot (rede caiu no meio), baixamos um so para
 * preservar - nunca enviamos sem essa garantia.
 */
async function enviarAgora(remoto) {
  if (!navigator.onLine) {
    E.Local.marcarPendente(true);
    pintarStatus('pendente', 'Pendente');
    return false;
  }

  let base = remoto;
  if (base === undefined) {
    const r = await sync.baixar();
    base = (r.estado === 'ok') ? E.normalizar(r.dados) : null;
    if (r.estado === 'erro' || r.estado === 'auth_error') {
      E.Local.marcarPendente(true);
      pintarStatus('pendente', 'Pendente');
      return false;
    }
  }

  const paraEnviar = E.carimbo(
    E.preservarNaoEditados(base, estado), 'mobile-' + VERSAO);

  // Trava final: se o Vault existia na nuvem e sumiu do que vamos enviar,
  // abortamos. Prefiro nao sincronizar a apagar dado do usuario.
  const tinhaVault = base && Array.isArray(base.notepad) && base.notepad.length > 0;
  const temVault   = Array.isArray(paraEnviar.notepad) && paraEnviar.notepad.length > 0;
  if (tinhaVault && !temVault) {
    pintarStatus('erro', 'Bloqueado');
    avisar('Envio bloqueado: o Vault sumiria. Nada foi alterado na nuvem.', 'mau');
    return false;
  }

  const res = await sync.enviar(paraEnviar);
  if (res.estado === 'ok') {
    estado._meta = paraEnviar._meta;
    E.Local.gravar(estado);
    E.Local.marcarPendente(false);
    pintarStatus('', 'Enviado');
    return true;
  }
  E.Local.marcarPendente(true);
  pintarStatus('pendente', 'Pendente');
  if (res.estado === 'auth_error') { avisar(res.msg, 'mau'); mostrarLogin(); }
  return false;
}

/** Grava local na hora e agenda o envio - a interface nunca espera a rede. */
function salvar() {
  E.Local.gravar(estado);
  E.Local.marcarPendente(true);
  pintarStatus('pendente', 'Salvando');
  clearTimeout(cronoGravar);
  cronoGravar = setTimeout(() => { enviarAgora(undefined); }, 1200);
}

/* ==========================================================================
 *  FILTROS
 * ======================================================================= */
function filtrar() {
  const t = hoje();
  let lista = estado.tasks.slice();

  if (filtro === 'myday') {
    lista = lista.filter(x =>
      x.isMyDay === false ? false : (x.isMyDay === true || x.dueDate === t));
  } else if (filtro === 'planned') {
    lista = lista.filter(x => !!x.dueDate);
  } else if (filtro.indexOf('cat:') === 0) {
    const id = filtro.slice(4);
    lista = lista.filter(x => x.categoryId === id);
  } else if (filtro.indexOf('proj:') === 0) {
    const id = filtro.slice(5);
    lista = lista.filter(x => x.projectId === id);
  }

  const ordem = { Urgente: 0, Alta: 1, 'Média': 2, Media: 2, 'Baixa': 3 };
  lista.sort((a, b) => {
    const fa = (Number(a.progress) || 0) >= 100, fb = (Number(b.progress) || 0) >= 100;
    if (fa !== fb) return fa ? 1 : -1;
    const pa = ordem[a.priority] === undefined ? 2 : ordem[a.priority];
    const pb = ordem[b.priority] === undefined ? 2 : ordem[b.priority];
    if (pa !== pb) return pa - pb;
    if (a.dueDate && b.dueDate) return a.dueDate < b.dueDate ? -1 : 1;
    if (a.dueDate) return -1;
    if (b.dueDate) return 1;
    return 0;
  });
  return lista;
}

function contar(f) {
  const salvo = filtro; filtro = f;
  const n = filtrar().filter(t => (Number(t.progress) || 0) < 100).length;
  filtro = salvo; return n;
}

/* ==========================================================================
 *  RENDER
 * ======================================================================= */
const TITULOS = { myday: 'Meu Dia', planned: 'Planejadas', all: 'Todas as Tarefas' };

function render() {
  renderChips();
  renderLista();
  renderPerfil();
}

function renderChips() {
  const base = [
    { id: 'myday',   nome: 'Meu Dia' },
    { id: 'planned', nome: 'Planejadas' },
    { id: 'all',     nome: 'Todas' }
  ];
  const cats  = estado.categories.map(c => ({ id: 'cat:' + c.id,  nome: c.name }));
  const projs = estado.projects.map(p => ({ id: 'proj:' + p.id, nome: p.name }));

  $('#chips-filtro').innerHTML = base.concat(cats, projs).map(f =>
    '<button class="chip' + (filtro === f.id ? ' ativo' : '') +
    '" data-f="' + esc(f.id) + '">' + esc(f.nome) +
    '<span class="n">' + contar(f.id) + '</span></button>'
  ).join('');

  $$('#chips-filtro .chip').forEach(b => {
    b.onclick = () => { filtro = b.dataset.f; vibrar(); render(); window.scrollTo(0, 0); };
  });
}

function renderLista() {
  const lista = filtrar();
  const ativas = lista.filter(t => (Number(t.progress) || 0) < 100);
  const feitas = lista.filter(t => (Number(t.progress) || 0) >= 100);

  let nome = TITULOS[filtro];
  if (!nome && filtro.indexOf('cat:') === 0) {
    const c = estado.categories.find(x => x.id === filtro.slice(4));
    nome = c ? c.name : 'Categoria';
  }
  if (!nome && filtro.indexOf('proj:') === 0) {
    const p = estado.projects.find(x => x.id === filtro.slice(5));
    nome = p ? p.name : 'Projeto';
  }
  $('#tit-lista').textContent = nome || 'Tarefas';
  $('#sub-lista').textContent =
    ativas.length + ' pendente' + (ativas.length === 1 ? '' : 's') +
    (feitas.length ? '  |  ' + feitas.length + ' concluida' + (feitas.length === 1 ? '' : 's') : '');

  if (!lista.length) {
    $('#lista').innerHTML =
      '<div class="vazio">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">' +
      '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>' +
      '<p>Nenhuma tarefa aqui.<br>Toque no + para criar.</p></div>';
    return;
  }

  let html = ativas.map(cartao).join('');
  if (feitas.length) {
    html += '<div style="margin:18px 2px 10px;font-size:11px;font-weight:700;' +
            'color:var(--texto-3);text-transform:uppercase;letter-spacing:.5px">' +
            'Concluidas (' + feitas.length + ')</div>' + feitas.map(cartao).join('');
  }
  $('#lista').innerHTML = html;

  $$('#lista .cartao').forEach(el => {
    el.querySelector('.marcar').onclick = (ev) => {
      ev.stopPropagation(); alternar(el.dataset.id);
    };
    el.onclick = () => abrirDetalhe(el.dataset.id);
  });
}

function cartao(t) {
  const pct = Math.max(0, Math.min(100, Number(t.progress) || 0));
  const feita = pct >= 100;
  const cat  = estado.categories.find(c => c.id === t.categoryId);
  const proj = estado.projects.find(p => p.id === t.projectId);
  const etapas = Array.isArray(t.steps) ? t.steps : [];
  const feitasN = etapas.filter(s => s.completed).length;

  const marcas = [];
  if (t.priority) {
    marcas.push('<span class="marca-item ' + classePri(t.priority) + '">' +
                esc(t.priority) + '</span>');
  }
  if (cat)  marcas.push('<span class="marca-item">' + esc(cat.name)  + '</span>');
  if (proj) marcas.push('<span class="marca-item">' + esc(proj.name) + '</span>');
  if (t.dueDate) {
    marcas.push('<span class="marca-item' + (atrasada(t) ? ' atrasada' : '') + '">' +
                dataBR(t.dueDate) + '</span>');
  }

  return '' +
  '<div class="cartao' + (feita ? ' feita' : '') + '" data-id="' + esc(t.id) + '">' +
    '<div class="cartao-topo">' +
      '<button class="marcar' + (feita ? ' feita' : '') + '" aria-label="Concluir">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3.4" ' +
        'stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>' +
      '</button>' +
      '<div class="cartao-txt">' +
        '<p class="cartao-tit">' + esc(t.title) + '</p>' +
        (marcas.length ? '<div class="marcas">' + marcas.join('') + '</div>' : '') +
      '</div>' +
    '</div>' +
    '<div class="barra">' +
      '<div class="barra-tri"><div class="barra-in' + (feita ? ' cheia' : '') +
      '" style="width:' + pct + '%"></div></div>' +
      '<span class="barra-pct">' + pct + '%</span>' +
    '</div>' +
    (etapas.length
      ? '<div class="etapas-resumo">Etapas ' + feitasN + '/' + etapas.length + '</div>'
      : '') +
  '</div>';
}

function renderPerfil() {
  $('#perfil-email').textContent = sync.email || '-';
  const total = estado.tasks.length;
  const feitas = estado.tasks.filter(t => (Number(t.progress) || 0) >= 100).length;
  const notas = Array.isArray(estado.notepad) ? estado.notepad.length : 0;

  const linha = (t, s, v) =>
    '<div class="item-lista"><div class="tx"><b>' + esc(t) + '</b>' +
    (s ? '<small>' + esc(s) + '</small>' : '') + '</div>' +
    '<span class="val">' + esc(v) + '</span></div>';

  $('#perfil-stats').innerHTML =
    linha('Tarefas', feitas + ' concluidas', String(total)) +
    linha('Projetos', '', String(estado.projects.length)) +
    linha('Categorias', '', String(estado.categories.length)) +
    linha('Notas no Vault', 'preservadas, nao exibidas aqui', String(notas)) +
    linha('Ultima alteracao', '',
      estado._meta && estado._meta.updatedAt
        ? new Date(estado._meta.updatedAt).toLocaleString('pt-BR')
        : '-');
}

/* ==========================================================================
 *  ACOES
 * ======================================================================= */
function acharTarefa(id) { return estado.tasks.find(t => t.id === id); }

function alternar(id) {
  const t = acharTarefa(id); if (!t) return;
  const feita = (Number(t.progress) || 0) >= 100;
  t.progress = feita ? 0 : 100;
  if (!feita && Array.isArray(t.steps)) t.steps.forEach(s => s.completed = true);
  vibrar(12);
  salvar(); render();
}

function novaTarefa(titulo) {
  const t = {
    id: 'task-' + Date.now() + '-' + Math.floor(Math.random() * 1000),
    title: titulo,
    progress: 0,
    priority: 'Média',
    categoryId: estado.categories.length ? estado.categories[0].id : null,
    projectId: null,
    dueDate: '',
    notes: '',
    steps: [],
    attachments: [],
    isMyDay: filtro === 'myday',
    createdAt: hoje()
  };
  if (filtro.indexOf('cat:')  === 0) t.categoryId = filtro.slice(4);
  if (filtro.indexOf('proj:') === 0) t.projectId  = filtro.slice(5);
  estado.tasks.unshift(t);
  salvar(); render();
  return t.id;
}

/* ==========================================================================
 *  FOLHA
 * ======================================================================= */
function abrirFolha(html) {
  $('#folha-conteudo').innerHTML = html;
  $('#folha').classList.add('aberta');
  $('#fundo').classList.add('aberto');
  document.body.style.overflow = 'hidden';
}

function fecharFolha() {
  $('#folha').classList.remove('aberta');
  $('#fundo').classList.remove('aberto');
  document.body.style.overflow = '';
  aberta = null;
}

function abrirNova() {
  abrirFolha(
    '<div class="campo"><label for="nt">Nova tarefa</label>' +
    '<input id="nt" class="entrada" placeholder="O que precisa ser feito?" ' +
    'autocomplete="off" enterkeyhint="done"></div>' +
    '<button id="nt-ok" class="btn btn-1">Adicionar</button>');

  const inp = $('#nt');
  setTimeout(() => inp.focus(), 120);

  const criar = () => {
    const v = inp.value.trim();
    if (!v) { inp.focus(); return; }
    const id = novaTarefa(v);
    fecharFolha();
    setTimeout(() => abrirDetalhe(id), 220);
  };
  $('#nt-ok').onclick = criar;
  inp.onkeydown = (e) => { if (e.key === 'Enter') criar(); };
}

function abrirDetalhe(id) {
  const t = acharTarefa(id); if (!t) return;
  aberta = id;
  const pct = Math.max(0, Math.min(100, Number(t.progress) || 0));

  const opcoes = (arr, sel, vazio) =>
    '<option value="">' + vazio + '</option>' +
    arr.map(o => '<option value="' + esc(o.id) + '"' +
      (o.id === sel ? ' selected' : '') + '>' + esc(o.name) + '</option>').join('');

  const etapas = (Array.isArray(t.steps) ? t.steps : []).map((s, i) =>
    '<div class="etapa' + (s.completed ? ' feita' : '') + '" data-i="' + i + '">' +
      '<button class="marcar' + (s.completed ? ' feita' : '') +
      '" style="width:19px;height:19px" aria-label="Concluir etapa">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3.4" ' +
        'stroke-linecap="round"><path d="M20 6L9 17l-5-5"/></svg>' +
      '</button>' +
      '<span>' + esc(s.title) + '</span>' +
      '<button class="lixo" aria-label="Remover etapa">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
        'stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>' +
      '</button>' +
    '</div>').join('');

  abrirFolha(
    '<div class="campo"><label for="d-tit">Tarefa</label>' +
    '<input id="d-tit" class="entrada" value="' + esc(t.title) + '"></div>' +

    '<div class="dupla">' +
      '<div class="campo"><label for="d-cat">Categoria</label>' +
      '<select id="d-cat" class="entrada">' +
      opcoes(estado.categories, t.categoryId, 'Nenhuma') + '</select></div>' +
      '<div class="campo"><label for="d-proj">Projeto</label>' +
      '<select id="d-proj" class="entrada">' +
      opcoes(estado.projects, t.projectId, 'Nenhum') + '</select></div>' +
    '</div>' +

    '<div class="dupla">' +
      '<div class="campo"><label for="d-pri">Prioridade</label>' +
      '<select id="d-pri" class="entrada">' +
      ['Baixa', 'Média', 'Alta', 'Urgente'].map(p =>
        '<option' + (p === t.priority ? ' selected' : '') + '>' + p + '</option>'
      ).join('') + '</select></div>' +
      '<div class="campo"><label for="d-data">Data limite</label>' +
      '<input id="d-data" class="entrada" type="date" value="' +
      esc(t.dueDate || '') + '"></div>' +
    '</div>' +

    '<div class="campo">' +
      '<label>Meu Dia</label>' +
      '<button id="d-myday" class="btn ' + (t.isMyDay ? 'btn-1' : 'btn-2') + '">' +
      (t.isMyDay ? 'Esta no Meu Dia' : 'Adicionar ao Meu Dia') + '</button>' +
    '</div>' +

    '<div class="campo">' +
      '<label for="d-prog">Progresso <span id="d-prog-v">' + pct + '%</span></label>' +
      '<input id="d-prog" class="faixa" type="range" min="0" max="100" step="5" ' +
      'value="' + pct + '"></div>' +

    '<div class="campo">' +
      '<label>Etapas</label>' +
      '<div id="d-etapas">' + etapas + '</div>' +
      '<div style="display:flex;gap:8px;margin-top:8px">' +
        '<input id="d-nova-etapa" class="entrada" placeholder="Nova etapa..." ' +
        'style="flex:1" enterkeyhint="done">' +
        '<button id="d-add-etapa" class="btn btn-2" style="width:46px;flex:0 0 46px">+</button>' +
      '</div>' +
    '</div>' +

    '<div class="campo"><label for="d-notas">Anotacoes</label>' +
    '<textarea id="d-notas" class="entrada" placeholder="Notas desta tarefa...">' +
    esc(t.notes || '') + '</textarea></div>' +

    (Array.isArray(t.attachments) && t.attachments.length
      ? '<p style="font-size:11.5px;color:var(--texto-3);margin:0 0 14px">' +
        t.attachments.length + ' anexo(s). Abra no computador para ver.</p>'
      : '') +

    '<div class="linha-btn" style="margin-top:6px">' +
      '<button id="d-excluir" class="btn btn-x">Excluir</button>' +
      '<button id="d-fechar" class="btn btn-1">Pronto</button>' +
    '</div>'
  );

  const mudou = () => { salvar(); renderLista(); renderChips(); };

  $('#d-tit').onchange   = (e) => { t.title = e.target.value.trim() || t.title; mudou(); };
  $('#d-cat').onchange   = (e) => { t.categoryId = e.target.value || null; mudou(); };
  $('#d-proj').onchange  = (e) => { t.projectId  = e.target.value || null; mudou(); };
  $('#d-pri').onchange   = (e) => { t.priority   = e.target.value; mudou(); };
  $('#d-data').onchange  = (e) => { t.dueDate    = e.target.value || ''; mudou(); };
  $('#d-notas').onchange = (e) => { t.notes      = e.target.value; salvar(); };

  $('#d-myday').onclick = (e) => {
    t.isMyDay = !t.isMyDay;
    e.target.className = 'btn ' + (t.isMyDay ? 'btn-1' : 'btn-2');
    e.target.textContent = t.isMyDay ? 'Esta no Meu Dia' : 'Adicionar ao Meu Dia';
    vibrar(); mudou();
  };

  const faixa = $('#d-prog');
  faixa.oninput  = (e) => { $('#d-prog-v').textContent = e.target.value + '%'; };
  faixa.onchange = (e) => { t.progress = parseInt(e.target.value, 10) || 0; mudou(); };

  const addEtapa = () => {
    const c = $('#d-nova-etapa'), v = c.value.trim();
    if (!v) return;
    if (!Array.isArray(t.steps)) t.steps = [];
    t.steps.push({ id: 'step-' + Date.now(), title: v, completed: false });
    c.value = ''; salvar(); abrirDetalhe(id);
    setTimeout(() => { const n = $('#d-nova-etapa'); if (n) n.focus(); }, 60);
  };
  $('#d-add-etapa').onclick = addEtapa;
  $('#d-nova-etapa').onkeydown = (e) => { if (e.key === 'Enter') addEtapa(); };

  $$('#d-etapas .etapa').forEach(el => {
    const i = parseInt(el.dataset.i, 10);
    el.querySelector('.marcar').onclick = () => {
      t.steps[i].completed = !t.steps[i].completed;
      vibrar(); salvar(); abrirDetalhe(id);
    };
    el.querySelector('.lixo').onclick = () => {
      t.steps.splice(i, 1); salvar(); abrirDetalhe(id);
    };
  });

  $('#d-excluir').onclick = () => {
    if (!confirm('Excluir "' + t.title + '"?\n\nIsso remove a tarefa em todos os seus aparelhos.')) return;
    estado.tasks = estado.tasks.filter(x => x.id !== id);
    salvar(); fecharFolha(); render();
    avisar('Tarefa excluida.');
  };
  $('#d-fechar').onclick = () => { fecharFolha(); render(); };
}

/* ==========================================================================
 *  LOGIN
 * ======================================================================= */
function mostrarLogin() {
  $('#tela-login').classList.remove('oculto');
  ['#topo', '#corpo', '#nav', '#fab'].forEach(s => $(s).classList.add('oculto'));
}

function mostrarApp() {
  $('#tela-login').classList.add('oculto');
  ['#topo', '#corpo', '#nav', '#fab'].forEach(s => $(s).classList.remove('oculto'));
}

function erroLogin(msg) {
  const e = $('#login-erro');
  if (!msg) { e.classList.add('oculto'); return; }
  e.textContent = msg; e.classList.remove('oculto');
}

async function autenticar(criando) {
  const email = $('#in-email').value.trim();
  const senha = $('#in-senha').value;
  if (!email || !senha) { erroLogin('Informe e-mail e senha.'); return; }

  erroLogin('');
  const bts = [$('#btn-entrar'), $('#btn-criar')];
  bts.forEach(b => b.disabled = true);
  $('#btn-entrar').textContent = 'Entrando...';

  try {
    const r = criando ? await sync.criarConta(email, senha)
                      : await sync.entrar(email, senha);
    if (!r.ok) { erroLogin(r.erro); return; }
    $('#in-senha').value = '';
    estado = E.Local.ler() || E.vazio();
    mostrarApp(); render();
    await sincronizar(false);
  } catch (e) {
    erroLogin('Falha de conexao: ' + e.message);
  } finally {
    bts.forEach(b => b.disabled = false);
    $('#btn-entrar').textContent = 'Entrar';
  }
}

/* ==========================================================================
 *  BOOT
 * ======================================================================= */
function trocarAba(aba) {
  $('#v-tarefas').classList.toggle('oculto', aba !== 'tarefas');
  $('#v-perfil').classList.toggle('oculto', aba !== 'perfil');
  $('#fab').classList.toggle('oculto', aba !== 'tarefas');
  $$('#nav button').forEach(b => b.classList.toggle('ativo', b.dataset.aba === aba));
  window.scrollTo(0, 0);
}

function ligarEventos() {
  $('#btn-entrar').onclick = () => autenticar(false);
  $('#btn-criar').onclick  = () => autenticar(true);
  $('#in-senha').onkeydown = (e) => { if (e.key === 'Enter') autenticar(false); };

  $('#fab').onclick   = abrirNova;
  $('#fundo').onclick = fecharFolha;
  $('#btn-sync').onclick = () => sincronizar(false);
  $('#btn-forcar-sync').onclick = () => sincronizar(false);

  $('#btn-sair').onclick = () => {
    if (!confirm('Sair desta conta?\n\nOs dados continuam na nuvem e no computador.')) return;
    sync.sair(); estado = E.vazio(); mostrarLogin();
  };

  $$('#nav button').forEach(b => { b.onclick = () => { vibrar(); trocarAba(b.dataset.aba); }; });

  // Voltar do Android fecha a folha em vez de sair do app
  window.addEventListener('popstate', () => {
    if ($('#folha').classList.contains('aberta')) fecharFolha();
  });
  $('#folha').addEventListener('transitionend', () => {
    if ($('#folha').classList.contains('aberta')) {
      try { history.pushState({ folha: 1 }, ''); } catch (e) {}
    }
  });

  window.addEventListener('online',  () => { pintarStatus('', 'Online'); sincronizar(true); });
  window.addEventListener('offline', () => pintarStatus('offline', 'Offline'));

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && sync.logado) sincronizar(true);
  });
}

async function iniciar() {
  $('#selo-versao').textContent = 'v' + VERSAO;
  ligarEventos();

  if (!sync.logado) { mostrarLogin(); return; }

  estado = E.Local.ler() || E.vazio();
  mostrarApp();
  render();
  pintarStatus(navigator.onLine ? 'girando' : 'offline',
               navigator.onLine ? 'Sincronizando' : 'Offline');
  await sincronizar(true);

  // Reenvia periodicamente o que ficou pendente por falta de rede.
  setInterval(() => {
    if (sync.logado && navigator.onLine && E.Local.temPendente() && !sincronizando) {
      enviarAgora(undefined);
    }
  }, 30000);
}

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  });
}

document.addEventListener('DOMContentLoaded', iniciar);
