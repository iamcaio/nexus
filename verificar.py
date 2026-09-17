# -*- coding: utf-8 -*-
r"""
NEXUS — roda TODAS as verificacoes de uma vez.

Uso:
    cd C:\Dev\nexus
    python verificar.py

So Python. Nada a instalar.

------------------------------------------------------------------------------
POR QUE ESTE ARQUIVO EXISTE
------------------------------------------------------------------------------
Duas razoes praticas:

1. Quatro comandos separados viram tres comandos na pressa. Um comando so
   e o que voce vai realmente rodar antes de cada commit.

2. Uma classe de erro escapou DUAS vezes das verificacoes existentes: um byte
   nulo escrito dentro de um comentario, que faz o Python recusar o arquivo
   com "source code cannot contain null bytes". Os quatro verificadores nao
   olhavam para isso — eles auditavam o CONTEUDO dos arquivos, e nenhum
   verificava se os proprios arquivos eram carregaveis.

   A checagem 0 abaixo cobre isso. Ela e a primeira de proposito: se um script
   nem compila, o resultado dos outros nao significa nada.
------------------------------------------------------------------------------
"""
import collections
import io
import os

import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))

# Verificadores, na ordem em que fazem sentido rodar.
VERIFICADORES = [
    ("verificar_sanitizador.py", "politica anti-XSS do editor de notas"),
    ("validar_regras.py",        "gramatica e seguranca das regras do Firebase"),
    ("varrer_segredos.py",       "credenciais nos arquivos rastreados"),
    ("checar_buildps1.py",       "estrutura do build.ps1"),
]

# Bytes de controle aceitos em codigo-fonte: tab, LF, CR.
CONTROLE_OK = {9, 10, 13}

falhas = []


def cabecalho(txt):
    print()
    print("=" * 74)
    print(" " + txt)
    print("=" * 74)


def ok(msg):
    print("  OK     " + msg)


def falha(msg):
    print("  FALHA  " + msg)
    falhas.append(msg)


def aviso(msg):
    print("  aviso  " + msg)


def checar_integridade_dos_arquivos():
    """
    Checagem 0: os arquivos de texto do projeto sao carregaveis?

    Procura bytes de controle (que fazem o Python recusar o arquivo), BOM
    UTF-8 (que pode quebrar parsers como o do version_info.txt) e falha de
    compilacao. Se um verificador nao compila, o "OK" dos outros e ilusao.
    """
    cabecalho("0. INTEGRIDADE DOS ARQUIVOS DE TEXTO")

    alvos = []
    for pasta in (RAIZ, os.path.join(RAIZ, 'build_tools')):
        if not os.path.isdir(pasta):
            continue
        for nome in sorted(os.listdir(pasta)):
            if nome.endswith(('.py', '.ps1', '.iss', '.json', '.txt',
                              '.md', '.spec', '.js')):
                alvos.append(os.path.join(pasta, nome))

    problemas_locais = 0
    for caminho in alvos:
        rel = os.path.relpath(caminho, RAIZ)
        try:
            dados = open(caminho, 'rb').read()
        except OSError as e:
            print("  FALHA  %-46s ilegivel: %s" % (rel, e))
            problemas_locais += 1
            continue

        ruins = collections.Counter(
            b for b in dados if b < 32 and b not in CONTROLE_OK)
        if ruins:
            b, n = next(iter(ruins.items()))
            i = dados.find(bytes([b]))
            linha = dados[:i].count(b'\n') + 1
            print("  FALHA  %-46s byte 0x%02X na linha %d (%d no total)"
                  % (rel, b, linha, sum(ruins.values())))
            print("         %r" % dados[max(0, i - 45):i + 20])
            problemas_locais += 1
            continue

        if dados.startswith(b'\xef\xbb\xbf'):
            print("  aviso  %-46s tem BOM UTF-8" % rel)

        # ------------------------------------------------------------------
        # .ps1 SEM BOM precisa ser ASCII puro.
        # ------------------------------------------------------------------
        # O Windows PowerShell 5.1 (powershell.exe, o que vem no Windows) le
        # arquivos .ps1 sem BOM como ANSI/Windows-1252, nao como UTF-8.
        #
        # Um travessao U+2014 em UTF-8 e E2 80 94. Lido como 1252, vira tres
        # caracteres, e o ultimo (0x94) e U+201D — uma aspa dupla tipografica.
        # O PowerShell ACEITA aspas tipograficas como delimitador de string.
        #
        # Resultado: cada caractere acentuado no script vira uma aspa fantasma,
        # e o parser morre com "The string is missing the terminator" numa linha
        # que nao tem defeito nenhum. Foi exatamente o que aconteceu aqui.
        #
        # Duas saidas: gravar em UTF-8 COM BOM, ou manter o .ps1 em ASCII puro.
        # Escolhemos ASCII: funciona em qualquer PowerShell, qualquer locale,
        # qualquer editor, sem depender de um byte invisivel no inicio.
        if caminho.endswith('.ps1') and not dados.startswith(b'\xef\xbb\xbf'):
            fora = sorted({b for b in dados if b > 127})
            if fora:
                trecho = next((i for i, b in enumerate(dados) if b > 127), 0)
                linha_ = dados[:trecho].count(b'\n') + 1
                print("  FALHA  %-46s %d byte(s) nao-ASCII, 1o na linha %d"
                      % (rel, sum(1 for b in dados if b > 127), linha_))
                print("         O PowerShell 5.1 vai ler isso como Windows-1252")
                print("         e cada acento virara uma aspa fantasma.")
                print("         Troque por ASCII, ou grave o arquivo com BOM UTF-8.")
                problemas_locais += 1
                continue

        if caminho.endswith('.py'):
            # compile() embutido em vez de py_compile: valida a sintaxe sem
            # gravar .pyc em disco nenhum.
            try:
                compile(dados, caminho, 'exec')
            except (SyntaxError, ValueError) as e:
                print("  FALHA  %-46s nao compila" % rel)
                print("         %s: %s" % (type(e).__name__, str(e)[:100]))
                problemas_locais += 1
                continue

    if problemas_locais:
        falhas.append("%d arquivo(s) com problema de integridade"
                      % problemas_locais)
    else:
        print("  OK     %d arquivos: sem bytes de controle, todos os .py "
              "compilam" % len(alvos))


def rodar_verificadores():
    for i, (script, desc) in enumerate(VERIFICADORES, 1):
        caminho = os.path.join(RAIZ, 'build_tools', script)
        cabecalho("%d. %s" % (i, desc.upper()))

        if not os.path.exists(caminho):
            print("  FALHA  %s nao encontrado" % script)
            falhas.append("%s ausente" % script)
            continue

        r = subprocess.run([sys.executable, caminho],
                           capture_output=True, text=True, cwd=RAIZ)
        saida = (r.stdout or '') + (r.stderr or '')

        if r.returncode == 0:
            # Mostra so as linhas informativas, nao o relatorio inteiro.
            for l in saida.split('\n'):
                if any(m in l for m in ('OK ', 'aviso', 'ESPERADO',
                                        'Nenhum', 'presente:')):
                    print("  " + l.strip()[:100])
            print("  --> passou")
        else:
            for l in saida.split('\n'):
                if l.strip():
                    print("  " + l.rstrip()[:110])
            print("  --> FALHOU (codigo %d)" % r.returncode)
            falhas.append("%s: codigo %d" % (script, r.returncode))


def checar_notificacoes():
    """
    As notificacoes dependem de TRES lugares concordarem sobre o AUMID.

    Se eles divergirem, nada da erro: o toast simplesmente volta a aparecer
    assinado "Windows PowerShell", com o icone do PowerShell. E uma falha
    silenciosa e visualmente sutil - exatamente o tipo que passa batido.
    """
    import re
    cabecalho("6. NOTIFICACOES DO WINDOWS (AppUserModelID)")

    try:
        py = io.open(os.path.join(RAIZ, 'nexus.py'), encoding='utf-8').read()
        iss = io.open(os.path.join(RAIZ, 'nexus_installer.iss'),
                      encoding='utf-8').read()
    except OSError as e:
        aviso("nao foi possivel ler os arquivos: %s" % e)
        return

    m = re.search(r'APP_AUMID = "([^"]+)"', py)
    if not m:
        falha("APP_AUMID nao definido no nexus.py")
        return
    aumid = m.group(1)
    print("  AUMID: %s" % aumid)

    # Exige a CHAMADA completa, com a constante. Procurar so o nome da API
    # casaria com a mencao dela no comentario explicativo logo acima - e o
    # verificador aprovaria um arquivo onde a chamada real foi removida.
    if re.search(r'shell32\.SetCurrentProcessExplicitAppUserModelID\(\s*APP_AUMID\s*\)', py):
        ok("processo declara o AUMID")
    else:
        falha("AUSENTE: a chamada shell32.SetCurrentProcessExplicitAppUserModelID(APP_AUMID)")

    # `_registrar_identidade_windows\(\)` tambem casa com a linha do `def`,
    # porque 'def _registrar_identidade_windows():' contem '...()'. Sem exigir
    # a chamada dentro do main(), o verificador aprovaria um main() que nunca
    # registra o AUMID - e as notificacoes voltariam a sair como PowerShell.
    m_main = re.search(r'def main\(\):(.*?)(?=\nif __name__)', py, re.S)
    if m_main and re.search(r'^\s+_registrar_identidade_windows\(\)',
                            m_main.group(1), re.M):
        ok("registro chamado dentro do main()")
    else:
        falha("o main() nao chama _registrar_identidade_windows() - o AUMID "
              "nunca seria declarado e o toast sairia como PowerShell")

    if re.search(r'CreateToastNotifier\("\{APP_AUMID\}"\)', py):
        ok("o toast usa a constante, nao um literal solto")
    else:
        falha("o PowerShell do toast nao usa {APP_AUMID}")

    nos_atalhos = re.findall(r'AppUserModelID: "([^"]+)"', iss)
    if not nos_atalhos:
        falha("nenhum atalho do .iss tem AppUserModelID - sem isso o Windows "
              "recusa o AUMID e o toast sai como PowerShell")
    elif set(nos_atalhos) != {aumid}:
        falha("AUMID divergente: nexus.py=%r  .iss=%s" % (aumid, set(nos_atalhos)))
    else:
        ok("%d atalho(s) do instalador com o mesmo AUMID" % len(nos_atalhos))

    # o atalho do Menu Iniciar e o que conta; o da Area de Trabalho nao serve
    if re.search(r'\{autoprograms\}[^\n]*AppUserModelID', iss):
        ok("o atalho do Menu Iniciar carrega o AUMID (e o que o Windows exige)")
    else:
        falha("o atalho de {autoprograms} nao tem AppUserModelID - so o do "
              "Menu Iniciar registra o app para notificacoes")

    for padrao, desc in [
        (r'class WindowsNotifier', "classe WindowsNotifier"),
        (r'def send_desktop_notification', "metodo exposto ao JS"),
        (r'def update_taskbar_badge', "badge da barra de tarefas"),
        (r'notifiedTaskIds', "deduplicacao: nao repete a mesma tarefa"),
    ]:
        if re.search(padrao, py):
            ok(desc)
        else:
            falha("AUSENTE: " + desc)


def checar_versoes_alinhadas():
    """As tres versoes tem de ser a mesma, senao o release sai inconsistente."""
    cabecalho("5. VERSOES ALINHADAS")
    import re
    try:
        py = io.open(os.path.join(RAIZ, 'nexus.py'), encoding='utf-8').read()
        vi = io.open(os.path.join(RAIZ, 'version_info.txt'), encoding='utf-8').read()
        iss = io.open(os.path.join(RAIZ, 'nexus_installer.iss'), encoding='utf-8').read()
    except OSError as e:
        print("  aviso  nao foi possivel ler os arquivos de versao: %s" % e)
        return

    def pega(txt, padrao):
        m = re.search(padrao, txt)
        return m.group(1) if m else None

    achados = {
        'nexus.py APP_VERSION': pega(py, r'APP_VERSION = "v([\d.]+)"'),
        'nexus.py badge':       pega(py, r'>v([\d.]+)</button>'),
        'version_info.txt':     pega(vi, r"FileVersion', '([\d.]+)\.0'"),
        'nexus_installer.iss':  pega(iss, r'MyAppVersion\s+"([\d.]+)"'),
    }
    for k, v in achados.items():
        print("  %-24s %s" % (k, v or "NAO ENCONTRADA"))

    distintas = {v for v in achados.values() if v}
    if len(distintas) == 1 and None not in achados.values():
        print("  OK     todas em %s" % distintas.pop())
    else:
        print("  FALHA  versoes divergentes — rode: .\\build.ps1 -Version X.Y.Z -OnlyVersion")
        falhas.append("versoes divergentes")


def main():
    print()
    print("#" * 74)
    print("#  NEXUS — verificacao completa")
    print("#  pasta: %s" % RAIZ)
    print("#" * 74)

    checar_integridade_dos_arquivos()
    rodar_verificadores()
    checar_notificacoes()
    checar_versoes_alinhadas()

    print()
    print("=" * 74)
    if falhas:
        print(" %d PROBLEMA(S) — NAO COMMITE NEM PUBLIQUE" % len(falhas))
        for f in falhas:
            print("   x " + f)
    else:
        print(" TUDO OK")
        print()
        print(" Lembretes do que isto NAO cobre:")
        print("   - nao executa o sanitizador de verdade (precisa de Node)")
        print("   - nao testa o app rodando: abra o NEXUS.exe e confirme")
        print("     'TLS verificado' no painel de atualizacao")
        print("   - nao verifica se o instalador foi publicado no Releases")
    print("=" * 74)
    print()
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
