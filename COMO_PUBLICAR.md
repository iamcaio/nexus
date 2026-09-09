# NEXUS — segurança, build e publicação

Guia único. Siga na ordem. As Partes 0 e 1 são obrigatórias antes do primeiro
`git push` — depois dele, alguns erros não têm desfazer.

---

## Sumário

- [Parte 0 — Onde a pasta deve morar](#parte-0--onde-a-pasta-deve-morar)
- [Parte 1 — Blindagem antes do GitHub](#parte-1--blindagem-antes-do-github)
- [Parte 2 — Estado de segurança](#parte-2--estado-de-segurança)
- [Parte 3 — Firebase](#parte-3--firebase)
- [Parte 4 — Gerar o build](#parte-4--gerar-o-build)
- [Parte 5 — Publicar](#parte-5--publicar)
- [Parte 6 — O ciclo de atualização](#parte-6--o-ciclo-de-atualização)
- [Parte 7 — Como o usuário instala](#parte-7--como-o-usuário-instala)
- [Parte 8 — Limites conhecidos](#parte-8--limites-conhecidos)
- [Solução de problemas](#solução-de-problemas)

---

## Parte 0 — Onde a pasta deve morar

### O problema de hoje

`C:\NEXUS` contém, na mesma árvore:

| O quê | Onde | Deve ir para o GitHub? |
|---|---|---|
| Código-fonte | `nexus.py`, `build.ps1`, `*.iss` | **Sim** |
| **Seus dados pessoais** | `db\` — tarefas, notas, sessão | **Nunca** |
| Artefatos de build | `build\`, `dist\` (45 MB) | Não |
| Instaladores | `dist_installer\` (13 MB) | Releases, não repo |

Código e dados no mesmo lugar é o que cria o risco: o passo natural
("subir para o GitHub") passa a incluir seu banco pessoal.

### A recomendação

**Separe em duas pastas:**

```
C:\Dev\nexus          <- codigo. Vai para o GitHub.
C:\NEXUS\db           <- dados. Nunca sai da maquina.
```

Por que `C:\Dev\nexus` e não `Documentos`:

- **Fora do OneDrive.** Se sua pasta de usuário sincroniza, o OneDrive tentaria
  subir os 45 MB de `build\` e `dist\` a cada compilação — milhares de arquivos
  pequenos, e ele mantém handles abertos durante o upload. Isso causa
  exatamente o erro "file is being used by another process" que você já viu.
- **Caminho curto.** O PyInstaller gera caminhos profundos dentro de
  `build\`. Partindo de `C:\Users\<usuario>\Documents\Projetos\...`, você chega
  perto do limite de 260 caracteres do Windows, e os erros que isso produz são
  confusos.
- **Sem admin.** `C:\Dev` você cria e escreve sem elevação.

`C:\NEXUS\db` fica onde está. O `nexus.py` já aponta para lá, seus dados já
foram migrados do doNext, e mexer de novo no caminho dos dados é a mudança de
maior risco que existe neste projeto. Não churn sem motivo.

### Como mover (5 minutos)

```powershell
# 1. Feche o NEXUS.exe e qualquer editor com arquivos do projeto abertos.

# 2. Cria o destino
New-Item -ItemType Directory -Force -Path C:\Dev\nexus | Out-Null

# 3. Copia SO o codigo. Note os /XD: dados e artefatos ficam para tras.
robocopy C:\NEXUS C:\Dev\nexus /E /XD db build dist dist_installer __pycache__ .git

# 4. Confere que o banco NAO veio junto
Test-Path C:\Dev\nexus\db        # tem de responder False
Get-ChildItem C:\Dev\nexus

# 5. Testa o build no lugar novo
cd C:\Dev\nexus
.\build.ps1 -Version 6.1.0 -SkipInstaller
.\dist\NEXUS\NEXUS.exe           # suas tarefas continuam la, vindas de C:\NEXUS\db
```

Só depois que o app abrir com seus dados, apague o código antigo de `C:\NEXUS`
(mantendo `db\`):

```powershell
Get-ChildItem C:\NEXUS -Exclude db | Remove-Item -Recurse -Force
```

---

## Parte 1 — Blindagem antes do GitHub

### 1.1 Confirme o `.gitignore`

Já está no projeto. Ele bloqueia `db/`, `build/`, `dist/`, `dist_installer/`,
`__pycache__/` e qualquer `*.exe`. **Não remova essas linhas.**

O arquivo mais crítico é `db\cloud_session.json`. Ele contém um `refreshToken`
do Firebase: 204 caracteres que se trocam por credencial de acesso
indefinidamente. Quem tiver esse token lê e escreve nas suas tarefas — não
precisa da sua senha.

### 1.2 Inicialize o repositório com verificação

```powershell
cd C:\Dev\nexus
git init
git add .
```

#### Sobre o aviso `LF will be replaced by CRLF`

Você vai ver esse aviso em todos os arquivos de texto. **Não é erro e nada
quebrou.** É o Git for Windows avisando que vai converter fim de linha: LF no
repositório, CRLF no seu disco.

O `.gitattributes` deste projeto resolve isso de vez, colocando a regra dentro
do repositório em vez de depender da configuração de cada máquina. Sem ele, um
clone noutro computador com configuração diferente gera um commit que "mudou
5264 linhas" sem ninguém ter editado nada — e o histórico vira inútil para
revisão.

Se você já rodou `git add .` antes de ter o `.gitattributes`, renormalize:

```powershell
git add --renormalize .
```

#### Verificações antes de commitar

**Pare aqui.** Três checagens, em ordem de importância:

```powershell
# 1. Nada de db/, dist/, build/ pode aparecer nesta lista
git status --short

# 2. Confirmacao explicita dos arquivos sensiveis
git check-ignore -v db/cloud_session.json
git check-ignore -v db/tasks_db.json

# 3. Varredura de credenciais no conteudo dos arquivos
python build_tools\varrer_segredos.py
```

A terceira é a que o `.gitignore` **não** cobre. Ele impede que a pasta `db/`
entre no repositório, mas não protege contra uma credencial colada dentro de um
arquivo de código — que é como a maioria dos vazamentos reais acontece. O
script varre 13 padrões (tokens do Firebase, PATs do GitHub, chaves AWS, chaves
privadas PEM, strings de conexão com senha) e sai com código 1 se achar algo
crítico.

Ele deve reportar **um** achado esperado: a `apiKey` do Firebase no `nexus.py`.
Essa é pública por design — quem protege os dados são as Regras.

Se `git status` mostrar qualquer coisa de `db/`, **não commite**. Rode
`git rm -r --cached db` e reveja o `.gitignore`.

#### Não escreva dados pessoais nos arquivos do repositório

Seu e-mail, num repositório público, vira alvo de coleta automatizada para spam
e phishing. Use `seu@email.com` como exemplo na documentação. O
`varrer_segredos.py` sinaliza endereços de e-mail como "REVISAR" justamente
para você não deixar passar.

### 1.3 Identidade do git — e por que o e-mail importa

Na primeira vez, o git recusa o commit com "Author identity unknown". Ele
precisa de um nome e um e-mail, que ficam **gravados dentro de cada commit,
para sempre**.

Num repositório público, esse e-mail é lido por qualquer pessoa e por robôs de
coleta. E ele entra no hash do commit: trocar depois exige reescrever o
histórico, o que não desfaz o que já foi clonado ou indexado. **É uma escolha
de uma vez só.**

#### Não use o e-mail do trabalho

Este é um projeto pessoal. Um e-mail corporativo num repositório público
associa a empresa ao projeto, vira alvo de spam e phishing dirigido, e continua
lá depois que você trocar de emprego.

#### Use o endereço `noreply` do GitHub

O GitHub fornece um endereço que encaminha para você sem revelar o e-mail real.

1. GitHub → Settings → Emails
2. Marque **Keep my email addresses private**
3. Copie o endereço mostrado, no formato
   `12345678+seu-usuario@users.noreply.github.com`
4. Marque também **Block command line pushes that expose my email** — é a rede
   de proteção para o dia em que você esquecer de configurar num computador novo

Depois:

```powershell
# Identidade so para ESTE repositorio (sem --global).
# Assim seus outros projetos, inclusive os do trabalho, nao sao afetados.
git config user.name "Seu Nome"
git config user.email "12345678+seu-usuario@users.noreply.github.com"

# Confira antes de commitar
git config user.email
```

Use `--global` apenas se quiser esse mesmo e-mail como padrão em todos os
repositórios da máquina. Para quem mistura projetos pessoais e de trabalho no
mesmo computador, configurar por repositório é mais seguro.

### 1.4 Commit e push

```powershell
git commit -m "NEXUS 6.1.0 - correcoes de seguranca"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/nexus.git
git push -u origin main
```

Logo após o push, **abra o repositório no navegador e procure a pasta `db`.**
Confiar no `.gitignore` sem olhar é o erro clássico.

### 1.5 Público ou privado?

| | Privado | Público |
|---|---|---|
| Releases funcionam | Só com token na URL | Sim, URL direta |
| Auto-updater funciona | Exige embutir token no app (**não faça**) | Sim |
| Seu código fica visível | Não | Sim |

**Recomendação: repositório público.** Não porque seja mais seguro, mas porque
a alternativa é pior: um repo privado obriga a embutir um Personal Access Token
no executável para o updater baixar — e um token dentro de um `.exe`
distribuído é um token vazado, só que com passos extras.

Seu código não contém segredo. A `apiKey` do Firebase é pública por design; o
que protege os dados são as Regras. Se preferir manter o código fechado, use
outro host para os binários (Cloudflare R2, S3) e deixe o repo privado sem
Releases.

### 1.6 Se você já commitou o `db/` por engano

Apagar o arquivo **não resolve** — o git guarda o blob no histórico para
sempre.

1. **Rotacione a credencial imediatamente:** Firebase Console → Authentication →
   selecione o usuário → Redefinir senha. Isso invalida todos os refresh tokens
   existentes.
2. Se o repo era público, considere-o comprometido. O caminho limpo é apagar o
   repositório e criar outro — reescrever histórico com `git filter-repo` não
   remove o que já foi clonado ou indexado.

---

## Parte 2 — Estado de segurança

Uma auditoria de segurança foi feita em 8 de setembro de 2026. Quatro
correções entraram no código:

| Área | O que passou a valer |
|---|---|
| TLS | Verificação de certificado obrigatória. Login e atualização recusam conexão não verificada em vez de degradar. |
| Abertura de arquivos | 30 extensões executáveis bloqueadas; esquemas de URL perigosos recusados. |
| Editor de notas | Sanitização de HTML por lista de permissão, em quatro pontos. 28 testes automatizados. |
| Dependências | CSP adicionada; versões de bibliotecas fixadas. |

Rode as verificações a qualquer momento:

```powershell
node build_tools\testar_sanitizador.js    # 28 testes de XSS
python build_tools\validar_regras.py      # regras do Firebase
python build_tools\varrer_segredos.py     # credenciais antes do commit
```

> O detalhamento das falhas — como eram exploráveis e o que continua em aberto
> — fica em `SEGURANCA.md`, **fora deste repositório**. Publicar esse detalhe
> serviria de atalho para atacar instalações não atualizadas, e não traz
> benefício nenhum para quem só quer usar ou compilar o app.

## Parte 3 — Firebase

### 3.1 Publique as Regras

```powershell
python build_tools\validar_regras.py
```

O script valida a **gramática** das regras, não só se é JSON — são coisas
diferentes, e essa diferença já causou um erro aqui. Ele também confere quatro
invariantes de segurança, entre elas a mais importante: que `.read` e `.write`
exijam `auth.uid == $uid`. Um `auth != null` no lugar disso salva sem erro
nenhum no console e **libera os dados de todos para todos**.

Passando, cole o `firebase-rules.json` em Console → Realtime Database → Regras
→ Publicar.

| Caminho | Regra | Motivo |
|---|---|---|
| `database` | autenticado | Onde o Cogni grava. Preservado. |
| `apps/nexus/_release` | `.read: true` | O app checa versão antes do login. Contém só número de versão, URL pública e hash. Sem `.write`: só o console escreve. |
| `apps/nexus/users/$uid` | `auth.uid == $uid` | O que impede o usuário A de ler os dados do B. |
| `apps/donext/users/$uid` | leitura sim, `.write: false` | A migração precisa ler. Virou backup imutável. |
| `apps/cogni/users/$uid` | `auth.uid == $uid` | Mesmo isolamento. |

### 3.2 Armadilha das regras do RTDB

Qualquer chave que **não comece com ponto** é tratada como nó filho, e o valor
precisa ser um objeto. As únicas chaves com ponto válidas são `.read`,
`.write`, `.validate` e `.indexOn`.

Isto é JSON válido e regra **inválida**:

```json
"database": {
  "//": "meu comentário",
  ".read": "auth != null"
}
```

O console responde `Line 4: Expected '{'`. Para comentar, use `//` de linha ou
documente aqui.

### 3.3 A `apiKey` é pública — e o que realmente fazer a respeito

A `apiKey` do Firebase aparece em texto claro no `nexus.py`, e vai para o
GitHub. Isso é correto e esperado, mas a frase "pública por design" costuma ser
usada como se significasse "não há nada a fazer". Não é o caso.

**Ela já é pública, independentemente do GitHub.** Ela está embutida no
executável que você distribui, e sai de lá em segundos:

```python
import zlib, re
d = open(r'dist\NEXUS\NEXUS.exe','rb').read()
for m in re.finditer(rb'\x78[\x01\x9c\xda]', d):
    try: bruto = zlib.decompressobj().decompress(d[m.start():m.start()+400000])
    except Exception: continue
    achado = re.search(rb'AIza[A-Za-z0-9_\-]{35}', bruto)
    if achado: print(achado.group(0).decode()); break
```

Além disso, ela viaja na URL de toda chamada de autenticação — qualquer um com
o app instalado a vê com um proxy de rede. **Publicar no GitHub não muda em
nada a exposição dela.** Esconder seria teatro.

**O que a chave permite, mesmo com as Regras corretas.** As Regras protegem os
*dados*, não a *superfície de autenticação*. Com a `apiKey`, um estranho pode:

- criar contas no seu projeto Firebase, quantas quiser, se o cadastro estiver
  aberto — enche sua lista de usuários e consome cota;
- sondar quais e-mails existem no seu projeto (enumeração), útil para phishing
  direcionado contra seus usuários;
- disparar e-mails de redefinição de senha para endereços do seu projeto.

O que ela **não** permite: ler ou escrever dados de qualquer usuário. Isso é
barrado por `auth.uid == $uid` nas Regras.

**Três ações, 10 minutos, em ordem de retorno:**

**1. Desative a criação de contas** (se você e um grupo fechado são os únicos
usuários). Firebase Console → Authentication → Settings → *User actions* →
desmarque a criação de contas por usuários finais. Tentativas passam a receber
`auth/admin-restricted-operation`.

> Isso desativa o botão "Criar conta" do NEXUS. Novos usuários passam a ser
> cadastrados por você, no Console → Authentication → Add user. Para um app
> pessoal ou de time pequeno, é a troca certa. Se pretende abrir para o
> público, pule este item.

**2. Confirme a proteção contra enumeração de e-mail.** Mesma tela, *User
actions* → *Email enumeration protection*. Projetos criados a partir de
setembro de 2023 já vêm com ela ligada; confirme que ninguém desligou.

**3. Restrinja a chave às APIs que ela precisa.** Google Cloud Console → APIs e
Serviços → Credenciais → sua chave → *Restrições de API* → *Restringir chave* →
marque apenas **Identity Toolkit API** e **Token Service API**.

Assim, se a chave for reaproveitada em outro lugar, ela não abre nenhuma outra
API do Google cobrada no seu projeto.

> As restrições de *aplicativo* (referenciador HTTP, endereço IP, app Android
> ou iOS) não servem para um app desktop: não há referenciador, e restringir
> por IP quebraria para qualquer usuário que troque de rede. Restrição de API é
> a que funciona no seu caso.

**4. Ligue alertas de faturamento** no Google Cloud Console → Faturamento →
Orçamentos e alertas. É a rede de proteção para o caso de alguém abusar dos
endpoints de autenticação — você fica sabendo em horas, não na fatura.

### 3.4 Troque o e-mail da conta (opcional)

Se sua conta ainda usa um e-mail com o domínio antigo, isso é uma identidade no
Firebase Auth, não uma string no código. Console → Authentication → selecione o
usuário → editar e-mail. O UID permanece, então **os dados continuam intactos**.

> Não escreva seu e-mail real neste arquivo. Ele vai para um repositório
> público e vira alvo de coleta automatizada para spam e phishing.

---

## Parte 4 — Gerar o build

### 4.1 Pré-requisitos

```powershell
pip install pyinstaller pywebview certifi
winget install JRSoftware.InnoSetup
```

`certifi` **não é opcional**. Sem ele o app não valida certificado e bloqueia
login e atualização de propósito, em vez de aceitar conexão não verificada.

### 4.2 Compile

```powershell
cd C:\Dev\nexus
.\build.ps1 -Version 6.1.0 -Notes "Correcoes de seguranca: TLS verificado, XSS sanitizado, execucao de arquivos bloqueada"
```

O script sincroniza a versão em três arquivos, compila, empacota, calcula o
SHA-256 e imprime o manifesto pronto. Ele é idempotente: rodar duas vezes com a
mesma versão não grava nada em disco.

Flags úteis:

| Flag | Para quê |
|---|---|
| `-SkipInstaller` | Só o `.exe`, sem empacotar |
| `-OnlyInstaller` | Reaproveita o `dist\NEXUS` já compilado |
| `-OnlyVersion` | Só sincroniza a versão |
| `-BaseUrl` | Sua URL real, para não editar o manifesto à mão |

### 4.3 Verifique antes de publicar

```powershell
node build_tools\testar_sanitizador.js    # 28 testes de XSS
python build_tools\validar_regras.py      # regras do Firebase
python build_tools\checar_buildps1.py     # estrutura do build.ps1
```

Abra o app e confirme, no painel de atualização, que aparece **"TLS
verificado"**. Se aparecer "TLS SEM VERIFICACAO", o `certifi` não foi
empacotado — o `build.ps1` avisa se `cacert.pem` não estiver no build.

---

## Parte 5 — Publicar

**A ordem importa.** Inverter os passos 2 e 3 faz todo usuário ver uma
atualização que falha ao baixar.

### Passo 1 — Suba o instalador no Releases (não no repositório)

GitHub → Releases → Create a new release → tag `v6.1.0` → anexe
`dist_installer\NEXUS-Setup-6.1.0.exe` → Publish.

Binários vão para Releases, nunca para o repositório: o git nunca esquece
blobs, e alguns releases depois o histórico fica permanentemente inflado.

### Passo 2 — Teste a URL

Copie o endereço do arquivo anexado e **abra no navegador**. Se não baixar,
pare aqui. Confira também o hash:

```powershell
(Get-FileHash .\dist_installer\NEXUS-Setup-6.1.0.exe -Algorithm SHA256).Hash.ToLower()
```

Tem de ser idêntico ao `sha256` do manifesto.

### Passo 3 — Só então, o manifesto no Firebase

Console → Realtime Database → `/apps/nexus/_release/stable` → cole o JSON que o
`build.ps1` imprimiu, com a URL real:

```json
{
  "version": "6.1.0",
  "kind": "installer",
  "url": "https://github.com/SEU-USUARIO/nexus/releases/download/v6.1.0/NEXUS-Setup-6.1.0.exe",
  "sha256": "<o hash de 64 caracteres>",
  "size": 13025079,
  "notes": "Correcoes de seguranca",
  "mandatory": false
}
```

---

## Parte 6 — O ciclo de atualização

Depois da primeira vez, publicar uma versão nova é:

```powershell
# 1. Edite o nexus.py
# 2. Um comando:
.\build.ps1 -Version 6.1.1 -Notes "- Corrigido X" -BaseUrl "https://github.com/SEU-USUARIO/nexus/releases/download"
# 3. Suba o .exe no Releases com a tag v6.1.1
# 4. Cole o JSON no Firebase
```

Do lado do usuário: em até 6 horas, ou ao reabrir o app, aparece um selo azul
no cabeçalho. Ele clica, vê o changelog, clica em "Baixar e instalar", e o
NEXUS fecha e reabre atualizado. Nenhum comando.

### Nunca diminua o número da versão

O updater compara versões **numericamente**: só oferece atualização se a
publicada for maior que a instalada. Isso é o comportamento correto — evita que
um manifesto errado empurre uma versão antiga para todo mundo.

A consequência: se você publicou `6.0.4` e depois compila `3.0.1`, quem já tem
a `6.0.4` **nunca receberá a `3.0.1`**. O app dirá "está atualizado", porque
está — pela regra numérica. E o seu próprio teste de atualização vai parecer
que "não funciona", quando na verdade funcionou exatamente como deveria.

Se você precisa renumerar para baixo, o caminho é:

1. Decida o novo esquema e **nunca mais volte atrás**.
2. Quem já instalou a versão maior precisa reinstalar manualmente, baixando o
   instalador. Não há atalho.
3. Avise essas pessoas antes de publicar o manifesto novo.

Na prática: escolha o número agora e só avance. `6.1.0`, `6.1.1`, `6.2.0`.

### Testar antes de liberar para todos

Troque `UPDATE_CHANNEL = "stable"` para `"beta"` na sua cópia, publique o
manifesto em `/apps/nexus/_release/beta` e valide. Depois copie para `stable`.

### Segurança da atualização

Um auto-updater é, por definição, um canal de execução remota de código. Este
tem cinco travas:

1. Manifesto lido por HTTPS **com verificação de certificado**.
2. Download por HTTPS **com verificação**, sem fallback. Sem TLS verificável,
   a atualização é abortada.
3. O arquivo só é executado se o **SHA-256 bater**. Sem hash no manifesto, o
   app se recusa a instalar.
4. URL não-HTTPS no manifesto → bloqueado.
5. Limite de 400 MB.

**Não remova a verificação de hash para "simplificar".** Sem ela, quem
controlar o manifesto controla o que roda na máquina de todos os seus usuários.

---

## Parte 7 — Como o usuário instala

Mande o `NEXUS-Setup-6.1.0.exe`. Duplo clique, Avançar, Instalar.

- Não pede senha de administrador (instala em `%LOCALAPPDATA%\Programs\NEXUS`)
- Cria atalho no Menu Iniciar e na Área de Trabalho
- Aparece em "Aplicativos instalados", com desinstalador

**SmartScreen.** Na primeira vez o Windows mostra "aplicativo não reconhecido",
porque o instalador não tem assinatura digital. O usuário clica em "Mais
informações" → "Executar assim mesmo".

---

## Parte 8 — Limites conhecidos

Este projeto tem limitações de segurança conhecidas e documentadas. Elas estão
descritas em `SEGURANCA.md`, mantido fora do repositório.

O ponto que afeta diretamente quem instala: **o instalador não tem assinatura
digital de código.** O Windows exibe o aviso do SmartScreen na primeira
execução, e não há como verificar criptograficamente que o arquivo veio do
autor. Baixe apenas da página oficial de Releases e confira o SHA-256 publicado
no manifesto.

## Solução de problemas

### `Set-Content : The process cannot access the file`

1. Feche o arquivo em qualquer editor ou visualizador.
2. Feche o `NEXUS.exe`, principalmente se estiver rodando de dentro de `dist\`.
3. Rode de novo — o script é idempotente.
4. Persistindo, adicione a pasta do projeto às exclusões do Windows Defender.

O script nomeia os processos suspeitos em execução quando falha.

### `ISCC.exe nao encontrado`

O Inno Setup 6 não está instalado. O `.exe` **já foi gerado** — teste com
`.\dist\NEXUS\NEXUS.exe`. Depois:

```powershell
winget install JRSoftware.InnoSetup
# feche e reabra o PowerShell
.\build.ps1 -Version 6.1.0 -OnlyInstaller
```

O script procura o ISCC no PATH, no registro do Windows, no Program Files
(32 e 64 bits) e em instalações por usuário. **Inno Setup 5 não serve** — o
`.iss` usa diretivas exclusivas da 6.

### O executável abre e fecha na hora

```powershell
pyinstaller --noconfirm --clean --console nexus.spec
.\dist\NEXUS\NEXUS.exe
```

### "TLS SEM VERIFICACAO — atualizacao bloqueada"

O `certifi` não foi empacotado. `pip install certifi` e recompile.

### "Uma conexão de dados foi feita sem verificar o certificado"

Alguém ou alguma coisa está no meio da sua conexão. Causas comuns, em ordem:

1. Antivírus com inspeção HTTPS (Kaspersky, Avast, ESET)
2. Proxy corporativo
3. Data e hora do computador erradas
4. Rede hostil — se estiver em Wi-Fi público, **saia e não faça login**

Login e atualização não são afetados: eles recusam e falham, em vez de
degradar.

### Sem permissão no Firebase (401 / 403)

As Regras não foram publicadas, ou foram publicadas erradas. Rode
`python build_tools\validar_regras.py` e republique.

---

## Arquivos do projeto

| Arquivo | Para quê |
|---|---|
| `nexus.py` | O aplicativo. É este que você edita. |
| `nexus.spec` | Config do PyInstaller. Inclui `certifi`. |
| `version_info.txt` | Metadados do exe. Reduz falso-positivo de antivírus. |
| `nexus_installer.iss` | Script do instalador. |
| `build.ps1` | Gera tudo com um comando. |
| `firebase-rules.json` | Regras do Realtime Database. |
| `.gitignore` | **Impede o vazamento do `db/`. Não edite.** |
| `.gitattributes` | Fim de linha determinístico entre máquinas. |
| `nexus.ico` | Ícone. |
| `build_tools\varrer_segredos.py` | **Procura credenciais antes do commit.** |
| `build_tools\validar_regras.py` | Valida gramática e segurança das regras. |
| `build_tools\checar_buildps1.py` | Checagem estrutural do `build.ps1`. |
| `build_tools\testar_sanitizador.js` | 28 testes de XSS no editor de notas. |
