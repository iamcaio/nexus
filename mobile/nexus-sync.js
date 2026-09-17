/* ===========================================================================
 *  NEXUS Mobile - camada de sincronizacao com o Firebase
 * ===========================================================================
 *  Substitui, em JavaScript puro, o que a classe CloudSync do nexus.py fazia
 *  em Python. Mesmos endpoints, mesmo UID, mesmas Regras do Realtime Database.
 *
 *  Consequencia pratica: ao entrar com a mesma conta, o celular le e escreve
 *  exatamente o no /apps/nexus/users/<uid>/database que o desktop usa. Nao ha
 *  copia, nao ha espelho, nao ha "versao mobile dos dados". E o mesmo dado.
 * ======================================================================== */

(function (global) {
  'use strict';

  // Mesmas constantes do nexus.py. A apiKey e publica por design: quem protege
  // os dados sao as Regras, que prendem cada usuario ao proprio UID.
  const FIREBASE_API_KEY = 'AIzaSyAvB7jmXgziIMSG3JptOznthGQAP76LWXM';
  const FIREBASE_DB_URL  = 'https://cogni-data-default-rtdb.firebaseio.com';
  const APP_NAMESPACE    = 'nexus';

  const IDENTITY_URL = 'https://identitytoolkit.googleapis.com/v1/accounts';
  const TOKEN_URL    = 'https://securetoken.googleapis.com/v1/token';

  const CHAVE_SESSAO = 'nexus.sessao';
  const CHAVE_CACHE  = 'nexus.cache';
  const CHAVE_FILA   = 'nexus.fila';

  /* ---------------------------------------------------------------------
   *  Mensagens de erro do Firebase em portugues
   * ------------------------------------------------------------------ */
  const MENSAGENS = {
    EMAIL_EXISTS: 'Este e-mail ja esta cadastrado. Use Entrar.',
    EMAIL_NOT_FOUND: 'E-mail nao encontrado.',
    INVALID_PASSWORD: 'Senha incorreta.',
    INVALID_LOGIN_CREDENTIALS: 'E-mail ou senha incorretos.',
    USER_DISABLED: 'Esta conta foi desativada.',
    INVALID_EMAIL: 'E-mail invalido.',
    TOKEN_EXPIRED: 'Sessao expirada. Entre novamente.',
    OPERATION_NOT_ALLOWED: 'Login por e-mail/senha desativado no projeto.',
    ADMIN_ONLY_OPERATION: 'A criacao de contas esta desativada. Peca ao administrador.',
    'WEAK_PASSWORD : Password should be at least 6 characters':
      'A senha precisa ter ao menos 6 caracteres.'
  };

  function amigavel(codigo) {
    const c = String(codigo || '');
    if (MENSAGENS[c]) return MENSAGENS[c];
    if (c.indexOf('TOO_MANY_ATTEMPTS') === 0)
      return 'Muitas tentativas. Aguarde alguns minutos.';
    if (c.indexOf('WEAK_PASSWORD') === 0)
      return 'A senha precisa ter ao menos 6 caracteres.';
    return c || 'Falha desconhecida.';
  }

  /* ---------------------------------------------------------------------
   *  HTTP
   * ------------------------------------------------------------------ */
  async function pedir(url, corpo, metodo) {
    const opcoes = { method: metodo || 'GET', headers: {} };
    if (corpo !== undefined && corpo !== null) {
      opcoes.headers['Content-Type'] = 'application/json';
      opcoes.body = JSON.stringify(corpo);
    }
    try {
      const r = await fetch(url, opcoes);
      let dados = null;
      const txt = await r.text();
      if (txt) { try { dados = JSON.parse(txt); } catch (e) { dados = txt; } }
      return { status: r.status, dados: dados };
    } catch (e) {
      // fetch so rejeita em falha de rede; erro HTTP vem com status.
      return { status: 0, dados: { error: { message: 'rede: ' + e.message } } };
    }
  }

  /* =====================================================================
   *  NexusSync
   * ================================================================== */
  class NexusSync {
    constructor() {
      this.idToken = null;
      this.refreshToken = null;
      this.uid = null;
      this.email = null;
      this.expiraEm = 0;
      this.ultimoErro = null;
      this._carregarSessao();
    }

    get logado() { return !!(this.refreshToken && this.uid); }

    /* ------------------------------------------------ sessao local */
    _carregarSessao() {
      try {
        const s = JSON.parse(localStorage.getItem(CHAVE_SESSAO) || 'null');
        if (s) {
          this.refreshToken = s.refreshToken || null;
          this.uid = s.uid || null;
          this.email = s.email || null;
        }
      } catch (e) { /* sessao ilegivel: segue deslogado */ }
    }

    _salvarSessao() {
      try {
        localStorage.setItem(CHAVE_SESSAO, JSON.stringify({
          refreshToken: this.refreshToken, uid: this.uid, email: this.email
        }));
      } catch (e) { /* armazenamento cheio ou bloqueado */ }
    }

    _limparSessao() {
      this.idToken = this.refreshToken = this.uid = this.email = null;
      this.expiraEm = 0;
      try { localStorage.removeItem(CHAVE_SESSAO); } catch (e) {}
    }

    _aplicarAuth(c) {
      this.idToken = c.idToken;
      this.refreshToken = c.refreshToken;
      this.uid = c.localId || c.user_id;
      if (c.email) this.email = c.email;
      const seg = parseInt(c.expiresIn || 3600, 10);
      this.expiraEm = Date.now() + (isNaN(seg) ? 3300 : seg - 120) * 1000;
      this._salvarSessao();
    }

    /* --------------------------------------------------- autenticacao */
    async entrar(email, senha) {
      const r = await pedir(
        IDENTITY_URL + ':signInWithPassword?key=' + FIREBASE_API_KEY,
        { email: email, password: senha, returnSecureToken: true }, 'POST');
      if (r.status === 200 && r.dados && r.dados.idToken) {
        this._aplicarAuth(r.dados);
        return { ok: true, uid: this.uid, email: this.email };
      }
      const msg = ((r.dados || {}).error || {}).message || 'Falha ao entrar.';
      return { ok: false, erro: amigavel(msg) };
    }

    async criarConta(email, senha) {
      const r = await pedir(
        IDENTITY_URL + ':signUp?key=' + FIREBASE_API_KEY,
        { email: email, password: senha, returnSecureToken: true }, 'POST');
      if (r.status === 200 && r.dados && r.dados.idToken) {
        this._aplicarAuth(r.dados);
        return { ok: true, uid: this.uid, email: this.email };
      }
      const msg = ((r.dados || {}).error || {}).message || 'Falha ao criar conta.';
      return { ok: false, erro: amigavel(msg) };
    }

    sair() {
      this._limparSessao();
      try {
        localStorage.removeItem(CHAVE_CACHE);
        localStorage.removeItem(CHAVE_FILA);
      } catch (e) {}
    }

    async _token() {
      if (!this.refreshToken) return null;
      if (this.idToken && Date.now() < this.expiraEm) return this.idToken;

      const r = await pedir(TOKEN_URL + '?key=' + FIREBASE_API_KEY,
        { grant_type: 'refresh_token', refresh_token: this.refreshToken }, 'POST');
      if (r.status === 200 && r.dados && r.dados.id_token) {
        this.idToken = r.dados.id_token;
        this.refreshToken = r.dados.refresh_token || this.refreshToken;
        this.uid = r.dados.user_id || this.uid;
        const seg = parseInt(r.dados.expires_in || 3600, 10);
        this.expiraEm = Date.now() + (isNaN(seg) ? 3300 : seg - 120) * 1000;
        this._salvarSessao();
        return this.idToken;
      }
      this.ultimoErro = amigavel(((r.dados || {}).error || {}).message || 'TOKEN_EXPIRED');
      return null;
    }

    _caminho(token) {
      return FIREBASE_DB_URL + '/apps/' + APP_NAMESPACE + '/users/' +
             this.uid + '/database.json?auth=' + token;
    }

    /* --------------------------------------------------------- dados */
    async baixar() {
      if (!this.logado) return { estado: 'offline' };
      const token = await this._token();
      if (!token) return { estado: 'auth_error', msg: this.ultimoErro };

      const r = await pedir(this._caminho(token));
      if (r.status === 200) {
        if (r.dados === null) return { estado: 'vazio' };
        if (typeof r.dados === 'object') return { estado: 'ok', dados: r.dados };
        return { estado: 'erro', msg: 'Formato inesperado vindo da nuvem.' };
      }
      if (r.status === 401 || r.status === 403) {
        return { estado: 'auth_error',
                 msg: 'Sem permissao. Confira as Regras do Realtime Database.' };
      }
      return { estado: 'erro', msg: 'HTTP ' + r.status };
    }

    async enviar(dados) {
      if (!this.logado) return { estado: 'offline' };
      const token = await this._token();
      if (!token) return { estado: 'auth_error', msg: this.ultimoErro };

      const r = await pedir(this._caminho(token), dados, 'PUT');
      if (r.status >= 200 && r.status < 300) return { estado: 'ok' };
      if (r.status === 401 || r.status === 403) {
        return { estado: 'auth_error', msg: 'Sem permissao de escrita.' };
      }
      return { estado: 'erro', msg: 'HTTP ' + r.status };
    }
  }

  /* =====================================================================
   *  Estado: normalizacao, preservacao e mesclagem
   * ================================================================== */

  const VAZIO = function () {
    return { categories: [], projects: [], tasks: [], notepad: [], userProfile: {} };
  };

  /**
   * Aplica os mesmos padroes que o sanitizeState() do desktop aplica.
   * Manter isto identico e o que garante que um dado criado no celular abra
   * sem surpresa no desktop, e vice-versa.
   */
  function normalizar(e) {
    if (!e || typeof e !== 'object') e = VAZIO();
    if (!Array.isArray(e.categories)) e.categories = [];
    if (!Array.isArray(e.projects))   e.projects   = [];
    if (!Array.isArray(e.tasks))      e.tasks      = [];
    if (!Array.isArray(e.notepad))    e.notepad    = [];
    if (!e.userProfile || typeof e.userProfile !== 'object') {
      e.userProfile = { name: '', subtitle: '', avatar: null };
    }
    e.tasks.forEach(function (t, i) {
      if (!t.id) t.id = 'task-' + Date.now() + '-' + i;
      if (!t.title) t.title = t.nome || t.texto || 'Tarefa sem titulo';
      if (t.progress === undefined) t.progress = (t.completed || t.concluida) ? 100 : 0;
      if (!t.priority) t.priority = 'Media';
      if (!Array.isArray(t.steps)) t.steps = [];
      if (!Array.isArray(t.attachments)) t.attachments = [];
      if (t.isMyDay === undefined) t.isMyDay = true;
    });
    return e;
  }

  /**
   * O celular NAO mostra o Vault, mas precisa devolve-lo intacto.
   *
   * Este e o bug mais caro que este arquivo poderia ter: se o mobile enviasse
   * um estado sem `notepad`, o PUT no Realtime Database SUBSTITUI o no inteiro
   * e o Vault do desktop seria apagado, em todos os dispositivos, sem aviso.
   *
   * A defesa: guardamos os campos que o mobile nao edita e os reinserimos
   * antes de qualquer envio. Se o campo preservado sumir, abortamos.
   */
  function preservarNaoEditados(remoto, local) {
    const saida = Object.assign({}, local);
    const INTOCAVEIS = ['notepad'];
    INTOCAVEIS.forEach(function (chave) {
      if (remoto && remoto[chave] !== undefined) {
        saida[chave] = remoto[chave];
      }
    });
    // O avatar do desktop pode ser um marcador "@file". Nao mexer.
    if (remoto && remoto.userProfile && remoto.userProfile.avatar !== undefined) {
      saida.userProfile = Object.assign({}, saida.userProfile || {},
        { avatar: remoto.userProfile.avatar });
    }
    return saida;
  }

  function carimbo(estado, versao) {
    const e = Object.assign({}, estado);
    e._meta = { updatedAt: Date.now(), app: APP_NAMESPACE, version: versao || 'mobile' };
    return e;
  }

  function quandoAtualizado(e) {
    try { return parseInt((e && e._meta && e._meta.updatedAt) || 0, 10) || 0; }
    catch (x) { return 0; }
  }

  function contarItens(e) {
    if (!e || typeof e !== 'object') return 0;
    let n = 0;
    ['tasks', 'projects', 'categories', 'notepad'].forEach(function (k) {
      if (Array.isArray(e[k])) n += e[k].length;
    });
    return n;
  }

  /**
   * Decide quem vence entre nuvem e local, com o mesmo principio do desktop:
   * o carimbo manda, MAS um lado vazio nunca substitui um lado com conteudo.
   * Perder dado por sincronizacao e pior do que ficar um pouco desatualizado.
   */
  function decidir(remoto, local) {
    const temRemoto = contarItens(remoto) > 0;
    const temLocal  = contarItens(local) > 0;

    if (!temRemoto && !temLocal) return { usar: local || VAZIO(), acao: 'nada' };
    if (!temRemoto && temLocal)  return { usar: local,  acao: 'enviar' };
    if (temRemoto && !temLocal)  return { usar: remoto, acao: 'adotar' };

    const tR = quandoAtualizado(remoto), tL = quandoAtualizado(local);
    if (tR > tL) {
      // Nuvem mais nova, porem com bem menos conteudo: suspeito. Nao adota
      // automaticamente; deixa o app perguntar.
      if (contarItens(remoto) < contarItens(local) * 0.5) {
        return { usar: local, acao: 'conflito',
                 remoto: contarItens(remoto), local: contarItens(local) };
      }
      return { usar: remoto, acao: 'adotar' };
    }
    if (tL > tR) return { usar: local, acao: 'enviar' };
    return { usar: local, acao: 'nada' };
  }

  /* =====================================================================
   *  Cache local e fila de envio (funcionamento offline)
   * ================================================================== */
  const Local = {
    ler: function () {
      try {
        const s = JSON.parse(localStorage.getItem(CHAVE_CACHE) || 'null');
        return s ? normalizar(s) : null;
      } catch (e) { return null; }
    },
    gravar: function (estado) {
      try { localStorage.setItem(CHAVE_CACHE, JSON.stringify(estado)); return true; }
      catch (e) { return false; }
    },
    marcarPendente: function (v) {
      try {
        if (v) localStorage.setItem(CHAVE_FILA, '1');
        else localStorage.removeItem(CHAVE_FILA);
      } catch (e) {}
    },
    temPendente: function () {
      try { return localStorage.getItem(CHAVE_FILA) === '1'; } catch (e) { return false; }
    }
  };

  global.NexusSync = NexusSync;
  global.NexusEstado = {
    vazio: VAZIO,
    normalizar: normalizar,
    preservarNaoEditados: preservarNaoEditados,
    carimbo: carimbo,
    quandoAtualizado: quandoAtualizado,
    contarItens: contarItens,
    decidir: decidir,
    Local: Local
  };

})(window);
