# -*- coding: utf-8 -*-
r"""
NEXUS — verificacao da politica de sanitizacao do editor de notas.

Uso:
    cd C:\Dev\nexus
    python build_tools\verificar_sanitizador.py

NAO PRECISA DE NODE NEM DE NPM. Usa somente a biblioteca padrao do Python.

------------------------------------------------------------------------------
O QUE ESTE SCRIPT VERIFICA — E O QUE ELE NAO VERIFICA
------------------------------------------------------------------------------
O sanitizador e JavaScript e depende do DOM do navegador. Sem um motor de JS,
este script NAO executa a funcao sanitizarHtml() de verdade.

O que ele faz e auditar a POLITICA no codigo-fonte: se a lista de tags
permitidas ficou com algo perigoso, se a checagem de atributos `on*` continua
la, se o parse usa <template> (que monta a arvore sem executar nada), e se a
sanitizacao e chamada nos quatro pontos necessarios.

Isso pega a regressao realista: alguem — voce, eu, ou uma IA daqui a seis meses
— mexe no editor e adiciona 'IFRAME' na lista, ou remove a checagem de `on*`.

O que ele NAO pega: um erro de logica na implementacao que a politica nao
revela. Para isso existe o teste completo em Node, que executa 28 vetores reais
contra a funcao. Se voce quiser essa garantia mais forte:

    winget install OpenJS.NodeJS.LTS
    # feche e reabra o PowerShell
    npm install jsdom
    node build_tools\sanitizador_teste_completo_NODE.js

Os dois se complementam. Este roda sempre; aquele roda quando voce quiser a
verificacao completa.

Codigo de saida: 0 se a politica esta correta, 1 se ha problema.
------------------------------------------------------------------------------
"""
import io
import os
import re
import sys

# Tags que NUNCA podem estar na lista de permitidas. Cada uma e um vetor de
# execucao de codigo ou de exfiltracao de dados.
TAGS_PROIBIDAS = {
    'SCRIPT',    # execucao direta
    'IFRAME',    # carrega documento externo, src=javascript:
    'OBJECT',    # plugin / execucao
    'EMBED',     # idem
    'APPLET',    # idem
    'FORM',      # postar dados para fora
    'INPUT',     # componente de form
    'BUTTON',    # componente de form
    'SVG',       # onload dentro do SVG
    'MATH',      # vetores via MathML
    'LINK',      # importar CSS externo
    'META',      # meta refresh redireciona
    'STYLE',     # @import externo
    'BASE',      # sequestra URLs relativas
    'IMG',       # onerror e o vetor de XSS mais comum ao colar
    'VIDEO',     # onerror / onloadstart
    'AUDIO',     # idem
    'SOURCE',    # idem
    'TRACK',     # idem
    'IFRAME',
}

# Atributos que nunca podem estar permitidos.
ATRIBUTOS_PROIBIDOS = {
    'src', 'srcdoc', 'srcset', 'onerror', 'onload', 'onclick',
    'onmouseover', 'formaction', 'action', 'background', 'dynsrc',
    'lowsrc', 'data', 'codebase', 'xlink:href',
}

# Esquemas de URL que o teste do href precisa recusar.
ESQUEMAS_PERIGOSOS = [
    'javascript:alert(1)',
    'JaVaScRiPt:alert(1)',
    '  javascript:alert(1)',
    'java\tscript:alert(1)',
    'java\nscript:alert(1)',
    'java\x00script:alert(1)',
    'vbscript:msgbox(1)',
    'data:text/html,<script>alert(1)</script>',
    'file:///C:/Windows/System32/cmd.exe',
    'ms-msdt:/id PCWDiagnostic',
    'search-ms:query=x',
]

ESQUEMAS_LEGITIMOS = [
    'https://exemplo.com',
    'http://exemplo.com',
    'mailto:alguem@exemplo.com',
    '#ancora',
    '/caminho/relativo',
    './arquivo.html',
]

problemas = []
avisos = []


def ok(msg):
    print("  OK     " + msg)


def falha(msg):
    print("  FALHA  " + msg)
    problemas.append(msg)


def aviso(msg):
    print("  aviso  " + msg)
    avisos.append(msg)


def extrair_conjunto(fonte, nome):
    """Le um `const NOME = new Set([...])` do JavaScript."""
    m = re.search(
        r'const\s+' + nome + r'\s*=\s*new\s+Set\(\s*\[(.*?)\]\s*\)',
        fonte, re.S)
    if not m:
        return None
    return {v.upper() for v in re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))}


def traduzir_regex_js(js):
    r"""
    Adapta uma regex do JavaScript para o `re` do Python.

    O modulo `re` do Python 3 entende `\uXXXX` dentro de classe de caractere
    exatamente como o JavaScript, entao a classe de controle passa sem
    alteracao. O que muda e a barra invertida antes de `/`: em JS ela e
    obrigatoria porque `/` delimita a expressao; em Python ela e um escape
    invalido.
    """
    return js.replace(r'\/', '/')


def main():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    caminho = os.path.join(raiz, 'nexus.py')
    if not os.path.exists(caminho):
        print("nexus.py nao encontrado em %s" % raiz)
        return 2

    fonte = io.open(caminho, encoding='utf-8').read()

    print("=" * 74)
    print(" 1. LISTA DE TAGS PERMITIDAS")
    print("=" * 74)

    tags = extrair_conjunto(fonte, 'TAGS_PERMITIDAS')
    if tags is None:
        falha("TAGS_PERMITIDAS nao encontrada. A sanitizacao foi removida?")
        print()
        return 1

    intrusas = tags & TAGS_PROIBIDAS
    if intrusas:
        falha("tags perigosas na lista de permitidas: %s"
              % ', '.join(sorted(intrusas)))
    else:
        ok("%d tags permitidas, nenhuma perigosa" % len(tags))

    esperadas = {'B', 'STRONG', 'I', 'EM', 'P', 'UL', 'LI', 'A', 'BR'}
    faltando = esperadas - tags
    if faltando:
        aviso("formatacao basica ausente (o editor pode perder recursos): %s"
              % ', '.join(sorted(faltando)))
    else:
        ok("formatacao basica preservada (negrito, italico, listas, links)")

    print()
    print("=" * 74)
    print(" 2. LISTA DE ATRIBUTOS PERMITIDOS")
    print("=" * 74)

    attrs = extrair_conjunto(fonte, 'ATRIBUTOS_PERMITIDOS')
    if attrs is None:
        falha("ATRIBUTOS_PERMITIDOS nao encontrada")
    else:
        attrs_min = {a.lower() for a in attrs}
        intrusos = attrs_min & ATRIBUTOS_PROIBIDOS
        eventos = {a for a in attrs_min if a.startswith('on')}
        if intrusos or eventos:
            falha("atributos perigosos permitidos: %s"
                  % ', '.join(sorted(intrusos | eventos)))
        else:
            ok("%d atributos permitidos, nenhum perigoso" % len(attrs_min))

    print()
    print("=" * 74)
    print(" 3. MECANISMOS DE DEFESA NO CODIGO")
    print("=" * 74)

    checagens = [
        (r"nome\.startsWith\(\s*['\"]on['\"]\s*\)",
         "remocao de qualquer atributo on* (onclick, onerror, onload...)"),
        (r"createElement\(\s*['\"]template['\"]\s*\)",
         "parse via <template>: monta a arvore sem executar nada"),
        (r"createTreeWalker",
         "percorre todos os elementos, inclusive aninhados"),
        (r"nome\s*===\s*['\"]href['\"][^\n]*_urlSegura|_urlSegura\(attr\.value\)",
         "validacao de URL no atributo href"),
        (r"tagName\s*===\s*['\"]SCRIPT['\"]",
         "conteudo de <script> descartado, nao apenas a tag"),
        (r"Array\.from\(\s*no\.attributes\s*\)",
         "copia a lista de atributos antes de remover (evita pular elementos)"),
        (r"addEventListener\(\s*['\"]paste['\"]",
         "intercepta o colar"),
        (r"addEventListener\(\s*['\"]drop['\"]",
         "intercepta o arrastar-e-soltar"),
        (r"function\s+sanitizarHtml",
         "funcao sanitizarHtml definida"),
    ]
    for padrao, desc in checagens:
        if re.search(padrao, fonte):
            ok(desc)
        else:
            falha("AUSENTE: " + desc)

    print()
    print("=" * 74)
    print(" 4. PONTOS DE APLICACAO (todos os quatro sao necessarios)")
    print("=" * 74)

    pontos = [
        (r"insertHTML['\"]\s*,\s*false\s*,\s*sanitizarHtml\(html\)",
         "ao colar / arrastar — limpa antes de entrar no documento"),
        (r"noteEditorBody'\)\.innerHTML\s*=\s*\n?\s*sanitizarHtml",
         "ao abrir a nota — limpa notas antigas ja contaminadas"),
        (r"note\.content\s*=\s*sanitizarHtml",
         "ao salvar a nota — ultima barreira antes do disco e da nuvem"),
        (r"instalarSanitizacaoDoEditor\(\)",
         "instalacao dos interceptadores no boot"),
    ]
    for padrao, desc in pontos:
        if re.search(padrao, fonte):
            ok(desc)
        else:
            falha("AUSENTE: " + desc)

    print()
    print("=" * 74)
    print(" 5. TESTE EXECUTAVEL: validacao de URL (regex real do codigo)")
    print("=" * 74)

    m_limpa = re.search(
        r"replace\(\s*/\[([^\]]+)\]/g\s*,\s*''\s*\)", fonte)
    m_teste = re.search(
        r"return\s+/\^\((.*?)\)/i\.test\(limpo\)", fonte)

    if not (m_limpa and m_teste):
        falha("nao foi possivel extrair a regex de _urlSegura para testar")
    else:
        try:
            classe = traduzir_regex_js(m_limpa.group(1))
            alternativas = traduzir_regex_js(m_teste.group(1))
            re_limpa = re.compile('[' + classe + ']')
            re_teste = re.compile('^(' + alternativas + ')', re.I)

            def url_segura(v):
                return bool(re_teste.match(re_limpa.sub('', str(v))))

            falhou = 0
            for u in ESQUEMAS_PERIGOSOS:
                if url_segura(u):
                    falha("URL perigosa ACEITA: %r" % u)
                    falhou += 1
            if not falhou:
                ok("%d esquemas perigosos recusados (javascript:, data:, "
                   "file:, ms-msdt:, com tab/nulo/maiusculas)"
                   % len(ESQUEMAS_PERIGOSOS))

            falhou = 0
            for u in ESQUEMAS_LEGITIMOS:
                if not url_segura(u):
                    falha("URL legitima RECUSADA: %r" % u)
                    falhou += 1
            if not falhou:
                ok("%d esquemas legitimos aceitos (https, http, mailto, "
                   "ancora, relativo)" % len(ESQUEMAS_LEGITIMOS))
        except re.error as e:
            falha("regex extraida nao compila em Python: %s" % e)

    print()
    print("=" * 74)
    if problemas:
        print(" %d PROBLEMA(S) — NAO PUBLIQUE ANTES DE CORRIGIR" % len(problemas))
        for p in problemas:
            print("   x " + p)
    else:
        print(" POLITICA DE SANITIZACAO CORRETA")
        print(" Lembrete: isto audita a politica, nao executa o sanitizador.")
        print(" Para a verificacao completa (28 vetores), instale o Node:")
        print("   winget install OpenJS.NodeJS.LTS")
        print("   npm install jsdom")
        print("   node build_tools\\sanitizador_teste_completo_NODE.js")
    if avisos:
        print("\n %d aviso(s) nao bloqueante(s)." % len(avisos))
    print("=" * 74)

    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
