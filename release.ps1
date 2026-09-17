# ===========================================================================
#  NEXUS - publicar uma versao, de ponta a ponta
# ===========================================================================
#  Uso:
#     .\release.ps1 -Version 6.1.2 -Notes "- Corrigido X`n- Adicionado Y"
#     .\release.ps1 -Version 6.1.2 -DryRun     (mostra o que faria, sem fazer)
#
#  Faz, nesta ordem, e para em qualquer erro:
#     1. Sincroniza a versao nos tres arquivos e compila (build.ps1)
#     2. Roda verificar.py - aborta se algo falhar
#     3. Commita com mensagem DERIVADA do codigo, nao digitada
#     4. Cria a tag vX.Y.Z
#     5. Faz push do commit e da tag
#     6. Cria o Release no GitHub e sobe o instalador (se o gh existir)
#     7. Gera o manifesto com a URL real, pronto para colar no Firebase
# ===========================================================================
#
#  POR QUE ESTE SCRIPT EXISTE
#
#  Uma versao vive em SEIS lugares: nexus.py, version_info.txt, o .iss, a
#  mensagem do commit, a tag do git e o manifesto do Firebase. Mantendo isso a
#  mao, eles divergem - e divergiram:
#
#     commit "NEXUS 6.1.1"  ->  continha codigo 6.1.0
#     commit "NEXUS 6.0.2"  ->  continha codigo 6.1.0
#
#  Nada disso quebra o app. Quebra a sua capacidade de responder "que codigo
#  esta rodando na maquina do usuario?" - que e a pergunta que importa quando
#  aparece um bug.
#
#  A defesa aqui: a mensagem do commit e a tag sao LIDAS do nexus.py depois do
#  build. Elas nao podem mentir, porque nao sao digitadas.
# ===========================================================================

param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Notes = "",
    [string]$Repo = "iamcaio/nexus",
    [switch]$DryRun,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Etapa($n, $txt) { Write-Host "`n[$n/7] $txt" -ForegroundColor Cyan }
function Detalhe($txt)   { Write-Host "      $txt" -ForegroundColor DarkGray }
function Aviso($txt)     { Write-Host "      $txt" -ForegroundColor Yellow }
function Executar($cmd) {
    if ($DryRun) { Write-Host "      [dry-run] $cmd" -ForegroundColor Magenta; return }
    Write-Host "      > $cmd" -ForegroundColor DarkGray
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) { throw "Falhou: $cmd" }
}

if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Versao deve ser X.Y.Z. Recebido: '$Version'"
}
if ($DryRun) {
    Write-Host "`n*** MODO DRY-RUN - nada sera alterado ***" -ForegroundColor Magenta
}

# ---------------------------------------------------------------------------
#  0. A versao nao pode ser menor que a ultima publicada
# ---------------------------------------------------------------------------
$tags = @(git tag -l "v*" 2>$null)
if ($tags.Count -gt 0) {
    $maior = $tags |
        ForEach-Object { [version]($_ -replace '^v', '') } |
        Sort-Object -Descending |
        Select-Object -First 1
    if ([version]$Version -le $maior) {
        Write-Host ""
        Write-Host "  A versao $Version nao e maior que a ultima tag (v$maior)." -ForegroundColor Red
        Write-Host ""
        Write-Host "  O updater compara numericamente: quem tem v$maior instalada" -ForegroundColor Yellow
        Write-Host "  NUNCA receberia a $Version. O app diria 'esta atualizado' -" -ForegroundColor Yellow
        Write-Host "  corretamente - e o seu teste pareceria quebrado." -ForegroundColor Yellow
        Write-Host ""
        throw "Use uma versao maior que $maior."
    }
    Detalhe "ultima tag: v$maior -> publicando $Version"
} else {
    Aviso "nenhuma tag local encontrada. Se voce criou releases pela interface"
    Aviso "do GitHub, rode 'git fetch --tags' antes para esta checagem valer."
}

# ---------------------------------------------------------------------------
#  1. BUILD
# ---------------------------------------------------------------------------
Etapa 1 "Sincronizando versao e compilando"
if ($SkipBuild) {
    Detalhe "-SkipBuild: reaproveitando o build existente"
} else {
    $argsBuild = "-Version $Version -BaseUrl `"https://github.com/$Repo/releases/download`""
    if ($Notes) { $argsBuild += " -Notes `"$Notes`"" }
    Executar ".\build.ps1 $argsBuild"
}

# ---------------------------------------------------------------------------
#  2. VERIFICAR - a versao real vem daqui, nao do parametro
# ---------------------------------------------------------------------------
Etapa 2 "Verificacoes"
if (-not $DryRun) {
    python verificar.py
    if ($LASTEXITCODE -ne 0) {
        throw "verificar.py falhou. Corrija antes de publicar."
    }
}

# Le a versao DO CODIGO. Se divergir do parametro, algo deu errado no build.
$py = Get-Content -Raw -Encoding UTF8 "nexus.py"
if ($py -match 'APP_VERSION = "v([\d.]+)"') {
    $versaoReal = $Matches[1]
} else {
    throw "Nao foi possivel ler APP_VERSION do nexus.py."
}
if ($versaoReal -ne $Version -and -not $DryRun) {
    throw "O codigo diz $versaoReal mas voce pediu $Version. O build nao aplicou a versao."
}
Detalhe "versao confirmada no codigo: $versaoReal"

# ---------------------------------------------------------------------------
#  3. COMMIT - mensagem derivada, nunca digitada
# ---------------------------------------------------------------------------
Etapa 3 "Commit"
$msg = "NEXUS $versaoReal"
if ($Notes) {
    $primeira = ($Notes -split "`n")[0].Trim().TrimStart('-', ' ')
    if ($primeira) { $msg += " - $primeira" }
}
Detalhe "mensagem: $msg"

Executar "git add -A ."
$pendente = git diff --cached --name-only
if (-not $pendente -and -not $DryRun) {
    Aviso "nada para commitar - o codigo ja esta commitado nesta versao"
} else {
    Executar "git commit -m `"$msg`""
}

# ---------------------------------------------------------------------------
#  4. TAG
# ---------------------------------------------------------------------------
Etapa 4 "Tag v$versaoReal"
$existe = git tag -l "v$versaoReal"
if ($existe) {
    throw "A tag v$versaoReal ja existe. Escolha outra versao - reutilizar tag " +
          "faz o Release apontar para codigo diferente do que ele diz conter."
}
Executar "git tag -a v$versaoReal -m `"$msg`""

# ---------------------------------------------------------------------------
#  5. PUSH
# ---------------------------------------------------------------------------
Etapa 5 "Enviando para o GitHub"
Executar "git push origin main"
Executar "git push origin v$versaoReal"

# ---------------------------------------------------------------------------
#  6. RELEASE + UPLOAD DO INSTALADOR
# ---------------------------------------------------------------------------
Etapa 6 "Release no GitHub"
$setup = "dist_installer\NEXUS-Setup-$versaoReal.exe"

if (-not (Test-Path $setup)) {
    Aviso "instalador nao encontrado em $setup"
    Aviso "rode sem -SkipBuild, ou suba o arquivo manualmente."
} else {
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if ($gh) {
        $notasRelease = if ($Notes) { $Notes } else { "Versao $versaoReal" }
        Executar "gh release create v$versaoReal `"$setup`" --title `"NEXUS $versaoReal`" --notes `"$notasRelease`""
        Detalhe "instalador publicado no Releases"
    } else {
        Aviso "GitHub CLI (gh) nao instalado - upload manual necessario:"
        Aviso "  1. https://github.com/$Repo/releases/new?tag=v$versaoReal"
        Aviso "  2. anexe $setup"
        Aviso "  3. Publish release"
        Aviso ""
        Aviso "Para automatizar nas proximas vezes: winget install GitHub.cli"
    }
}

# ---------------------------------------------------------------------------
#  7. MANIFESTO
# ---------------------------------------------------------------------------
Etapa 7 "Manifesto para o Firebase"

$manifesto = "dist_installer\manifest-$versaoReal.json"
if (Test-Path $manifesto) {
    $conteudo = Get-Content -Raw $manifesto
    if ($conteudo -match 'SEU-USUARIO') {
        Aviso "o manifesto tem placeholder na URL - corrigindo para $Repo"
        $conteudo = $conteudo -replace 'SEU-USUARIO/nexus', $Repo
        if (-not $DryRun) {
            [System.IO.File]::WriteAllText(
                (Join-Path $PSScriptRoot $manifesto), $conteudo,
                (New-Object System.Text.UTF8Encoding($false)))
        }
    }
    Write-Host ""
    Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host " COLE EM /apps/nexus/_release/stable  (console do Firebase)" -ForegroundColor Yellow
    Write-Host "=======================================================" -ForegroundColor Yellow
    Write-Host $conteudo
    Write-Host "=======================================================" -ForegroundColor Yellow
} else {
    Aviso "manifesto nao encontrado em $manifesto"
}

Write-Host ""
Write-Host "Codigo, tag e instalador publicados como $versaoReal." -ForegroundColor Green
Write-Host ""
Write-Host "FALTA UM PASSO, E ELE E MANUAL DE PROPOSITO:" -ForegroundColor White
Write-Host "  Colar o manifesto acima no console do Firebase." -ForegroundColor White
Write-Host ""
Write-Host "As Regras nao dao .write ao no _release, entao nenhum token pode" -ForegroundColor DarkGray
Write-Host "gravar ali - nem este script. Esse no decide qual arquivo sera" -ForegroundColor DarkGray
Write-Host "baixado e EXECUTADO na maquina dos seus usuarios; se um token" -ForegroundColor DarkGray
Write-Host "pudesse alterar, roubar o token bastaria para comprometer todos." -ForegroundColor DarkGray
Write-Host ""
Write-Host "Antes de colar, confirme que a URL do manifesto baixa o arquivo." -ForegroundColor White
