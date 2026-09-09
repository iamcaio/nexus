; ===========================================================================
;  NEXUS - Script de instalacao (Inno Setup 6)
; ===========================================================================
;  Requisito unico: Inno Setup 6, gratuito, em https://jrsoftware.org/isdl.php
;
;  Compilar:  iscc nexus_installer.iss
;  Resultado: dist_installer\NEXUS-Setup-<versao>.exe
;
;  NAO edite a versao aqui a mao. O build.ps1 reescreve o #define MyAppVersion
;  abaixo a partir do parametro -Version, junto com nexus.py e version_info.txt.
;  Editar em um lugar so e como as tres versoes passam a discordar.
;
;  O que este instalador resolve, e que o pyinstaller sozinho nao resolve:
;    - duplo clique instala; nao ha pasta solta nem "qual .exe eu abro?"
;    - atalho no Menu Iniciar e (opcional) na Area de Trabalho
;    - entra em "Aplicativos instalados" do Windows, com desinstalador
;    - /SILENT permite que o proprio app se atualize sem perguntar nada
;    - PrivilegesRequired=lowest: instala por usuario, SEM pedir admin
; ===========================================================================

#define MyAppName        "NEXUS"
#define MyAppVersion     "6.1.0"
#define MyAppPublisher   "NEXUS"
#define MyAppExeName     "NEXUS.exe"

[Setup]
AppId={{BA859885-5E38-56A2-AD6E-8212C685BCD0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}

; Instala em %LOCALAPPDATA%\Programs\NEXUS -> nao exige administrador.
; Trocar para {autopf}\NEXUS + PrivilegesRequired=admin se preferir
; instalacao para todos os usuarios da maquina.
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

OutputDir=dist_installer
OutputBaseFilename={#MyAppName}-Setup-{#MyAppVersion}
SetupIconFile=nexus.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

; Fecha o NEXUS automaticamente durante um update silencioso e o reabre.
CloseApplications=yes
RestartApplications=yes
CloseApplicationsFilter=*.exe

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Area de Trabalho"; GroupDescription: "Atalhos:"; Flags: checkedonce

[Files]
; O PyInstaller --onedir gera dist\NEXUS\ com o exe e o _internal.
Source: "dist\NEXUS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}";  Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; skipifsilent: num update automatico o app e reaberto pelo RestartApplications,
; nao por aqui. Sem isso o NEXUS poderia abrir duas vezes.
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir o {#MyAppName} agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Limpa apenas o cache de atualizacao. Os DADOS do usuario em C:\NEXUS\db
; NAO sao apagados de proposito: desinstalar o app nao deve destruir tarefas.
Type: filesandordirs; Name: "{app}\_internal\__pycache__"
