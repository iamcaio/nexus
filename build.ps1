# ===========================================================================
#  NEXUS - Build de release em UM comando
# ===========================================================================
#  Uso:   .\build.ps1 -Version 6.0.0
#  Uso:   .\build.ps1 -Version 6.0.1 -Notes "- Corrigido X"
#  Uso:   .\build.ps1 -Version 6.0.1 -SkipInstaller      (so o .exe)
#  Uso:   .\build.ps1 -Version 6.0.1 -OnlyVersion        (so sincroniza versao)
#  Uso:   .\build.ps1 -Version 6.0.1 -OnlyInstaller      (reaproveita dist\NEXUS)
#
#  Ordem: sincroniza versao -> pyinstaller -> Inno Setup -> SHA-256 -> manifesto
# ===========================================================================
#
#  NOTAS DE ROBUSTEZ (aprendidas na pratica, nao teoria):
#
#  1. GRAVACAO IDEMPOTENTE. Se o arquivo ja esta na versao pedida, ele NAO e
#     reescrito. Rodar o build duas vezes com a mesma versao nao toca em disco.
#     Isso elimina a causa mais comum de "file is being used by another
#     process": reescrever um arquivo que nao precisava mudar.
#
#  2. SEM BOM. `Set-Content -Encoding UTF8` no PowerShell 5.1 escreve um BOM
#     UTF-8 (EF BB BF) no inicio do arquivo. Num version_info.txt isso pode
#     quebrar o parser de recursos do PyInstaller. Aqui usamos
#     [System.IO.File]::WriteAllText com UTF8Encoding($false), que nunca
#     escreve BOM em nenhuma versao do PowerShell.
#
#  3. GRAVACAO ATOMICA COM RETRY. Escreve num .tmp e depois substitui. Se o
#     arquivo estiver travado (antivirus, editor aberto, indexador do Windows),
#     tenta de novo com espera crescente antes de desistir.
#
#  4. VALIDACAO ANTES DE GRAVAR. Se um regex nao casar, o script para ANTES de
#     escrever qualquer coisa. Falha parcial no meio da sincronizacao de versao
#     e o pior resultado possivel: tres arquivos discordando entre si.
# ===========================================================================

param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Notes = "",
    [switch]$SkipInstaller,
    [switch]$OnlyVersion,
    [switch]$OnlyInstaller,
    [string]$BaseUrl = "https://github.com/SEU-USUARIO/nexus/releases/download"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Etapa($n, $txt) { Write-Host "`n[$n] $txt" -ForegroundColor Cyan }
function Detalhe($txt)   { Write-Host "    $txt" -ForegroundColor DarkGray }
function Aviso($txt)     { Write-Host "    $txt" -ForegroundColor Yellow }

if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Versao deve ser X.Y.Z (ex: 6.0.1). Recebido: '$Version'"
}

# Combinacoes contraditorias de switches. Melhor recusar do que adivinhar qual
# o usuario quis e fazer a coisa errada em silencio.
if ($OnlyInstaller -and $SkipInstaller) {
    throw "-OnlyInstaller e -SkipInstaller se contradizem: um gera SO o " +
          "instalador, o outro gera TUDO MENOS o instalador."
}
if ($OnlyVersion -and ($OnlyInstaller -or $SkipInstaller)) {
    throw "-OnlyVersion nao compila nada, entao nao combina com " +
          "-OnlyInstaller nem -SkipInstaller."
}

# ===========================================================================
#  Utilitarios de arquivo
# ===========================================================================

$Utf8SemBom = New-Object System.Text.UTF8Encoding($false)

function Read-TextFile([string]$Caminho) {
    if (-not (Test-Path -LiteralPath $Caminho)) {
        throw "Arquivo nao encontrado: $Caminho"
    }
    return [System.IO.File]::ReadAllText(
        (Resolve-Path -LiteralPath $Caminho), $Utf8SemBom)
}

function Get-QuemTrava([string]$Caminho) {
    <#
      Nao existe API simples em PowerShell para descobrir qual processo tem um
      handle aberto. Em vez de fingir precisao, listamos os suspeitos que
      REALMENTE estao rodando agora. Isso e acionavel; um "arquivo em uso"
      generico nao e.
    #>
    $suspeitos = @{
        'Code'            = 'VS Code'
        'notepad'         = 'Bloco de Notas'
        'notepad++'       = 'Notepad++'
        'sublime_text'    = 'Sublime Text'
        'pycharm64'       = 'PyCharm'
        'idea64'          = 'IntelliJ'
        'devenv'          = 'Visual Studio'
        'WINWORD'         = 'Word'
        'Claude'          = 'Claude / Cowork (visualizador de arquivos)'
        'OneDrive'        = 'OneDrive (sincronizacao)'
        'Dropbox'         = 'Dropbox (sincronizacao)'
        'GoogleDriveFS'   = 'Google Drive (sincronizacao)'
        'MsMpEng'         = 'Windows Defender (varredura em tempo real)'
        'SearchIndexer'   = 'Indexador de Busca do Windows'
        'python'          = 'Python (processo antigo ainda vivo?)'
        'NEXUS'           = 'NEXUS.exe (o proprio app aberto)'
        'pyinstaller'     = 'PyInstaller de um build anterior'
    }
    $achados = @()
    foreach ($nome in $suspeitos.Keys) {
        if (Get-Process -Name $nome -ErrorAction SilentlyContinue) {
            $achados += "$($suspeitos[$nome])  [$nome.exe]"
        }
    }
    return $achados
}

function Write-TextFileIfChanged {
    <#
      Grava somente se o conteudo mudou. Gravacao atomica (tmp + replace) com
      retry exponencial. Devolve $true se gravou, $false se nada mudou.
    #>
    param(
        [Parameter(Mandatory)][string]$Caminho,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Conteudo,
        [int]$Tentativas = 6
    )

    $completo = (Resolve-Path -LiteralPath $Caminho).Path

    if ((Read-TextFile $completo) -ceq $Conteudo) {
        Detalhe "$(Split-Path $completo -Leaf): ja esta correto, nao reescrito"
        return $false
    }

    $tmp = "$completo.tmp"
    $espera = 250

    for ($i = 1; $i -le $Tentativas; $i++) {
        try {
            [System.IO.File]::WriteAllText($tmp, $Conteudo, $Utf8SemBom)
            # Move -Force e atomico o suficiente no mesmo volume NTFS.
            Move-Item -LiteralPath $tmp -Destination $completo -Force
            Detalhe "$(Split-Path $completo -Leaf): atualizado"
            return $true
        }
        catch {
            # Catch generico de proposito. Com $ErrorActionPreference = "Stop",
            # o PowerShell embrulha IOException em ActionPreferenceStopException,
            # e um `catch [System.IO.IOException]` NAO capturaria. Aqui tratamos
            # qualquer falha de escrita como possivelmente transitoria.
            if (Test-Path -LiteralPath $tmp) {
                Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
            }
            if ($i -eq $Tentativas) {
                Write-Host ""
                Write-Host "  ARQUIVO TRAVADO: $completo" -ForegroundColor Red
                Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
                Write-Host ""
                $quem = Get-QuemTrava $completo
                if ($quem.Count -gt 0) {
                    Write-Host "  Processos em execucao que costumam causar isto:" -ForegroundColor Yellow
                    foreach ($q in $quem) { Write-Host "    - $q" -ForegroundColor Yellow }
                } else {
                    Write-Host "  Nenhum suspeito obvio em execucao." -ForegroundColor Yellow
                }
                Write-Host ""
                Write-Host "  O que fazer, na ordem:" -ForegroundColor White
                Write-Host "    1. Feche o arquivo em qualquer editor/visualizador aberto"
                Write-Host "    2. Feche o NEXUS.exe, se estiver rodando"
                Write-Host "    3. Rode de novo. O script e idempotente: repetir e seguro."
                Write-Host "    4. Se persistir, adicione C:\doNext ao Windows Defender:"
                Write-Host "       Seguranca do Windows > Protecao contra virus >"
                Write-Host "       Gerenciar configuracoes > Exclusoes > Adicionar pasta"
                Write-Host ""
                throw "Nao foi possivel gravar $(Split-Path $completo -Leaf) apos $Tentativas tentativas."
            }
            Aviso "$(Split-Path $completo -Leaf) travado (tentativa $i/$Tentativas), aguardando $espera ms..."
            Start-Sleep -Milliseconds $espera
            $espera = [Math]::Min($espera * 2, 4000)
        }
    }
    return $false
}

function Find-ISCC {
    <#
      Localiza o ISCC.exe (compilador de linha de comando do Inno Setup).

      Procura em quatro lugares, porque o instalador do Inno Setup pode cair em
      qualquer um deles dependendo de como foi instalado (winget, instalador
      grafico, por usuario, portatil):
        1. PATH        - se o instalador registrou, ou se voce adicionou
        2. Registro    - onde o proprio Inno Setup grava o caminho real
        3. Program Files (x86 e x64) - instalacao padrao
        4. LocalAppData - instalacao "somente para mim"

      A busca no registro e a que mais importa: e a unica que funciona quando
      o usuario instalou numa pasta fora do padrao.
    #>

    # 1. Ja esta no PATH?
    $noPath = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($noPath) { return $noPath.Source }

    # 2. Registro. O Inno Setup grava o diretorio de instalacao aqui.
    $chaves = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1'
    )
    foreach ($k in $chaves) {
        try {
            $loc = (Get-ItemProperty -Path $k -ErrorAction Stop).InstallLocation
            if ($loc) {
                $exe = Join-Path $loc "ISCC.exe"
                if (Test-Path -LiteralPath $exe) { return $exe }
            }
        } catch { }
    }

    # 3 e 4. Caminhos comuns, incluindo instalacao por usuario.
    $candidatos = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($c in $candidatos) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }

    # Inno Setup 5 nao serve: este .iss usa diretivas que so existem na 6
    # (ArchitecturesInstallIn64BitMode=x64compatible, PrivilegesRequiredOverridesAllowed).
    # Melhor avisar do que compilar errado.
    $v5 = @(
        "${env:ProgramFiles(x86)}\Inno Setup 5\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 5\ISCC.exe"
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if ($v5) {
        Aviso "Encontrado Inno Setup 5 em '$v5', mas este script exige a versao 6."
        Aviso "Instale a 6 (pode conviver com a 5): https://jrsoftware.org/isdl.php"
    }

    return $null
}

function Invoke-Regex {
    <#
      Aplica um -replace exigindo exatamente uma ocorrencia. Se o padrao nao
      casar, para o build. Um regex que silenciosamente nao casa produz um
      release com versoes discordantes — o bug de release classico.
    #>
    param(
        [Parameter(Mandatory)][string]$Texto,
        [Parameter(Mandatory)][string]$Padrao,
        [Parameter(Mandatory)][string]$Novo,
        [Parameter(Mandatory)][string]$Rotulo
    )
    $n = ([regex]$Padrao).Matches($Texto).Count
    if ($n -ne 1) {
        throw "[$Rotulo] o padrao casou $n vez(es), esperado exatamente 1.`n" +
              "  padrao: $Padrao`n" +
              "  Isso significa que o arquivo mudou de forma inesperada. " +
              "Nada foi gravado."
    }
    # Regex.Replace trata '$' na substituicao como referencia de grupo ($1, $&).
    # Escapamos para '$$' para que o texto seja inserido literalmente.
    $seguro = $Novo.Replace('$', '$$')
    return ([regex]$Padrao).Replace($Texto, $seguro, 1)
}

# ===========================================================================
#  1. SINCRONIZAR A VERSAO
# ===========================================================================
Etapa 1 "Sincronizando a versao $Version"

$arquivos = @("nexus.py", "version_info.txt", "nexus_installer.iss")
foreach ($a in $arquivos) {
    if (-not (Test-Path -LiteralPath $a)) {
        throw "Arquivo obrigatorio ausente: $a (rode o script dentro de C:\doNext\NEXUS)"
    }
}

$p      = $Version.Split('.')
$quad   = "$($p[0]), $($p[1]), $($p[2]), 0"
$dotted = "$Version.0"

# --- Monta TUDO na memoria primeiro. So depois grava. ---
$py = Read-TextFile "nexus.py"
$py = Invoke-Regex $py 'APP_VERSION = "v[\d\.]+"' "APP_VERSION = `"v$Version`"" 'nexus.py APP_VERSION'
$py = Invoke-Regex $py '>v[\d\.]+</button>'       ">v$Version</button>"          'nexus.py badge do header'

$vi = Read-TextFile "version_info.txt"
$vi = Invoke-Regex $vi 'filevers=\([\d, ]+\)' "filevers=($quad)" 'version_info filevers'
$vi = Invoke-Regex $vi 'prodvers=\([\d, ]+\)' "prodvers=($quad)" 'version_info prodvers'
$vi = Invoke-Regex $vi "StringStruct\('FileVersion', '[\d\.]+'\)" `
                       "StringStruct('FileVersion', '$dotted')"  'version_info FileVersion'
$vi = Invoke-Regex $vi "StringStruct\('ProductVersion', '[\d\.]+'\)" `
                       "StringStruct('ProductVersion', '$dotted')" 'version_info ProductVersion'

$iss = Read-TextFile "nexus_installer.iss"
$iss = Invoke-Regex $iss '#define MyAppVersion\s+"[\d\.]+"' `
                         "#define MyAppVersion     `"$Version`"" 'iss MyAppVersion'

# --- Agora sim, grava. Cada gravacao e no-op se nada mudou. ---
$mudou = $false
$mudou = (Write-TextFileIfChanged -Caminho "nexus.py"            -Conteudo $py)  -or $mudou
$mudou = (Write-TextFileIfChanged -Caminho "version_info.txt"    -Conteudo $vi)  -or $mudou
$mudou = (Write-TextFileIfChanged -Caminho "nexus_installer.iss" -Conteudo $iss) -or $mudou

if (-not $mudou) { Detalhe "Os tres arquivos ja estavam na versao $Version." }

if ($OnlyVersion) {
    Write-Host "`nVersao sincronizada. Nada foi compilado (-OnlyVersion)." -ForegroundColor Green
    exit 0
}

# ===========================================================================
#  2. PYINSTALLER
# ===========================================================================
if ($OnlyInstaller) {
    Etapa 2 "Reaproveitando o build existente (-OnlyInstaller)"

    if (-not (Test-Path "dist\NEXUS\NEXUS.exe")) {
        throw "-OnlyInstaller exige um dist\NEXUS\NEXUS.exe ja compilado, e nao existe.`n" +
              "  Rode primeiro sem -OnlyInstaller."
    }

    # Guarda-corpo: o exe reaproveitado precisa ser DESTA versao. Empacotar um
    # binario antigo dentro de um instalador novo produz um release em que o
    # app diz uma versao e o instalador diz outra — e o auto-updater entra em
    # loop, oferecendo a mesma atualizacao para sempre.
    $verExe = (Get-Item "dist\NEXUS\NEXUS.exe").VersionInfo.FileVersion
    if ($verExe -and ($verExe -replace '[,\s]', '.') -notlike "$Version*") {
        throw "O dist\NEXUS\NEXUS.exe existente e da versao '$verExe', mas voce " +
              "pediu $Version.`n  Rode sem -OnlyInstaller para recompilar."
    }
    Detalhe "dist\NEXUS\NEXUS.exe: versao $verExe (compativel)"
}
else {
    Etapa 2 "Compilando o executavel (pyinstaller)"

    foreach ($d in @("build", "dist")) {
        if (Test-Path $d) {
            try { Remove-Item $d -Recurse -Force }
            catch { throw "Nao foi possivel limpar '$d': $($_.Exception.Message)`n" +
                          "  Feche o NEXUS.exe se ele estiver rodando de dentro de dist\." }
        }
    }

    python -m pip install --quiet --upgrade pyinstaller pywebview certifi
    if ($LASTEXITCODE -ne 0) { throw "pip falhou ao instalar as dependencias." }

    pyinstaller --noconfirm --clean nexus.spec
    if ($LASTEXITCODE -ne 0) { throw "pyinstaller retornou codigo $LASTEXITCODE." }
    if (-not (Test-Path "dist\NEXUS\NEXUS.exe")) {
        throw "pyinstaller nao gerou dist\NEXUS\NEXUS.exe"
    }
}

$mb = [math]::Round((Get-ChildItem "dist\NEXUS" -Recurse |
        Measure-Object Length -Sum).Sum / 1MB, 1)
Detalhe "dist\NEXUS\ -> $mb MB"

# certifi empacotado? Sem ele o auto-updater se bloqueia por seguranca.
$temCertifi = (Get-ChildItem "dist\NEXUS" -Recurse -Filter "cacert.pem" `
                -ErrorAction SilentlyContinue).Count -gt 0
if ($temCertifi) { Detalhe "certifi/cacert.pem incluido: TLS verificavel OK" }
else { Aviso "cacert.pem NAO encontrado no build. O auto-updater vai se recusar a instalar. Rode: pip install certifi" }

if ($SkipInstaller) {
    Write-Host "`nPronto (sem instalador). Teste: .\dist\NEXUS\NEXUS.exe" -ForegroundColor Green
    exit 0
}

# ===========================================================================
#  3. INSTALADOR
# ===========================================================================
Etapa 3 "Compilando o instalador (Inno Setup)"

$iscc = Find-ISCC

if (-not $iscc) {
    Write-Host ""
    Write-Host "  O Inno Setup 6 nao esta instalado nesta maquina." -ForegroundColor Red
    Write-Host ""
    Write-Host "  O EXECUTAVEL FOI GERADO COM SUCESSO. Falta so empacotar." -ForegroundColor Green
    Write-Host "  Voce ja pode testar o app agora:" -ForegroundColor Green
    Write-Host "      .\dist\NEXUS\NEXUS.exe" -ForegroundColor White
    Write-Host ""
    Write-Host "  Para gerar o instalador, escolha UMA opcao:" -ForegroundColor White
    Write-Host ""
    Write-Host "  A) Pelo winget (mais rapido, ja vem no Windows 10/11):" -ForegroundColor Cyan
    Write-Host "        winget install JRSoftware.InnoSetup"
    Write-Host ""
    Write-Host "  B) Baixando o instalador:" -ForegroundColor Cyan
    Write-Host "        https://jrsoftware.org/isdl.php"
    Write-Host "        Escolha 'innosetup-6.x.x.exe' e instale com as opcoes padrao."
    Write-Host ""
    Write-Host "  Depois de instalar, FECHE e reabra o PowerShell e rode:" -ForegroundColor White
    Write-Host "        .\build.ps1 -Version $Version -OnlyInstaller" -ForegroundColor White
    Write-Host ""
    Write-Host "  -OnlyInstaller reaproveita o dist\NEXUS que acabou de ser" -ForegroundColor DarkGray
    Write-Host "  compilado, em vez de rodar o pyinstaller de novo." -ForegroundColor DarkGray
    Write-Host ""
    throw "ISCC.exe nao encontrado. Veja as instrucoes acima."
}
Detalhe "ISCC: $iscc"

& $iscc "nexus_installer.iss" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Inno Setup retornou codigo $LASTEXITCODE." }

$setup = "dist_installer\NEXUS-Setup-$Version.exe"
if (-not (Test-Path $setup)) { throw "Inno Setup nao gerou $setup" }

# ===========================================================================
#  4. SHA-256
# ===========================================================================
Etapa 4 "Calculando SHA-256"

$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
$size = (Get-Item $setup).Length
Detalhe $hash

# ===========================================================================
#  5. MANIFESTO
# ===========================================================================
Etapa 5 "Manifesto para o Firebase"

$notas = if ($Notes) { $Notes } else { "Versao $Version" }
$manifesto = [ordered]@{
    version   = $Version
    kind      = "installer"
    url       = "$BaseUrl/v$Version/NEXUS-Setup-$Version.exe"
    sha256    = $hash
    size      = $size
    notes     = $notas
    mandatory = $false
} | ConvertTo-Json -Depth 3

[System.IO.File]::WriteAllText(
    (Join-Path $PSScriptRoot "dist_installer\manifest-$Version.json"),
    $manifesto, $Utf8SemBom)

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host " COLE ISTO NO FIREBASE em /apps/nexus/_release/stable" -ForegroundColor Yellow
Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host $manifesto
Write-Host "=======================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "Instalador:  $setup" -ForegroundColor Green
Write-Host "Tamanho:     $([math]::Round($size/1MB,1)) MB" -ForegroundColor Green
Write-Host ""
Write-Host "PROXIMOS PASSOS (nesta ordem, sempre):" -ForegroundColor White
Write-Host "  1. Suba $setup para o GitHub Releases na tag v$Version"
Write-Host "  2. Confirme que a URL do manifesto abre o arquivo"
Write-Host "  3. SO DEPOIS cole o JSON no Firebase"
Write-Host ""
Write-Host "Se inverter a ordem 3 -> 1, todo usuario que abrir o NEXUS" -ForegroundColor DarkYellow
Write-Host "vera uma atualizacao que ainda nao existe para download." -ForegroundColor DarkYellow
