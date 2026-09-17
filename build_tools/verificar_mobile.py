# -*- coding: utf-8 -*-
r"""
NEXUS - compatibilidade entre o app desktop e o PWA mobile.

Uso:
    cd C:\Dev\nexus
    python build_tools\verificar_mobile.py

So Python. Nada a instalar.

------------------------------------------------------------------------------
POR QUE ESTE VERIFICADOR EXISTE
------------------------------------------------------------------------------
Os dois apps escrevem no MESMO no do Firebase:
/apps/nexus/users/<uid>/database

Nao ha "copia mobile" dos dados. E o mesmo dado. Isso significa que uma
divergencia entre os dois modelos nao da erro - da PERDA SILENCIOSA.

O cenario concreto, e o unico que realmente assusta:

  O celular nao mostra o Vault. Se ele enviar um estado sem o campo `notepad`,
  o PUT no Realtime Database SUBSTITUI o no inteiro. Suas 30 notas somem da
  nuvem, e o desktop, ao sincronizar, adota o estado sem elas. Em todos os
  aparelhos. Sem mensagem de erro.

Este script confere que a protecao contra isso existe no codigo, e que os dois
lados concordam sobre a forma dos dados.

Codigo de saida: 0 se compativel, 1 se ha risco.
------------------------------------------------------------------------------
"""
import io
import json
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESKTOP = os.path.join(RAIZ, 'nexus.py')
MOBILE = os.path.join(RAIZ, 'mobile')

problemas = []
avisos = []


def ok(m):
    print("  OK     " + m)


def falha(m):
    print("  FALHA  " + m)
    problemas.append(m)


def aviso(m):
    print("  aviso  " + m)
    avisos.append(m)


def cabecalho(t):
    print()
    print("=" * 74)
    print(" " + t)
    print("=" * 74)


def ler(caminho):
    try:
        return io.open(caminho, encoding='utf-8').read()
    except OSError:
        return None


def main():
    desktop = ler(DESKTOP)
    if desktop is None:
        print("nexus.py nao encontrado em %s" % RAIZ)
        return 2
    if not os.path.isdir(MOBILE):
        print("pasta mobile\\ nao encontrada")
        return 2

    arquivos = {}
    for nome in ('index.html', 'app.js', 'nexus-sync.js', 'sw.js',
                 'styles.css', 'manifest.webmanifest'):
        arquivos[nome] = ler(os.path.join(MOBILE, nome))

    # ---------------------------------------------------- 1. arquivos
    cabecalho("1. ARQUIVOS DO PWA")
    for nome, conteudo in arquivos.items():
        if conteudo is None:
            falha("mobile\\%s ausente" % nome)
        else:
            ok("mobile\\%-22s %d bytes" % (nome, len(conteudo.encode('utf-8'))))

    if any(v is None for v in arquivos.values()):
        print("\nArquivos faltando; interrompendo.")
        return 1

    sync = arquivos['nexus-sync.js']
    app = arquivos['app.js']

    # -------------------------------- 2. mesmo projeto Firebase
    cabecalho("2. APONTAM PARA O MESMO BANCO")

    def pega(txt, padrao):
        m = re.search(padrao, txt)
        return m.group(1) if m else None

    pares = [
        ('apiKey',
         pega(desktop, r'FIREBASE_API_KEY = "([^"]+)"'),
         pega(sync, r"FIREBASE_API_KEY\s*=\s*'([^']+)'")),
        ('URL do banco',
         pega(desktop, r'FIREBASE_DB_URL = "([^"]+)"'),
         pega(sync, r"FIREBASE_DB_URL\s*=\s*'([^']+)'")),
        ('namespace',
         pega(desktop, r'APP_NAMESPACE = "([^"]+)"'),
         pega(sync, r"APP_NAMESPACE\s*=\s*'([^']+)'")),
    ]
    for nome, d, m in pares:
        if d is None or m is None:
            falha("%s: nao consegui extrair (desktop=%r mobile=%r)" % (nome, d, m))
        elif d != m:
            falha("%s DIVERGE - desktop=%r mobile=%r" % (nome, d, m))
        else:
            ok("%-14s identico nos dois (%s)"
               % (nome, d if len(d) < 46 else d[:43] + '...'))

    # o caminho do no precisa ser o mesmo
    if re.search(r'/apps/\'\s*\+\s*APP_NAMESPACE\s*\+\s*\'/users/', sync) or \
       re.search(r"apps/'\s*\+\s*APP_NAMESPACE", sync):
        ok("caminho    /apps/<ns>/users/<uid>/database.json")
    else:
        falha("o caminho do no no mobile nao segue /apps/<ns>/users/<uid>/database")

    # ------------------------------ 3. PROTECAO DO VAULT (o item critico)
    cabecalho("3. PROTECAO DO VAULT - O ITEM CRITICO")

    checagens = [
        (sync, r"INTOCAVEIS\s*=\s*\[[^\]]*'notepad'",
         "lista de campos intocaveis inclui 'notepad'"),
        (sync, r'function preservarNaoEditados',
         "funcao preservarNaoEditados existe"),
        (app, r'preservarNaoEditados\(',
         "o app chama preservarNaoEditados antes de enviar"),
        (app, r'tinhaVault\s*&&\s*!temVault',
         "trava final: aborta o envio se o Vault sumiria"),
        (sync, r"userProfile.*avatar", "preserva o avatar do perfil"),
    ]
    for texto, padrao, desc in checagens:
        if re.search(padrao, texto, re.S):
            ok(desc)
        else:
            falha("AUSENTE: " + desc)

    # O mobile nunca pode montar um estado do zero e enviar
    if re.search(r'sync\.enviar\(', app):
        chamadas = re.findall(r'sync\.enviar\(([^)]*)\)', app)
        seguras = [c for c in chamadas if 'paraEnviar' in c]
        if len(seguras) == len(chamadas):
            ok("todas as %d chamadas a enviar() usam o estado preservado"
               % len(chamadas))
        else:
            falha("ha chamada a sync.enviar() sem passar pelo estado preservado")

    # ---------------------------------------- 4. modelo de dados
    cabecalho("4. MODELO DE DADOS")

    campos_desktop = set(re.findall(
        r"if \(!?t\.(\w+)", desktop))
    esperados = {'id', 'title', 'progress', 'priority', 'steps',
                 'attachments', 'isMyDay'}
    faltando_no_mobile = []
    for campo in sorted(esperados):
        if not re.search(r'\bt\.%s\b|\b%s:' % (campo, campo), sync):
            faltando_no_mobile.append(campo)
    if faltando_no_mobile:
        falha("normalizar() do mobile nao trata: %s"
              % ', '.join(faltando_no_mobile))
    else:
        ok("normalizar() cobre os %d campos que o desktop garante"
           % len(esperados))

    # os cinco arrays de topo
    for chave in ('categories', 'projects', 'tasks', 'notepad'):
        if re.search(r"Array\.isArray\(e\.%s\)" % chave, sync):
            ok("array de topo '%s' normalizado" % chave)
        else:
            falha("array de topo '%s' NAO e normalizado no mobile" % chave)

    # a nova tarefa do mobile precisa nascer com os mesmos campos
    m = re.search(r'function novaTarefa[^{]*\{(.*?)\n\}', app, re.S)
    if m:
        corpo = m.group(1)
        faltam = [c for c in ('id', 'title', 'progress', 'priority',
                              'steps', 'attachments', 'isMyDay')
                  if (c + ':') not in corpo]
        if faltam:
            falha("novaTarefa() do mobile nao define: %s" % ', '.join(faltam))
        else:
            ok("novaTarefa() cria a tarefa com todos os campos do desktop")
    else:
        aviso("nao consegui localizar novaTarefa() para comparar")

    # ------------------------------------------ 5. filtros iguais
    cabecalho("5. FILTROS IDENTICOS AO DESKTOP")

    if re.search(r"isMyDay === false \? false : \(x?t?\.?isMyDay === true", app) or \
       re.search(r"isMyDay === false[^\n]*isMyDay === true[^\n]*dueDate", app):
        ok("filtro 'Meu Dia' usa a mesma regra do desktop")
    else:
        falha("o filtro 'Meu Dia' do mobile nao reproduz a regra do desktop")

    if re.search(r"filtro === 'planned'[^\n]*\n[^\n]*dueDate", app):
        ok("filtro 'Planejadas' usa dueDate, como o desktop")
    else:
        aviso("nao confirmei o filtro 'Planejadas'")

    # ------------------------------------------ 6. carimbo _meta
    cabecalho("6. CARIMBO DE TEMPO E CONFLITO")

    if re.search(r"_meta\s*=\s*\{\s*updatedAt", sync):
        ok("mobile grava _meta.updatedAt, como o desktop")
    else:
        falha("mobile nao grava _meta.updatedAt - a resolucao de conflito quebra")

    if re.search(r'function decidir', sync) and \
       re.search(r'contarItens\(remoto\) <', sync):
        ok("resolucao de conflito: lado vazio nunca substitui lado com conteudo")
    else:
        falha("falta a protecao 'lado vazio nao substitui' na resolucao de conflito")

    # ------------------------------------------ 7. PWA e seguranca
    cabecalho("7. PWA E SEGURANCA")

    html = arquivos['index.html']
    sw = arquivos['sw.js']

    try:
        man = json.loads(arquivos['manifest.webmanifest'])
        for chave in ('name', 'start_url', 'display', 'icons'):
            if chave not in man:
                falha("manifest sem '%s'" % chave)
        if man.get('display') not in ('standalone', 'fullscreen', 'minimal-ui'):
            aviso("display='%s' nao instala como app" % man.get('display'))
        else:
            ok("manifest valido, display=%s, %d icone(s)"
               % (man['display'], len(man.get('icons', []))))
        for ic in man.get('icons', []):
            p = os.path.join(MOBILE, ic['src'])
            if not os.path.exists(p):
                aviso("icone ausente: %s (rode mobile\\gerar_icones.py)" % ic['src'])
    except Exception as e:
        falha("manifest.webmanifest invalido: %s" % e)

    if 'Content-Security-Policy' in html:
        ok("CSP presente no index.html")
        if "connect-src" in html and 'firebaseio.com' in html:
            ok("connect-src limita os destinos aos hosts do Firebase")
        else:
            aviso("CSP sem connect-src restrito")
    else:
        falha("index.html sem Content-Security-Policy")

    # o SW nao pode cachear dado do Firebase
    if re.search(r"NUNCA_CACHEAR", sw) and 'firebaseio.com' in sw:
        ok("service worker NAO cacheia respostas do Firebase")
    else:
        falha("o service worker pode estar cacheando dados do Firebase - isso "
              "faria o app mostrar tarefas desatualizadas com cara de corretas")

    # nenhum CDN
    cdns = re.findall(r'https?://(?:cdn|unpkg|jsdelivr|fonts)\S*', html + arquivos['styles.css'])
    if cdns:
        falha("dependencia de CDN encontrada (quebra o offline): %s" % cdns[:3])
    else:
        ok("zero dependencia de CDN - funciona offline de verdade")

    # o Vault nao pode estar na interface
    if re.search(r'\bVault\b', html) and not re.search(
            r'Vault nao esta disponivel', html):
        aviso("a palavra Vault aparece no HTML; confirme que e so o texto "
              "explicativo, nao uma tela")
    if re.search(r'notepad', app):
        # so pode aparecer para PRESERVAR e para contar, nunca para editar
        usos = re.findall(r'[^\n]*notepad[^\n]*', app)
        editando = [u for u in usos if re.search(r'notepad\.(push|splice)|notepad\s*=\s*\[', u)]
        if editando:
            falha("o mobile EDITA notepad: %s" % editando[0].strip()[:70])
        else:
            ok("o mobile le notepad apenas para contar e preservar")

    # ------------------------------------------------- resumo
    print()
    print("=" * 74)
    if problemas:
        print(" %d PROBLEMA(S) - NAO PUBLIQUE O MOBILE" % len(problemas))
        for p in problemas:
            print("   x " + p)
    else:
        print(" DESKTOP E MOBILE COMPATIVEIS")
        print()
        print(" O que isto NAO garante:")
        print("   - nao executa o app; teste no celular antes de confiar")
        print("   - nao valida a sintaxe do JavaScript (sem Node aqui)")
        print("   - o primeiro login no celular deve ser feito com o desktop")
        print("     fechado, e confira o Vault no desktop logo depois")
    if avisos:
        print("\n %d aviso(s)." % len(avisos))
    print("=" * 74)
    return 1 if problemas else 0


if __name__ == '__main__':
    sys.exit(main())
