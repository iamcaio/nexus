# -*- coding: utf-8 -*-
"""
NEXUS — varredura de segredos nos arquivos rastreados pelo git.

Uso:
    cd C:\\Dev\\nexus
    python build_tools\\varrer_segredos.py

Rode ANTES de todo `git commit`. O .gitignore impede que a pasta db\\ entre no
repositorio, mas ele nao protege contra uma credencial colada dentro de um
arquivo de codigo — que e como a maioria dos vazamentos reais acontece.

Codigo de saida: 0 se limpo, 1 se encontrou algo critico.
"""
import os
import re
import subprocess
import sys

# (nome, padrao, severidade)
#   CRITICO  -> nunca pode ir para o repositorio
#   REVISAR  -> pode ser legitimo; olhe caso a caso
#   ESPERADO -> sabemos que esta la e tudo bem
PADROES = [
    ("refreshToken do Firebase", rb'AMf-v[A-Za-z0-9_\-]{40,}', 'CRITICO'),
    ("idToken JWT", rb'eyJ[A-Za-z0-9_\-]{20,}\.eyJ[A-Za-z0-9_\-]{20,}', 'CRITICO'),
    ("GitHub Personal Access Token", rb'gh[pousr]_[A-Za-z0-9]{36}', 'CRITICO'),
    ("GitHub fine-grained token", rb'github_pat_[A-Za-z0-9_]{50,}', 'CRITICO'),
    ("AWS Access Key", rb'AKIA[0-9A-Z]{16}', 'CRITICO'),
    ("Chave privada (PEM)", rb'-----BEGIN [A-Z ]*PRIVATE KEY-----', 'CRITICO'),
    ("Slack token", rb'xox[baprs]-[A-Za-z0-9\-]{10,}', 'CRITICO'),
    ("Google OAuth client secret", rb'GOCSPX-[A-Za-z0-9_\-]{20,}', 'CRITICO'),
    ("Service account JSON", rb'"type"\s*:\s*"service_account"', 'CRITICO'),
    ("String de conexao com senha", rb'(?i)(mongodb|postgres|mysql|redis)://[^:\s]+:[^@\s]+@', 'CRITICO'),

    ("senha atribuida no codigo",
     rb'(?i)(password|senha|passwd|pwd)\s*[:=]\s*["\'][^"\'\s]{6,}["\']', 'REVISAR'),
    ("secret/private key atribuido",
     rb'(?i)(secret|api_?secret|private_?key|auth_?token)\s*[:=]\s*["\'][^"\'\s]{12,}["\']', 'REVISAR'),
    ("endereco de e-mail", rb'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.(com|br|org|net|io)', 'REVISAR'),

    ("Firebase apiKey (publica por design)", rb'AIza[A-Za-z0-9_\-]{35}', 'ESPERADO'),
]

# ---------------------------------------------------------------------------
# LISTA DE ACEITOS
# ---------------------------------------------------------------------------
# Um alerta que dispara toda vez deixa de ser alerta: voce aprende a ignorar a
# saida inteira e, no dia em que aparecer algo real, passa batido. Por isso o
# que e comprovadamente inofensivo entra aqui, com o motivo escrito.
#
# Criterio para entrar nesta lista: o valor precisa ser publico POR DESIGN ou
# um placeholder evidente. Na duvida, NAO adicione — prefira revisar de novo.
# ---------------------------------------------------------------------------
ACEITOS = {
    # Placeholders da documentacao e da interface
    b'seu@email.com',        # campo de exemplo no formulario de login
    b'a@b.com',              # dado de teste do sanitizador
    b'exemplo.com',
    b'you@example.com',      # exemplo que o proprio git sugere
    b'seu-usuario',
    b'SEU-USUARIO',
    b'<usuario>',

    # Endereco noreply do GitHub. Ele existe justamente PARA ser publico: e o
    # mecanismo oficial de esconder o e-mail real nos commits. Revela apenas o
    # ID e o nome de usuario do GitHub — ambos ja visiveis na URL do
    # repositorio. Sinalizar isso seria alarme falso permanente.
    b'users.noreply.github.com',
}

# Marcadores de placeholder. Se o trecho contiver um destes, e exemplo de
# documentacao, nao valor real.
#
# ATENCAO — REGRA QUE NAO PODE SER RELAXADA:
# Estes marcadores SO se aplicam a achados de severidade REVISAR e ESPERADO.
# NUNCA a CRITICO.
#
# Motivo: um token real e uma sequencia aleatoria em base64. Nada impede que
# um refreshToken legitimo contenha "xxxx" ou "12345678" por puro acaso — e
# se isso acontecesse, o filtro esconderia a credencial de verdade.
#
# A assimetria e deliberada. Falso positivo num CRITICO custa 10 segundos de
# conferencia. Falso negativo custa a credencial. Diante da duvida, o script
# mostra.
MARCADORES_PLACEHOLDER = (
    b'seu-usuario', b'SEU-USUARIO', b'seu_usuario', b'<usuario>', b'<user>',
    b'example.com', b'exemplo.com', b'YOUR_', b'SEU_',
    b'cole-aqui', b'placeholder', b'changeme', b'CHANGEME',
)


def eh_binario(dados):
    return b'\x00' in dados[:8000]


def main():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(raiz)

    try:
        r = subprocess.run(['git', 'ls-files'], capture_output=True, text=True)
        if r.returncode != 0:
            print("Nao e um repositorio git (ou o git nao esta no PATH).")
            return 2
        arquivos = [a for a in r.stdout.split('\n') if a.strip()]
    except FileNotFoundError:
        print("git nao encontrado no PATH.")
        return 2

    print("Varrendo %d arquivo(s) rastreado(s) em %s\n" % (len(arquivos), raiz))

    achados = {}
    for f in arquivos:
        if not os.path.exists(f):
            continue
        try:
            dados = open(f, 'rb').read()
        except OSError:
            continue
        if eh_binario(dados):
            continue
        for nome, pat, sev in PADROES:
            for m in re.finditer(pat, dados):
                trecho = m.group(0)
                # Filtros de ruido: aplicados apenas fora do nivel CRITICO.
                # Ver o comentario em MARCADORES_PLACEHOLDER — esconder um
                # achado critico por heuristica e o unico erro caro aqui.
                if sev != 'CRITICO':
                    if any(a in trecho for a in ACEITOS):
                        continue
                    if any(p in trecho for p in MARCADORES_PLACEHOLDER):
                        continue
                linha = dados[:m.start()].count(b'\n') + 1
                achados.setdefault((sev, nome), []).append(
                    (f, linha, trecho[:52].decode('utf-8', 'replace')))

    ordem = {'CRITICO': 0, 'REVISAR': 1, 'ESPERADO': 2}
    if not achados:
        print("  Nenhum padrao encontrado.")

    for chave in sorted(achados, key=lambda k: ordem[k[0]]):
        sev, nome = chave
        itens = achados[chave]
        print("[%s] %s — %d ocorrencia(s)" % (sev, nome, len(itens)))
        vistos = set()
        for f, l, t in itens:
            if (f, t) in vistos:
                continue
            vistos.add((f, t))
            print("    %s:%d  %s" % (f, l, t))
            if len(vistos) >= 8:
                print("    ...")
                break
        print()

    criticos = sum(len(v) for k, v in achados.items() if k[0] == 'CRITICO')
    revisar = sum(len(v) for k, v in achados.items() if k[0] == 'REVISAR')

    print("=" * 70)
    if criticos:
        print("  %d SEGREDO(S) CRITICO(S) — NAO COMMITE" % criticos)
        print("  Remova do arquivo E rotacione a credencial: se ela ja existiu,")
        print("  trate como comprometida.")
    else:
        print("  Nenhum segredo critico.")
    if revisar:
        print("  %d item(ns) para revisar manualmente acima." % revisar)
    print("=" * 70)

    return 1 if criticos else 0


if __name__ == "__main__":
    sys.exit(main())
