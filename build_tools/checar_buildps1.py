# -*- coding: utf-8 -*-
"""
Checagem estrutural do build.ps1 sem executar PowerShell.

Nao substitui rodar no Windows. Pega a classe de erro que mais aparece:
balanceamento, param() fora de posicao, funcao usada antes de existir e
anti-padroes conhecidos (BOM, catch tipado).

IMPORTANTE: as verificacoes de anti-padrao olham APENAS codigo executavel.
Comentarios que EXPLICAM um anti-padrao nao sao o anti-padrao.
"""
import io
import re
import sys


def tirar_comentarios(texto):
    """Remove blocos <# #>, comentarios de linha e o conteudo de strings."""
    t = re.sub(r'<#.*?#>', '', texto, flags=re.S)
    saida = []
    for linha in t.splitlines():
        fora = []
        aspas = None
        i = 0
        while i < len(linha):
            c = linha[i]
            if aspas is None and c == '#':
                break                      # comentario ate o fim da linha
            if aspas is None and c in '"\'':
                aspas = c
            elif aspas == c:
                aspas = None
            fora.append(c)
            i += 1
        saida.append("".join(fora))
    return "\n".join(saida)


def main():
    caminho = "build.ps1"
    s = io.open(caminho, encoding="utf-8").read()
    codigo = tirar_comentarios(s)
    prob = []

    # ------------------------------------------------ 1. balanceamento
    sem_str = re.sub(r'"(?:[^"`]|`.)*"', '""', codigo)
    sem_str = re.sub(r"'[^']*'", "''", sem_str)
    for ab, fe, nome in (('{', '}', 'chaves'),
                         ('(', ')', 'parenteses'),
                         ('[', ']', 'colchetes')):
        a, f = sem_str.count(ab), sem_str.count(fe)
        print("  %-11s abre=%-4d fecha=%-4d %s"
              % (nome, a, f, "OK" if a == f else "DESBALANCEADO"))
        if a != f:
            prob.append("%s desbalanceados (%d abre / %d fecha)" % (nome, a, f))

    # --------------------------------------- 2. param() no lugar certo
    limpo = re.sub(r'(?m)^\s*#.*$', '', s).strip()
    if limpo.startswith("param("):
        print("  param()     primeiro statement executavel: OK")
    else:
        prob.append("param() precisa ser o primeiro statement. Encontrado: %r"
                    % limpo[:60])

    # ------------------------- 3. funcoes definidas antes do uso
    defs = {m.group(1): m.start()
            for m in re.finditer(r'^function ([\w-]+)', s, re.M)}
    print("  funcoes     %s" % ", ".join(sorted(defs)))
    for nome, pos in defs.items():
        usos = [m.start() for m in
                re.finditer(r'(?<![\w-])%s(?![\w-])' % re.escape(nome), codigo)]
        # posicoes em `codigo` nao batem com `s`; usamos ordem relativa
        pos_codigo = codigo.find("function " + nome)
        antes = [u for u in usos if pos_codigo >= 0 and u < pos_codigo]
        if antes:
            prob.append("%s e chamada antes de ser definida" % nome)

    # ------------------------------- 4. variaveis criticas
    for var in ("$Utf8SemBom",):
        d = codigo.find(var + " =")
        u = codigo.find(var)
        if d < 0:
            prob.append("%s nunca definida" % var)
        elif u < d:
            prob.append("%s usada antes de ser definida" % var)
        else:
            print("  %s definida antes do uso: OK" % var)

    # --------------------------- 5. anti-padroes (somente em codigo)
    checks = [
        (r'Set-Content[^\n]*-Encoding\s+UTF8',
         "Set-Content -Encoding UTF8 escreve BOM no PowerShell 5.1"),
        (r'catch\s*\[\s*System\.IO\.IOException\s*\]',
         "catch tipado nao captura com $ErrorActionPreference = Stop"),
        (r'Out-File[^\n]*-Encoding\s+UTF8',
         "Out-File -Encoding UTF8 tambem escreve BOM no PS 5.1"),
    ]
    for padrao, msg in checks:
        if re.search(padrao, codigo):
            prob.append(msg)
    if not any(re.search(p, codigo) for p, _ in checks):
        print("  anti-padroes de gravacao/BOM: nenhum em codigo executavel")

    # --------------------------- 6. positivos obrigatorios
    obrigatorios = [
        (r'WriteAllText', "gravacao via [System.IO.File]::WriteAllText"),
        (r'UTF8Encoding\(\$false\)', "encoding UTF-8 sem BOM"),
        (r'Move-Item[^\n]*-Force', "substituicao atomica via Move-Item"),
        (r'Start-Sleep', "retry com espera"),
        (r'-ceq', "comparacao sensivel a caso para detectar mudanca real"),
    ]
    for padrao, desc in obrigatorios:
        if re.search(padrao, codigo):
            print("  presente: %s" % desc)
        else:
            prob.append("AUSENTE: %s" % desc)

    print("\n" + "=" * 68)
    if prob:
        print("PROBLEMAS (%d):" % len(prob))
        for p in prob:
            print("  x", p)
    else:
        print("Nenhum problema estrutural. Gravacao sem BOM, atomica e com retry.")
    print("=" * 68)
    return 1 if prob else 0


if __name__ == "__main__":
    sys.exit(main())
