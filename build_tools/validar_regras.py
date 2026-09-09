# -*- coding: utf-8 -*-
"""
Valida firebase-rules.json contra a GRAMATICA das regras do Realtime Database.

Por que este script existe: json.load() aceitava o arquivo anterior sem
reclamar, porque ele ERA JSON valido. Mas nao era uma REGRA valida. As duas
coisas nao sao a mesma, e foi exatamente essa diferenca que passou batida.

Regra fundamental do RTDB: qualquer chave que NAO comece com "." e um caminho
filho, e o valor dela TEM de ser um objeto. Chave ".algo" e uma diretiva, e o
valor e string ou booleano.
"""
import json
import sys

DIRETIVAS_EXPRESSAO = {".read", ".write", ".validate"}
DIRETIVAS_OUTRAS = {".indexOn"}
DIRETIVAS = DIRETIVAS_EXPRESSAO | DIRETIVAS_OUTRAS

erros = []
avisos = []


def checar(no, caminho="rules"):
    if not isinstance(no, dict):
        erros.append(f"{caminho}: esperado objeto, encontrado "
                     f"{type(no).__name__}")
        return

    for chave, valor in no.items():
        aqui = f"{caminho}/{chave}"

        if chave.startswith("."):
            if chave not in DIRETIVAS:
                erros.append(f"{aqui}: diretiva desconhecida. "
                             f"Validas: {sorted(DIRETIVAS)}")
                continue
            if chave in DIRETIVAS_EXPRESSAO:
                if not isinstance(valor, (str, bool)):
                    erros.append(f"{aqui}: deve ser string ou booleano, "
                                 f"nao {type(valor).__name__}")
            elif chave == ".indexOn":
                if not isinstance(valor, (str, list)):
                    erros.append(f"{aqui}: deve ser string ou lista")
            continue

        # ---- Chave sem ponto = caminho filho. Valor OBRIGATORIAMENTE objeto.
        if not isinstance(valor, dict):
            erros.append(
                f"{aqui}: e interpretado como NO FILHO, portanto o valor "
                f"precisa ser um objeto '{{...}}'. Encontrado "
                f"{type(valor).__name__}. "
                + ("Chaves de comentario como \"//\" NAO existem em regras "
                   "do RTDB — use comentarios de linha // fora do JSON, ou "
                   "documente em outro arquivo."
                   if chave.strip("/ ") == "" or chave.startswith("//")
                   else "Este e o erro 'Expected {' do console.")
            )
            continue

        if chave.startswith("$"):
            if len(chave) < 2:
                erros.append(f"{aqui}: variavel de caminho precisa de nome")
        checar(valor, aqui)


def main():
    caminho = "firebase-rules.json"
    try:
        with open(caminho, encoding="utf-8") as f:
            bruto = f.read()
    except OSError as e:
        print("Nao foi possivel ler o arquivo:", e)
        return 2

    if "//" in bruto and '"//"' in bruto:
        avisos.append('O arquivo contem uma chave "//". O RTDB nao suporta '
                      'chaves de comentario.')

    try:
        doc = json.loads(bruto)
    except json.JSONDecodeError as e:
        print(f"JSON invalido na linha {e.lineno}: {e.msg}")
        return 2

    if "rules" not in doc:
        erros.append("raiz: falta a chave 'rules'")
    elif len(doc) != 1:
        erros.append(f"raiz: deve conter APENAS 'rules'. "
                     f"Encontrado: {sorted(doc)}")
    else:
        checar(doc["rules"])

    # ---------------------------------------------- checagens de intencao
    try:
        apps = doc["rules"]["apps"]
        nexus = apps["nexus"]

        if nexus["_release"].get(".read") is not True:
            erros.append("apps/nexus/_release/.read deve ser true: o app "
                         "checa a versao ANTES do login.")
        if ".write" in nexus["_release"]:
            avisos.append("apps/nexus/_release tem .write. Sem ele, so o "
                          "console escreve — que e o desejado.")

        for ramo in ("nexus", "cogni"):
            r = apps[ramo]["users"]["$uid"]
            for d in (".read", ".write"):
                if "auth.uid == $uid" not in str(r.get(d, "")):
                    erros.append(f"apps/{ramo}/users/$uid{d}: sem "
                                 f"'auth.uid == $uid' um usuario le/escreve "
                                 f"dados de outro.")

        leg = apps["donext"]["users"]["$uid"]
        if leg.get(".write") is not False:
            erros.append("apps/donext/users/$uid/.write deveria ser false: "
                         "o ramo legado e backup imutavel.")
        if "auth.uid == $uid" not in str(leg.get(".read", "")):
            erros.append("apps/donext/users/$uid/.read: a migracao precisa "
                         "de leitura, mas so do proprio UID.")

        db = doc["rules"]["database"]
        if not db.get(".read") or not db.get(".write"):
            avisos.append("rules/database perdeu .read/.write — isso pode "
                          "quebrar o Cogni.")
    except (KeyError, TypeError) as e:
        erros.append(f"estrutura esperada ausente: {e}")

    print("=" * 68)
    if erros:
        print("ERROS (%d) — o console do Firebase vai recusar:" % len(erros))
        for e in erros:
            print("  x", e)
    else:
        print("GRAMATICA: valida. O console aceita este arquivo.")
        print("INTENCAO : isolamento por UID, _release publico, legado")
        print("           somente-leitura, ramo do Cogni preservado.")
    if avisos:
        print("\nAVISOS (%d):" % len(avisos))
        for a in avisos:
            print("  !", a)
    print("=" * 68)
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
