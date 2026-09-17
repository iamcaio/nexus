# ===========================================================================
#  NEXUS Mobile - publicar uma versao nova
# ===========================================================================
#  Uso:
#     .\publicar-mobile.ps1
#     .\publicar-mobile.ps1 -Notas "Icone novo no cabecalho"
#     .\publicar-mobile.ps1 -DryRun          (mostra o que faria)
#     .\publicar-mobile.ps1 -Versao 1.2.0    (define a versao em vez de +1)
#
#  Faz, nesta ordem, parando em qualquer erro:
#     1. Sobe a versao em app.js e sw.js
#     2. Roda verificar_mobile.py
#     3. Commita e faz push
#     4. O GitHub Actions publica sozinho
# ===========================================================================
#
#  POR QUE ESTE SCRIPT EXISTE
#
#  Publicar um PWA e so copiar arquivos. O que da errado nao e o deploy - e
#  esquecer de trocar o VERSAO_CACHE no sw.js.
#
#  Quando isso acontece, o service worker instalado no celular continua
#  servindo os arquivos ANTIGOS do cache. Voce publica, abre o app, nada mudou,
#  e conclui que o deploy falhou. Ele nao falhou; o cache venceu.
#
#  Aqui a versao sobe automaticamente nos dois arquivos. Voce nao tem como
#  esquecer, porque nao precisa lembrar.
# ===========================================================================

param(
    [string]$Versao = "",
    [string]$Notas = "",
    [string]$Repo = "iamcaio/nexus",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Utf8SemBom = New-Object System.Text.UTF8Encoding($false)

function Etapa($n, $txt) { Write-Host "`n[$n/4] $txt" -ForegroundColor Cyan }
function Detalhe($txt)   { Write-Host "      $txt" -ForegroundColor DarkGray }
function Aviso($txt)     { Write-Host "      $txt" -ForegroundColor Yellow }

function Executar($cmd) {
    if ($DryRun) { Write-Host "      [dry-run] $cmd" -ForegroundColor Magenta; return }
    Write-Host "      > $cmd" -ForegroundColor DarkGray
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) { throw "Falhou: $cmd" }
}

function GravarSemBom($caminho, $conteudo) {
    if ($DryRun) { return }
    [System.IO.File]::WriteAllText(
        (Resolve-Path -LiteralPath $caminho).Path, $conteudo, $Utf8SemBom)
}

if (-not (Test-Path "mobile\app.js")) {
    throw "mobile\app.js nao encontrado. Rode este script de dentro de C:\Dev\nexus."
}
if ($DryRun) {
    Write-Host "`n*** MODO DRY-RUN - nada sera alterado ***" -ForegroundColor Magenta
}

# ---------------------------------------------------------------------------
#  1. VERSAO
# ---------------------------------------------------------------------------
Etapa 1 "Versao"

$appJs = Get-Content -Raw -Encoding UTF8 "mobile\app.js"
if ($appJs -notmatch "const VERSAO = '([\d.]+)';") {
    throw "Nao achei 'const VERSAO' em mobile\app.js."
}
$atual = $Matches[1]

if ($Versao) {
    if ($Versao -notmatch '^\d+\.\d+\.\d+$') { throw "Versao deve ser X.Y.Z." }
    $nova = $Versao
    if ([version]$nova -le [version]$atual) {
        throw "A versao $nova nao e maior que a atual ($atual)."
    }
} else {
    # Incrementa o ultimo numero: 1.0.1 -> 1.0.2
    $p = $atual.Split('.')
    $nova = "$($p[0]).$($p[1]).$([int]$p[2] + 1)"
}
Detalhe "$atual -> $nova"

$appJs = $appJs -replace "const VERSAO = '[\d.]+';", "const VERSAO = '$nova';"
GravarSemBom "mobile\app.js" $appJs

$swJs = Get-Content -Raw -Encoding UTF8 "mobile\sw.js"
if ($swJs -notmatch "VERSAO_CACHE = 'nexus-mobile-v[\d.]+';") {
    throw "Nao achei VERSAO_CACHE em mobile\sw.js."
}
$swJs = $swJs -replace "VERSAO_CACHE = 'nexus-mobile-v[\d.]+';",
                       "VERSAO_CACHE = 'nexus-mobile-v$nova';"
GravarSemBom "mobile\sw.js" $swJs

Detalhe "app.js e sw.js sincronizados em $nova"

# ---------------------------------------------------------------------------
#  2. VERIFICAR
# ---------------------------------------------------------------------------
Etapa 2 "Verificacoes"

if (-not $DryRun) {
    python build_tools\verificar_mobile.py
    if ($LASTEXITCODE -ne 0) {
        throw "verificar_mobile.py falhou. Corrija antes de publicar."
    }
} else {
    Detalhe "[dry-run] python build_tools\verificar_mobile.py"
}

$faltando = @()
foreach ($i in @('icon-192.png', 'icon-512.png', 'icon-maskable-512.png')) {
    if (-not (Test-Path "mobile\icons\$i")) { $faltando += $i }
}
if ($faltando.Count -gt 0) {
    Write-Host ""
    Write-Host "  Icones faltando: $($faltando -join ', ')" -ForegroundColor Red
    Write-Host "  Sem eles o Android instala o app com uma letra generica." -ForegroundColor Yellow
    Write-Host "  Rode:  cd mobile ; python gerar_icones.py" -ForegroundColor Yellow
    throw "Gere os icones antes de publicar."
}
Detalhe "os tres icones estao presentes"

# ---------------------------------------------------------------------------
#  3. COMMIT E PUSH
# ---------------------------------------------------------------------------
Etapa 3 "Enviando para o GitHub"

$msg = "NEXUS Mobile $nova"
if ($Notas) { $msg += " - $Notas" }
Detalhe "mensagem: $msg"

Executar "git add -A mobile .github publicar-mobile.ps1 build_tools"

$pendente = git diff --cached --name-only
if (-not $pendente -and -not $DryRun) {
    Aviso "nada mudou desde o ultimo commit"
} else {
    Executar "git commit -m `"$msg`""
    Executar "git push origin main"
}

# ---------------------------------------------------------------------------
#  4. PUBLICACAO
# ---------------------------------------------------------------------------
Etapa 4 "Publicacao"

$temWorkflow = Test-Path ".github\workflows\publicar-mobile.yml"
if ($temWorkflow) {
    Detalhe "o GitHub Actions assume daqui - leva 1 a 2 minutos"
    Write-Host ""
    Write-Host "  Acompanhe:  https://github.com/$Repo/actions" -ForegroundColor White
    Write-Host "  URL do app: https://$($Repo.Split('/')[0]).github.io/$($Repo.Split('/')[1])/" -ForegroundColor Green
} else {
    Aviso "workflow nao encontrado - publique manualmente"
}

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host " NO CELULAR, DEPOIS QUE O DEPLOY TERMINAR" -ForegroundColor Yellow
Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Mudou codigo (telas, regras, correcoes):" -ForegroundColor White
Write-Host "     feche e reabra o app. O service worker baixa a versao nova."
Write-Host "     Confira o selo no topo: deve mostrar v$nova."
Write-Host ""
Write-Host "  Mudou o ICONE do app:" -ForegroundColor White
Write-Host "     desinstale e instale de novo."
Write-Host ""
Write-Host "     O Android grava o icone no momento da instalacao e NAO o" -ForegroundColor DarkGray
Write-Host "     atualiza quando o manifest muda. Nao ha como forcar pelo" -ForegroundColor DarkGray
Write-Host "     app; e comportamento do sistema. Reinstalar e o unico jeito." -ForegroundColor DarkGray
Write-Host "     Seus dados nao se perdem: eles ficam no Firebase." -ForegroundColor DarkGray
Write-Host ""
