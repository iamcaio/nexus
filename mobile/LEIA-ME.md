# NEXUS Mobile — PWA

Versão para celular do NEXUS. **Só Tarefas** — o Vault fica no computador, por
decisão de segurança.

Não é uma cópia dos seus dados. É o **mesmo** nó do Firebase que o desktop usa:
`/apps/nexus/users/<uid>/database`. Você entra com a mesma conta e vê as
mesmas tarefas, na hora.

---

## Antes de qualquer coisa

```powershell
cd C:\Dev\nexus
python build_tools\verificar_mobile.py
```

Ele confere que os dois apps apontam para o mesmo banco, que o modelo de dados
bate, e — o item que mais importa — que a proteção do Vault está no lugar.

**Por que essa proteção existe.** O celular não mostra o Vault. Se ele enviasse
um estado sem o campo `notepad`, o `PUT` no Realtime Database **substitui o nó
inteiro** e suas 30 notas sumiriam da nuvem. O desktop, ao sincronizar,
adotaria o estado sem elas. Em todos os aparelhos, sem mensagem de erro.

O código tem duas travas contra isso: o mobile reinsere o `notepad` vindo da
nuvem antes de todo envio, e aborta se detectar que o Vault sumiria.

---

## 1. Gerar os ícones

```powershell
cd C:\Dev\nexus\mobile
pip install Pillow
python gerar_icones.py
```

Usa o `nexus.ico` do desktop, para o app ficar igual nos dois lugares. Sem
Pillow, o script explica a alternativa.

## 2. Testar no computador

```powershell
python C:\Dev\nexus\mobile\servir.py
```

Só isso. O navegador abre sozinho já no app — sem listagem de diretório, sem
clicar em `mobile/`.

O `servir.py` faz o que o `python -m http.server` não faz:

- serve a pasta `mobile\` como raiz
- desliga o cache do navegador, para você não editar um arquivo e continuar
  vendo o antigo
- manda o `Content-Type` correto do `.webmanifest` — sem isso o Chrome ignora
  o manifest e o app não fica instalável
- mostra o IP da sua rede, para abrir no celular

**Abrir o `index.html` com duplo clique não funciona.** `file://` bloqueia
service worker e `fetch`.

Pelo IP você testa interface e login no celular, mas **não** a instalação nem o
offline: service worker exige `https://` ou `localhost`. Para isso, publique.

## 3. Publicar

### Configuração (uma vez só)

GitHub → **Settings → Pages → Source: "GitHub Actions"**.

O workflow `.github/workflows/publicar-mobile.yml` já está no repositório.

### A cada versão nova

```powershell
cd C:\Dev\nexus
.\publicar-mobile.ps1 -Notas "Icone novo no cabecalho"
```

Ele sobe a versão em `app.js` e `sw.js`, roda o verificador, confere os
ícones, commita e faz push. O GitHub Actions publica em 1–2 minutos em
`https://iamcaio.github.io/nexus/`.

Para ver o que faria sem alterar nada: `.\publicar-mobile.ps1 -DryRun`

**O workflow recusa o deploy se:** a compatibilidade desktop/mobile quebrar,
faltar algum ícone, ou você mudar arquivos sem trocar o `VERSAO_CACHE`. Esse
último é o erro clássico de PWA — o celular serviria o cache antigo e pareceria
que o deploy falhou.

### Alternativa: Firebase Hosting

Se preferir o mesmo domínio do banco:

```powershell
npm install -g firebase-tools
firebase login
cd C:\Dev\nexus
firebase init hosting     # pasta publica: mobile    | SPA: nao
firebase deploy --only hosting
```

Sai `https://cogni-data.web.app`. Funciona bem, mas aí você perde as
verificações automáticas do workflow — teria de lembrar de rodá-las.

## 4. Instalar no celular

Abra a URL no navegador do celular.

- **Android/Chrome:** aparece "Instalar app", ou menu ⋮ → *Adicionar à tela
  inicial*
- **iPhone/Safari:** botão Compartilhar → *Adicionar à Tela de Início*
  (no iPhone só funciona pelo Safari — é limitação da Apple, não do app)

Depois de instalado abre em tela cheia, sem barra de navegador, com ícone
próprio.

---

## Como atualizar o mobile

1. Edite os arquivos em `mobile\`
2. `.\publicar-mobile.ps1 -Notas "o que mudou"`

O script cuida da versão nos dois arquivos. Você não precisa lembrar.

### No celular, depois do deploy

| O que mudou | O que fazer |
|---|---|
| Código: telas, regras, correções | Feche e reabra o app. Confira o selo no topo. |
| **O ícone do app** | **Desinstale e instale de novo.** |

**Por que o ícone exige reinstalar.** O Android grava o ícone no momento da
instalação e não o atualiza quando o manifest muda. Não há como forçar pelo
código — é comportamento do sistema, não limitação deste app.

Seus dados não se perdem ao desinstalar: eles estão no Firebase, não no
aparelho.

Se o app instalou com uma **letra genérica** em vez do cubo, foi porque os
ícones não estavam disponíveis na hora da instalação. O Android então gera um
ícone com a inicial do nome. Publique com os ícones presentes e reinstale.

---

## O que o mobile faz

| Recurso | Estado |
|---|---|
| Ver e filtrar tarefas (Meu Dia, Planejadas, Todas) | sim |
| Filtrar por categoria e projeto | sim |
| Criar, editar, concluir e excluir tarefas | sim |
| Prioridade, data limite, Meu Dia, progresso | sim |
| Etapas (checklist): criar, marcar, remover | sim |
| Anotações da tarefa | sim |
| Funcionar sem internet e enviar depois | sim |
| Criar categorias e projetos | não — use o computador |
| Anexos | mostra a contagem; abrir só no computador |
| Vault | **não**, por decisão de segurança |
| Kanban e gráficos | não |

## Funcionamento offline

Salva na hora no aparelho e envia quando houver rede. O selo no topo mostra:

| Selo | Significado |
|---|---|
| Atualizado | em dia com a nuvem |
| Salvando / Pendente | gravado no aparelho, aguardando envio |
| Offline | sem rede; nada se perde |
| Conflito | nuvem e aparelho divergem muito — nada foi sobrescrito |
| Sessão | token expirou; entre de novo |

**Sobre "Conflito":** acontece quando a nuvem está mais nova mas com muito
menos conteúdo. Em vez de adotar, o app para e avisa. Perder dado por
sincronização automática é pior do que ficar desatualizado por uma hora.
Resolva no computador, com o painel da nuvem.

---

## Primeiro login: faça assim

1. Feche o NEXUS no computador
2. Entre no celular e confira que suas tarefas aparecem
3. Mude uma coisa pequena no celular (marque uma etapa)
4. Abra o desktop e confirme que a mudança chegou
5. **Confira o Vault no desktop** — as notas têm de estar todas lá

O passo 5 é o que valida a proteção mais importante. Faça uma vez, com
atenção.

---

## Limites conhecidos

**iPhone.** O Safari apaga dados de sites não usados por ~7 dias. Se o app
ficar semanas sem abrir, o cache local some — os dados na nuvem continuam
intactos, mas ele precisa baixar tudo de novo. Instalar na tela de início
reduz o problema, não elimina.

**Sem notificações push.** Exige um servidor de push e chaves VAPID. Não foi
implementado.

**Sem biometria.** Quem abrir o celular desbloqueado tem acesso às suas
tarefas. Foi um dos motivos para o Vault ficar de fora.

**O `localStorage` tem limite de ~5 MB.** Suficiente para milhares de tarefas,
mas se você tiver muitos anexos em base64 no banco, o cache local pode falhar.
O app continua funcionando online.

---

## Arquivos

| Arquivo | Para quê |
|---|---|
| `index.html` | Estrutura e CSP |
| `styles.css` | Estilos. Sem Tailwind, sem CDN. |
| `nexus-sync.js` | Firebase em JS puro — substitui a camada Python |
| `app.js` | Interface e regras de tarefa |
| `sw.js` | Service worker: cache do app, **nunca** dos dados |
| `manifest.webmanifest` | Torna instalável |
| `gerar_icones.py` | Gera os PNGs a partir do `nexus.ico` |
| `servir.py` | Servidor local de teste |
| `icons/icon.svg` | Fonte vetorial do ícone |

Fora desta pasta:

| Arquivo | Para quê |
|---|---|
| `..\publicar-mobile.ps1` | Sobe versão, verifica, commita e publica |
| `..\build_tools\verificar_mobile.py` | Compatibilidade desktop/mobile |
| `..\.github\workflows\publicar-mobile.yml` | Deploy automático no Pages |
