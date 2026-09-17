import sys
import os
import json
import time
import ssl
import traceback
import urllib.request
import urllib.error
import hashlib
import threading
import subprocess
import tempfile
import shutil

def show_native_error_dialog(title, message):
    """Exibe um alerta nativo do sistema com o erro exato caso ocorra uma falha ao abrir."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, str(message), str(title), 0x10)
    except Exception:
        print(f"[{title}] {message}")

try:
    import webview
except Exception as e:
    err_msg = f"Não foi possível carregar a biblioteca 'pywebview'.\n\nErro:\n{traceback.format_exc()}\n\nPor favor, execute 'pip install pywebview' no terminal."
    show_native_error_dialog("Erro ao Iniciar - NEXUS", err_msg)
    sys.exit(1)

APP_VERSION = "v6.2.0"

# ---------------------------------------------------------------------------
# NOTIFICAÇÕES DESKTOP E ÍCONE NA BARRA DE TAREFAS (WINDOWS)
# ---------------------------------------------------------------------------
class WindowsNotifier:
    """Dispara notificações nativas do Windows (Toast Notifications) em segundo plano."""
    @staticmethod
    def notify(title, message, sound=True):
        def _run():
            try:
                clean_title = str(title or "NEXUS").replace('"', '`"').replace('$', '`$')
                clean_msg = str(message or "").replace('"', '`"').replace('$', '`$')
                audio_tag = '<audio src="ms-winsoundevent:Notification.Default" />' if sound else '<audio silent="true" />'
                
                ps_script = f'''
                [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
                [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
                
                $template = @"
                <toast>
                    <visual>
                        <binding template="ToastGeneric">
                            <text>{clean_title}</text>
                            <text>{clean_msg}</text>
                        </binding>
                    </visual>
                    {audio_tag}
                </toast>
"@
                $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
                $xml.LoadXml($template)
                $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
                $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("NEXUS")
                $notifier.Show($toast)
                '''
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                    capture_output=True, text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )
            except Exception as e:
                print(f"[Notifier] Erro ao disparar notificação: {e}")

        threading.Thread(target=_run, daemon=True).start()


class TaskbarOverlayHelper:
    """Gerencia o ícone de sobreposição (badge) no ícone da Barra de Tarefas do Windows."""
    _helper_cls = None
    _init_attempted = False

    @classmethod
    def _init_helper(cls):
        if cls._init_attempted:
            return cls._helper_cls
        cls._init_attempted = True
        try:
            import clr
            from System.CodeDom.Compiler import CodeDomProvider, CompilerParameters
            
            csharp_code = """
            using System;
            using System.Runtime.InteropServices;
            using System.Drawing;

            public static class TaskbarBadge {
                [ComImport]
                [Guid("ea1afb91-9e28-4b86-90e9-9e9f8a5eefaf")]
                [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
                private interface ITaskbarList3 {
                    void HrInit();
                    void AddTab(IntPtr hwnd);
                    void DeleteTab(IntPtr hwnd);
                    void ActivateTab(IntPtr hwnd);
                    void SetActiveAlt(IntPtr hwnd);
                    void MarkFullscreenWindow(IntPtr hwnd, int fFullscreen);
                    void SetProgressValue(IntPtr hwnd, ulong ullCompleted, ulong ullTotal);
                    void SetProgressState(IntPtr hwnd, int tbpFlags);
                    void RegisterTab(IntPtr hwndTab, IntPtr hwndMDI);
                    void UnregisterTab(IntPtr hwndTab);
                    void SetTabOrder(IntPtr hwndTab, IntPtr hwndInsertBefore);
                    void SetTabActive(IntPtr hwndTab, IntPtr hwndMDI, uint dwReserved);
                    void ThumbBarAddButtons(IntPtr hwnd, uint cButtons, IntPtr pButton);
                    void ThumbBarUpdateButtons(IntPtr hwnd, uint cButtons, IntPtr pButton);
                    void ThumbBarSetImageList(IntPtr hwnd, IntPtr himl);
                    void SetOverlayIcon(IntPtr hwnd, IntPtr hIcon, [MarshalAs(UnmanagedType.LPWStr)] string pszDescription);
                    void SetThumbnailTooltip(IntPtr hwnd, [MarshalAs(UnmanagedType.LPWStr)] string pszTip);
                    void SetThumbnailClip(IntPtr hwnd, IntPtr prcClip);
                }

                [ComImport]
                [Guid("56fdf344-fd6d-11d0-958a-006097c9a090")]
                [ClassInterface(ClassInterfaceType.None)]
                private class TaskbarList { }

                private static ITaskbarList3 _taskbar;

                static TaskbarBadge() {
                    try {
                        _taskbar = (ITaskbarList3)new TaskbarList();
                        _taskbar.HrInit();
                    } catch { }
                }

                [DllImport("user32.dll", CharSet = CharSet.Auto)]
                private static extern bool DestroyIcon(IntPtr handle);

                public static void SetBadge(IntPtr hwnd, string text, string desc) {
                    if (_taskbar == null || hwnd == IntPtr.Zero) return;
                    try {
                        if (string.IsNullOrEmpty(text)) {
                            _taskbar.SetOverlayIcon(hwnd, IntPtr.Zero, null);
                            return;
                        }

                        using (Bitmap bmp = new Bitmap(32, 32)) {
                            using (Graphics g = Graphics.FromImage(bmp)) {
                                g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
                                g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;

                                using (Brush bgBrush = new SolidBrush(Color.FromArgb(220, 38, 38))) {
                                    g.FillEllipse(bgBrush, 1, 1, 30, 30);
                                }
                                using (Pen borderPen = new Pen(Color.White, 2.0f)) {
                                    g.DrawEllipse(borderPen, 1, 1, 30, 30);
                                }

                                float fontSize = text.Length > 2 ? 10f : (text.Length > 1 ? 12f : 14f);
                                using (Font f = new Font("Arial", fontSize, FontStyle.Bold))
                                using (Brush textBrush = new SolidBrush(Color.White)) {
                                    StringFormat sf = new StringFormat();
                                    sf.Alignment = StringAlignment.Center;
                                    sf.LineAlignment = StringAlignment.Center;
                                    g.DrawString(text, f, textBrush, new RectangleF(0, 0, 32, 32), sf);
                                }
                            }

                            IntPtr hIcon = bmp.GetHicon();
                            try {
                                _taskbar.SetOverlayIcon(hwnd, hIcon, desc ?? "NEXUS");
                            } finally {
                                DestroyIcon(hIcon);
                            }
                        }
                    } catch { }
                }

                public static void Clear(IntPtr hwnd) {
                    if (_taskbar == null || hwnd == IntPtr.Zero) return;
                    try {
                        _taskbar.SetOverlayIcon(hwnd, IntPtr.Zero, null);
                    } catch { }
                }
            }
            """
            provider = CodeDomProvider.CreateProvider("CSharp")
            params = CompilerParameters()
            params.GenerateInMemory = True
            params.ReferencedAssemblies.Add("System.dll")
            params.ReferencedAssemblies.Add("System.Drawing.dll")
            params.ReferencedAssemblies.Add("System.Windows.Forms.dll")
            results = provider.CompileAssemblyFromSource(params, csharp_code)
            if not results.Errors.HasErrors:
                cls._helper_cls = results.CompiledAssembly.GetType("TaskbarBadge")
        except Exception as e:
            print(f"[TaskbarOverlay] Aviso: suporte a overlay não carregou: {e}")
        return cls._helper_cls

    @classmethod
    def find_main_hwnd(cls, window=None):
        try:
            if window and hasattr(window, "native") and window.native:
                if hasattr(window.native, "Handle"):
                    return int(window.native.Handle.ToInt64())
        except Exception:
            pass

        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            current_pid = os.getpid()
            found = []

            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def enum_cb(hwnd, lparam):
                if user32.IsWindowVisible(hwnd):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value == current_pid:
                        found.append(hwnd)
                return True

            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            if found:
                return found[0]
        except Exception:
            pass
        return 0

    @classmethod
    def set_overlay(cls, count, description="", window=None):
        try:
            helper = cls._init_helper()
            if not helper:
                return
            hwnd_val = cls.find_main_hwnd(window)
            if not hwnd_val:
                return
            from System import IntPtr
            hwnd_ptr = IntPtr(hwnd_val)
            if count is None or count <= 0:
                helper.GetMethod("Clear").Invoke(None, [hwnd_ptr])
            else:
                text = "99+" if count > 99 else str(count)
                desc = description or f"NEXUS - {count} tarefa(s) próxima(s) da data limite"
                helper.GetMethod("SetBadge").Invoke(None, [hwnd_ptr, text, desc])
        except Exception as e:
            print(f"[TaskbarOverlay] Erro ao aplicar overlay: {e}")

# ---------------------------------------------------------------------------
# CAMADA DE NUVEM (Firebase Realtime Database + Firebase Authentication)
# ---------------------------------------------------------------------------
# O MESMO banco atende os dois aplicativos sem misturar dados porque cada um
# grava embaixo do seu próprio ramo, e cada usuário embaixo do próprio UID:
#
#   /apps/nexus/users/<uid>/...       <- este aplicativo (NEXUS, atual)
#   /apps/donext/users/<uid>/...      <- ramo legado (doNext) mantido como backup
#   /apps/cogni/users/<uid>/...       <- o Cogni
#   /database/...                     <- onde o Cogni grava hoje (preservado)
#
# Nada aqui toca em /database, então o Cogni continua funcionando intacto.
# ---------------------------------------------------------------------------

APP_NAMESPACE = "nexus"

# Ramo antigo do app quando ele se chamava "doNext". NAO REMOVER: e a origem da
# migracao automatica. O nó legado nunca é apagado — vira backup permanente.
LEGACY_APP_NAMESPACE = "donext"

# ---------------------------------------------------------------------------
# Credenciais do projeto Firebase, já embutidas: o usuário final só informa
# e-mail e senha.
#
# Esta chave NÃO é secreta — ela apenas identifica o projeto e é visível em
# qualquer app Firebase. Quem impede o acesso aos dados são as Regras do
# Realtime Database, que exigem login e prendem cada usuário ao próprio UID.
# Por isso é essencial manter as Regras publicadas (firebase-rules.json).
# ---------------------------------------------------------------------------
FIREBASE_API_KEY = "AIzaSyAvB7jmXgziIMSG3JptOznthGQAP76LWXM"
FIREBASE_DB_URL = "https://cogni-data-default-rtdb.firebaseio.com"

IDENTITY_URL = "https://identitytoolkit.googleapis.com/v1/accounts"
TOKEN_URL = "https://securetoken.googleapis.com/v1/token"

# ---------------------------------------------------------------------------
# ATUALIZACAO AUTOMATICA
# ---------------------------------------------------------------------------
# O manifesto de versao mora no MESMO Firebase que voce ja administra, num nó
# de leitura publica. Publicar uma nova versao passa a ser: subir o instalador
# em qualquer host e editar um JSON de 6 linhas no console do Firebase.
#
#   /apps/nexus/_release/stable  ->  { version, url, sha256, notes, ... }
#
# O binario em si NAO fica no Firebase (banda cara). O campo "url" aponta para
# onde voce quiser: GitHub Releases, Cloudflare R2, S3, um servidor proprio.
#
# CANAL "beta": troque UPDATE_CHANNEL para testar antes de liberar para todos.
# ---------------------------------------------------------------------------
UPDATE_CHANNEL = "stable"
UPDATE_MANIFEST_URL = (
    f"{FIREBASE_DB_URL}/apps/{APP_NAMESPACE}/_release/{UPDATE_CHANNEL}.json"
)

# Intervalo minimo entre checagens automaticas (segundos). 6 horas.
UPDATE_CHECK_INTERVALO = 6 * 60 * 60

# Tamanho maximo aceito para o download, em bytes. Barreira contra um
# manifesto adulterado apontando para um arquivo gigante (DoS de disco).
UPDATE_TAMANHO_MAX = 400 * 1024 * 1024


def _versao_tupla(v):
    """'v6.1.2' -> (6, 1, 2). Trecho nao-numerico vira 0. Nunca levanta."""
    try:
        limpo = str(v or "").strip().lstrip("vV").split("-")[0].split("+")[0]
        partes = []
        for p in limpo.split(".")[:4]:
            digitos = "".join(c for c in p if c.isdigit())
            partes.append(int(digitos) if digitos else 0)
        while len(partes) < 3:
            partes.append(0)
        return tuple(partes)
    except Exception:
        return (0, 0, 0)


def _versao_maior(a, b):
    """True se a > b comparando semanticamente, nao como texto.

    Detalhe que quebra comparacao por string: '6.10.0' > '6.9.0' e verdadeiro
    numericamente e FALSO alfabeticamente. Por isso a comparacao e por tupla.
    """
    return _versao_tupla(a) > _versao_tupla(b)


class AutoUpdater:
    """
    Verificacao e aplicacao de atualizacoes do NEXUS.

    Modelo de confianca, explicitado de proposito:
      * O manifesto e lido por HTTPS COM verificacao de certificado.
      * O instalador e baixado por HTTPS COM verificacao de certificado.
      * O arquivo baixado SO e executado se o SHA-256 conferir com o do
        manifesto. Sem hash no manifesto, o app se recusa a instalar.
      * O download vai para uma pasta do usuario, nunca para Program Files.

    Sem o passo do SHA-256, um auto-updater e uma porta de execucao remota de
    codigo. Ele nao e opcional.
    """

    def __init__(self, pasta_dados):
        self.pasta = os.path.join(pasta_dados, "updates")
        try:
            os.makedirs(self.pasta, exist_ok=True)
        except Exception:
            self.pasta = tempfile.gettempdir()
        self.arquivo_estado = os.path.join(self.pasta, "update_state.json")
        self.manifesto = None
        self.ultimo_erro = None
        self.ultima_checagem = 0
        self._prog = {"fase": "idle", "pct": 0, "recebido": 0,
                      "total": 0, "mensagem": ""}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ estado
    def _set(self, **kw):
        with self._lock:
            self._prog.update(kw)

    def progresso(self):
        with self._lock:
            return dict(self._prog)

    # --------------------------------------------------------- manifesto
    def verificar(self, forcar=False):
        """
        Le o manifesto e diz se existe versao nova.

        Devolve sempre um dict com 'status':
          up_to_date | update_available | error | throttled
        """
        agora = time.time()
        if not forcar and (agora - self.ultima_checagem) < UPDATE_CHECK_INTERVALO \
                and self.manifesto is not None:
            return self._resposta_do_manifesto()

        if _ssl_ctx_strict is None:
            return {"status": "error", "current": APP_VERSION,
                    "message": "Nao foi possivel montar um contexto TLS seguro "
                               "nesta maquina. Atualizacao desativada por seguranca."}

        st, corpo = _http_json(UPDATE_MANIFEST_URL, timeout=12, ctx=_ssl_ctx_strict)
        self.ultima_checagem = agora

        if st != 200:
            self.ultimo_erro = f"HTTP {st} ao ler o manifesto."
            return {"status": "error", "current": APP_VERSION,
                    "message": "Nao foi possivel consultar atualizacoes agora. "
                               "Verifique a conexao."}
        if not isinstance(corpo, dict) or not corpo.get("version"):
            # Nó ausente ou vazio: nao e erro do usuario, so nao ha release.
            self.manifesto = None
            return {"status": "up_to_date", "current": APP_VERSION,
                    "message": "Nenhuma atualizacao publicada."}

        self.manifesto = corpo
        return self._resposta_do_manifesto()

    def _resposta_do_manifesto(self):
        m = self.manifesto or {}
        nova = m.get("version")
        if not nova or not _versao_maior(nova, APP_VERSION):
            return {"status": "up_to_date", "current": APP_VERSION,
                    "latest": nova or APP_VERSION}
        return {
            "status": "update_available",
            "current": APP_VERSION,
            "latest": nova,
            "notes": m.get("notes") or "",
            "size": m.get("size") or 0,
            "mandatory": bool(m.get("mandatory")),
            "kind": m.get("kind") or "installer",
            "hasHash": bool(m.get("sha256")),
        }

    # ---------------------------------------------------------- download
    def baixar_e_aplicar(self):
        """Roda em thread separada. Acompanhe por progresso()."""
        t = threading.Thread(target=self._fluxo, daemon=True)
        t.start()
        return {"status": "started"}

    def _fluxo(self):
        try:
            self._baixar_e_aplicar_sync()
        except Exception as e:
            self._set(fase="error", pct=0,
                      mensagem=f"{type(e).__name__}: {e}")

    def _baixar_e_aplicar_sync(self):
        m = self.manifesto
        if not m:
            r = self.verificar(forcar=True)
            m = self.manifesto
            if not m:
                self._set(fase="error", mensagem="Nenhuma versao publicada.")
                return

        url = (m.get("url") or "").strip()
        esperado = (m.get("sha256") or "").strip().lower()
        kind = (m.get("kind") or "installer").lower()

        if not url.lower().startswith("https://"):
            self._set(fase="error",
                      mensagem="O manifesto aponta para uma URL nao-HTTPS. "
                               "Instalacao bloqueada.")
            return
        if len(esperado) != 64:
            self._set(fase="error",
                      mensagem="O manifesto nao traz um SHA-256 valido. "
                               "Instalacao bloqueada por seguranca.")
            return
        if _ssl_ctx_strict is None:
            self._set(fase="error",
                      mensagem="Sem TLS verificavel nesta maquina. "
                               "Baixe a atualizacao manualmente.")
            return

        nome = os.path.basename(url.split("?")[0]) or "NEXUS-update.exe"
        destino = os.path.join(self.pasta, nome)
        parcial = destino + ".part"

        self._set(fase="downloading", pct=0, recebido=0, total=0,
                  mensagem="Baixando atualizacao...")

        h = hashlib.sha256()
        recebido = 0
        req = urllib.request.Request(
            url, headers={"User-Agent": f"NexusDesktop/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=60, context=_ssl_ctx_strict) as resp:
            total = int(resp.headers.get("Content-Length") or m.get("size") or 0)
            if total and total > UPDATE_TAMANHO_MAX:
                self._set(fase="error",
                          mensagem="Arquivo maior que o limite permitido.")
                return
            self._set(total=total)
            with open(parcial, "wb") as f:
                while True:
                    bloco = resp.read(262144)
                    if not bloco:
                        break
                    recebido += len(bloco)
                    if recebido > UPDATE_TAMANHO_MAX:
                        f.close()
                        os.remove(parcial)
                        self._set(fase="error",
                                  mensagem="Download excedeu o limite permitido.")
                        return
                    h.update(bloco)
                    f.write(bloco)
                    pct = int(recebido * 100 / total) if total else 0
                    self._set(pct=min(pct, 99), recebido=recebido)

        obtido = h.hexdigest().lower()
        if obtido != esperado:
            try:
                os.remove(parcial)
            except Exception:
                pass
            self._set(fase="error", pct=0,
                      mensagem="A verificacao de integridade FALHOU. O arquivo "
                               "baixado nao corresponde ao publicado e foi "
                               "descartado. Nada foi instalado.")
            return

        try:
            if os.path.exists(destino):
                os.remove(destino)
            os.rename(parcial, destino)
        except Exception as e:
            self._set(fase="error", mensagem=f"Falha ao salvar: {e}")
            return

        self._set(fase="verified", pct=100,
                  mensagem="Integridade confirmada. Iniciando instalacao...")
        time.sleep(0.6)

        if kind == "zip":
            self._aplicar_zip(destino)
        else:
            self._aplicar_instalador(destino)

    # ------------------------------------------------- aplicar: instalador
    def _aplicar_instalador(self, caminho):
        """
        Executa o instalador Inno Setup em modo silencioso e fecha o app.

        /SILENT              -> sem assistente, so a barra de progresso
        /CLOSEAPPLICATIONS   -> fecha o NEXUS em execucao
        /RESTARTAPPLICATIONS -> reabre o NEXUS ao terminar
        /NORESTART           -> nunca reinicia o Windows
        """
        try:
            self._set(fase="installing", pct=100,
                      mensagem="O instalador vai abrir e o NEXUS sera reiniciado.")
            subprocess.Popen(
                [caminho, "/SILENT", "/CLOSEAPPLICATIONS",
                 "/RESTARTAPPLICATIONS", "/NORESTART"],
                close_fds=True,
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
            )
            time.sleep(1.5)
            os._exit(0)
        except Exception as e:
            self._set(fase="error",
                      mensagem=f"Nao foi possivel iniciar o instalador: {e}")

    # -------------------------------------------------- aplicar: zip portatil
    def _aplicar_zip(self, caminho):
        """
        Versao portatil: extrai o zip e troca a pasta do app por um .bat que
        roda DEPOIS que o processo atual morre (Windows nao deixa sobrescrever
        um .exe em uso).
        """
        try:
            import zipfile
            extraido = os.path.join(self.pasta, "novo")
            if os.path.isdir(extraido):
                shutil.rmtree(extraido, ignore_errors=True)
            os.makedirs(extraido, exist_ok=True)
            with zipfile.ZipFile(caminho) as z:
                # Protecao contra zip-slip: nenhum membro pode escapar da pasta.
                base = os.path.abspath(extraido)
                for membro in z.namelist():
                    alvo = os.path.abspath(os.path.join(extraido, membro))
                    if not alvo.startswith(base + os.sep) and alvo != base:
                        self._set(fase="error",
                                  mensagem="Pacote de atualizacao invalido "
                                           "(caminho fora da pasta).")
                        return
                z.extractall(extraido)

            # Se o zip tem uma unica pasta raiz, usa o conteudo dela.
            itens = [os.path.join(extraido, n) for n in os.listdir(extraido)]
            if len(itens) == 1 and os.path.isdir(itens[0]):
                extraido = itens[0]

            destino_app = os.path.dirname(os.path.abspath(sys.executable))
            bat = os.path.join(self.pasta, "aplicar_update.bat")
            exe_nome = os.path.basename(sys.executable)
            with open(bat, "w", encoding="mbcs", errors="replace") as f:
                f.write(
                    "@echo off\r\n"
                    "chcp 65001 >nul\r\n"
                    "echo Aplicando atualizacao do NEXUS...\r\n"
                    ":wait\r\n"
                    f'tasklist /FI "IMAGENAME eq {exe_nome}" | find /I "{exe_nome}" >nul\r\n'
                    "if not errorlevel 1 (\r\n"
                    "  timeout /t 1 /nobreak >nul\r\n"
                    "  goto wait\r\n"
                    ")\r\n"
                    f'robocopy "{extraido}" "{destino_app}" /E /IS /IT /NFL /NDL /NJH /NJS /R:2 /W:1 >nul\r\n'
                    f'start "" "{os.path.join(destino_app, exe_nome)}"\r\n'
                    'del "%~f0"\r\n'
                )
            self._set(fase="installing", pct=100,
                      mensagem="Substituindo arquivos e reabrindo o NEXUS...")
            subprocess.Popen(["cmd", "/c", bat], close_fds=True,
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            time.sleep(1.0)
            os._exit(0)
        except Exception as e:
            self._set(fase="error", mensagem=f"Falha ao aplicar o pacote: {e}")




# ---------------------------------------------------------------------------
# CONTEXTOS SSL
# ---------------------------------------------------------------------------
# Antes havia UM unico contexto sem verificacao de certificado. Isso era
# tolerável enquanto o app só lia JSON, mas passou a ser inaceitável quando
# passamos a BAIXAR E EXECUTAR um instalador: sem verificar o certificado,
# qualquer intermediário na rede poderia entregar um .exe malicioso.
#
# Agora existem dois contextos com propósitos distintos:
#   _ssl_ctx        -> tráfego de dados. Tenta verificar; se o Windows falhar
#                      na cadeia de certificados, cai para permissivo (mantém
#                      o app funcionando como antes).
#   _ssl_ctx_strict -> DOWNLOAD DE ATUALIZACAO. Nunca cai para permissivo.
#                      Se não conseguir validar o certificado, a atualização
#                      é abortada. Além disso o arquivo baixado só é executado
#                      após conferir o SHA-256 declarado no manifesto.
# ---------------------------------------------------------------------------
def _montar_ssl_strict():
    """Contexto com verificacao real de certificado. Usa certifi se existir."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    try:
        return ssl.create_default_context()
    except Exception:
        return None


_ssl_ctx_strict = _montar_ssl_strict()

# Contexto permissivo. MANTIDO APENAS como ultimo recurso para trafego de
# DADOS, nunca para autenticacao, e sempre deixando rastro em _TLS_DEGRADADO
# para a interface poder avisar o usuario.
_ssl_ctx_inseguro = ssl._create_unverified_context()

# Vira True se em algum momento tivermos caido para o contexto sem verificacao.
# A interface mostra um aviso vermelho quando isso acontece: uma conexao sem
# verificacao de certificado nao deve ser silenciosa.
_TLS_DEGRADADO = False
_TLS_MOTIVO = ""


def _http_json(url, payload=None, method="GET", timeout=15, ctx=None,
               permitir_fallback=False):
    """Requisição HTTP simples que devolve (status, dict|str). Nunca levanta.

    SEGURANCA — mudanca importante em relacao as versoes anteriores:

    Antes, TODO o trafego usava um contexto SSL sem verificacao de
    certificado. Isso significava que o e-mail e a SENHA enviados no login, e
    o token de acesso embutido na URL dos dados, podiam ser lidos por qualquer
    intermediario na rede: Wi-Fi de aeroporto, roteador comprometido, proxy
    corporativo que intercepta TLS. O atacante so precisava apresentar um
    certificado qualquer, e o app aceitava.

    Agora o padrao e VERIFICAR. O certifi vai empacotado no executavel, entao
    a verificacao funciona mesmo quando o repositorio de certificados do
    Windows esta quebrado — que era o motivo original da gambiarra.

    `permitir_fallback=True` autoriza, em ultimo caso, repetir a requisicao
    sem verificacao. Isso NUNCA e usado para autenticacao. Quando acontece,
    marca _TLS_DEGRADADO e a interface avisa.
    """
    global _TLS_DEGRADADO, _TLS_MOTIVO
    data = None
    headers = {"User-Agent": f"NexusDesktop/{APP_VERSION}"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    def _executar(contexto):
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method=method)
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=contexto) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw) if raw.strip() else None
            except json.JSONDecodeError:
                return resp.status, raw

    contexto = ctx or _ssl_ctx_strict
    try:
        if contexto is None:
            raise ssl.SSLError("Nenhum contexto TLS verificavel disponivel.")
        return _executar(contexto)
    except urllib.error.HTTPError as e:
        try:
            corpo = json.loads(e.read().decode("utf-8"))
        except Exception:
            corpo = {"error": {"message": str(e)}}
        return e.code, corpo
    except (ssl.SSLError, ssl.SSLCertVerificationError) as e:
        if not permitir_fallback:
            # Autenticacao e atualizacao morrem aqui, de proposito.
            return 0, {"error": {"message":
                "Nao foi possivel validar o certificado do servidor "
                f"({type(e).__name__}). A conexao foi recusada por seguranca. "
                "Verifique a data e a hora do computador e, se estiver em rede "
                "corporativa, se ha um proxy interceptando HTTPS."}}
        try:
            resultado = _executar(_ssl_ctx_inseguro)
            _TLS_DEGRADADO = True
            _TLS_MOTIVO = f"{type(e).__name__}: {e}"
            print(f"[NEXUS TLS] AVISO: conexao sem verificacao de certificado. {e}")
            return resultado
        except Exception as e2:
            return 0, {"error": {"message": f"{type(e2).__name__}: {e2}"}}
    except urllib.error.URLError as e:
        motivo = getattr(e, "reason", e)
        if isinstance(motivo, ssl.SSLError) and permitir_fallback:
            try:
                resultado = _executar(_ssl_ctx_inseguro)
                _TLS_DEGRADADO = True
                _TLS_MOTIVO = str(motivo)
                print(f"[NEXUS TLS] AVISO: conexao sem verificacao. {motivo}")
                return resultado
            except Exception as e2:
                return 0, {"error": {"message": f"{type(e2).__name__}: {e2}"}}
        return 0, {"error": {"message": f"{type(e).__name__}: {motivo}"}}
    except Exception as e:
        return 0, {"error": {"message": f"{type(e).__name__}: {e}"}}


def _mensagem_amigavel(codigo):
    """Traduz os códigos do Firebase Auth para algo legível."""
    return {
        "EMAIL_EXISTS": "Este e-mail já está cadastrado. Use 'Entrar'.",
        "EMAIL_NOT_FOUND": "E-mail não encontrado. Crie uma conta primeiro.",
        "INVALID_PASSWORD": "Senha incorreta.",
        "INVALID_LOGIN_CREDENTIALS": "E-mail ou senha incorretos.",
        "USER_DISABLED": "Esta conta foi desativada no console do Firebase.",
        "WEAK_PASSWORD : Password should be at least 6 characters":
            "A senha precisa ter ao menos 6 caracteres.",
        "INVALID_EMAIL": "E-mail inválido.",
        "TOO_MANY_ATTEMPTS_TRY_LATER : Access to this account has been temporarily disabled due to many failed login attempts. You can immediately restore it by resetting your password or you can try again later.":
            "Muitas tentativas. Aguarde alguns minutos e tente de novo.",
        "OPERATION_NOT_ALLOWED":
            "Login por e-mail/senha está desativado. Ative em Authentication > Sign-in method.",
        "TOKEN_EXPIRED": "Sessão expirada. Entre novamente.",
    }.get(str(codigo), str(codigo))


def _tem_conteudo(d):
    """True se o dicionário do banco tem algo além de estrutura vazia."""
    if not isinstance(d, dict):
        return False
    for chave in ("tasks", "projects", "categories", "notepad"):
        v = d.get(chave)
        if isinstance(v, (list, dict)) and len(v) > 0:
            return True
    perfil = d.get("userProfile")
    if isinstance(perfil, dict) and len(perfil) > 0:
        return True
    return False


def _contar_itens(d):
    """Quantos registros existem no banco, para mostrar ao usuário."""
    total = 0
    if isinstance(d, dict):
        for chave in ("tasks", "projects", "categories", "notepad"):
            v = d.get(chave)
            if isinstance(v, (list, dict)):
                total += len(v)
    return total


class CloudSync:
    """
    Autenticação e sincronização com o Firebase.

    Princípio de segurança adotado: a nuvem NUNCA sobrescreve dados locais bons
    por engano. A decisão de quem vence usa o carimbo `_meta.updatedAt`, e um
    lado vazio jamais substitui um lado com conteúdo.
    """

    def __init__(self, pasta_db):
        self.config_file = os.path.join(pasta_db, "cloud_config.json")
        self.session_file = os.path.join(pasta_db, "cloud_session.json")
        # Já vem embutido: o usuário final só informa e-mail e senha.
        self.api_key = FIREBASE_API_KEY.strip()
        self.db_url = FIREBASE_DB_URL.strip().rstrip("/")
        self.id_token = None
        self.refresh_token = None
        self.uid = None
        self.email = None
        self.expira_em = 0
        self.ultimo_erro = ""
        self._carregar_config()
        self._carregar_sessao()

    # -------------------------- configuração --------------------------- #
    def _carregar_config(self):
        """
        Sobrescrita opcional. Serve para apontar o app para outro projeto sem
        recompilar; se o arquivo não existir, valem as constantes embutidas.
        """
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                chave = (cfg.get("apiKey") or "").strip()
                url = (cfg.get("databaseURL") or "").strip().rstrip("/")
                if chave:
                    self.api_key = chave
                if url:
                    self.db_url = url
        except Exception as e:
            print(f"[Cloud] Config ilegível: {e}")

    def salvar_config(self, api_key, db_url):
        self.api_key = (api_key or "").strip()
        self.db_url = (db_url or "").strip().rstrip("/")
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump({"apiKey": self.api_key, "databaseURL": self.db_url}, f, indent=2)
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @property
    def configurado(self):
        return bool(self.api_key and self.db_url and not self.api_key.startswith("COLE_AQUI"))

    @property
    def logado(self):
        return bool(self.uid and self.refresh_token)

    # ---------------------------- sessão ------------------------------- #
    def _carregar_sessao(self):
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, "r", encoding="utf-8") as f:
                    s = json.load(f)
                self.refresh_token = s.get("refreshToken")
                self.uid = s.get("uid")
                self.email = s.get("email")
        except Exception as e:
            print(f"[Cloud] Sessão ilegível: {e}")

    def _salvar_sessao(self):
        try:
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump({"refreshToken": self.refresh_token,
                           "uid": self.uid, "email": self.email}, f, indent=2)
        except Exception as e:
            print(f"[Cloud] Falha ao gravar sessão: {e}")

    def _limpar_sessao(self):
        self.id_token = self.refresh_token = self.uid = self.email = None
        self.expira_em = 0
        try:
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
        except Exception:
            pass

    # --------------------------- autenticação -------------------------- #
    def _aplicar_resposta_auth(self, corpo):
        self.id_token = corpo.get("idToken")
        self.refresh_token = corpo.get("refreshToken")
        self.uid = corpo.get("localId") or corpo.get("user_id")
        if corpo.get("email"):
            self.email = corpo["email"]
        try:
            self.expira_em = time.time() + int(corpo.get("expiresIn", 3600)) - 120
        except Exception:
            self.expira_em = time.time() + 3300
        self._salvar_sessao()

    def criar_conta(self, email, senha):
        if not self.configurado:
            return {"status": "error", "message": "Configure a chave da API e a URL do banco primeiro."}
        st, corpo = _http_json(f"{IDENTITY_URL}:signUp?key={self.api_key}",
                               {"email": email, "password": senha, "returnSecureToken": True},
                               method="POST")
        if st == 200 and isinstance(corpo, dict) and corpo.get("idToken"):
            self._aplicar_resposta_auth(corpo)
            return {"status": "success", "uid": self.uid, "email": self.email}
        msg = (corpo or {}).get("error", {}).get("message", "Falha ao criar conta.")
        return {"status": "error", "message": _mensagem_amigavel(msg)}

    def entrar(self, email, senha):
        if not self.configurado:
            return {"status": "error", "message": "Configure a chave da API e a URL do banco primeiro."}
        st, corpo = _http_json(f"{IDENTITY_URL}:signInWithPassword?key={self.api_key}",
                               {"email": email, "password": senha, "returnSecureToken": True},
                               method="POST")
        if st == 200 and isinstance(corpo, dict) and corpo.get("idToken"):
            self._aplicar_resposta_auth(corpo)
            return {"status": "success", "uid": self.uid, "email": self.email}
        msg = (corpo or {}).get("error", {}).get("message", "Falha ao entrar.")
        return {"status": "error", "message": _mensagem_amigavel(msg)}

    def sair(self):
        self._limpar_sessao()
        return {"status": "success"}

    def _token_valido(self):
        """Garante um idToken vivo, renovando pelo refreshToken quando preciso."""
        if not self.refresh_token:
            return None
        if self.id_token and time.time() < self.expira_em:
            return self.id_token
        st, corpo = _http_json(
            f"{TOKEN_URL}?key={self.api_key}",
            {"grant_type": "refresh_token", "refresh_token": self.refresh_token},
            method="POST")
        if st == 200 and isinstance(corpo, dict) and corpo.get("id_token"):
            self.id_token = corpo["id_token"]
            self.refresh_token = corpo.get("refresh_token", self.refresh_token)
            self.uid = corpo.get("user_id", self.uid)
            try:
                self.expira_em = time.time() + int(corpo.get("expires_in", 3600)) - 120
            except Exception:
                self.expira_em = time.time() + 3300
            self._salvar_sessao()
            return self.id_token
        self.ultimo_erro = _mensagem_amigavel((corpo or {}).get("error", {}).get("message", "TOKEN_EXPIRED"))
        return None

    # ------------------------------ dados ------------------------------ #
    def _caminho_dados(self, token):
        # Cada app no seu ramo, cada usuário no seu UID: sem colisão.
        return f"{self.db_url}/apps/{APP_NAMESPACE}/users/{self.uid}/database.json?auth={token}"

    def _caminho_dados_legado(self, token):
        """Mesmo caminho, mas no ramo antigo (/apps/donext/...)."""
        return (f"{self.db_url}/apps/{LEGACY_APP_NAMESPACE}/users/{self.uid}"
                f"/database.json?auth={token}")

    def _caminho_marca_migracao(self, token):
        """Sinalizador que evita repetir a migração a cada login."""
        return (f"{self.db_url}/apps/{APP_NAMESPACE}/users/{self.uid}"
                f"/_migratedFrom.json?auth={token}")

    def migrar_ramo_legado(self):
        """
        Migração one-shot doNext -> NEXUS no Realtime Database.

        Regras de segurança que tornam isto reversível e idempotente:
          1. Só copia se o ramo NOVO estiver vazio. Nunca sobrescreve dado novo.
          2. Só copia se o ramo ANTIGO tiver conteúdo de verdade.
          3. NUNCA apaga o ramo antigo — ele fica como backup permanente.
          4. Grava um marcador /_migratedFrom para não tentar de novo.

        Devolve um dict com o que aconteceu, para a interface poder avisar.
        """
        if not (self.configurado and self.logado):
            return {"status": "skip", "reason": "offline"}
        token = self._token_valido()
        if not token:
            return {"status": "skip", "reason": "sem token"}

        # (4) Já migrado? Sai barato.
        st, marca = _http_json(self._caminho_marca_migracao(token))
        if st == 200 and marca:
            return {"status": "already", "reason": "marcador presente"}

        # (1) O ramo novo já tem dados? Então não há o que migrar.
        st_novo, novo = _http_json(self._caminho_dados(token))
        if st_novo == 200 and isinstance(novo, dict) and _tem_conteudo(novo):
            _http_json(self._caminho_marca_migracao(token),
                       "nao-necessario", method="PUT")
            return {"status": "already", "reason": "ramo novo já populado"}
        if st_novo in (401, 403):
            return {"status": "error",
                    "message": "Sem permissão de leitura no ramo NEXUS. "
                               "Publique as Regras do Realtime Database."}

        # (2) O ramo antigo tem conteúdo?
        st_old, antigo = _http_json(self._caminho_dados_legado(token))
        if st_old != 200 or not isinstance(antigo, dict) or not _tem_conteudo(antigo):
            _http_json(self._caminho_marca_migracao(token),
                       "sem-dados-legados", method="PUT")
            return {"status": "empty", "reason": "nada no ramo doNext"}

        # (3) Copia. O ramo antigo permanece intacto.
        st_put, corpo = _http_json(self._caminho_dados(token), antigo, method="PUT")
        if st_put not in (200, 201, 204):
            return {"status": "error",
                    "message": f"Falha ao gravar no ramo NEXUS (HTTP {st_put})."}

        _http_json(self._caminho_marca_migracao(token),
                   f"apps/{LEGACY_APP_NAMESPACE} em " + time.strftime("%Y-%m-%d %H:%M:%S"),
                   method="PUT")
        return {"status": "migrated", "items": _contar_itens(antigo)}

    def baixar(self):
        if not (self.configurado and self.logado):
            return {"status": "offline", "message": "Não conectado."}
        token = self._token_valido()
        if not token:
            return {"status": "auth_error", "message": self.ultimo_erro or "Sessão expirada."}
        st, corpo = _http_json(self._caminho_dados(token),
                               permitir_fallback=True)
        if st == 200:
            if corpo is None:
                return {"status": "empty"}
            if isinstance(corpo, dict):
                return {"status": "ok", "data": corpo}
            return {"status": "error", "message": "Formato inesperado vindo da nuvem."}
        if st in (401, 403):
            return {"status": "auth_error",
                    "message": "Sem permissão. Confira as Regras do Realtime Database."}
        return {"status": "error",
                "message": (corpo or {}).get("error", f"HTTP {st}") if isinstance(corpo, dict) else f"HTTP {st}"}

    def enviar(self, dados_dict):
        if not (self.configurado and self.logado):
            return {"status": "offline", "message": "Não conectado."}
        token = self._token_valido()
        if not token:
            return {"status": "auth_error", "message": self.ultimo_erro or "Sessão expirada."}
        st, corpo = _http_json(self._caminho_dados(token), dados_dict,
                               method="PUT", permitir_fallback=True)
        if st in (200, 201, 204):
            return {"status": "success"}
        if st in (401, 403):
            return {"status": "auth_error",
                    "message": "Sem permissão de escrita. Confira as Regras do banco."}
        return {"status": "error",
                "message": (corpo or {}).get("error", f"HTTP {st}") if isinstance(corpo, dict) else f"HTTP {st}"}

    def resumo(self):
        return {
            "configured": self.configurado,
            "signedIn": self.logado,
            "email": self.email,
            # uid, apiKey e o caminho completo NAO sao expostos a interface.
            "databaseURL": self.db_url,
        }


class NexusDesktopAPI:
    r"""
    Bridge Python entre a interface gráfica NEXUS e o sistema operacional.
    Persistência local segura em C:\NEXUS\db\tasks_db.json, com sincronização
    opcional para o Firebase Realtime Database e atualização automática.
    """
    def __init__(self):
        # ATENÇÃO: precisa começar com "_".
        # O pywebview enumera os atributos públicos da API para expô-los ao JS e,
        # ao encontrar um objeto não-chamável, entra dentro dele. O Window tem
        # propriedades (width, height, x, y) que fazem events.shown.wait(15).
        # Com o atributo público, a injeção de window.pywebview.api ficava presa
        # por até ~60s e o app concluía que a ponte não respondeu.
        self._window = None

        # Pasta raiz do app. Dentro dela, CADA CONTA tem a sua propria subpasta
        # (users/<uid>), para que dois usuarios no mesmo computador nunca
        # enxerguem os arquivos um do outro.
        self._migracao_disco = None
        self._base_dir = r"C:\NEXUS\db"
        try:
            os.makedirs(self._base_dir, exist_ok=True)
            teste = os.path.join(self._base_dir, ".w")
            with open(teste, "w") as f:
                f.write("1")
            os.remove(teste)
        except Exception as e:
            print(f"[NEXUS DB Init Warning] {e}")
            appdata = os.getenv("LOCALAPPDATA", os.path.expanduser("~"))
            self._base_dir = os.path.join(appdata, "NEXUS", "db")
            os.makedirs(self._base_dir, exist_ok=True)

        # Migracao de disco: quem ja usava o doNext tem os dados em C:\doNext\db.
        # Copiamos (nao movemos) uma unica vez. A pasta antiga permanece intacta
        # como rede de seguranca; se algo der errado o usuario nao perde nada.
        self._migrar_pasta_legada()

        self.AVATAR_MARKER = "@file"
        # So libera gravacao depois de uma leitura integra nesta sessao.
        self.load_ok = False
        # Sincronizacao opcional com o Firebase (privada: "_" evita que o
        # pywebview entre no objeto ao enumerar a API).
        self._cloud = CloudSync(self._base_dir)
        self._ultimo_sync = None

        # Atualizacao automatica. A checagem roda em thread separada para nao
        # atrasar a abertura da janela nem um milissegundo.
        self._updater = AutoUpdater(self._base_dir)
        self._update_cache = None
        threading.Thread(target=self._checar_update_em_background,
                         daemon=True).start()

        self._aplicar_caminhos_do_usuario()

    # ------------------------------------------------------------------ #
    # Migração doNext -> NEXUS (disco)
    # ------------------------------------------------------------------ #
    def _migrar_pasta_legada(self):
        r"""
        Copia C:\doNext\db -> C:\NEXUS\db uma única vez.

        Decisões deliberadas:
          * COPIA, não move. A pasta antiga fica como backup. Custa alguns MB
            e elimina a classe de bug mais caro que existe: perda de dados.
          * Só age se o destino estiver vazio. Se o usuário já tem dados no
            NEXUS, nada acontece.
          * Deixa um arquivo .migrado no destino como marcador.
          * Qualquer exceção é engolida com log: uma migração que falha não
            pode impedir o app de abrir.
        """
        marcador = os.path.join(self._base_dir, ".migrado_de_donext")
        if os.path.exists(marcador):
            return

        candidatos = [
            r"C:\doNext\db",
            os.path.join(os.getenv("LOCALAPPDATA", os.path.expanduser("~")),
                         "doNext", "db"),
        ]
        origem = next((c for c in candidatos
                       if os.path.isdir(c) and os.path.abspath(c) != os.path.abspath(self._base_dir)),
                      None)
        if not origem:
            try:
                with open(marcador, "w", encoding="utf-8") as f:
                    f.write("nada a migrar")
            except Exception:
                pass
            return

        # Destino já tem dados? Então não mexe.
        try:
            ja_tem = any(
                n not in (".migrado_de_donext", ".w")
                for n in os.listdir(self._base_dir)
            )
        except Exception:
            ja_tem = False
        if ja_tem:
            try:
                with open(marcador, "w", encoding="utf-8") as f:
                    f.write("destino ja populado; migracao dispensada")
            except Exception:
                pass
            return

        copiados = 0
        try:
            import shutil
            for raiz, _dirs, arquivos in os.walk(origem):
                rel = os.path.relpath(raiz, origem)
                destino = self._base_dir if rel == "." else os.path.join(self._base_dir, rel)
                os.makedirs(destino, exist_ok=True)
                for nome in arquivos:
                    try:
                        shutil.copy2(os.path.join(raiz, nome), os.path.join(destino, nome))
                        copiados += 1
                    except Exception as e:
                        print(f"[NEXUS Migracao] {nome}: {e}")
            with open(marcador, "w", encoding="utf-8") as f:
                f.write(f"origem={origem} arquivos={copiados} "
                        f"em={time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"[NEXUS Migracao] {copiados} arquivo(s) copiado(s) de {origem}")
            # Só reporta quando algo foi realmente copiado. Uma pasta antiga
            # existente porém vazia não é uma migração e não merece aviso.
            if copiados > 0:
                self._migracao_disco = {"origem": origem, "arquivos": copiados}
        except Exception as e:
            print(f"[NEXUS Migracao] Falhou (o app segue normalmente): {e}")

    # ------------------------------------------------------------------ #
    # Isolamento por conta
    # ------------------------------------------------------------------ #
    def _pasta_do_usuario(self):
        """
        Pasta de dados da conta atual. Sem conta, usa uma pasta neutra, de modo
        que o modo "somente neste computador" tambem fique separado.
        """
        if self._cloud.logado and self._cloud.uid:
            return os.path.join(self._base_dir, "users", self._cloud.uid)
        return os.path.join(self._base_dir, "local")

    def _aplicar_caminhos_do_usuario(self):
        """
        Reaponta os arquivos para a pasta da conta atual. Chamado no inicio e
        sempre que entra ou sai uma conta: sem isso o cache da conta anterior
        continuaria em uso e vazaria para a proxima.
        """
        pasta = self._pasta_do_usuario()
        try:
            os.makedirs(pasta, exist_ok=True)
        except Exception as e:
            print(f"[NEXUS] Falha ao preparar pasta da conta: {e}")

        self.data_file = os.path.join(pasta, "tasks_db.json")
        self.backup_file = self.data_file + ".bak"
        # O avatar e base64 e pode ter varios MB; fica fora do banco para nao
        # atravessar a ponte Python->JS no boot.
        self.avatar_file = os.path.join(pasta, "avatar.dat")

        # Troca de conta invalida a leitura anterior: bloqueia a gravacao ate
        # que os dados da nova conta tenham sido lidos com sucesso.
        self.load_ok = False
        self._ultimo_sync = None

        if not os.path.exists(self.data_file):
            try:
                self._write_atomic('{"categories":[],"projects":[],"tasks":[],"notepad":[],"userProfile":{}}')
            except Exception as e:
                print(f"[NEXUS] Falha ao criar banco da conta: {e}")

    # ------------------------------------------------------------------ #
    # Nuvem: configuração, conta e status (expostos ao JS)
    # ------------------------------------------------------------------ #
    def cloud_status(self):
        r = self._cloud.resumo()
        r["lastSync"] = self._ultimo_sync
        return r

    def cloud_save_config(self, api_key, database_url):
        return self._cloud.salvar_config(api_key, database_url)

    def cloud_sign_up(self, email, password):
        r = self._cloud.criar_conta(email, password)
        if r.get("status") == "success":
            self._aplicar_caminhos_do_usuario()
            # Conta nova nao tem dado legado, mas marcamos para nao checar sempre.
            try:
                r["migracao"] = self._cloud.migrar_ramo_legado()
            except Exception as e:
                r["migracao"] = {"status": "error", "message": str(e)}
        return r

    def cloud_sign_in(self, email, password):
        r = self._cloud.entrar(email, password)
        if r.get("status") == "success":
            self._aplicar_caminhos_do_usuario()
            # Ponto exato da migracao de nuvem: temos UID e token validos, e
            # ainda nao lemos nada. Se falhar, o login continua valido.
            try:
                r["migracao"] = self._cloud.migrar_ramo_legado()
            except Exception as e:
                r["migracao"] = {"status": "error", "message": str(e)}
        return r

    def cloud_migrate_legacy(self):
        """Permite disparar a migração manualmente pela interface."""
        try:
            return self._cloud.migrar_ramo_legado()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def migration_report(self):
        """O que a migração de disco fez neste boot (None se nada fez)."""
        return self._migracao_disco

    def cloud_sign_out(self):
        r = self._cloud.sair()
        self._aplicar_caminhos_do_usuario()
        return r

    def cloud_push_now(self):
        """Envia o estado local atual para a nuvem, sob demanda."""
        try:
            if not os.path.exists(self.data_file):
                return {"status": "error", "message": "Nada local para enviar."}
            with open(self.data_file, "r", encoding="utf-8-sig") as f:
                dados = json.loads(f.read())
            res = self._cloud.enviar(dados)
            if res.get("status") == "success":
                self._ultimo_sync = time.strftime("%H:%M:%S")
            return res
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def cloud_pull_now(self):
        """Traz o que está na nuvem e substitui o local (ação explícita)."""
        res = self._cloud.baixar()
        if res.get("status") != "ok":
            return res
        try:
            texto = json.dumps(res["data"], ensure_ascii=False)
            self._write_atomic(texto)
            self._ultimo_sync = time.strftime("%H:%M:%S")
            return {"status": "success", "data": texto}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def _carimbo(d):
        """Lê o _meta.updatedAt de um dicionário de estado (0 se não houver)."""
        try:
            return int((d.get("_meta") or {}).get("updatedAt") or 0)
        except Exception:
            return 0

    @staticmethod
    def _peso(d):
        """
        Quantidade de conteúdo que o usuário realmente criou.

        Categorias ficam de fora de propósito: uma instalação nova gera a
        categoria "Geral" e a nota de boas-vindas sozinha. Se elas contassem,
        um app recém-instalado pareceria "cheio" e poderia sobrescrever a
        máquina que tem o trabalho de verdade.
        """
        try:
            tarefas = len(d.get("tasks") or [])
            projetos = len(d.get("projects") or [])
            notas = len(d.get("notepad") or [])
            # Desconta a nota de boas-vindas criada automaticamente.
            if notas == 1:
                titulo = str((d["notepad"][0] or {}).get("title", "")).lower()
                if "bem-vindo" in titulo:
                    notas = 0
            return tarefas + projetos + notas
        except Exception:
            return 0

    def set_window(self, window):
        self._window = window

    def get_db_path(self):
        return self.data_file

    def get_app_version(self):
        return APP_VERSION

    # ------------------------------------------------------------------ #
    # Notificações e Taskbar Badge (Windows)
    # ------------------------------------------------------------------ #
    def send_desktop_notification(self, title, message, sound=True):
        """Envia uma notificação Toast nativa no Windows para alertar sobre prazos."""
        try:
            WindowsNotifier.notify(title, message, sound=bool(sound))
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def update_taskbar_badge(self, count, description=""):
        """Atualiza ou remove o badge numérico no ícone do NEXUS na barra de tarefas do Windows."""
        try:
            win = self._window or (webview.windows[0] if webview.windows else None)
            TaskbarOverlayHelper.set_overlay(count, description, window=win)
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ------------------------------------------------------------------ #
    # Atualizacao automatica (expostos ao JS)
    # ------------------------------------------------------------------ #
    def _checar_update_em_background(self):
        """Espera o app abrir e so depois consulta o manifesto."""
        try:
            time.sleep(6)
            self._update_cache = self._updater.verificar(forcar=True)
        except Exception as e:
            self._update_cache = {"status": "error", "message": str(e),
                                  "current": APP_VERSION}

    def update_cached(self):
        """Resultado da checagem automatica. None enquanto nao terminou."""
        return self._update_cache

    def update_check_now(self):
        """Checagem manual, disparada pelo botao da interface."""
        try:
            self._update_cache = self._updater.verificar(forcar=True)
            return self._update_cache
        except Exception as e:
            return {"status": "error", "message": str(e), "current": APP_VERSION}

    def update_install(self):
        """Inicia download + verificacao + instalacao. Acompanhe via update_progress."""
        try:
            return self._updater.baixar_e_aplicar()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def update_progress(self):
        try:
            return self._updater.progresso()
        except Exception as e:
            return {"fase": "error", "pct": 0, "mensagem": str(e)}

    def update_channel_info(self):
        """Diagnostico: onde o app procura atualizacao e se o TLS esta ok."""
        return {
            "channel": UPDATE_CHANNEL,
            "manifest": UPDATE_MANIFEST_URL.split("?")[0],
            "tlsVerificavel": _ssl_ctx_strict is not None,
            "tlsDegradado": _TLS_DEGRADADO,
            "tlsMotivo": _TLS_MOTIVO,
            "pasta": self._updater.pasta,
        }

    def security_status(self):
        """
        Estado de seguranca da conexao, para a interface poder avisar.

        `tlsDegradado` vira True se em algum momento uma requisicao de DADOS
        teve de ser repetida sem verificar o certificado. Isso nunca acontece
        com login nem com atualizacao — esses recusam e falham. Mas o usuario
        precisa saber, porque significa que alguem ou alguma coisa esta no meio
        da conexao: antivirus com inspecao HTTPS, proxy corporativo, ou algo
        pior.
        """
        return {
            "tlsVerificavel": _ssl_ctx_strict is not None,
            "tlsDegradado": _TLS_DEGRADADO,
            "motivo": _TLS_MOTIVO,
            "authSempreVerificado": True,
        }

    def open_external(self, url):
        """Abre um link no navegador padrao (usado no fallback manual)."""
        try:
            u = str(url or "")
            if not (u.startswith("https://") or u.startswith("http://")):
                return {"status": "error", "message": "URL invalida."}
            import webbrowser
            webbrowser.open(u)
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ---------------------- avatar em arquivo separado ---------------------- #
    def _extract_avatar(self, parsed):
        """
        Se o objeto tiver um avatar embutido, grava-o à parte e deixa apenas um
        marcador no banco. Devolve True quando houve extração.
        """
        try:
            perfil = parsed.get("userProfile")
            if not isinstance(perfil, dict):
                return False
            av = perfil.get("avatar")
            if not isinstance(av, str) or not av or av == self.AVATAR_MARKER:
                return False

            with open(self.avatar_file + ".tmp", "w", encoding="utf-8") as f:
                f.write(av)
                f.flush()
                os.fsync(f.fileno())
            os.replace(self.avatar_file + ".tmp", self.avatar_file)
            perfil["avatar"] = self.AVATAR_MARKER
            return True
        except Exception as e:
            print(f"[NEXUS Avatar Write Warning] {e}")
            return False

    def get_avatar(self):
        """Carregado sob demanda, depois que a interface já renderizou."""
        try:
            if os.path.exists(self.avatar_file):
                with open(self.avatar_file, "r", encoding="utf-8") as f:
                    dado = f.read().strip()
                return dado or None
        except Exception as e:
            print(f"[NEXUS Avatar Read Warning] {e}")
        return None

    def clear_avatar(self):
        try:
            if os.path.exists(self.avatar_file):
                os.remove(self.avatar_file)
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _write_atomic(self, json_str):
        """
        Grava em .tmp no mesmo diretório e troca com os.replace(), que é atômico.
        Uma queda no meio da gravação deixa o arquivo antigo intacto em vez de
        um JSON truncado. Sem BOM na escrita: o BOM já é tratado na leitura.
        """
        tmp_file = self.data_file + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(json_str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, self.data_file)

    def save_state_to_disk(self, json_str):
        """Salva as tarefas, notas do Vault e configurações no arquivo JSON local com atomicidade."""
        try:
            if not self.load_ok:
                return {"status": "blocked",
                        "message": "Gravação bloqueada: o banco ainda não foi lido com sucesso."}

            if not json_str or not str(json_str).strip():
                return {"status": "error", "message": "Dados vazios não gravados."}

            # Valida antes de tocar no arquivo: um erro de serialização no
            # front-end nunca deve substituir um banco bom por lixo.
            try:
                parsed = json.loads(json_str)
            except json.JSONDecodeError as e:
                return {"status": "error", "message": f"JSON inválido: {e}"}

            if not isinstance(parsed, dict):
                return {"status": "error", "message": "A raiz precisa ser um objeto JSON."}

            # Se o front-end mandou um avatar embutido (troca de foto), ele sai
            # para o arquivo próprio antes da gravação: o banco fica sempre leve.
            self._extract_avatar(parsed)

            # Carimbo de atualização: é o que decide quem vence quando o mesmo
            # usuário mexe no app em duas máquinas diferentes.
            parsed["_meta"] = {"updatedAt": int(time.time() * 1000),
                               "app": APP_NAMESPACE, "version": APP_VERSION}
            json_str = json.dumps(parsed, ensure_ascii=False)

            # Preserva a versão anterior antes de sobrescrever.
            try:
                if os.path.exists(self.data_file) and os.path.getsize(self.data_file) > 0:
                    import shutil
                    shutil.copyfile(self.data_file, self.backup_file)
            except Exception:
                pass

            # O disco vem primeiro: se a rede falhar, os dados já estão salvos.
            self._write_atomic(json_str)

            resultado = {"status": "success", "file": self.data_file,
                         "bytes": len(json_str.encode("utf-8")), "cloud": "off"}

            if self._cloud.configurado and self._cloud.logado:
                envio = self._cloud.enviar(parsed)
                resultado["cloud"] = envio.get("status", "error")
                if envio.get("status") == "success":
                    self._ultimo_sync = time.strftime("%H:%M:%S")
                    resultado["lastSync"] = self._ultimo_sync
                else:
                    # Sem rede não é erro: o local está gravado e sobe depois.
                    resultado["cloudMessage"] = envio.get("message", "")
            return resultado
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def load_state_from_disk(self):
        """
        Lê os dados locais diretamente do disco no boot da aplicação.
        Retorna sempre um dicionário com 'status', para que o front-end
        diferencie "banco vazio" de "falha na leitura" — é essa distinção
        que impede o app de sobrescrever dados bons com um estado vazio.
        """
        self.load_ok = False
        vazio = '{"categories":[],"projects":[],"tasks":[],"notepad":[],"userProfile":{}}'

        try:
            if not os.path.exists(self.data_file):
                self._write_atomic(vazio)
                self.load_ok = True
                return {"status": "empty", "data": vazio, "file": self.data_file}

            with open(self.data_file, "r", encoding="utf-8-sig") as f:
                content = f.read()

            if not content or not content.strip():
                self.load_ok = True
                return {"status": "empty", "data": vazio, "file": self.data_file}

            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as e:
                # Tenta o backup antes de desistir.
                try:
                    if os.path.exists(self.backup_file):
                        with open(self.backup_file, "r", encoding="utf-8-sig") as f:
                            bkp = f.read()
                        json.loads(bkp)
                        self.load_ok = True
                        return {"status": "ok", "data": bkp, "file": self.data_file,
                                "recovered": True}
                except Exception:
                    pass

                # Preserva o arquivo problemático em vez de apagá-lo.
                quarentena = None
                try:
                    import datetime
                    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    quarentena = f"{self.data_file}.corrupt_{stamp}"
                    os.replace(self.data_file, quarentena)
                except Exception:
                    pass

                return {"status": "corrupt", "file": self.data_file,
                        "quarantine": quarentena,
                        "message": f"JSON inválido na linha {e.lineno}, coluna {e.colno}."}

            if not isinstance(parsed, dict):
                return {"status": "corrupt", "file": self.data_file,
                        "message": "A raiz do arquivo não é um objeto JSON."}

            # Migração/otimização: tira o avatar embutido e regrava o banco
            # enxuto, para que a ponte transfira poucos KB em vez de MB.
            if self._extract_avatar(parsed):
                content = json.dumps(parsed, ensure_ascii=False)
                try:
                    self._write_atomic(content)
                except Exception as e:
                    print(f"[NEXUS Avatar Split Warning] {e}")

            self.load_ok = True

            # ---------------- Reconciliação com a nuvem ----------------
            # Regras, em ordem:
            #   1) lado vazio nunca substitui lado com conteúdo;
            #   2) entre dois lados com conteúdo, vence o carimbo mais recente;
            #   3) qualquer falha de rede é ignorada — o local segue valendo.
            cloud_info = {"state": "off"}
            if self._cloud.configurado and self._cloud.logado:
                res = self._cloud.baixar()
                estado = res.get("status")

                if estado == "ok":
                    remoto = res["data"]
                    t_local, t_remoto = self._carimbo(parsed), self._carimbo(remoto)
                    p_local, p_remoto = self._peso(parsed), self._peso(remoto)

                    if t_remoto > t_local and p_remoto >= p_local:
                        # Nuvem mais nova e não menor: adota a nuvem.
                        content = json.dumps(remoto, ensure_ascii=False)
                        parsed = remoto
                        try:
                            self._write_atomic(content)
                        except Exception as e:
                            print(f"[Cloud] Falha ao gravar cache local: {e}")
                        cloud_info = {"state": "pulled", "at": time.strftime("%H:%M:%S"),
                                      "items": p_remoto}

                    elif t_remoto > t_local and p_remoto < p_local:
                        # Nuvem mais nova PORÉM com menos conteúdo. É o caso
                        # clássico de um app recém-instalado em outra máquina
                        # ter subido um banco quase vazio. Aqui não se decide
                        # sozinho: mantém o local e avisa o usuário.
                        cloud_info = {"state": "conflict",
                                      "at": time.strftime("%H:%M:%S"),
                                      "localItems": p_local, "cloudItems": p_remoto}

                    elif t_local > t_remoto:
                        if p_local >= p_remoto:
                            env = self._cloud.enviar(parsed)
                            cloud_info = {"state": "pushed" if env.get("status") == "success" else "push_failed",
                                          "at": time.strftime("%H:%M:%S"),
                                          "items": p_local, "message": env.get("message", "")}
                        else:
                            # Local mais novo mas com menos conteúdo: mesma
                            # cautela, na direção contrária.
                            cloud_info = {"state": "conflict",
                                          "at": time.strftime("%H:%M:%S"),
                                          "localItems": p_local, "cloudItems": p_remoto}
                    else:
                        cloud_info = {"state": "in_sync", "at": time.strftime("%H:%M:%S")}

                elif estado == "empty":
                    # Primeira sincronização desta conta: semeia a nuvem.
                    env = self._cloud.enviar(parsed)
                    cloud_info = {"state": "seeded" if env.get("status") == "success" else "push_failed",
                                  "at": time.strftime("%H:%M:%S"),
                                  "message": env.get("message", "")}
                else:
                    cloud_info = {"state": estado or "error",
                                  "message": res.get("message", "")}

                if cloud_info.get("at"):
                    self._ultimo_sync = cloud_info["at"]

            return {
                "status": "ok",
                "data": content,
                "file": self.data_file,
                "hasAvatar": os.path.exists(self.avatar_file),
                "cloud": cloud_info,
                "account": self._cloud.resumo(),
                "stats": {
                    "tasks": len(parsed.get("tasks") or []),
                    "projects": len(parsed.get("projects") or []),
                    "categories": len(parsed.get("categories") or []),
                    "notepad": len(parsed.get("notepad") or []),
                },
            }
        except Exception as e:
            print(f"[NEXUS DB Read Error] {e}")
            return {"status": "error", "file": self.data_file, "message": str(e)}

    def save_file_native(self, content, default_name, file_format):
        try:
            win = self._window or (webview.windows[0] if webview.windows else None)
            if not win:
                return {"status": "error", "message": "Janela não inicializada."}
            
            file_types = ('CSV Files (*.csv)', 'All Files (*.*)') if file_format == "csv" else ('Excel Files (*.xlsx)', 'All Files (*.*)')
            result = win.create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=default_name,
                file_types=file_types
            )
            if result:
                save_path = result if isinstance(result, str) else result[0]
                with open(save_path, "w", encoding="utf-8-sig") as f:
                    f.write(content)
                return {"status": "success", "path": save_path}
            return {"status": "cancelled"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def pick_file_native(self):
        try:
            win = self._window or (webview.windows[0] if webview.windows else None)
            if not win:
                return {"status": "error", "message": "Janela não inicializada."}

            result = win.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False)
            if result:
                file_path = result[0] if isinstance(result, (list, tuple)) else result
                file_path = os.path.normpath(file_path)
                return {
                    "status": "success",
                    "path": file_path,
                    "name": os.path.basename(file_path),
                    "size": os.path.getsize(file_path) if os.path.exists(file_path) else 0
                }
            return {"status": "cancelled"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # Extensoes que o Windows EXECUTA em vez de abrir. os.startfile() nelas
    # equivale a rodar codigo. Como o caminho vem do banco (que sincroniza da
    # nuvem) e da interface (que renderiza HTML), tratamos como nao-confiavel.
    EXTENSOES_EXECUTAVEIS = {
        ".exe", ".com", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe",
        ".js", ".jse", ".wsf", ".wsh", ".msi", ".msp", ".scr", ".pif",
        ".hta", ".cpl", ".jar", ".reg", ".lnk", ".url", ".inf", ".application",
        ".gadget", ".msc", ".sct", ".shb", ".shs", ".ws",
    }

    def open_external_target(self, target_path):
        try:
            if not target_path:
                return {"status": "error", "message": "Caminho não informado."}
            target_str = str(target_path).strip('"\'')

            if target_str.lower().startswith(("http://", "https://")):
                import webbrowser
                webbrowser.open(target_str)
            elif ":" in target_str.split("\\")[0].split("/")[0][2:]:
                # Bloqueia esquemas como file:, javascript:, ms-msdt:, search-ms:
                # Um caminho do Windows tem ':' so na posicao 1 (C:\...).
                return {"status": "error",
                        "message": "Tipo de link não permitido por segurança."}
            else:
                clean_path = os.path.normpath(target_str)

                ext = os.path.splitext(clean_path)[1].lower()
                if ext in self.EXTENSOES_EXECUTAVEIS:
                    return {"status": "error",
                            "message": f"Por segurança, o NEXUS não abre arquivos "
                                       f"'{ext}', que o Windows executaria como "
                                       f"programa.\n\nAbra manualmente se confia "
                                       f"na origem:\n{clean_path}"}

                if os.path.exists(clean_path):
                    if sys.platform == "win32":
                        os.startfile(clean_path)
                    elif sys.platform == "darwin":
                        import subprocess
                        subprocess.call(["open", clean_path])
                    else:
                        import subprocess
                        subprocess.call(["xdg-open", clean_path])
                else:
                    return {"status": "error", "message": f"Arquivo não encontrado no disco:\n{clean_path}"}
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

HTML_CONTENT = r"""<!DOCTYPE html>
<html lang="pt-BR" class="dark h-full">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NEXUS</title>

    <!-- ===================================================================
         POLITICA DE SEGURANCA DE CONTEUDO (CSP)
         ===================================================================
         Nao elimina XSS sozinha — o app tem todo o JS inline, entao
         'unsafe-inline' e inevitavel sem uma reescrita grande. O que ela FAZ:

           script-src  -> um <script src="http://site-do-atacante/x.js">
                          injetado numa nota nao carrega.
           connect-src -> impede que codigo injetado exfiltre suas tarefas
                          para um servidor de terceiros via fetch.
           object-src  -> mata <object>, <embed>, <applet>.
           base-uri    -> impede sequestro de URLs relativas via <base>.
           form-action -> impede que um <form> injetado poste seus dados fora.
    -->
    <meta http-equiv="Content-Security-Policy" content="
        default-src 'self';
        script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net;
        style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com;
        font-src 'self' data: https://cdnjs.cloudflare.com https://fonts.gstatic.com;
        img-src 'self' data: blob:;
        connect-src 'self' https://cogni-data-default-rtdb.firebaseio.com https://identitytoolkit.googleapis.com https://securetoken.googleapis.com;
        object-src 'none';
        base-uri 'none';
        form-action 'none';
        frame-src 'none';
    ">

    <!-- VERSOES FIXAS. 'npm/chart.js' sem versao entrega o que o CDN quiser
         hoje: uma versao nova quebra o app sem aviso, e um pacote comprometido
         vira execucao de codigo com acesso a ponte pywebview. Sempre fixe.

         MELHOR AINDA: baixe estes 4 arquivos para uma pasta assets\ e
         referencie localmente. O app passa a funcionar offline e deixa de
         depender de tres CDNs de terceiros. Veja COMO_PUBLICAR.md. -->
    <script src="https://cdn.tailwindcss.com/3.4.5"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>

    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: { 
                extend: { 
                    colors: {
                        notion: {
                            bg: '#191919',
                            sidebar: '#202020',
                            card: '#222222',
                            hover: 'rgba(255, 255, 255, 0.055)',
                            border: '#2f2f2f',
                            accent: '#2eaadc',
                            purple: '#7053ff',
                            text: '#d3d3d3',
                            subtext: '#8a8a8e'
                        }
                    }
                }
            }
        }
    </script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
        
        html, body {
            height: 100% !important;
            width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
            /* Base do app inteiro. As classes text-xs / text-[10px] do Tailwind
               são relativas a este valor, então subir aqui aumenta tudo junto,
               mantendo as proporções entre título, rótulo e legenda. */
            font-size: 16px;
        }

        /* ---------- Arredondamento global ----------
           O app usava cantos de 3-4px. Aqui todos os elementos ganham um raio
           maior de uma vez, sem precisar reescrever classe por classe. */
        .rounded-sm  { border-radius: 6px !important; }
        .rounded     { border-radius: 9px !important; }
        .rounded-md  { border-radius: 10px !important; }
        .rounded-lg  { border-radius: 12px !important; }
        .rounded-xl  { border-radius: 14px !important; }
        .rounded-2xl { border-radius: 18px !important; }
        .notion-card { border-radius: 12px !important; }
        input:not([type="checkbox"]):not([type="radio"]),
        select, textarea, button { border-radius: 9px; }
        /* Caixas de seleção e botões redondos continuam circulares */
        .rounded-full { border-radius: 9999px !important; }
        /* As caixinhas de marcar (16px) ficariam um círculo com raio 9px.
           Aqui elas viram quadrados bem arredondados, que é o efeito desejado. */
        .rounded.border.w-4, .rounded.border.w-3\.5, .rounded.border.w-5 { border-radius: 6px !important; }
        input[type="checkbox"] { border-radius: 6px; }
        body {
            font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", sans-serif;
            background-color: #191919;
            color: #d3d3d3;
            user-select: none;
        }

        .notion-btn {
            background-color: transparent;
            border: 1px solid transparent;
            transition: all 0.12s ease-in-out;
            color: #b4b4b4;
        }
        .notion-btn:hover {
            background-color: rgba(255, 255, 255, 0.055);
            color: #efefef;
        }
        .notion-btn.active {
            background-color: rgba(255, 255, 255, 0.08);
            color: #ffffff;
            font-weight: 600;
        }

        /* ---------- Árvore do Vault: linhas-guia ----------
           Cada nível desenha um segmento vertical ligando o pai aos filhos e
           um "cotovelo" horizontal até cada item, para dar de bater o olho e
           saber de qual ramo cada nota faz parte. */
        :root { --tree-line: #3a3a3a; --tree-line-ativa: #2eaadc; --tree-indent: 16px; }

        .note-node     { position: relative; }
        .note-row-wrap { position: relative; }
        /* Todo o recuo de nível vem daqui, um único lugar. */
        .note-children { position: relative; padding-left: var(--tree-indent); }

        /* As linhas são puramente decorativas: sem pointer-events elas ficavam
           POR CIMA do chevron (são pseudo-elementos posicionados) e engoliam o
           clique de recolher em toda nota aninhada. */
        .note-node::before, .note-node::after,
        .note-row-wrap::before, .note-row-wrap::after { pointer-events: none; }

        /* Linha que atravessa o nó inteiro, ligando este filho ao próximo. */
        .note-children > .note-node:not(:last-child)::before {
            content: '';
            position: absolute;
            left: 7px; top: 0; bottom: 0;
            width: 1px;
            background: var(--tree-line);
        }
        /* No último filho a linha desce só até o meio da linha e fecha o ramo. */
        .note-children > .note-node:last-child > .note-row-wrap::before {
            content: '';
            position: absolute;
            left: 7px; top: 0;
            height: 50%;
            width: 1px;
            background: var(--tree-line);
        }
        /* Cotovelo horizontal, sempre no centro vertical da linha (top:50%),
           então acompanha qualquer mudança de altura ou de tamanho de fonte. */
        .note-children > .note-node > .note-row-wrap::after {
            content: '';
            position: absolute;
            left: 7px; top: 50%;
            width: 9px; height: 1px;
            background: var(--tree-line);
        }
        /* Ramo da nota aberta fica destacado */
        .note-node.no-caminho > .note-row-wrap::after,
        .note-node.no-caminho > .note-row-wrap::before,
        .note-node.no-caminho:not(:last-child)::before { background: var(--tree-line-ativa); }

        .note-toggle {
            width: 18px; height: 18px;
            display: flex; align-items: center; justify-content: center;
            border-radius: 5px;
            color: #8a8a8e;
            flex-shrink: 0;
            /* Fica acima de qualquer decoração e garante o próprio alvo de clique */
            position: relative;
            z-index: 2;
            pointer-events: auto;
            transition: transform .15s ease, background-color .12s ease, color .12s ease;
        }
        .note-toggle:hover { background: rgba(255,255,255,0.09); color: #fff; }
        .note-toggle.recolhido { transform: rotate(-90deg); }
        .note-toggle-vazio { width: 18px; flex-shrink: 0; }

        /* Contador de subnotas escondidas */
        .note-badge-filhos {
            font-size: 9px;
            font-family: ui-monospace, "JetBrains Mono", monospace;
            background: rgba(46,170,220,0.14);
            color: #7fd0ef;
            border: 1px solid rgba(46,170,220,0.25);
            border-radius: 999px;
            padding: 0 5px;
            line-height: 15px;
            flex-shrink: 0;
        }

        .notion-card {
            background-color: #202020;
            border: 1px solid #2f2f2f;
            transition: all 0.15s ease-in-out;
        }
        .notion-card:hover {
            border-color: rgba(255, 255, 255, 0.18);
            background-color: #242424;
        }
        .notion-card.selected {
            border-color: #2eaadc;
            background-color: rgba(46, 170, 220, 0.08);
        }

        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #333333; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #444444; }

        #noteEditorBody:empty:before {
            content: attr(placeholder);
            color: #55555e;
            pointer-events: none;
            display: block;
        }
        #noteEditorBody h1 { font-size: 1.75rem; font-weight: 700; margin-top: 1rem; margin-bottom: 0.5rem; color: #ffffff; border-bottom: 1px solid #2f2f2f; padding-bottom: 0.25rem; }
        #noteEditorBody h2 { font-size: 1.35rem; font-weight: 600; margin-top: 0.75rem; margin-bottom: 0.35rem; color: #f0f0f3; }
        #noteEditorBody ul { list-style-type: disc; margin-left: 1.5rem; margin-top: 0.3rem; margin-bottom: 0.3rem; }
        #noteEditorBody ol { list-style-type: decimal; margin-left: 1.5rem; margin-top: 0.3rem; margin-bottom: 0.3rem; }
        #noteEditorBody blockquote { border-left: 3px solid #2eaadc; padding-left: 0.75rem; color: #9b9b9b; font-style: italic; margin: 0.5rem 0; }
        #noteEditorBody mark { background: rgba(234, 179, 8, 0.25); color: #fef08a; padding: 0.1rem 0.3rem; border-radius: 3px; }
        #noteEditorBody code { font-family: 'JetBrains Mono', monospace; background: #282828; padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.88em; color: #e2e2e2; }
    </style>
</head>
<body class="h-full w-full flex flex-col antialiased overflow-hidden select-none bg-[#191919] text-[#d3d3d3]">

    <!-- HEADER ESTILO NOTION -->
    <header class="h-12 bg-[#202020] border-b border-[#2f2f2f] px-4 flex items-center justify-between z-30 select-none flex-shrink-0 w-full">
        <div class="flex items-center gap-2.5">
            <div class="w-6 h-6 flex items-center justify-center bg-transparent flex-shrink-0">
                <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAYAAADimHc4AAAK+0lEQVR42u2da6xdRRXH/+vce6GWUh6JyKNAC1KNaUqBgopo1EQoIK9gDIm1mOADHzGG4BfBEHwgEI0xGI1fRHm0QvCDAiYQRRGQGgm+EPoAUcFaobRQQik9j58fzhozjnufs/d53HPO7Z7k5t59z5y9Z6//zH89ZmaNVJWRFpvERgOW0XbMjAqA4Qp+ytvcMrNW8llNUs2BaFYADF7wCoL160MkzfcquyQ9l3yuSQDCxlzwNUk1M2v49UpJZ0haLmmJpIO86g5JT0v6k6R7zOwRrz+dNVqqUoDjgZnoejlwE7CV7mWr110RfX/G9UZVCgh/2nu+gCOBLwPbIgHvAepAI/mp+2ehbAO+ChwVRpOPiKrk8XzgbuB1wCeAxyOB1oFmgRHQ9LqhPAF8EpifPqcqSc/0v88EfpkIvkX50kpGxP3A2RHI/x1pFc+3r08AbgZejQTfKNDbu42KRjQidgO3ACfutfrBBR/z/BHO1c/nUEieUJsJEN3AiilsG3ANsChpk+1NPL+f8/xfStBN3JvrbvFsTf7X6EJLMbiPu35YMKf1g3N7TDergF8llk2zBJ//GrgIONp/LnKOj+/X6kJdqX44K4wAp6XanKGb6PpE4Id99NiNwGdCj02etR/wKWBDHyPqZuCkxCS2SRX+dNSjDnPO3VqC52PO3g5cCyxO9UiwoiKdcrQ/64WSzwod4d/+rMOzOtGk8HwwK/cHPuo9tww9BIG9BtxWxGrJsKpWAD/yexTxI1Ka2wx8HFgYdaipcef5mG7eD/yihCOV9tT7gfOzPOSS7Tg3w68o0477gHPLtmPUcZtbStjzac97yrn8gH56XjISF7rFtbnHkbgbWDt28aUucZuy3Ps88PVgm0fRzEHqosOB64HnMpRwEV30wljElwrGbYr2rob3rlOGNcwzrLGVPkobPVpjo4sv9Rm3Se3vh1xX1GbD/o79EQflbOCBPvyREF+qDWrEFupFwLKScZs8e37/lK9nkTrDCF4AfLoP/yHEl5ZF72LDEH5o8MXAlhIc2kjs+esiDh1ZDCZ9tuuwa/vwH7YAFw8chET4l0cP3FOil7wGrPMpxbGKQmZYcSe5TtrdgxXXAD4/UBAi4V+SzD4V5ckHgXOSOPzYOTSJ2TrluumBEmZrPEt3SSy7QQj/VKePImHfUDbFcZtJiTRmRGzT+FIRut0OnNoXCD40a04VP456QaeeD/BP4CvAGyc51p7oh2OBLwHPJu+aVYKM7ghWXU/vHvWC44Ed/tBunI/z54H+3Xkxv05gQHEG2Nf/PsCtHQrohJbL7PieR0HEh1dGHFdkHrYF/BH4yLjzfgl9cLG/U7dOSCKrK3ryDyL6MeCuEgCkw/Nu4J1Jj6qNseDTiaPT/B1aBagnC4A7w31LNyQado8WGHZZdBTqvwx8G1g6yBjPkDl/KXADsDPjfYq+Py67haVBSAJsT0SOSdllIbFH+Tf3Iw4YJ6sosXoWApd5W7PeoWhpRjGjI/sBYHE0mdIs4A0W8QvWAxdGHDsS/ZCsR5oGLgAeLmH3d/KHmlHIZXEnAPrl45akaUlTkhqSstbnm6QZSU2v81ZJ6yStA04xs4aZNWfLMw6er5m1zKwBnCzpVkm3SXqbt7Hpbc5qD15nyt+9r4W/vQIQBP2MpKskbfLG0AGI0OCmP/cDku71+PxRZlaXNDSfIQommpnVgUXAdZLukfRBb1Mj6lB5gsfrbJZ0tctAOe/c+/DsQkExxx0MLHFFW0ZpxcN3g3ucQ/GaM7zbSyPdVsTCS42K77hzdnCOjixMQf0CsAk4LvreO9xsbRWMr2etz1k1KLM1w6w8PZm/KNu+nwGnRfc7zmUwMgA2ep0asE+k0D4cma9l4+t7gB8ELzI1EXucAVsOfD8SZtn5i9+7MxaU9j7+zoXkM3QA4mEeDfU3AF+I1gK1Ss6/bgGuBg7JEmrBeerXA1d5fKpMjL8VrRG6Ejg09pCjdxwrAGo58fU3AzcCr/Rotj7mI2pep/nixKycB3wI+HOPZuUuX8H3lqz5i37kM3QAsgTi16uAe/tYn3MX8N60p2c85z3AnX085+fAWZ0WCEwEADmBrQU9rJSLe+ZO4HvAsRnPOQb4LvBSjyNtM/CxyBLLdRAnCoCcWMthPv/6XEmzNQD1rIc1DgIO9PDBMyV0TSNZj3R9mbWgEwlAh/U5a6P7FVm/mS5fLLssph7da517wqWsrUHKZ1ZDw2aGu/81Dwc8Imm1pAskrXcPsyap3iGsEdz/hqR3SXq3/x3CInnhg7rfe1rSb/2Zq83sd8Hf8LDIrKY7GEls3uMw9Sg08FO1N2BfJukpj8PIBZvX7hDWaEbAZZVwjxm1N3NfLukMM/tJu2MybWb1UW3mHunkiO+AbzkQL5vZNyWdLulbkl5JhKyc+FJeyCIGZ5ekGySdbmbfkLTTn0nYhT+qMvLZqUBLwdY2s7+a2eckrZJ0ZyToRsHIYyuKVpqkuyWtMrPPmtmTwUcZBd2MJQAJEPVgtprZQx4xXSPp0Yhm6BKlDfT0B//uhWb2YDArnW7GJq3N2M3PmlnTFfWUpIaZrXVaukLSFu/V5AjfJP1L0hclvc/MbpVUd0Ab45g9ZWz3PvkkTTBbt5vZNcDDPnlyqFNNLaKdIPzVZnZf9N3mqHl+okZAjn4IXukGSS/mmJrmnz3hdafHhecnFoDYonH6mN9l1E5Lmu91JyJr1qRtRm4WUMLNSXqhvTdbSAVAVSoAKgCqUgFQAVABUJUKgAqAqlQATGxhmAA01XkSZB9J83LSyc/lYv7O8yTt26FeS11CI90A2Cnp1QykzW+8SNIKjzjO7BXdvS34GX/nE1wGraQDBlntkvRSLwDgyyh2qj0JkgWA1I4+XgYsMbPdk7YbsgfhhzD3bmCJ2osIwr6ILAC2mNlOX3HRKgyAo1vz3+tz2jPlyJ8s6Q7g/Gi3y5xKCxyWP/psXR04T9Idkla6DPI2dKzvWddGK4CX+6bjvDTBcfKO24eRFnjoK9E60E1GeuXbokSAjQ7plHcAy2NZ9oy8r9fvlKogKyXN4uglpicNgGSZ+2Lga0kqm0aXVAU3+gKDWr+cFxI0bemynSddNjiwZB2zCUBOso6NBZc/xrmDlvXV++Oe4L/XRCuOZzVdzWwAMMB0NXVgTSy7QfDgSBM2DROAnIRN65KEr2USNl0egTiUrFlrZjtl2ZCWy+elLNs+VinL0gZHOmHWkvYNGoAhJ+0bbm6kIaStPKdb2spBATDRaSs7WAr9Jm5tdkvc2i8AcypxawdbeWipi/vctTn3Uhd3sSKGkbx7pgcAZvjf5N2XAk+WMCvHP3l3ltccXQ86fX3Nd0J2A+CYhH7OYy6nr+/i0AziAIfbg/9A+8SlTV1yVxzhdU9kbzrAIUc/DOoIkxc9bcHJkbmYBcAGV7BXeTCsF1002UeY5PkOUa/s5xCfv0eCbWUkCtwBPN2jPT+3DvHJs7/9updjrIpmbezFH5mbx1gViDSWPcit2eXzVkkg946D3HJiMP0cZdhLqY4yLDDbVPYwz6I5PKvDPIv4D1TH2Y6NfqgOdB6x/1DkSPNmhtCrI82HGF+6KXLk6JBnaKvXHd+4TVRszIGoqb0+KeSSOEntrCrLJb1d0lFe9R+SfiPpMUn3eBqcEE1tjSoTysQDEOsHqb17PgJmqaQ3eZWNkjaGTdlp/XEuk3asSMiA8n+9OowWtVPQTMxe4Ym0f6PV2HGuCMY9LUFVxrD8B8dhzR63a2DrAAAAAElFTkSuQmCC" alt="NEXUS" class="w-full h-full object-contain">
            </div>
            <span class="font-bold text-sm tracking-wide text-white">NEXUS</span>
            <button id="app-version-badge" onclick="abrirUpdateModal()" title="Ver atualizacoes" class="text-[10px] text-[#8a8a8e] font-mono px-1.5 py-0.5 rounded bg-white/5 border border-white/5 hover:text-white hover:border-white/20 transition cursor-pointer">v6.2.0</button>
            <button id="updateDot" onclick="abrirUpdateModal()" title="Nova versao disponivel" class="hidden items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded bg-[#2eaadc]/20 border border-[#2eaadc]/40 text-sky-200 cursor-pointer animate-pulse">
                <i class="fa-solid fa-arrow-up text-[8px]"></i><span id="updateDotLabel">novo</span>
            </button>
        </div>

        <!-- Status ÚNICO: representa o banco na nuvem (Firebase), não mais o
             arquivo local. Clicar abre o painel de sincronização. -->
        <div id="dbStatusBar" class="hidden md:flex items-center gap-2.5 bg-white/5 border border-white/5 px-3 py-1 rounded text-xs font-mono select-none" title="Banco de dados na nuvem">
            <span id="status-dot-indicator" class="w-2 h-2 rounded-full bg-emerald-500 shadow-sm"></span>
            <i id="cloudBadgeIcon" class="fa-solid fa-cloud text-[11px] text-gray-500"></i>
            <span id="db-filepath-text" class="text-[#8a8a8e] font-medium truncate max-w-[300px]">Conectando...</span>
            <span class="text-gray-600">•</span>
            <span id="status-save-label" class="text-gray-400 font-sans text-[11px]">Pronto</span>
        </div>

        <div class="flex items-center gap-1.5">
            <!-- Botão de Notificações / Sino de Vencimentos -->
            <div class="relative">
                <button id="notifBellBtn" onclick="toggleNotificationPanel()" class="notion-btn px-2.5 py-1 rounded text-xs text-gray-300 hover:text-white flex items-center gap-1.5 cursor-pointer relative" title="Central de Notificações de Prazos">
                    <i id="notifBellIcon" class="fa-regular fa-bell text-xs"></i>
                    <span class="hidden sm:inline">Prazos</span>
                    <span id="notifBadgeCount" class="hidden absolute -top-1.5 -right-1.5 px-1.5 py-0.2 bg-rose-600 text-white font-bold text-[9px] rounded-full border border-[#202020] shadow-sm">0</span>
                </button>
            </div>

            <button onclick="executeDiskSave(true)" class="notion-btn px-2.5 py-1 rounded text-xs text-gray-300 hover:text-white flex items-center gap-1.5 cursor-pointer" title="Salvar no Disco">
                <i class="fa-regular fa-floppy-disk text-xs"></i> <span>Salvar</span>
            </button>
            <button onclick="exportDatabaseToCSV()" class="notion-btn px-2.5 py-1 rounded text-xs text-gray-300 hover:text-white flex items-center gap-1.5 cursor-pointer" title="Exportar CSV">
                <i class="fa-solid fa-file-export text-xs"></i> <span>Exportar CSV</span>
            </button>
            <button onclick="triggerImportCSV()" class="notion-btn px-2.5 py-1 rounded text-xs text-sky-400 hover:text-white flex items-center gap-1.5 cursor-pointer" title="Importar CSV">
                <i class="fa-solid fa-file-import text-xs"></i> <span>Importar CSV</span>
            </button>
            <input type="file" id="csvFileInput" accept=".csv" class="hidden" onchange="importDatabaseFromCSVFile(event)">
        </div>
    </header>

    <!-- BARRA DE AÇÕES EM MASSA (MULTI-SELEÇÃO) -->
    <div id="batch-actions-bar" class="hidden bg-[#242428] border-b border-[#2eaadc]/40 px-6 py-2 flex items-center justify-between text-xs transition-all z-20">
        <div class="flex items-center gap-3">
            <span class="font-bold text-sky-300"><i class="fa-solid fa-check-double mr-1.5"></i> <span id="batch-selected-count">0 itens selecionados</span></span>
            <button onclick="clearAllSelections()" class="text-gray-400 hover:text-white cursor-pointer underline">Limpar Seleção</button>
        </div>
        <div class="flex items-center gap-2">
            <button onclick="batchSetMyDay(true)" class="notion-btn px-3 py-1 bg-amber-600/20 border border-amber-500/30 text-amber-300 hover:bg-amber-600/40 rounded cursor-pointer" title="Adicionar as tarefas selecionadas ao Meu Dia">
                <i class="fa-regular fa-sun mr-1"></i> Add ao Meu Dia
            </button>
            <button onclick="batchSetMyDay(false)" class="notion-btn px-3 py-1 bg-white/5 border border-white/10 text-gray-300 hover:bg-white/10 rounded cursor-pointer" title="Remover as tarefas selecionadas do Meu Dia">
                <i class="fa-regular fa-circle-xmark mr-1"></i> Remover do Meu Dia
            </button>
            <button onclick="batchMarkDone()" class="notion-btn px-3 py-1 bg-emerald-600/20 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-600/40 rounded cursor-pointer">
                <i class="fa-solid fa-check mr-1"></i> Concluir Tarefas
            </button>
            <button onclick="batchDeleteSelectedItems()" class="notion-btn px-3 py-1 bg-rose-600/20 border border-rose-500/30 text-rose-300 hover:bg-rose-600/40 rounded cursor-pointer">
                <i class="fa-regular fa-trash-can mr-1"></i> Excluir Selecionados
            </button>
        </div>
    </div>

    <!-- MAIN APP WRAPPER -->
    <div class="flex-1 flex flex-col md:flex-row overflow-hidden w-full h-[calc(100vh-3rem)] relative">
        
        <!-- SIDEBAR ESTILO NOTION -->
        <aside class="w-64 bg-[#202020] border-r border-[#2f2f2f] flex flex-col flex-shrink-0 z-20 h-full select-none">
            <div class="p-3 border-b border-[#2f2f2f] flex flex-col gap-2.5">
                <div class="notion-btn rounded p-2 flex items-center justify-between cursor-pointer group hover:bg-white/5 transition" onclick="openProfileModal()">
                    <div class="flex items-center gap-2.5 truncate">
                        <div class="w-8 h-8 rounded bg-white/5 border border-white/10 flex items-center justify-center text-white font-bold text-xs flex-shrink-0 overflow-hidden relative">
                            <img id="profile-avatar-img" src="" class="w-full h-full object-cover hidden" alt="Avatar">
                            <span id="profile-initials-sidebar">CA</span>
                        </div>
                        <div class="truncate">
                            <h2 id="profile-name" class="font-bold text-xs leading-tight text-white tracking-wide truncate">Caio</h2>
                            <span id="profile-subtitle" class="text-[10px] text-[#8a8a8e] font-semibold uppercase block truncate">DEV</span>
                        </div>
                    </div>
                    <i class="fa-solid fa-gear text-xs text-gray-500 group-hover:text-gray-300 transition"></i>
                </div>

                <div class="grid grid-cols-2 gap-1 p-0.5 rounded bg-white/5 border border-white/5 text-xs font-semibold">
                    <button id="mode-btn-tasks" onclick="switchAppMode('tasks')" class="py-1.5 rounded flex items-center justify-center gap-1.5 bg-[#2a2a2a] text-white border border-white/10 transition cursor-pointer">
                        <i class="fa-solid fa-list-check text-xs"></i> Tarefas
                    </button>
                    <button id="mode-btn-notepad" onclick="switchAppMode('notepad')" class="py-1.5 rounded flex items-center justify-center gap-1.5 text-gray-400 hover:text-white transition cursor-pointer">
                        <i class="fa-solid fa-book-bookmark text-xs"></i> Vault
                    </button>
                </div>
            </div>

            <div id="sidebar-tasks-panel" class="flex-1 overflow-y-auto p-2 space-y-0.5 text-xs">
                <div class="pb-1.5">
                    <div class="relative">
                        <i class="fa-solid fa-magnifying-glass absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 text-xs"></i>
                        <input type="text" id="searchInput" oninput="debouncedRenderTasksList()" placeholder="Buscar tarefas..." class="w-full pl-8 pr-2.5 py-1.5 bg-white/5 hover:bg-white/10 focus:bg-white/10 border border-transparent focus:border-white/20 rounded text-xs text-gray-200 placeholder-gray-500 focus:outline-none transition">
                    </div>
                </div>

                <button onclick="selectList('myday')" id="nav-myday" class="nav-btn notion-btn active w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded font-medium text-gray-300 cursor-pointer">
                    <i class="fa-regular fa-sun text-xs w-4 text-center text-amber-400"></i> <span class="flex-1 text-left">Meu Dia</span> <span id="badge-myday" class="text-[11px] text-gray-400 font-mono font-bold">0</span>
                </button>
                <button onclick="selectList('planned')" id="nav-planned" class="nav-btn notion-btn w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded font-medium text-gray-300 cursor-pointer">
                    <i class="fa-regular fa-calendar-check text-xs w-4 text-center text-sky-400"></i> <span class="flex-1 text-left">Planejadas</span> <span id="badge-planned" class="text-[11px] text-gray-400 font-mono font-bold">0</span>
                </button>
                <button onclick="selectList('all')" id="nav-all" class="nav-btn notion-btn w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded font-medium text-gray-300 cursor-pointer">
                    <i class="fa-solid fa-bars-staggered text-xs w-4 text-center text-purple-400"></i> <span class="flex-1 text-left">Todas as Tarefas</span> <span id="badge-all" class="text-[11px] text-gray-400 font-mono font-bold">0</span>
                </button>

                <hr class="my-2.5 border-[#2f2f2f]">
                <div>
                    <div class="flex items-center justify-between px-2.5 py-1 text-[11px] font-bold text-[#8a8a8e] uppercase tracking-wider">
                        <span>Categorias</span>
                        <button onclick="openCategoryModal()" class="text-gray-500 hover:text-white cursor-pointer transition p-0.5" title="Nova Categoria"><i class="fa-solid fa-plus text-xs"></i></button>
                    </div>
                    <div id="sidebar-categories" class="space-y-0.5"></div>
                </div>

                <hr class="my-2.5 border-[#2f2f2f]">
                <div>
                    <div class="flex items-center justify-between px-2.5 py-1 text-[11px] font-bold text-[#8a8a8e] uppercase tracking-wider">
                        <span>Projetos</span>
                        <button onclick="openProjectModal()" class="text-gray-500 hover:text-white cursor-pointer transition p-0.5" title="Novo Projeto"><i class="fa-solid fa-plus text-xs"></i></button>
                    </div>
                    <div id="sidebar-projects" class="space-y-0.5"></div>
                </div>
            </div>

            <!-- SIDEBAR VAULT NOTES PANEL WITH MULTI-SELECTION -->
            <div id="sidebar-notepad-panel" class="flex-1 flex flex-col p-2 overflow-y-auto space-y-2 hidden text-xs">
                <div class="flex items-center justify-between px-2 py-1 text-[11px] font-bold text-[#8a8a8e] uppercase tracking-wider">
                    <span>Estrutura do Vault</span>
                    <div class="flex items-center gap-1">
                        <button id="btn-expandir-tudo" onclick="expandirOuRecolherTudo()" class="notion-btn px-2 py-1 rounded text-gray-400 hover:text-white cursor-pointer" title="Expandir/Recolher tudo">
                            <i class="fa-solid fa-angles-up text-[9px]"></i>
                        </button>
                        <button onclick="addRootNote()" class="notion-btn px-2 py-1 rounded text-xs text-sky-400 hover:text-white flex items-center gap-1 cursor-pointer">
                            <i class="fa-solid fa-plus"></i> Nota
                        </button>
                    </div>
                </div>
                <div id="notepad-tree-container" class="flex-1 overflow-y-auto space-y-0.5"></div>
            </div>
        </aside>

        <!-- MAIN TASKS & RESPONSIVE DRAWER WORKSPACE -->
        <main id="main-tasks-view" class="flex-1 flex h-full overflow-hidden bg-[#191919] relative min-w-0 transition-all">
            
            <div class="flex-1 flex flex-col h-full overflow-hidden min-w-0">
                <header class="px-6 py-4 flex items-center justify-between border-b border-[#2f2f2f] flex-wrap gap-2 flex-shrink-0">
                    <div class="flex items-center gap-3 min-w-0">
                        <i id="current-list-icon" class="fa-regular fa-sun text-xl text-amber-400 flex-shrink-0"></i>
                        <div class="min-w-0">
                            <h2 id="current-list-title" class="text-xl font-bold text-white tracking-tight truncate">Meu Dia</h2>
                            <span id="current-list-subtitle" class="text-xs text-[#8a8a8e] font-medium truncate block">Tarefas em foco para hoje</span>
                        </div>
                    </div>

                    <div class="flex items-center gap-2 flex-shrink-0">
                        <div class="flex flex-wrap items-center bg-white/5 border border-white/5 p-0.5 rounded text-xs font-semibold">
                            <button id="view-mode-list" onclick="setViewMode('list')" class="px-2.5 py-1 rounded bg-[#2a2a2a] text-white border border-white/10 transition cursor-pointer">
                                <i class="fa-solid fa-list mr-1"></i> Lista
                            </button>
                            <button id="view-mode-kanban" onclick="setViewMode('kanban')" class="px-2.5 py-1 rounded text-gray-400 hover:text-white transition cursor-pointer">
                                <i class="fa-solid fa-table-columns mr-1"></i> Kanban
                            </button>
                            <button id="view-mode-charts" onclick="setViewMode('charts')" class="px-2.5 py-1 rounded text-gray-400 hover:text-white transition cursor-pointer">
                                <i class="fa-solid fa-chart-pie mr-1"></i> Gráficos
                            </button>
                        </div>
                    </div>
                </header>

                <div class="px-6 pt-3 pb-1 flex-shrink-0" id="quick-input-container">
                    <div class="bg-[#202020] border border-[#2f2f2f] hover:border-white/20 focus-within:border-[#2eaadc]/50 rounded p-2.5 flex items-center gap-3 transition">
                        <button onclick="createNewTaskFromInput()" class="text-[#2eaadc] hover:text-sky-300 transition cursor-pointer">
                            <i class="fa-solid fa-plus text-sm"></i>
                        </button>
                        <input type="text" id="quickTaskInput" onkeydown="if(event.key==='Enter') createNewTaskFromInput()" placeholder="Adicionar uma tarefa no NEXUS... (Pressione Enter)" class="w-full min-w-0 bg-transparent text-xs text-gray-100 placeholder-gray-500 focus:outline-none font-medium">
                    </div>
                </div>

                <div class="flex-1 px-6 py-2 overflow-y-auto space-y-2 pb-12 min-h-0" id="main-content-scroll">
                    <div id="list-view-container" class="space-y-2">
                        <div id="active-tasks-list" class="space-y-2"></div>
                        <div id="completed-section" class="pt-4 hidden">
                            <button onclick="toggleCompletedTasks()" class="notion-btn flex items-center gap-2 px-2.5 py-1 rounded text-xs font-semibold text-gray-400 hover:text-white transition cursor-pointer mb-2">
                                <i id="completed-chevron" class="fa-solid fa-chevron-down text-xs transition-transform"></i> Concluídas <span id="completed-count" class="px-1.5 py-0.5 bg-white/5 rounded font-mono">0</span>
                            </button>
                            <div id="completed-tasks-list" class="space-y-2"></div>
                        </div>
                    </div>

                    <!-- min-w-0 em cada coluna: sem isso, itens de grid nao encolhem
                         abaixo do conteudo e os cards vazam para fora da coluna. -->
                    <div id="kanban-view-container" class="hidden grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 h-full pb-6">
                        <div class="flex flex-col min-w-0 bg-[#202020] border border-[#2f2f2f] rounded p-2.5">
                            <span class="text-xs font-bold text-gray-400 uppercase tracking-wider pb-2 border-b border-[#2f2f2f] mb-2 flex justify-between gap-2"><span class="truncate">A Fazer</span> <span id="kanban-count-todo" class="font-mono flex-shrink-0">0</span></span>
                            <div id="kanban-col-todo" class="space-y-2 flex-1 overflow-y-auto overflow-x-hidden min-h-[140px] min-w-0"></div>
                        </div>
                        <div class="flex flex-col min-w-0 bg-[#202020] border border-[#2f2f2f] rounded p-2.5">
                            <span class="text-xs font-bold text-sky-400 uppercase tracking-wider pb-2 border-b border-[#2f2f2f] mb-2 flex justify-between gap-2"><span class="truncate">Em Execução</span> <span id="kanban-count-progress" class="font-mono flex-shrink-0">0</span></span>
                            <div id="kanban-col-progress" class="space-y-2 flex-1 overflow-y-auto overflow-x-hidden min-h-[140px] min-w-0"></div>
                        </div>
                        <div class="flex flex-col min-w-0 bg-[#202020] border border-[#2f2f2f] rounded p-2.5">
                            <span class="text-xs font-bold text-amber-400 uppercase tracking-wider pb-2 border-b border-[#2f2f2f] mb-2 flex justify-between gap-2"><span class="truncate">Quase Pronto</span> <span id="kanban-count-review" class="font-mono flex-shrink-0">0</span></span>
                            <div id="kanban-col-review" class="space-y-2 flex-1 overflow-y-auto overflow-x-hidden min-h-[140px] min-w-0"></div>
                        </div>
                        <div class="flex flex-col min-w-0 bg-[#202020] border border-[#2f2f2f] rounded p-2.5">
                            <span class="text-xs font-bold text-emerald-400 uppercase tracking-wider pb-2 border-b border-[#2f2f2f] mb-2 flex justify-between gap-2"><span class="truncate">Concluído</span> <span id="kanban-count-done" class="font-mono flex-shrink-0">0</span></span>
                            <div id="kanban-col-done" class="space-y-2 flex-1 overflow-y-auto overflow-x-hidden min-h-[140px] min-w-0"></div>
                        </div>
                    </div>

                    <div id="charts-view-container" class="hidden grid grid-cols-1 md:grid-cols-2 gap-4 p-2">
                        <div class="bg-[#202020] border border-[#2f2f2f] rounded p-4">
                            <h4 class="text-xs font-bold text-gray-200 mb-3">Tarefas por Categoria</h4>
                            <canvas id="chartCategories" height="200"></canvas>
                        </div>
                        <div class="bg-[#202020] border border-[#2f2f2f] rounded p-4">
                            <h4 class="text-xs font-bold text-gray-200 mb-3">Tarefas por Prioridade</h4>
                            <canvas id="chartPriorities" height="200"></canvas>
                        </div>
                    </div>
                </div>
            </div>

            <!-- RESPONSIVE RIGHT DRAWER (PAINEL LATERAL DE CONFIGURAÇÃO DA TAREFA) -->
            <!-- Antes era flex-shrink-0 com 384px fixos: numa janela pequena ele
                 tomava o espaço todo e sobrava quase nada para a lista. Agora
                 cede largura até 264px antes de a lista ficar apertada. -->
            <div id="taskDetailDrawer" class="max-w-full h-full bg-[#202020] border-l border-[#2f2f2f] flex flex-col z-30 transition-all duration-200 hidden" style="flex:0 1 384px; min-width:264px">
                <div class="p-3.5 border-b border-[#2f2f2f] flex items-center justify-between">
                    <span class="text-xs font-bold text-[#8a8a8e] uppercase tracking-wider">Detalhes da Tarefa</span>
                    <button onclick="closeTaskDetailDrawer()" class="notion-btn p-1 rounded text-gray-400 hover:text-white cursor-pointer"><i class="fa-solid fa-xmark text-xs"></i></button>
                </div>
                
                <div class="flex-1 overflow-y-auto p-4 space-y-3.5 text-xs" id="detailDrawerBody">
                    <div>
                        <label class="text-[11px] font-bold text-gray-500 uppercase block mb-1">Título</label>
                        <input type="text" id="detailTaskTitle" oninput="debouncedUpdateTaskTitle()" class="w-full p-2 bg-white/5 border border-transparent focus:border-white/20 rounded text-xs text-white focus:outline-none">
                    </div>

                    <div class="grid grid-cols-2 gap-2.5">
                        <div>
                            <label class="text-[11px] font-bold text-gray-500 uppercase block mb-1">Categoria</label>
                            <select id="detailTaskCategory" onchange="updateTaskFromDrawer()" class="w-full p-1.5 bg-[#181818] border border-[#2f2f2f] rounded text-xs text-gray-200 focus:outline-none"></select>
                        </div>
                        <div>
                            <label class="text-[11px] font-bold text-gray-500 uppercase block mb-1">Projeto</label>
                            <select id="detailTaskProject" onchange="updateTaskFromDrawer()" class="w-full p-1.5 bg-[#181818] border border-[#2f2f2f] rounded text-xs text-gray-200 focus:outline-none"></select>
                        </div>
                    </div>

                    <div class="grid grid-cols-2 gap-2.5">
                        <div>
                            <label class="text-[11px] font-bold text-gray-500 uppercase block mb-1">Prioridade</label>
                            <select id="detailTaskPriority" onchange="updateTaskFromDrawer()" class="w-full p-1.5 bg-[#181818] border border-[#2f2f2f] rounded text-xs text-gray-200 focus:outline-none">
                                <option value="Baixa">Baixa</option>
                                <option value="Média">Média</option>
                                <option value="Alta">Alta</option>
                                <option value="Urgente">Urgente</option>
                            </select>
                        </div>
                        <div>
                            <label class="text-[11px] font-bold text-gray-500 uppercase block mb-1">Data Limite</label>
                            <input type="date" id="detailTaskDueDate" onchange="updateTaskFromDrawer()" class="w-full p-1.5 bg-[#181818] border border-[#2f2f2f] rounded text-xs text-gray-200 focus:outline-none">
                        </div>
                    </div>

                    <!-- MEU DIA -->
                    <div>
                        <span class="text-[11px] font-bold text-gray-400 uppercase mb-1 block">Meu Dia</span>
                        <button id="detailMyDayBtn" onclick="toggleMyDayFromDrawer()" class="w-full flex items-center justify-between gap-2 p-2 bg-[#181818] border border-[#2f2f2f] rounded text-xs transition cursor-pointer hover:border-amber-500/40">
                            <span class="flex items-center gap-2 min-w-0">
                                <i id="detailMyDayIcon" class="fa-regular fa-sun text-amber-400 flex-shrink-0"></i>
                                <span id="detailMyDayLabel" class="truncate text-gray-300">Não está no Meu Dia</span>
                            </span>
                            <span id="detailMyDayAction" class="text-[10px] font-semibold text-sky-300 flex-shrink-0">Adicionar</span>
                        </button>
                    </div>

                    <div>
                        <div class="flex justify-between text-[11px] font-bold text-gray-400 uppercase mb-1">
                            <span>Progresso (%)</span>
                            <span id="detailProgressLabel" class="font-mono text-[#2eaadc]">0%</span>
                        </div>
                        <input type="range" id="detailTaskProgress" min="0" max="100" step="5" oninput="updateProgressFromDrawer(this.value)" class="w-full accent-[#2eaadc] cursor-pointer">
                    </div>

                    <div class="pt-2 border-t border-[#2f2f2f]">
                        <div class="flex items-center justify-between mb-1.5">
                            <span class="text-[11px] font-bold text-gray-400 uppercase">Etapas (Checklist)</span>
                            <span id="detailStepsProgress" class="text-[11px] font-mono text-[#2eaadc]">0/0</span>
                        </div>
                        <div id="detailStepsContainer" class="space-y-1.5 mb-2"></div>
                        <div class="flex gap-2">
                            <input type="text" id="newStepInput" onkeydown="if(event.key==='Enter') addStepFromDrawer()" placeholder="Nova etapa..." class="flex-1 p-1.5 bg-white/5 border border-transparent focus:border-white/20 rounded text-xs text-white focus:outline-none">
                            <button onclick="addStepFromDrawer()" class="notion-btn px-2.5 py-1 rounded text-xs text-sky-400 hover:text-white cursor-pointer font-bold"><i class="fa-solid fa-plus"></i></button>
                        </div>
                    </div>

                    <div class="pt-2 border-t border-[#2f2f2f]">
                        <div class="flex items-center justify-between mb-1.5">
                            <span class="text-[11px] font-bold text-gray-400 uppercase flex items-center gap-2">
                                Anexos de Arquivos
                                <span id="detailAttachmentsCount" class="font-mono text-[#2eaadc] normal-case">0</span>
                            </span>
                            <button onclick="pickAttachmentForTask()" class="notion-btn px-2 py-1 rounded text-xs text-sky-300 hover:text-white cursor-pointer flex items-center gap-1">
                                <i class="fa-solid fa-paperclip"></i> Anexar
                            </button>
                        </div>
                        <div id="detailAttachmentsContainer" class="space-y-1"></div>
                    </div>

                    <div class="pt-2 border-t border-[#2f2f2f]">
                        <label class="text-[11px] font-bold text-gray-500 uppercase block mb-1">Anotações</label>
                        <textarea id="detailTaskNotes" oninput="debouncedUpdateTaskNotes()" rows="4" placeholder="Adicionar notas para esta tarefa..." class="w-full p-2 bg-white/5 border border-transparent focus:border-white/20 rounded text-xs text-gray-200 focus:outline-none resize-none"></textarea>
                    </div>

                    <div class="pt-3 border-t border-[#2f2f2f] flex justify-between items-center">
                        <button onclick="deleteCurrentTaskFromDrawer()" class="notion-btn px-2.5 py-1.5 rounded text-xs text-rose-400 hover:bg-rose-500/10 cursor-pointer flex items-center gap-1.5">
                            <i class="fa-regular fa-trash-can"></i> Excluir Tarefa
                        </button>
                        <span id="detailCreatedAt" class="text-[10px] text-gray-500 font-mono"></span>
                    </div>
                </div>
            </div>
        </main>

        <!-- MAIN VAULT NOTES WORKSPACE -->
        <main id="main-notepad-view" class="flex-1 flex h-full overflow-hidden bg-[#191919] relative hidden min-w-0">
            <div id="note-editor-container" class="flex-1 flex flex-col h-full overflow-hidden">
                
                <!-- FORMATTING TOOLBAR WITH CLEAR FORMATTING -->
                <div class="p-3 border-b border-[#2f2f2f] flex items-center justify-between gap-2 flex-wrap flex-shrink-0 bg-[#202020]">
                    <div class="flex items-center gap-2 flex-1 min-w-0">
                        <button onclick="openNoteIconModal()" id="btn-current-note-icon" class="p-1.5 rounded bg-white/5 hover:bg-white/10 text-sky-400 cursor-pointer" title="Personalizar Ícone da Nota">
                            <i class="fa-regular fa-file-lines text-sm"></i>
                        </button>
                        <input type="text" id="noteTitleInput" oninput="saveNoteTitleLive()" class="bg-transparent text-lg font-bold text-white placeholder-gray-600 focus:outline-none flex-1 truncate" placeholder="Título da Nota">
                    </div>
                    
                    <div class="flex items-center gap-1 bg-white/5 border border-white/5 p-1 rounded text-xs flex-wrap">
                        <button onclick="formatDoc('bold')" class="notion-btn px-2 py-1 rounded text-gray-300 hover:text-white" title="Negrito"><i class="fa-solid fa-bold"></i></button>
                        <button onclick="formatDoc('italic')" class="notion-btn px-2 py-1 rounded text-gray-300 hover:text-white" title="Itálico"><i class="fa-solid fa-italic"></i></button>
                        <button onclick="formatDoc('underline')" class="notion-btn px-2 py-1 rounded text-gray-300 hover:text-white" title="Sublinhado"><i class="fa-solid fa-underline"></i></button>
                        <button onclick="formatDoc('strikeThrough')" class="notion-btn px-2 py-1 rounded text-gray-300 hover:text-white" title="Tachado"><i class="fa-solid fa-strikethrough"></i></button>
                        <div class="h-4 w-px bg-[#2f2f2f] mx-0.5"></div>
                        <button onclick="formatDoc('formatBlock', '<h1>')" class="notion-btn px-2 py-1 rounded text-gray-300 hover:text-white font-bold" title="H1">H1</button>
                        <button onclick="formatDoc('formatBlock', '<h2>')" class="notion-btn px-2 py-1 rounded text-gray-300 hover:text-white font-bold" title="H2">H2</button>
                        <div class="h-4 w-px bg-[#2f2f2f] mx-0.5"></div>
                        <button onclick="formatDoc('insertUnorderedList')" class="notion-btn px-2 py-1 rounded text-gray-300 hover:text-white" title="Lista Marcadores"><i class="fa-solid fa-list-ul"></i></button>
                        <button onclick="formatDoc('insertOrderedList')" class="notion-btn px-2 py-1 rounded text-gray-300 hover:text-white" title="Lista Numerada"><i class="fa-solid fa-list-ol"></i></button>
                        <div class="h-4 w-px bg-[#2f2f2f] mx-0.5"></div>
                        <button onclick="formatDoc('foreColor', '#2eaadc')" class="notion-btn px-2 py-1 rounded text-sky-400 hover:text-white" title="Cor Azul"><i class="fa-solid fa-palette"></i></button>
                        <button onclick="formatDoc('hiliteColor', '#4a441e')" class="notion-btn px-2 py-1 rounded text-amber-300 hover:text-white" title="Marca-texto"><i class="fa-solid fa-highlighter"></i></button>
                        <div class="h-4 w-px bg-[#2f2f2f] mx-0.5"></div>
                        <!-- BUTTON: LIMPAR FORMATAÇÃO -->
                        <button onclick="formatDoc('removeFormat')" class="notion-btn px-2 py-1 rounded text-rose-400 hover:text-rose-300 font-medium cursor-pointer" title="Limpar Formatação">
                            <i class="fa-solid fa-eraser mr-1"></i> Limpar Formatação
                        </button>
                    </div>

                    <div class="flex items-center gap-1.5">
                        <button onclick="addChildNote(selectedNoteId)" class="notion-btn px-2 py-1 rounded text-xs text-sky-400 hover:text-white flex items-center gap-1 cursor-pointer" title="Criar Subnota">
                            <i class="fa-solid fa-code-branch text-xs"></i> Subnota
                        </button>
                        <button onclick="deleteCurrentNote()" class="notion-btn px-2 py-1 rounded text-xs text-rose-400 hover:bg-rose-500/10 cursor-pointer" title="Excluir Nota">
                            <i class="fa-regular fa-trash-can"></i>
                        </button>
                    </div>
                </div>

                <div id="noteEditorBody" contenteditable="true" oninput="saveNoteContentLive()" placeholder="Comece a digitar sua anotação no Vault aqui..." class="flex-1 p-8 overflow-y-auto text-sm text-gray-200 focus:outline-none min-h-0 leading-relaxed font-sans bg-[#191919]"></div>

                <div class="h-7 border-t border-[#2f2f2f] px-6 flex items-center justify-between text-xs text-gray-500 font-mono flex-shrink-0 bg-[#202020]">
                    <span id="note-word-count">0 palavras • 0 caracteres</span>
                    <span id="note-last-saved">Salvo no Vault local</span>
                </div>
            </div>
        </main>
    </div>

    <!-- PROFILE MODAL -->
    <div id="profileModal" class="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4 hidden">
        <div class="bg-[#202020] border border-[#2f2f2f] rounded-lg p-5 w-full max-w-sm space-y-4 shadow-2xl">
            <h3 class="text-sm font-bold text-white">Editar Perfil</h3>

            <div class="flex flex-col items-center justify-center gap-2 pb-1">
                <div class="w-16 h-16 rounded bg-white/5 border border-white/10 flex items-center justify-center overflow-hidden relative group cursor-pointer shadow" onclick="document.getElementById('profileAvatarInput').click()" title="Clique para escolher foto do computador">
                    <img id="modalAvatarPreview" src="" class="w-full h-full object-cover hidden" alt="Foto de Perfil">
                    <span id="modalAvatarInitials" class="text-white font-bold text-base">CA</span>
                    <div class="absolute inset-0 bg-black/60 flex flex-col items-center justify-center opacity-0 group-hover:opacity-100 transition text-white">
                        <i class="fa-solid fa-camera text-sm mb-1"></i>
                        <span class="text-[9px] font-medium">Alterar</span>
                    </div>
                </div>

                <div class="flex items-center gap-2">
                    <button type="button" onclick="document.getElementById('profileAvatarInput').click()" class="px-2.5 py-1 bg-sky-600/20 hover:bg-sky-600/30 border border-sky-500/30 text-sky-300 rounded text-xs font-semibold cursor-pointer transition flex items-center gap-1">
                        <i class="fa-solid fa-upload text-xs"></i> Carregar Foto
                    </button>
                    <button type="button" onclick="removeProfileAvatar()" id="removeAvatarBtn" class="px-2 py-1 bg-white/5 hover:bg-rose-500/20 border border-white/10 hover:border-rose-500/30 text-gray-400 hover:text-rose-300 rounded text-xs cursor-pointer transition hidden" title="Remover Foto">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
                <input type="file" id="profileAvatarInput" accept="image/*" class="hidden" onchange="handleProfileAvatarUpload(event)">
            </div>

            <div class="space-y-2.5 text-xs">
                <div>
                    <label class="text-gray-400 uppercase font-bold block mb-1">Nome</label>
                    <input type="text" id="profileNameInput" oninput="updateModalAvatarPreview()" class="w-full p-1.5 bg-white/5 border border-white/10 rounded text-xs text-white focus:outline-none">
                </div>
                <div>
                    <label class="text-gray-400 uppercase font-bold block mb-1">Subtítulo / Função</label>
                    <input type="text" id="profileSubtitleInput" class="w-full p-1.5 bg-white/5 border border-white/10 rounded text-xs text-white focus:outline-none">
                </div>
            </div>
            <!-- Conta conectada + saída -->
            <div id="profileAccountBox" class="hidden pt-3 border-t border-[#2f2f2f] space-y-2">
                <div class="flex items-center gap-2 text-[11px] text-gray-400">
                    <i class="fa-solid fa-circle-check text-emerald-400"></i>
                    <span class="truncate">Conectado como <span id="profileAccountEmail" class="text-gray-200 font-medium"></span></span>
                </div>
                <button onclick="closeProfileModal(); openCloudModal();" class="w-full px-3 py-1.5 rounded text-xs bg-white/5 border border-white/10 text-gray-200 hover:bg-white/10 cursor-pointer transition">
                    <i class="fa-solid fa-cloud mr-1"></i> Sincronização na nuvem
                </button>
                <button onclick="sairDaNuvem()" class="w-full px-3 py-1.5 rounded text-xs bg-rose-600/15 border border-rose-500/30 text-rose-300 hover:bg-rose-600/25 cursor-pointer transition">
                    <i class="fa-solid fa-right-from-bracket mr-1"></i> Sair desta conta
                </button>
            </div>

            <div class="flex justify-end gap-2 pt-2">
                <button onclick="closeProfileModal()" class="notion-btn px-3 py-1.5 rounded text-xs text-gray-400 hover:text-white cursor-pointer">Cancelar</button>
                <button onclick="saveProfile()" class="px-3.5 py-1.5 rounded text-xs bg-[#2eaadc] hover:bg-sky-500 text-white font-bold cursor-pointer transition">Salvar</button>
            </div>
        </div>
    </div>

    <!-- CATEGORY MODAL -->
    <div id="categoryModal" class="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4 hidden">
        <div class="bg-[#202020] border border-[#2f2f2f] rounded-lg p-5 w-full max-w-sm space-y-4 shadow-2xl">
            <h3 id="categoryModalTitle" class="text-sm font-bold text-white">Categoria</h3>
            <input type="hidden" id="editingCategoryId">
            <div class="space-y-3 text-xs">
                <div>
                    <label class="text-gray-400 uppercase font-bold block mb-1">Nome da Categoria</label>
                    <input type="text" id="newCategoryName" placeholder="Ex: Pessoal, Estudos..." class="w-full p-1.5 bg-white/5 border border-white/10 rounded text-xs text-white focus:outline-none">
                </div>
                <div>
                    <label class="text-gray-400 uppercase font-bold block mb-1">Escolher Ícone</label>
                    <div id="categoryIconPicker" class="grid grid-cols-6 gap-1.5 p-2 bg-white/5 rounded max-h-32 overflow-y-auto"></div>
                </div>
            </div>
            <div class="flex justify-between items-center pt-2">
                <button id="deleteCatBtn" onclick="deleteCurrentEditingCategory()" class="hidden px-2.5 py-1 rounded text-xs text-rose-400 hover:bg-rose-500/10 cursor-pointer">Excluir</button>
                <div class="flex gap-2 ml-auto">
                    <button onclick="closeCategoryModal()" class="notion-btn px-3 py-1.5 rounded text-xs text-gray-400 hover:text-white cursor-pointer">Cancelar</button>
                    <button onclick="saveCategoryModal()" class="px-3.5 py-1.5 rounded text-xs bg-[#2eaadc] hover:bg-sky-500 text-white font-bold cursor-pointer transition">Salvar</button>
                </div>
            </div>
        </div>
    </div>

    <!-- PROJECT MODAL -->
    <div id="projectModal" class="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4 hidden">
        <div class="bg-[#202020] border border-[#2f2f2f] rounded-lg p-5 w-full max-w-sm space-y-4 shadow-2xl">
            <h3 id="projectModalTitle" class="text-sm font-bold text-white">Projeto</h3>
            <input type="hidden" id="editingProjectId">
            <div class="space-y-3 text-xs">
                <div>
                    <label class="text-gray-400 uppercase font-bold block mb-1">Nome do Projeto</label>
                    <input type="text" id="newProjectName" placeholder="Ex: Redesign App..." class="w-full p-1.5 bg-white/5 border border-white/10 rounded text-xs text-white focus:outline-none">
                </div>
                <div>
                    <label class="text-gray-400 uppercase font-bold block mb-1">Escolher Ícone</label>
                    <div id="projectIconPicker" class="grid grid-cols-6 gap-1.5 p-2 bg-white/5 rounded max-h-32 overflow-y-auto"></div>
                </div>
            </div>
            <div class="flex justify-between items-center pt-2">
                <button id="deleteProjBtn" onclick="deleteCurrentEditingProject()" class="hidden px-2.5 py-1 rounded text-xs text-rose-400 hover:bg-rose-500/10 cursor-pointer">Excluir</button>
                <div class="flex gap-2 ml-auto">
                    <button onclick="closeProjectModal()" class="notion-btn px-3 py-1.5 rounded text-xs text-gray-400 hover:text-white cursor-pointer">Cancelar</button>
                    <button onclick="saveProjectModal()" class="px-3.5 py-1.5 rounded text-xs bg-[#2eaadc] hover:bg-sky-500 text-white font-bold cursor-pointer transition">Salvar</button>
                </div>
            </div>
        </div>
    </div>

    <!-- NOTE ICON CUSTOMIZATION MODAL -->
    <div id="noteIconModal" class="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4 hidden">
        <div class="bg-[#202020] border border-[#2f2f2f] rounded-lg p-5 w-full max-w-sm space-y-4 shadow-2xl">
            <h3 class="text-sm font-bold text-white">Personalizar Ícone da Nota</h3>
            <div class="space-y-3 text-xs">
                <div>
                    <label class="text-gray-400 uppercase font-bold block mb-1">Escolher Ícone</label>
                    <div id="noteIconPickerContainer" class="grid grid-cols-6 gap-1.5 p-2 bg-white/5 rounded max-h-36 overflow-y-auto"></div>
                </div>
            </div>
            <div class="flex justify-end gap-2 pt-2">
                <button onclick="closeNoteIconModal()" class="notion-btn px-3 py-1.5 rounded text-xs text-gray-400 hover:text-white cursor-pointer">Cancelar</button>
                <button onclick="saveNoteIconModal()" class="px-3.5 py-1.5 rounded text-xs bg-[#2eaadc] hover:bg-sky-500 text-white font-bold cursor-pointer transition">Salvar Ícone</button>
            </div>
        </div>
    </div>

    <!-- ================= TELA DE ENTRADA ================= -->
    <div id="loginGate" class="fixed inset-0 z-[60] bg-[#191919] hidden items-center justify-center p-6">
        <div class="w-full max-w-sm">
            <div class="flex items-center gap-3 mb-6 justify-center">
                <div class="w-10 h-10 flex items-center justify-center flex-shrink-0">
                    <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAYAAADDPmHLAAAR3ElEQVR42u2df7BdVXXHP+vdex95SZAYILUEKdYZf/Pjj1bFDo4MiIxVO6KlUwhgpTC2WqTiaC2/1DLWdiytVqoiBhgFoUEt5UcoWJyOoOjUCQ6xOqTYkgRsJQmhIT94797z7R9n7WRzuO+9c+4798e57+yZO3nv5Zxzz97ru9f6rrX3XgvqVre6Ld5mi63DkiZm6bsAzCypATCeQreovwoCz4zFc/5/MYDBxlzwBgThJ0GgkhrApP8fQAJMm1knAsyEAyExM9UAqJ7wG6lGt7b/vhxYBbwKeCVwJPACv/z/gK3AT4H/AJ40s11+X9O1QacGQHUEPwF0zCyRtBI4ATjL/30hsARoZTTADLAPeAp4ELgR+J6Z7XCN0HBt0KFuo2nnJTUdAEhaJulUSfdI2qkDLZHU9s+Mf8LvSXTdTkn3SjpN0rIALv+OiXrER8jOB8EElS3pOEk3SNoRCT0WdmeWTwyKAIanJH1V0vGZ72g6x6jbMNW9pFb0+4slfVLS1kjw011m93wtaInp6L7HJV0p6agIePs1Tt2GIPigiiWtlHSepIddcOoyk3tpseaQa4mNks6XdGhkelo1EIZr578taU9G8B2V1zoZIOyR9J2aHwzXzh+bsfOdSN33q7Uz4Ko8P7AqqHtgwsxmgp0HzgfeC6z2YE3bXbq8ajjJRANDFDDv7O34M5p+3xPAdcA1ZrbZhd8Y5/hBVe18Es3ibJspSBazz6okP7ARFPz+MKyZddzG/hbwEeANwJTPePy6orM2eA07gN3+83IPEOEBoaLaJKwZNIG9wA+AvwK+a2a7Q1SSKBxdA6CLnfeBNzNru019FXAx8HYXUOKCLCKgIPgQIdwO3AF8Dfhvv+YlwJnA24DDFvA9ikC5E7gduArYGPUJj1KKuvXkzxdl7uGe3ZL+RdLJkpZ2eYelkk6StF7SM7OQvrxEcb74Qe02DtDOz0h6SNK5kl6Ysc2BscfvsELSGkkbMs+YWWz8YJD+/NKS/Pkw+0LbLOlySauzsy920yI3sxX+LukISZdIeqwELRTHD+5btPGDOeL21y/Qnw+CD2DZLulaSa+JQDavf97l/SYkvVrSNZK2LfD9xip+UAU7P9XrDIs0VBDOVM0PqmvnGwt892bNDypq5/sA4pofVN3Ol9ivmh9U2c6XoNlqfpAZlEra+Qrzg4lRmvWVt/Ml84NLB8QPGsPufNOFYZKOqbqdL5EfNPrMD46Nxr05NOH7v8skXeizdCzsfAX4wRZJF/lZBwYOgqiDqyStlbTXX2x6nOx8ibGPFZLOLokfBNO4z8f+8IGCICP8W2dR3b3a+ctG0c6XyA9Wl8QP4ntulbRqICDwDk1IOtjRF2b99Ljb+QXyg2Yf+EE87mtdJta3CeOCD+r4ikiFzRQU/lx2vjmuK2MF+EEREMQy+HgwO6WPX4wsSaf4rO0UnPmxLftx1e18H/jBQz2eYQjadLukU6LvsH6o/mWSbvIvfjbnCyfRZ5PH0H8tdmMW46aIyKsJ/OAoSR+T9EhmzPKM77P+800uo4nSxjSQMf/5OA9RJgVUf8ev3yPpI9GzWpKWLOaDFD62SyRNRibwYjePSQFSHbyJxyUdF43vvFogz+AbkDii3kK6aVLk340brpsELgK+LOl40h2y+4CJ0lVWRRbMgIaPQccF92XSTbAHFZBPuE4um7f4sxPK2PQb2f4VTtpUwpm7Le4OjY3LV4JruLmEM4ySdLekFbHsygLASyX9PGKrCzlaFUC0wRdQVmTsYmMMBZ/dH3GIpLO6BIcWMraS9KikXy8lLpCx/ydGfutCzt9lw77PSLpT0hslLalK2HcB7t8SH8vbFxgeng0A2ySdGK/VzPV+8yHEOHB+7jDSUzULPdAQDk50SE/hLAXeCrwWuEXS54BNZqZIVVYyUVN8rtEn08uAC4EzgMN9LMNJpDKieHIZHTqLDAsDIG5TEdnI8yLzEZCGf8LJncOA9zsYrpb0NTP733DQUlJlDlpGR8E6frxtFWmOovcDL/XLguBbBYRrOa9ZWmQ25m1FGGVCen4vD1gaDsS2f14CfAq4TdK7gOVRpq9KrAYC+Dsvl/RO4Dbg0y780M8m+Y6dhdPPSQE5WT8AUKQFoXY4cGZuvpdu+vu0/f7XAWuB6yS91lVpG7AR3Q/QjN5xQtJvANcC1wOv9z61I3WfZzZ3CoKlJ3tcdnsW2AA8HnW07Z3J8z7BLLWBg4F3+Qz6lKSj3Qx0gJHwFvwdmq7u25KOBq4E/tlt/cGu7olAPl8Lgjc3EU8AD/nYjiwAwkyfBv6a9ETvvf57q6AqC/wg5O97kQdI1kt6H7DSE0ZoyHsCW6TH2GeAlZIuAO4CPgz8atTfvDM4Np0tH7v7gHeQHjefjjTDSGqA/arezDYAvw98ANgYqfmkgFloRKozAV4B/C1wq6TTgKkoc8hAdwWnXbQZYImkU4F1wN+RZiHNZi3Jq+6TSEv8BPgg8Htm9qNuY1xG68cGAgMmXRhPuR2/B7iANK3LERRL65J1GyeBNwHHA7dL+hvgJ+H8fb/cxi75CxqSjgE+BPwOB/IXFHXrsulmfkGabuZLwBbnPBPe79J5T79mTNszYbSAlpltAT5BmoDhJtLcvK3I1uc1C63Idz4EOBu4E7hU0pFOwJKy+UFk5xMX/mrgElf37wFW+DsF1d3IKfiQ6aQF7AJudtN5hZltjsYvia6tBAAsRneUcHmDa4I1wHcjhpsUBEJ8z2rgUuBOSecAh5TFD+Kdvv7MQyStcdBdRppwOhDcXux8cH8fAM4Bznd1L//eJLL3ViUAPKfDkR/fAvaY2R3O7j8MbOriNuYBWCNyGwGOBb4AfF3Sm4DJXvlBxs63gZakN5KmlfkicFzk3eR164j6F8CyCfgocLqZ3QbszsQR+p5PaGDbiYP7FjaXmNmTwOclrQf+2LXCqogfWA/8YAlwGvCbwDpJnwUe8WjcvGHlyM7H4duXR+Hbw3oM3wbSG0jtL4GvA58HHg1h73iyDKoNPKrmQAiErWlmjwIfcyL1T8AzmVhAL/zgUOB9wHrgYkkvcm2QeFi5MYudDynhZyT9CvCn/ow/cuGHZ7QKqvsw2XZ7TON04KNm9p/+PiGOMPBQ91DCqmamoOKizj8InAucB/x7xIx7DSt3gP1BGUnvBg7OhpVnCd+e7oL6Sw9Nd6IIZdHwbejDj0gTXJ5jZg+ESRBm/bDSxw01rm5mMT9oArvMbJ0HPi4lTePWjGIBeflBHIFsuEkIYeXXke7ECWYm2PmGpP3XeSg6G74tEsULYNwMXAG83cxuBnaFJfZhCn7gHGA+sxDsr/ODX0j6jIdTLwLe7Wo99rOL8IM2aTLI00mTTt4o6Woz+7mD72jnIWd71DHmIUX9+WCOtgPf9ODQz7x6STM8e1SWt0cCAMEsOElU5Db+TNJFwC3Olk8kXepsRzNzvlnZ8EEPGT2DbX+rpKv8bx/yCJ5lAJaH2ceZQlvAHuB+D91+38z2Rl7IyGUKbTJizQcoiWLt02b2HUkbnCheTJpBtBFxg4l5hGWRQMPMfoXPThxUMVPPo+oDqBS5sBs9VP0tM3sqnHdghGsNNRnRlnEbW8DTZnaDpH91MnUexbOFB40RiOWSyNvoJf1snC18LWm28C1RzCMJsYhRbSO/5y64jcFdMrOtwF8Av+2BmaejsPIMxZadFc3gIgQvqPunPbT9NuATZrYl2vjZrsIOpkpsuuziNsrMfuy+/lnAv7nwe1lf6DV8e7+Txgs8xK3IratMMugmFWpd+MFeM7tL0g+B3yVdPn1ZROby8IO86j4EmjYBnwNuMbMno53TA4/iLToAzMYPzGybpC8Cd5NuvFzjbD+ssxvFt1R1C9/eCFzt0cvK2PnKm4D5+IGr3oaZ/Rfw5+4tfIPnhpXzbEKB5+64CeHbb/kz/8zMHo32+berXhKm8gcvZgkr/4B088kfAD90geb16wM3SEhD0ucB7/FQdScTvq180YcmY9Iy/CCElb8h6X7StfaLOLAbyeaY/ZDuyvkscIOZ/U+061dVtPOLAgCxWYjDym67r3Jz8Bn3/ZMunCBwhX3uZl7jgGr59WNZ5mUsz+a7WQg2/yD/eVvOGEEH2Ob3HOSzfmxr/DQZ75YAM64RpnJyAAOm/J4ZSt6FW2uAoSgEK7qXPsz4sU9aUde5XeStBkANgLrVAKhbDYC61QCoWw2AutUAqFsNgLrVAKhbDYC61QCoWw2AutUAqFsNAKDYurj5errqIV5wU5S4Iq+c1A8A7GX+IgQizWZ1FMU2YdZtjsnkY3mUj63muVakB1RLAUC8KWIb6Q4Zm+NZAQCnkB7HTkjz69RAKD7tQ5bQxMfylAgAE3MAYIb0aHouzT0nAHxXTDhi9QRpere50BdA8HrSbB/hhVqLsTDUAoQfcgxM+xieS5qwIs9Jp6dJ0/TGMizFBGwnPRY1l50JAJgizQv4J6Rp26YZYlrXKgk+Sj87TZp/8AM+llNzzP5YHpuAHXl520S+91KDNJHhfREqNcczE+AFpDl2bpF0MrBk0GldKyT4bPrZgySdRJpJ7NM+lskc8gqmOuQW3uUyKwcA/mId0rN32zhwcmYuc5C4zXoz8I/A33tqVaKU6s3FzA+6pJmXpFeTHj5dR1qlbTIH+Q7nHJ4E7nZZWSkAcBsin7GPAHdEwEjmYa4hbdtK0qNadwGXSFrtHR6ZtO9DsvNxmvkjSNPlrQf+0McsbEufy6NKIkHfCWxyWanUswxR0aPjourX0zlLmmWrhQ2kdGycAs4rdO3ywkztWYoudfyas/plquYpHdtLafkgg8eiopG5z3sU6VzHBfQwaR6c6Yjl5/FjQ1pXI03r+g/Azc4PDnLbZ+NePHoWO/8Feks/G659lvT428Muo07f1JZ3ZLmXfA9oHcny8aOgAQZUPv7a0msGz2O7kLRK0rpZhFoECHE10cslHRkN3EKzfQ8VALNUCb0sqhKa9CD4LFhu9apkCy8U2QMIDpf0FUl7I1QWKSvbV34wLAD0wc7HYxUmzT5JayPhNwZt08LALpN0YQmojquJ7vY6xSdLmooGtde07wMBQJcqoVOSTpK0foFVQoPgk0hbflDSsoHO/G4gcFVtko6RdL2kHQuwa6Xyg0EBoI92PguWpyR9VdKx0bgP94S3dzYIZ6mkUyV9W9KejKorgx8UqjY+CAB0sfNHeDXwx0rQiMFc7JF0n6TTolnfGJn4SWSng81bKek8SQ9HHZ8ZND/oJwBmsfNrSrLzMxEQNko6X9Kh3cZ6VBczwu8vlvRJSVuHwQ/6AYAB2vnHJV0p6aiyvKJBxrcb0QA1PXrYD37wFeceXflBmQAYgp0/PjOG1Vo3iWbK0PhBHBjpEQD7nzFEO1/tyGgXWzlIfjApadJ/P7MAAM70eyb9Myw7Pz6LZEPkB5M+oGcXAMDZAUC1na8+PwjftcaFNx8AnvHikOH9XlPb+eryg62SPu5m54wCGuAMv+dy5xhJ9E5jZedt2GbBlzM7XlRpJfBO0rSur+RAWRjIv808W8qlDXwf2EpajWwZ3bdXhb/tJq1feCTwBtLNmWEZe6LHd0iAn5Kmn/2mmW13gYc6hUNLOG0johEaeLXOwA9Iy8K8l+JlYWKBJtF+hLxFpsJ9zejnPPft3zfB88vJXEdaTmazq/gmI1JHyEbILGTLszdJi0NdTFpRO5Rn7/QIhCJC7FXwiu7ZCdzuGzU2Rn2CMc073C9+sKwEfpAU5BKdAm7d4vDnxyR+UGZbnP78mMQPFtoWtz8/IvGDYyXdsMD4QS+Cr/35MeMHtZ2v+cGcdn6mtvPjwQ+SHghebecrvL4Q84N4Jre7uHlJFCLOao7azlecH9wjaecs7ttMBhgxKHZKunfc7byNIRC6rS+cQFpj+ATSM/fLeX69pDZpZbGdwIOkVUK/Z2Y7RiVuXwOgOBAs1PmTtJy0nOzLSRd53ky64ANpRo17gAdIT0D/0sx2BXWPVw4bx3EaaxsWry/47E3875OuCQ7zS7cBOz0rBz7jQ7aTZJzj9ouCxLhALerv82Z00BjhV78mGfexWXQsNpNzL/wbBJ3Uq3SLz4WsXbm6Ld72/3G4QD+URfQRAAAAAElFTkSuQmCC" alt="NEXUS" class="w-full h-full object-contain">
                </div>
                <div>
                    <div class="font-bold text-lg text-white tracking-tight leading-none">NEXUS</div>
                    <div class="text-[10px] text-[#8a8a8e]">Entre para sincronizar seus dados</div>
                </div>
            </div>

            <div class="bg-[#202020] border border-[#2f2f2f] rounded p-5 space-y-3">
                <input type="email" id="gateEmail" placeholder="seu@email.com" autocomplete="username"
                       class="w-full p-2.5 bg-[#181818] border border-[#2f2f2f] rounded text-xs text-gray-200 focus:outline-none focus:border-[#2eaadc]/60">
                <input type="password" id="gatePassword" placeholder="Senha (mínimo 6 caracteres)" autocomplete="current-password"
                       class="w-full p-2.5 bg-[#181818] border border-[#2f2f2f] rounded text-xs text-gray-200 focus:outline-none focus:border-[#2eaadc]/60">

                <div id="gateError" class="hidden text-[11px] text-rose-300 bg-rose-500/10 border border-rose-500/25 rounded p-2"></div>

                <button id="gateSignIn" onclick="gateEntrar()"
                        class="w-full px-3 py-2.5 rounded text-xs font-bold bg-[#2eaadc] hover:bg-sky-500 text-white cursor-pointer transition">
                    Entrar
                </button>
                <button id="gateSignUp" onclick="gateCriarConta()"
                        class="w-full px-3 py-2 rounded text-xs bg-white/5 border border-white/10 text-gray-200 hover:bg-white/10 cursor-pointer transition">
                    Criar uma conta
                </button>

                <button onclick="gateUsarLocal()"
                        class="w-full text-[10px] text-gray-600 hover:text-gray-400 pt-1 cursor-pointer transition">
                    Continuar sem conta (somente neste computador)
                </button>
            </div>

            <p class="text-[10px] text-gray-600 text-center mt-4 leading-relaxed">
                Seus dados ficam isolados na sua conta.<br>Use o mesmo login em outros computadores para sincronizar.
            </p>
        </div>
    </div>

    <!-- ================= NUVEM / CONTA ================= -->
    <div id="cloudModal" class="fixed inset-0 bg-black/70 z-50 hidden items-center justify-center p-4">
        <div class="bg-[#202020] border border-[#2f2f2f] rounded w-full max-w-lg max-h-[92vh] overflow-y-auto">
            <div class="p-4 border-b border-[#2f2f2f] flex items-center justify-between">
                <span class="text-sm font-bold text-white flex items-center gap-2">
                    <i class="fa-solid fa-cloud text-[#2eaadc]"></i> Sincronização na Nuvem
                </span>
                <button onclick="closeCloudModal()" class="text-gray-500 hover:text-white cursor-pointer"><i class="fa-solid fa-xmark"></i></button>
            </div>

            <div class="p-4 space-y-4">
                <!-- Estado atual -->
                <div id="cloudStatusBox" class="p-3 rounded border border-[#2f2f2f] bg-[#191919] text-xs text-gray-400">
                    Carregando...
                </div>

                <!-- Conta -->
                <div id="cloudAuthSection" class="space-y-2 pt-2 border-t border-[#2f2f2f]">
                    <span class="text-[11px] font-bold text-gray-400 uppercase">Sua conta</span>
                    <div id="cloudLoginForm" class="space-y-2">
                        <input type="email" id="cloudEmail" placeholder="seu@email.com" class="w-full p-2 bg-[#181818] border border-[#2f2f2f] rounded text-xs text-gray-200 focus:outline-none focus:border-[#2eaadc]/50">
                        <input type="password" id="cloudPassword" placeholder="Senha (mínimo 6 caracteres)" class="w-full p-2 bg-[#181818] border border-[#2f2f2f] rounded text-xs text-gray-200 focus:outline-none focus:border-[#2eaadc]/50">
                        <div class="flex items-center gap-2">
                            <button onclick="entrarNaNuvem()" class="notion-btn flex-1 px-3 py-1.5 rounded text-xs bg-[#2eaadc]/20 border border-[#2eaadc]/40 text-sky-200 hover:bg-[#2eaadc]/30 cursor-pointer">
                                <i class="fa-solid fa-right-to-bracket mr-1"></i> Entrar
                            </button>
                            <button onclick="criarContaNaNuvem()" class="notion-btn flex-1 px-3 py-1.5 rounded text-xs bg-white/5 border border-white/10 text-gray-200 hover:bg-white/10 cursor-pointer">
                                <i class="fa-solid fa-user-plus mr-1"></i> Criar conta
                            </button>
                        </div>
                    </div>
                    <div id="cloudLoggedBox" class="hidden space-y-2">
                        <button onclick="sairDaNuvem()" class="notion-btn w-full px-3 py-1.5 rounded text-xs bg-rose-600/15 border border-rose-500/30 text-rose-300 hover:bg-rose-600/25 cursor-pointer">
                            <i class="fa-solid fa-right-from-bracket mr-1"></i> Sair desta conta
                        </button>
                    </div>
                </div>

                <!-- Passo 3: sincronizar -->
                <div id="cloudSyncSection" class="space-y-2 pt-2 border-t border-[#2f2f2f]">
                    <span class="text-[11px] font-bold text-gray-400 uppercase">Sincronizar agora</span>
                    <div class="flex items-center gap-2">
                        <button onclick="enviarParaNuvem()" class="notion-btn flex-1 px-3 py-1.5 rounded text-xs bg-white/5 border border-white/10 text-gray-200 hover:bg-white/10 cursor-pointer" title="Sobrescreve a nuvem com o que está nesta máquina">
                            <i class="fa-solid fa-cloud-arrow-up mr-1"></i> Enviar
                        </button>
                        <button onclick="baixarDaNuvem()" class="notion-btn flex-1 px-3 py-1.5 rounded text-xs bg-white/5 border border-white/10 text-gray-200 hover:bg-white/10 cursor-pointer" title="Substitui esta máquina pelo que está na nuvem">
                            <i class="fa-solid fa-cloud-arrow-down mr-1"></i> Baixar
                        </button>
                    </div>
                    <p class="text-[10px] text-gray-600 leading-relaxed">
                        No dia a dia isso é automático. Use estes botões só para resolver um conflito,
                        escolhendo qual lado deve prevalecer.
                    </p>
                </div>
            </div>
        </div>
    </div>

    <!-- ================= ATUALIZACAO ================= -->
    <div id="updateModal" class="fixed inset-0 bg-black/70 z-[60] hidden items-center justify-center p-4">
        <div class="bg-[#202020] border border-[#2f2f2f] rounded w-full max-w-lg max-h-[92vh] overflow-y-auto">
            <div class="p-4 border-b border-[#2f2f2f] flex items-center justify-between">
                <span class="text-sm font-bold text-white flex items-center gap-2">
                    <i class="fa-solid fa-cloud-arrow-down text-[#2eaadc]"></i> Atualizacao do NEXUS
                </span>
                <button onclick="fecharUpdateModal()" class="text-gray-500 hover:text-white cursor-pointer"><i class="fa-solid fa-xmark"></i></button>
            </div>

            <div class="p-4 space-y-4">
                <div id="updStatusBox" class="p-3 rounded border border-[#2f2f2f] bg-[#191919] text-xs text-gray-400">
                    Verificando...
                </div>

                <div id="updNotesBox" class="hidden">
                    <span class="text-[11px] font-bold text-gray-400 uppercase">O que mudou</span>
                    <pre id="updNotes" class="mt-1 p-3 rounded border border-[#2f2f2f] bg-[#181818] text-[11px] text-gray-300 whitespace-pre-wrap font-sans leading-relaxed max-h-40 overflow-y-auto"></pre>
                </div>

                <div id="updProgressBox" class="hidden space-y-1.5">
                    <div class="h-2 w-full rounded bg-[#181818] border border-[#2f2f2f] overflow-hidden">
                        <div id="updBar" class="h-full bg-[#2eaadc] transition-all duration-300" style="width:0%"></div>
                    </div>
                    <div class="flex items-center justify-between text-[10px] text-gray-500 font-mono">
                        <span id="updPhase">-</span><span id="updPct">0%</span>
                    </div>
                </div>

                <div class="flex items-center gap-2 pt-2 border-t border-[#2f2f2f]">
                    <button id="updBtnCheck" onclick="verificarAtualizacao(true)" class="notion-btn flex-1 px-3 py-1.5 rounded text-xs bg-white/5 border border-white/10 text-gray-200 hover:bg-white/10 cursor-pointer">
                        <i class="fa-solid fa-rotate mr-1"></i> Verificar agora
                    </button>
                    <button id="updBtnInstall" onclick="instalarAtualizacao()" class="notion-btn flex-1 px-3 py-1.5 rounded text-xs bg-[#2eaadc]/20 border border-[#2eaadc]/40 text-sky-200 hover:bg-[#2eaadc]/30 cursor-pointer hidden">
                        <i class="fa-solid fa-download mr-1"></i> Baixar e instalar
                    </button>
                </div>

                <p class="text-[10px] text-gray-600 leading-relaxed">
                    O NEXUS confere a assinatura SHA-256 do arquivo antes de instalar.
                    Se a conferencia falhar, o download e descartado e nada e executado.
                    Seus dados e sua conta nao sao afetados pela atualizacao.
                </p>
                <p id="updDiag" class="text-[9px] text-gray-700 font-mono leading-relaxed break-all"></p>
            </div>
        </div>
    <!-- PAINEL / CENTRAL DE NOTIFICAÇÕES DE PRAZOS -->
    <div id="notificationPanel" class="fixed top-14 right-4 w-96 max-w-[calc(100vw-2rem)] bg-[#202020] border border-[#333333] shadow-2xl rounded-lg z-50 hidden flex-col overflow-hidden animate-fadeIn">
        <div class="p-3 border-b border-[#2f2f2f] flex items-center justify-between bg-[#1b1b1b]">
            <div class="flex items-center gap-2">
                <i class="fa-solid fa-bell text-sky-400 text-xs"></i>
                <span class="font-bold text-xs text-white">Tarefas & Prazos</span>
                <span id="notifTotalBadge" class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/10 text-gray-300">0 alertas</span>
            </div>
            <div class="flex items-center gap-1.5">
                <button onclick="testarNotificacaoWindows()" title="Testar Notificação Windows" class="text-[10px] text-gray-400 hover:text-sky-300 px-1.5 py-0.5 rounded hover:bg-white/5 cursor-pointer">
                    <i class="fa-solid fa-volume-high mr-1"></i>Testar
                </button>
                <button onclick="toggleNotificationPanel(false)" class="text-gray-400 hover:text-white text-xs p-1 cursor-pointer">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>
        </div>
        <div id="notificationList" class="p-2 overflow-y-auto max-h-[380px] space-y-2 text-xs">
            <!-- Itens de notificação renderizados dinamicamente via JS -->
        </div>
        <div class="p-2 border-t border-[#2f2f2f] bg-[#1a1a1a] flex items-center justify-between text-[11px] text-gray-400">
            <span class="flex items-center gap-1"><i class="fa-brands fa-windows text-sky-400 text-xs"></i> Notificações Desktop Ativas</span>
            <button onclick="checkDeadlinesAndNotify(true)" class="text-sky-400 hover:underline cursor-pointer">Atualizar</button>
        </div>
    </div>

    <div id="toastContainer" class="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none"></div>

    <script>
        let state = { categories: [], projects: [], tasks: [], notepad: [], userProfile: {} };
        let appMode = 'tasks';
        let currentFilter = 'myday';
        let currentViewMode = 'list';
        let selectedTaskId = null;
        let selectedNoteId = null;
        let saveStateTimeout = null;
        let tempProfileAvatar = null;
        
        // CRITICAL DATABASE LOAD & INITIALIZATION GUARDS
        let isLoadedFromDisk = false;
        let isInitializing = false;
        let dbBlocked = false;          // leitura falhou -> proibido gravar
        let dbBlockedReason = '';
        let bootFallbackRendered = false;
        let reconexaoTimer = null;

        /* A ponte do pywebview pode demorar bem mais que o previsto em máquinas
           lentas ou no primeiro arranque. Em vez de travar o app numa mensagem
           de erro, seguimos sondando: quando a API aparecer, o banco carrega
           sozinho e a gravação é reabilitada. */
        function aguardarPonteEmSegundoPlano() {
            if (reconexaoTimer) return;
            reconexaoTimer = setInterval(() => {
                if (isLoadedFromDisk) { clearInterval(reconexaoTimer); reconexaoTimer = null; return; }
                if (window.pywebview && window.pywebview.api &&
                    typeof window.pywebview.api.load_state_from_disk === 'function') {
                    clearInterval(reconexaoTimer); reconexaoTimer = null;
                    esconderAvisoConexao();
                    dbBlocked = false;
                    isInitializing = false;
                    initNativeApp();
                }
            }, 500);
        }

        function tentarReconectarAgora() {
            if (isLoadedFromDisk) return;
            dbBlocked = false;
            isInitializing = false;
            esconderAvisoConexao();
            setDbPathLabel("Conectando ao backend...", true);
            initNativeApp();
        }

        function mostrarAvisoConexao() {
            let el = document.getElementById('aviso-conexao');
            if (!el) {
                el = document.createElement('div');
                el.id = 'aviso-conexao';
                el.style.cssText = "position:fixed;left:50%;transform:translateX(-50%);bottom:18px;z-index:9999;" +
                    "background:#2a1f1f;border:1px solid #f43f5e66;color:#fda4af;padding:10px 14px;border-radius:6px;" +
                    "font-size:12px;display:flex;align-items:center;gap:12px;box-shadow:0 6px 24px #0008;max-width:92vw";
                el.innerHTML = '<span>Conectando ao backend... a gravação está desativada até o banco carregar.</span>' +
                    '<button id="btn-reconectar" style="background:#f43f5e22;border:1px solid #f43f5e66;color:#fda4af;' +
                    'padding:4px 10px;border-radius:4px;cursor:pointer;font-size:11px;font-weight:600">Tentar agora</button>';
                document.body.appendChild(el);
                el.querySelector('#btn-reconectar').addEventListener('click', tentarReconectarAgora);
            }
            el.style.display = 'flex';
        }

        function esconderAvisoConexao() {
            const el = document.getElementById('aviso-conexao');
            if (el) el.style.display = 'none';
        }

        // MULTI-SELECTION STATE
        let selectedTaskIds = new Set();
        let selectedCategoryIds = new Set();
        let selectedProjectIds = new Set();
        let selectedNoteIds = new Set();

        let selectedCategoryIcon = 'fa-regular fa-folder';
        let selectedProjectIcon = 'fa-solid fa-folder-tree';
        let tempNoteIcon = 'fa-regular fa-file-lines';

        const AVAILABLE_ICONS = [
            'fa-regular fa-file-lines', 'fa-regular fa-folder', 'fa-solid fa-folder-tree', 'fa-solid fa-briefcase',
            'fa-regular fa-star', 'fa-solid fa-code', 'fa-solid fa-rocket', 'fa-regular fa-lightbulb',
            'fa-solid fa-book', 'fa-solid fa-bullseye', 'fa-solid fa-layer-group', 'fa-solid fa-tag',
            'fa-solid fa-gear', 'fa-solid fa-chart-line', 'fa-solid fa-laptop-code', 'fa-regular fa-compass'
        ];

        function sanitizeState() {
            if (!state || typeof state !== 'object') state = { categories: [], projects: [], tasks: [], notepad: [], userProfile: {} };
            if (!Array.isArray(state.categories)) state.categories = [];
            if (!Array.isArray(state.projects)) state.projects = [];
            if (!Array.isArray(state.tasks)) state.tasks = [];
            if (!Array.isArray(state.notepad)) state.notepad = [];
            if (!state.userProfile || typeof state.userProfile !== 'object') state.userProfile = { name: "", subtitle: "", avatar: null };

            // Lista vazia e um estado VALIDO: nao recria a categoria de exemplo.

            state.tasks.forEach((t, idx) => {
                if (!t.id) t.id = 'task-' + Date.now() + '-' + idx;
                if (!t.title) t.title = t.nome || t.texto || 'Tarefa sem título';
                if (t.progress === undefined) t.progress = (t.completed || t.concluida) ? 100 : 0;
                if (!t.priority) t.priority = 'Média';
                if (!t.categoryId && state.categories.length > 0) t.categoryId = state.categories[0].id;
                if (!Array.isArray(t.steps)) t.steps = [];
                if (!Array.isArray(t.attachments)) t.attachments = [];
                if (t.isMyDay === undefined) t.isMyDay = true;
            });

            // Vault vazio e um estado VALIDO: nao recria a nota de exemplo.
        }

        async function initNativeApp() {
            if (isLoadedFromDisk || isInitializing) return;
            isInitializing = true;

            // O WebView2 injeta o objeto "api" ANTES de popular seus métodos.
            // Esperar só por window.pywebview.api passa cedo demais e a chamada
            // seguinte estoura "is not a function". Aqui esperamos o método real.
            let attempts = 0;
            while (attempts < 300) {
                if (window.pywebview && window.pywebview.api &&
                    typeof window.pywebview.api.load_state_from_disk === 'function') {
                    break;
                }
                await new Promise(res => setTimeout(res, 50));
                attempts++;
            }

            const apiPronta = !!(window.pywebview && window.pywebview.api &&
                typeof window.pywebview.api.load_state_from_disk === 'function');

            if (!apiPronta) {
                // A ponte pode simplesmente estar demorando. Em vez de desistir
                // de vez, renderiza a interface em modo somente-leitura e segue
                // tentando em segundo plano: assim que a API subir, recarrega.
                dbBlocked = true;
                dbBlockedReason = "Aguardando a ponte com o Python...";
                setDbPathLabel("Conectando ao backend...", true);
                isInitializing = false;
                if (!bootFallbackRendered) {
                    bootFallbackRendered = true;
                    sanitizeState();
                    renderProfile();
                    renderAll();
                }
                mostrarAvisoConexao();
                aguardarPonteEmSegundoPlano();
                return;
            }

            // Sem conta conectada, o app abre na tela de entrada em vez de
            // carregar direto — assim o usuário final só precisa de e-mail e senha.
            try {
                const st = await window.pywebview.api.cloud_status();
                cloudInfo = st;
                if (st.configured && !st.signedIn && !modoLocalEscolhido) {
                    isInitializing = false;
                    mostrarGate();
                    return;
                }
            } catch (e) { /* sem status: segue como app local */ }

            esconderGate();

            try {
                const dbPath = await window.pywebview.api.get_db_path();
                if (dbPath) setDbPathLabel(dbPath, false);
            } catch (e) { /* rótulo é cosmético; segue o carregamento */ }

            try {
                const ver = await window.pywebview.api.get_app_version();
                const badge = document.getElementById('app-version-badge');
                if (ver && badge) badge.innerText = ver;
            } catch (e) { /* idem */ }

            /* Migracao e atualizacao: ambas silenciosas e nao-bloqueantes.
               A checagem de versao no Python leva ~6s, entao consultamos
               algumas vezes em vez de uma so. */
            try { avisarMigracao(null); } catch (e) { /* cosmetico */ }
            try { setTimeout(checarSegurancaDaConexao, 8000); } catch (e) { }
            try { instalarSanitizacaoDoEditor(); } catch (e) { }
            try {
                let tentativas = 0;
                const t = setInterval(async () => {
                    tentativas++;
                    const r = await verificarAtualizacao(false);
                    if (r || tentativas >= 8) clearInterval(t);
                }, 3000);
            } catch (e) { /* cosmetico */ }

            try {
                let res = await window.pywebview.api.load_state_from_disk();

                // Compatibilidade: versões antigas devolviam a string crua.
                if (typeof res === 'string') {
                    res = { status: 'ok', data: res };
                }
                if (!res || typeof res !== 'object') {
                    throw new Error("Resposta inesperada do backend.");
                }

                if (res.file) setDbPathLabel(res.file, false);

                if (res.status === 'ok' || res.status === 'empty') {
                    if (res.data) {
                        let parsed = res.data;
                        if (typeof parsed === 'string') {
                            parsed = JSON.parse(parsed);
                            if (typeof parsed === 'string') parsed = JSON.parse(parsed);
                        }
                        if (parsed && typeof parsed === 'object') applyLoadedData(parsed);
                    }

                    isLoadedFromDisk = true;      // só aqui a gravação é liberada
                    dbBlocked = false;
                    dbBlockedReason = '';
                    isInitializing = false;
                    if (reconexaoTimer) { clearInterval(reconexaoTimer); reconexaoTimer = null; }
                    esconderAvisoConexao();

                    if (res.account) { cloudInfo = res.account; cloudInfo.lastSync = (res.cloud || {}).at; pintarBadgeNuvem(); }
                    finalizeInit(false, res.recovered, null, res.cloud);
                    return;
                }

                // status 'corrupt' ou 'error'
                dbBlocked = true;
                dbBlockedReason = res.message || "Não foi possível ler o banco de dados.";
                setDbPathLabel("ERRO AO LER O BANCO — gravação desativada", true);
                isInitializing = false;
                finalizeInit(true, false, res.quarantine);

            } catch (err) {
                console.error("Erro na inicialização nativa:", err);
                // IMPORTANTE: não marcar isLoadedFromDisk aqui. Destravar a
                // gravação após uma falha de leitura é justamente o que fazia
                // o app sobrescrever o banco com um estado vazio.
                dbBlocked = true;
                dbBlockedReason = String(err && err.message ? err.message : err);
                setDbPathLabel("ERRO AO LER O BANCO — gravação desativada", true);
                isInitializing = false;
                finalizeInit(true);
            }
        }

        /* Só escreve na barra em caso de ERRO. No estado normal quem manda é
           pintarBadgeNuvem(), para não reaparecer o caminho do arquivo local. */
        function setDbPathLabel(texto, isErro) {
            const el = document.getElementById('db-filepath-text');
            if (!el || !isErro) return;
            el.innerText = texto;
            el.style.color = '#fb7185';
        }

        function applyLoadedData(parsed) {
            if (!parsed || typeof parsed !== 'object') return;

            if (parsed.data && typeof parsed.data === 'object') parsed = parsed.data;
            if (parsed.state && typeof parsed.state === 'object') parsed = parsed.state;

            if (Array.isArray(parsed)) {
                state.tasks = parsed;
            } else {
                const tasksList = parsed.tasks || parsed.tarefas || parsed.items;
                if (Array.isArray(tasksList)) state.tasks = tasksList;

                const catList = parsed.categories || parsed.categorias;
                if (Array.isArray(catList) && catList.length > 0) state.categories = catList;

                const projList = parsed.projects || parsed.projetos;
                if (Array.isArray(projList) && projList.length > 0) state.projects = projList;

                const noteList = parsed.notepad || parsed.notes || parsed.vault;
                if (Array.isArray(noteList) && noteList.length > 0) state.notepad = noteList;

                const prof = parsed.userProfile || parsed.profile;
                if (prof && typeof prof === 'object') state.userProfile = { ...state.userProfile, ...prof };
            }
        }

        /* Carrega o avatar DEPOIS que a tela já está montada. Se ele for grande
           (bancos antigos guardavam a imagem original, de vários MB), reduz e
           regrava a versão leve — o app se conserta sozinho na primeira abertura. */
        async function carregarAvatarSobDemanda() {
            try {
                if (!window.pywebview || !window.pywebview.api ||
                    typeof window.pywebview.api.get_avatar !== 'function') return;

                const dado = await window.pywebview.api.get_avatar();
                if (!dado) return;

                avatarDataUri = dado;
                renderProfile();

                // ~700 KB em base64: acima disso vale reduzir de vez.
                if (dado.length > 700000) {
                    const menor = await reduzirImagem(dado, 256);
                    if (menor && menor.length < dado.length) {
                        avatarDataUri = menor;
                        state.userProfile.avatar = menor;   // o Python separa de novo
                        renderProfile();
                        saveState(false, true);
                        console.info('NEXUS: avatar reduzido de',
                            Math.round(dado.length/1024), 'KB para', Math.round(menor.length/1024), 'KB');
                    }
                }
            } catch (e) {
                console.warn('Falha ao carregar avatar:', e);
            }
        }

        function reduzirImagem(dataUri, maxDim) {
            return new Promise(resolve => {
                try {
                    const img = new Image();
                    img.onload = () => {
                        try {
                            let { width, height } = img;
                            const escala = Math.min(1, maxDim / Math.max(width, height));
                            width = Math.max(1, Math.round(width * escala));
                            height = Math.max(1, Math.round(height * escala));
                            const cv = document.createElement('canvas');
                            cv.width = width; cv.height = height;
                            cv.getContext('2d').drawImage(img, 0, 0, width, height);
                            resolve(cv.toDataURL('image/jpeg', 0.85));
                        } catch (e) { resolve(null); }
                    };
                    img.onerror = () => resolve(null);
                    img.src = dataUri;
                } catch (e) { resolve(null); }
            });
        }

        function finalizeInit(falhou = false, recuperado = false, quarentena = null, nuvem = null) {
            bootFallbackRendered = true;
            sanitizeState();
            renderProfile();
            renderAll();

            if (falhou) {
                const lbl = document.getElementById('status-save-label');
                const dot = document.getElementById('status-dot-indicator');
                if (lbl) lbl.innerText = "Gravação desativada";
                if (dot) dot.className = "w-2 h-2 rounded-full bg-rose-500 shadow-sm";

                const extra = quarentena
                    ? `\n\nO arquivo problemático foi preservado em:\n${quarentena}`
                    : '';
                setTimeout(() => alert(
                    "Não foi possível carregar o banco de dados.\n\n" +
                    dbBlockedReason + extra +
                    "\n\nA gravação foi DESATIVADA para não sobrescrever seus dados. " +
                    "Corrija o arquivo e reabra o NEXUS."
                ), 300);
                return;
            }

            const total = state.tasks.length;
            const notas = state.notepad.length;
            if (cloudInfo && cloudInfo.signedIn) {
                // Com conta, a barra fala da NUVEM (mesmo padrão do Cogni).
                const mapa = { pulled: 'atualizado', pushed: 'enviado', seeded: 'enviado', in_sync: 'sincronizado' };
                marcarEventoNuvem(mapa[(nuvem || {}).state] || 'sincronizado');
            } else {
                showAutoSaveUI(recuperado
                    ? `Restaurado do backup (${total} tarefas)`
                    : `Banco carregado (${total} tarefas, ${notas} notas)`);
            }

            // Interface já está na tela: agora sim busca a imagem do perfil.
            setTimeout(carregarAvatarSobDemanda, 50);
            setTimeout(atualizarStatusNuvem, 120);

            if (nuvem && nuvem.state) {
                const rotulos = {
                    pulled:  `Dados atualizados da nuvem (${nuvem.items || 0} itens)`,
                    pushed:  `Nuvem atualizada com esta máquina (${nuvem.items || 0} itens)`,
                    seeded:  'Primeira sincronização concluída',
                    in_sync: 'Tudo sincronizado com a nuvem',
                };
                if (rotulos[nuvem.state]) showToast(rotulos[nuvem.state]);
                else if (nuvem.state === 'conflict') avisarConflitoNuvem(nuvem);
                else if (nuvem.state === 'auth_error') showToast('Nuvem: ' + (nuvem.message || 'sessão expirada.'));
                else if (nuvem.state === 'push_failed' || nuvem.state === 'error')
                    showToast('Sem conexão com a nuvem — salvo apenas nesta máquina.');
            }

            // Monitor de prazos e atualizacao do icone da barra de tarefas
            try { checkDeadlinesAndNotify(false); } catch (e) { console.warn("Erro ao checar prazos:", e); }
        }

        window.addEventListener('pywebviewready', initNativeApp);
        document.addEventListener('DOMContentLoaded', () => {
            setTimeout(initNativeApp, 100);
            // Checagem periodica a cada 5 minutos
            setInterval(() => {
                if (isLoadedFromDisk && !dbBlocked) {
                    checkDeadlinesAndNotify(false);
                }
            }, 5 * 60 * 1000);
        });

        function saveState(showVisualIndicator = true, immediate = false) {
            if (dbBlocked) {
                console.warn("Salvamento bloqueado: falha ao ler o banco.", dbBlockedReason);
                return;
            }
            if (!isLoadedFromDisk) {
                console.warn("Salvamento bloqueado: o aplicativo ainda está lendo o banco do disco.");
                return;
            }
            if (saveStateTimeout) clearTimeout(saveStateTimeout);
            if (immediate) {
                executeDiskSave(showVisualIndicator);
            } else {
                saveStateTimeout = setTimeout(() => {
                    executeDiskSave(showVisualIndicator);
                }, 600);
            }
        }

        function executeDiskSave(showVisualIndicator = true) {
            if (!isLoadedFromDisk || dbBlocked) return;
            try {
                const jsonStr = JSON.stringify(state);
                if (window.pywebview && window.pywebview.api &&
                    typeof window.pywebview.api.save_state_to_disk === 'function') {
                    window.pywebview.api.save_state_to_disk(jsonStr).then((res) => {
                        if (res && res.status === 'success') {
                            if (res.lastSync) cloudInfo.lastSync = res.lastSync;
                            // "cloud" diz se a nuvem aceitou; sem rede vira offline.
                            if (cloudInfo.signedIn) {
                                marcarEventoNuvem(res.cloud === 'success' ? 'enviado' : 'offline');
                            } else if (showVisualIndicator) {
                                showAutoSaveUI();
                            }
                            // Reavalia prazos e taskbar overlay
                            try { checkDeadlinesAndNotify(false); } catch (e) { }
                        } else {
                            const detalhe = (res && res.message) ? res.message : 'motivo desconhecido';
                            console.error("Falha ao gravar:", detalhe);
                            const lbl = document.getElementById('status-save-label');
                            const dot = document.getElementById('status-dot-indicator');
                            if (lbl) lbl.innerText = "ERRO ao salvar";
                            if (dot) dot.className = "w-2 h-2 rounded-full bg-rose-500 shadow-sm";
                        }
                    }).catch(err => console.error("Disk save error:", err));
                }
            } catch (e) { console.error("Disk save error:", e); }
        }

        // Garante que uma gravação pendente não se perca ao fechar a janela.
        window.addEventListener('beforeunload', () => {
            if (isLoadedFromDisk && !dbBlocked && saveStateTimeout) {
                clearTimeout(saveStateTimeout);
                executeDiskSave(false);
            }
        });

        function showAutoSaveUI(overrideText = null) {
            const lbl = document.getElementById('status-save-label');
            const dot = document.getElementById('status-dot-indicator');
            if (lbl) {
                if (overrideText) {
                    lbl.innerText = overrideText;
                } else {
                    const now = new Date();
                    const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;
                    lbl.innerText = `Salvo às ${timeStr}`;
                }
            }
            if (dot) {
                dot.className = "w-2 h-2 rounded-full bg-emerald-500 shadow-sm";
            }
        }

        function renderAll() {
            renderSidebarCategories();
            renderSidebarProjects();
            renderBadges();
            if (appMode === 'tasks') {
                if (currentViewMode === 'list') renderTasksList();
                else if (currentViewMode === 'kanban') renderKanbanView();
                else if (currentViewMode === 'charts') renderChartsView();
            } else {
                renderNotepadTree();
            }
            try { checkDeadlinesAndNotify(false); } catch (e) { }
        }

        /* O avatar não vive mais dentro de state (nem do tasks_db.json).
           Fica nesta variável, carregada depois que a tela já apareceu. */
        let avatarDataUri = null;
        const AVATAR_MARKER = '@file';

        function getAvatarSrc() {
            const p = state.userProfile || {};
            if (avatarDataUri) return avatarDataUri;
            // Avatar recém-escolhido, ainda não gravado
            if (typeof p.avatar === 'string' && p.avatar && p.avatar !== AVATAR_MARKER) return p.avatar;
            return null;
        }

        function renderProfile() {
            const p = state.userProfile || {};
            const nameEl = document.getElementById('profile-name');
            const subEl = document.getElementById('profile-subtitle');
            const initEl = document.getElementById('profile-initials-sidebar');
            const imgEl = document.getElementById('profile-avatar-img');

            if (nameEl) nameEl.innerText = p.name || "Caio";
            if (subEl) subEl.innerText = p.subtitle || "DEV";

            const avatarSrc = getAvatarSrc();
            if (avatarSrc && imgEl) {
                imgEl.src = avatarSrc;
                imgEl.classList.remove('hidden');
                if (initEl) initEl.classList.add('hidden');
            } else {
                if (imgEl) imgEl.classList.add('hidden');
                if (initEl) {
                    initEl.classList.remove('hidden');
                    const parts = (p.name || "CA").trim().split(' ');
                    initEl.innerText = parts.length > 1 ? (parts[0][0] + parts[1][0]).toUpperCase() : (parts[0].slice(0, 2)).toUpperCase();
                }
            }
        }

        function openProfileModal() {
            const p = state.userProfile || {};
            document.getElementById('profileNameInput').value = p.name || 'Caio';
            document.getElementById('profileSubtitleInput').value = p.subtitle || 'DEV';
            tempProfileAvatar = getAvatarSrc();
            updateModalAvatarPreview();
            const box = document.getElementById('profileAccountBox');
            const em = document.getElementById('profileAccountEmail');
            if (box && em) {
                if (cloudInfo && cloudInfo.signedIn) {
                    em.innerText = cloudInfo.email || '';
                    box.classList.remove('hidden');
                } else {
                    box.classList.add('hidden');
                }
            }
            document.getElementById('profileModal').classList.remove('hidden');
        }

        function handleProfileAvatarUpload(event) {
            const file = event.target.files && event.target.files[0];
            if (!file) return;

            const reader = new FileReader();
            reader.onload = function(e) {
                const img = new Image();
                img.onload = function() {
                    const canvas = document.createElement('canvas');
                    const maxDim = 256;
                    let width = img.width;
                    let height = img.height;

                    if (width > height) {
                        if (width > maxDim) {
                            height = Math.round((height * maxDim) / width);
                            width = maxDim;
                        }
                    } else {
                        if (height > maxDim) {
                            width = Math.round((width * maxDim) / height);
                            height = maxDim;
                        }
                    }

                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, width, height);

                    tempProfileAvatar = canvas.toDataURL('image/jpeg', 0.85);
                    updateModalAvatarPreview();
                };
                img.src = e.target.result;
            };
            reader.readAsDataURL(file);
        }

        function removeProfileAvatar() {
            tempProfileAvatar = null;
            const fileInput = document.getElementById('profileAvatarInput');
            if (fileInput) fileInput.value = '';
            updateModalAvatarPreview();
        }

        function updateModalAvatarPreview() {
            const name = document.getElementById('profileNameInput').value || 'Caio';
            const initialsEl = document.getElementById('modalAvatarInitials');
            const imgEl = document.getElementById('modalAvatarPreview');
            const removeBtn = document.getElementById('removeAvatarBtn');

            if (tempProfileAvatar) {
                imgEl.src = tempProfileAvatar;
                imgEl.classList.remove('hidden');
                initialsEl.classList.add('hidden');
                if (removeBtn) removeBtn.classList.remove('hidden');
            } else {
                imgEl.classList.add('hidden');
                initialsEl.classList.remove('hidden');
                if (removeBtn) removeBtn.classList.add('hidden');

                const parts = name.trim().split(' ');
                initialsEl.innerText = parts.length > 1 ? (parts[0][0] + parts[1][0]).toUpperCase() : (parts[0].slice(0, 2)).toUpperCase();
            }
        }

        function closeProfileModal() { document.getElementById('profileModal').classList.add('hidden'); }
        
        function saveProfile() {
            if (!state.userProfile) state.userProfile = {};
            state.userProfile.name = document.getElementById('profileNameInput').value.trim() || 'Caio';
            state.userProfile.subtitle = document.getElementById('profileSubtitleInput').value.trim() || 'DEV';

            if (tempProfileAvatar) {
                // Vai embutido só nesta gravação; o Python move para avatar.dat.
                state.userProfile.avatar = tempProfileAvatar;
                avatarDataUri = tempProfileAvatar;
            } else {
                state.userProfile.avatar = null;
                avatarDataUri = null;
                if (window.pywebview && window.pywebview.api &&
                    typeof window.pywebview.api.clear_avatar === 'function') {
                    window.pywebview.api.clear_avatar().catch(() => {});
                }
            }

            saveState(true, true);
            renderProfile();
            closeProfileModal();
            showToast("Perfil atualizado!");
        }

        function switchAppMode(mode) {
            appMode = mode;
            const btnTasks = document.getElementById('mode-btn-tasks');
            const btnNotepad = document.getElementById('mode-btn-notepad');
            const sideTasks = document.getElementById('sidebar-tasks-panel');
            const sideNotepad = document.getElementById('sidebar-notepad-panel');
            const mainTasks = document.getElementById('main-tasks-view');
            const mainNotepad = document.getElementById('main-notepad-view');

            if (mode === 'tasks') {
                btnTasks.className = "py-1.5 rounded flex items-center justify-center gap-1.5 bg-[#2a2a2a] text-white border border-white/10 transition cursor-pointer";
                btnNotepad.className = "py-1.5 rounded flex items-center justify-center gap-1.5 text-gray-400 hover:text-white transition cursor-pointer";
                sideTasks.classList.remove('hidden');
                sideNotepad.classList.add('hidden');
                mainTasks.classList.remove('hidden');
                mainNotepad.classList.add('hidden');
                renderTasksList();
            } else {
                btnNotepad.className = "py-1.5 rounded flex items-center justify-center gap-1.5 bg-[#2a2a2a] text-white border border-white/10 transition cursor-pointer";
                btnTasks.className = "py-1.5 rounded flex items-center justify-center gap-1.5 text-gray-400 hover:text-white transition cursor-pointer";
                sideNotepad.classList.remove('hidden');
                sideTasks.classList.add('hidden');
                mainNotepad.classList.remove('hidden');
                mainTasks.classList.add('hidden');
                renderNotepadTree();
                if (!selectedNoteId && state.notepad.length > 0) {
                    selectNote(state.notepad[0].id);
                }
            }
        }

        function setViewMode(mode) {
            // Ao mudar de visão, descarrega edições pendentes e fecha o painel.
            // Sem isso o Kanban abria já com a tarefa que estava aberta na Lista,
            // e o destaque ficava preso nela.
            flushPendingDrawerEdits();
            if (currentViewMode !== mode && selectedTaskId) {
                selectedTaskId = null;
                const dr = document.getElementById('taskDetailDrawer');
                if (dr) dr.classList.add('hidden');
            }
            currentViewMode = mode;
            document.getElementById('view-mode-list').className = mode === 'list' ? "px-2.5 py-1 rounded bg-[#2a2a2a] text-white border border-white/10 transition cursor-pointer" : "px-2.5 py-1 rounded text-gray-400 hover:text-white transition cursor-pointer";
            document.getElementById('view-mode-kanban').className = mode === 'kanban' ? "px-2.5 py-1 rounded bg-[#2a2a2a] text-white border border-white/10 transition cursor-pointer" : "px-2.5 py-1 rounded text-gray-400 hover:text-white transition cursor-pointer";
            document.getElementById('view-mode-charts').className = mode === 'charts' ? "px-2.5 py-1 rounded bg-[#2a2a2a] text-white border border-white/10 transition cursor-pointer" : "px-2.5 py-1 rounded text-gray-400 hover:text-white transition cursor-pointer";

            document.getElementById('list-view-container').classList.toggle('hidden', mode !== 'list');
            document.getElementById('kanban-view-container').classList.toggle('hidden', mode !== 'kanban');
            document.getElementById('charts-view-container').classList.toggle('hidden', mode !== 'charts');

            if (mode === 'list') renderTasksList();
            else if (mode === 'kanban') renderKanbanView();
            else if (mode === 'charts') renderChartsView();
        }

        function selectList(id) {
            currentFilter = id;
            document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
            const activeBtn = document.getElementById(`nav-${id}`);
            if (activeBtn) activeBtn.classList.add('active');

            const titleEl = document.getElementById('current-list-title');
            const iconEl = document.getElementById('current-list-icon');
            const subEl = document.getElementById('current-list-subtitle');

            if (id === 'myday') {
                titleEl.innerText = "Meu Dia";
                iconEl.className = "fa-regular fa-sun text-xl text-amber-400";
                subEl.innerText = "Tarefas em foco para hoje";
            } else if (id === 'planned') {
                titleEl.innerText = "Planejadas";
                iconEl.className = "fa-regular fa-calendar-check text-xl text-sky-400";
                subEl.innerText = "Tarefas com data de conclusão";
            } else if (id === 'all') {
                titleEl.innerText = "Todas as Tarefas";
                iconEl.className = "fa-solid fa-bars-staggered text-xl text-purple-400";
                subEl.innerText = "Visão geral completa";
            } else if (id.startsWith('cat-')) {
                const cat = state.categories.find(c => c.id === id);
                titleEl.innerText = cat ? cat.name : "Categoria";
                iconEl.className = `${cat?.icon || 'fa-regular fa-folder'} text-xl text-sky-400`;
                subEl.innerText = "Filtro por Categoria";
            } else if (id.startsWith('proj-')) {
                const proj = state.projects.find(p => p.id === id);
                titleEl.innerText = proj ? proj.name : "Projeto";
                iconEl.className = `${proj?.icon || 'fa-solid fa-folder-tree'} text-xl text-purple-400`;
                subEl.innerText = "Filtro por Projeto";
            }

            renderAll();
        }

        function getFilteredTasks() {
            let list = [...state.tasks];
            const q = (document.getElementById('searchInput')?.value || '').toLowerCase().trim();
            if (q) return list.filter(t => (t.title && String(t.title).toLowerCase().includes(q)));

            const todayStr = new Date().toISOString().split('T')[0];
            // isMyDay === false = removido de propósito; vence sobre a data de hoje.
            if (currentFilter === 'myday') return list.filter(t => t.isMyDay === false ? false : (t.isMyDay === true || t.dueDate === todayStr));
            if (currentFilter === 'planned') return list.filter(t => t.dueDate);
            if (currentFilter === 'all') return list;
            if (currentFilter.startsWith('cat-')) return list.filter(t => t.categoryId === currentFilter);
            if (currentFilter.startsWith('proj-')) return list.filter(t => t.projectId === currentFilter);
            return list;
        }

        /* Redesenha a visão que está realmente na tela. Várias ações chamavam
           renderTasksList() fixo: no Kanban isso atualizava um container oculto
           e os cards ficavam com o destaque de seleção defasado, apontando para
           uma tarefa diferente da que o painel de detalhes estava exibindo. */
        function renderCurrentView() {
            if (appMode !== 'tasks') { renderNotepadTree(); return; }
            if (currentViewMode === 'kanban') renderKanbanView();
            else if (currentViewMode === 'charts') renderChartsView();
            else renderTasksList();
        }

        function renderTasksList() {
            const list = getFilteredTasks();
            const activeTasks = list.filter(t => (Number(t.progress) || 0) < 100);
            const doneTasks = list.filter(t => (Number(t.progress) || 0) >= 100);

            const activeContainer = document.getElementById('active-tasks-list');
            if (activeContainer) {
                activeContainer.innerHTML = activeTasks.length > 0 
                    ? activeTasks.map(t => createTaskCardHTML(t)).join('') 
                    : '<p class="text-xs text-gray-500 italic p-6 text-center">Nenhuma tarefa pendente neste filtro.</p>';
            }

            const completedSection = document.getElementById('completed-section');
            const completedContainer = document.getElementById('completed-tasks-list');
            const completedCount = document.getElementById('completed-count');

            if (doneTasks.length > 0) {
                completedSection.classList.remove('hidden');
                completedCount.innerText = doneTasks.length;
                completedContainer.innerHTML = doneTasks.map(t => createTaskCardHTML(t)).join('');
            } else {
                completedSection.classList.add('hidden');
            }
        }

        function createTaskCardHTML(t) {
            const progVal = Number(t.progress) || 0;
            const isDone = progVal >= 100;
            const cat = state.categories.find(c => c.id === t.categoryId);
            const proj = state.projects.find(p => p.id === t.projectId);
            const steps = Array.isArray(t.steps) ? t.steps : [];
            const atts = Array.isArray(t.attachments) ? t.attachments : [];
            const isBatchSelected = selectedTaskIds.has(t.id);

            let prioColor = 'text-gray-400 bg-white/5 border-white/5';
            if (t.priority === 'Urgente') prioColor = 'text-rose-400 bg-rose-500/10 border-rose-500/30';
            else if (t.priority === 'Alta') prioColor = 'text-amber-400 bg-amber-500/10 border-amber-500/30';
            else if (t.priority === 'Média') prioColor = 'text-sky-400 bg-sky-500/10 border-sky-500/30';

            let stepsHTML = '';
            if (steps.length > 0) {
                stepsHTML = `
                    <div class="mt-2 pt-2 border-t border-[#2f2f2f]/60 space-y-1" onclick="event.stopPropagation()">
                        <div class="text-[10px] text-gray-500 font-mono flex items-center justify-between mb-1">
                            <span>Etapas (${steps.filter(s=>s.completed).length}/${steps.length})</span>
                        </div>
                        <!-- auto-fill responde à largura do card; sm:grid-cols-2 respondia
                             à da janela e mantinha 2 colunas num card já estreito. -->
                        <div class="gap-1.5" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr))">
                            ${steps.map((s, idx) => `
                                <div class="flex items-center gap-2 p-1 bg-white/5 rounded hover:bg-white/10 transition text-xs">
                                    <button onclick="toggleStepDirect('${t.id}', ${idx})" class="w-3.5 h-3.5 rounded border ${s.completed ? 'bg-[#2eaadc] border-[#2eaadc] text-white' : 'border-gray-600 hover:border-sky-400'} flex items-center justify-center transition cursor-pointer flex-shrink-0">
                                        ${s.completed ? '<i class="fa-solid fa-check text-[8px]"></i>' : ''}
                                    </button>
                                    <span class="${s.completed ? 'line-through text-gray-500' : 'text-gray-300'} truncate text-[11px]">${escapeHtml(s.title)}</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }

            return `
                <div onclick="handleTaskCardClick(event, '${t.id}')" class="group notion-card rounded p-3 flex flex-col gap-2 cursor-pointer select-none ${selectedTaskId === t.id ? 'selected' : ''} ${isBatchSelected ? 'bg-sky-950/30 border-[#2eaadc]/50' : ''}">
                    <!-- flex-wrap + base mínima no título: quando o espaço aperta
                         (janela estreita ou painel de detalhes aberto), a fileira de
                         etiquetas desce para a linha de baixo em vez de esmagar o
                         título até sumir e vazar para fora do card. -->
                    <div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 min-w-0">
                        <div class="flex items-center gap-2.5 min-w-0" style="flex: 1 1 190px">
                            <button onclick="event.stopPropagation(); toggleTaskSelection('${t.id}')" class="w-4 h-4 rounded border ${isBatchSelected ? 'bg-[#2eaadc] border-[#2eaadc] text-white opacity-100' : 'border-gray-600 hover:border-sky-400 opacity-0 group-hover:opacity-100'} flex items-center justify-center transition cursor-pointer flex-shrink-0" title="Selecionar para exclusão/ações em massa">
                                ${isBatchSelected ? '<i class="fa-solid fa-check text-[9px]"></i>' : ''}
                            </button>

                            <button onclick="event.stopPropagation(); toggleTaskCompletion('${t.id}')" class="w-4 h-4 rounded-full border ${isDone ? 'bg-emerald-600 border-emerald-500 text-white' : 'border-gray-600 hover:border-sky-400'} flex items-center justify-center transition cursor-pointer flex-shrink-0">
                                ${isDone ? '<i class="fa-solid fa-check text-[9px]"></i>' : ''}
                            </button>
                            
                            <span class="text-xs ${isDone ? 'line-through text-gray-500' : 'text-gray-200 font-medium'} truncate min-w-0" title="${escapeHtml(t.title)}">${escapeHtml(t.title)}</span>
                        </div>

                        <div class="flex flex-wrap items-center justify-end gap-1.5 min-w-0" onclick="event.stopPropagation()">
                            ${t.priority ? `<span class="text-[10px] px-1.5 py-0.5 rounded border font-semibold whitespace-nowrap ${prioColor}">${t.priority}</span>` : ''}
                            ${cat ? `<span class="text-[10px] bg-white/5 text-gray-400 px-1.5 py-0.5 rounded border border-white/5 max-w-[45%] truncate whitespace-nowrap" title="${escapeHtml(cat.name)}"><i class="${cat.icon || 'fa-regular fa-folder'} mr-1 text-[9px]"></i>${escapeHtml(cat.name)}</span>` : ''}
                            ${proj ? `<span class="text-[10px] bg-sky-500/10 text-sky-300 px-1.5 py-0.5 rounded border border-sky-500/20 max-w-[45%] truncate whitespace-nowrap" title="${escapeHtml(proj.name)}"><i class="${proj.icon || 'fa-solid fa-folder-tree'} mr-1 text-[9px]"></i>${escapeHtml(proj.name)}</span>` : ''}
                            ${t.dueDate ? `<span class="text-[10px] text-gray-400 bg-white/5 px-1.5 py-0.5 rounded border border-white/5 whitespace-nowrap"><i class="fa-regular fa-calendar mr-1"></i>${formatDateBR(t.dueDate)}</span>` : ''}
                            ${atts.length > 0 ? `<span class="text-[10px] text-sky-300 bg-sky-500/10 px-1.5 py-0.5 rounded border border-sky-500/20 whitespace-nowrap" title="${escapeHtml(atts.map(a => a.name).join(', '))}"><i class="fa-solid fa-paperclip mr-1"></i>${atts.length} · ${formatarTamanho(atts.reduce((s,a)=>s+(Number(a.size)||0),0))}</span>` : ''}
                            ${t.notes ? `<i class="fa-regular fa-note-sticky text-gray-500 text-xs" title="Possui anotações"></i>` : ''}
                            <button onclick="toggleTaskMyDay('${t.id}')" class="text-xs ${t.isMyDay !== false ? 'text-amber-400' : 'text-gray-600 hover:text-amber-300'} transition cursor-pointer p-0.5" title="${t.isMyDay !== false ? 'Remover do Meu Dia' : 'Adicionar ao Meu Dia'}">
                                <i class="fa-regular fa-sun"></i>
                            </button>
                            <button onclick="toggleTaskStar('${t.id}')" class="text-xs ${t.isStarred ? 'text-amber-400' : 'text-gray-600 hover:text-amber-300'} transition cursor-pointer p-0.5" title="Favoritar">
                                <i class="${t.isStarred ? 'fa-solid' : 'fa-regular'} fa-star"></i>
                            </button>
                        </div>
                    </div>

                    <div class="flex items-center gap-3 pt-1 min-w-0" onclick="event.stopPropagation()">
                        <span class="text-[10px] font-mono font-bold text-[#2eaadc] w-7 flex-shrink-0">${progVal}%</span>
                        <div class="flex-1 min-w-0 bg-white/10 h-1.5 rounded-full overflow-hidden cursor-pointer relative" onclick="setTaskProgressFromClick(event, '${t.id}')" title="Clique para alterar o progresso da tarefa">
                            <div class="bg-[#2eaadc] h-full transition-all duration-300" style="width: ${progVal}%"></div>
                        </div>
                    </div>

                    ${stepsHTML}
                </div>
            `;
        }

        /* O card da lista é horizontal (título à esquerda, fileira de badges à
           direita que não encolhe). Numa coluna estreita do Kanban isso esmaga
           o título até zero e as badges vazam. Aqui o layout é vertical:
           título primeiro, em linha inteira, e o resto abaixo. */
        function createKanbanCardHTML(t) {
            const progVal = Number(t.progress) || 0;
            const isDone = progVal >= 100;
            const cat = state.categories.find(c => c.id === t.categoryId);
            const proj = state.projects.find(p => p.id === t.projectId);
            const steps = Array.isArray(t.steps) ? t.steps : [];
            const atts = Array.isArray(t.attachments) ? t.attachments : [];
            const isBatchSelected = selectedTaskIds.has(t.id);
            const feitas = steps.filter(s => s.completed).length;

            let prioColor = 'text-gray-400 bg-white/5 border-white/10';
            if (t.priority === 'Urgente') prioColor = 'text-rose-400 bg-rose-500/10 border-rose-500/30';
            else if (t.priority === 'Alta') prioColor = 'text-amber-400 bg-amber-500/10 border-amber-500/30';
            else if (t.priority === 'Média') prioColor = 'text-sky-400 bg-sky-500/10 border-sky-500/30';

            // Etapas viram um resumo clicável em vez de uma grade que estica o card.
            const stepsHTML = steps.length > 0 ? `
                <div class="flex items-center gap-1.5 text-[10px] text-gray-500 font-mono">
                    <i class="fa-solid fa-list-check text-[9px]"></i>
                    <span>${feitas}/${steps.length} etapas</span>
                </div>` : '';

            const badges = [
                t.priority ? `<span class="text-[10px] px-1.5 py-0.5 rounded border font-semibold ${prioColor} max-w-full truncate">${t.priority}</span>` : '',
                cat ? `<span class="text-[10px] bg-white/5 text-gray-400 px-1.5 py-0.5 rounded border border-white/10 max-w-full truncate"><i class="${cat.icon || 'fa-regular fa-folder'} mr-1 text-[9px]"></i>${escapeHtml(cat.name)}</span>` : '',
                proj ? `<span class="text-[10px] bg-sky-500/10 text-sky-300 px-1.5 py-0.5 rounded border border-sky-500/20 max-w-full truncate"><i class="${proj.icon || 'fa-solid fa-folder-tree'} mr-1 text-[9px]"></i>${escapeHtml(proj.name)}</span>` : '',
                t.dueDate ? `<span class="text-[10px] text-gray-400 bg-white/5 px-1.5 py-0.5 rounded border border-white/10 whitespace-nowrap"><i class="fa-regular fa-calendar mr-1"></i>${formatDateBR(t.dueDate)}</span>` : '',
                atts.length > 0 ? `<span class="text-[10px] text-sky-300 bg-sky-500/10 px-1.5 py-0.5 rounded border border-sky-500/20 whitespace-nowrap" title="${escapeHtml(atts.map(a => a.name).join(', '))}"><i class="fa-solid fa-paperclip mr-1"></i>${atts.length} · ${formatarTamanho(atts.reduce((s,a)=>s+(Number(a.size)||0),0))}</span>` : '',
                `<button onclick="toggleTaskMyDay('${t.id}')" class="text-[10px] px-1.5 py-0.5 rounded border whitespace-nowrap transition cursor-pointer ${t.isMyDay !== false ? 'text-amber-300 bg-amber-500/10 border-amber-500/20 hover:bg-amber-500/20' : 'text-gray-500 bg-white/5 border-white/10 hover:text-amber-300'}" title="${t.isMyDay !== false ? 'Remover do Meu Dia' : 'Adicionar ao Meu Dia'}"><i class="fa-regular fa-sun"></i></button>`,
            ].filter(Boolean).join('');

            return `
                <div onclick="handleTaskCardClick(event, '${t.id}')" class="group notion-card rounded p-2.5 flex flex-col gap-2 cursor-pointer select-none min-w-0 ${selectedTaskId === t.id ? 'selected' : ''} ${isBatchSelected ? 'bg-sky-950/30 border-[#2eaadc]/50' : ''}">

                    <div class="flex items-start gap-2 min-w-0">
                        <button onclick="event.stopPropagation(); toggleTaskCompletion('${t.id}')" class="w-4 h-4 mt-0.5 rounded-full border ${isDone ? 'bg-emerald-600 border-emerald-500 text-white' : 'border-gray-600 hover:border-sky-400'} flex items-center justify-center transition cursor-pointer flex-shrink-0" title="Concluir tarefa">
                            ${isDone ? '<i class="fa-solid fa-check text-[9px]"></i>' : ''}
                        </button>

                        <span class="flex-1 min-w-0 text-xs leading-snug break-words ${isDone ? 'line-through text-gray-500' : 'text-gray-100 font-medium'}" style="display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;" title="${escapeHtml(t.title)}">${escapeHtml(t.title)}</span>

                        <div class="flex items-center gap-1 flex-shrink-0" onclick="event.stopPropagation()">
                            <button onclick="toggleTaskStar('${t.id}')" class="text-xs ${t.isStarred ? 'text-amber-400' : 'text-gray-600 hover:text-amber-300'} transition cursor-pointer" title="Favoritar">
                                <i class="${t.isStarred ? 'fa-solid' : 'fa-regular'} fa-star"></i>
                            </button>
                            <button onclick="toggleTaskSelection('${t.id}')" class="w-4 h-4 rounded border ${isBatchSelected ? 'bg-[#2eaadc] border-[#2eaadc] text-white opacity-100' : 'border-gray-600 hover:border-sky-400 opacity-0 group-hover:opacity-100'} flex items-center justify-center transition cursor-pointer" title="Selecionar">
                                ${isBatchSelected ? '<i class="fa-solid fa-check text-[9px]"></i>' : ''}
                            </button>
                        </div>
                    </div>

                    ${badges ? `<div class="flex flex-wrap items-center gap-1 min-w-0" onclick="event.stopPropagation()">${badges}</div>` : ''}

                    ${stepsHTML}

                    <div class="flex items-center gap-2 min-w-0" onclick="event.stopPropagation()">
                        <span class="text-[10px] font-mono font-bold text-[#2eaadc] flex-shrink-0">${progVal}%</span>
                        <div class="flex-1 min-w-0 bg-white/10 h-1.5 rounded-full overflow-hidden cursor-pointer" onclick="setTaskProgressFromClick(event, '${t.id}')" title="Clique para alterar o progresso">
                            <div class="bg-[#2eaadc] h-full transition-all duration-300" style="width: ${progVal}%"></div>
                        </div>
                    </div>
                </div>
            `;
        }

        function handleTaskCardClick(e, taskId) {
            openTaskDetailDrawer(taskId);
        }

        function setTaskProgressFromClick(e, taskId) {
            const rect = e.currentTarget.getBoundingClientRect();
            const clickX = e.clientX - rect.left;
            const pct = Math.round((clickX / rect.width) * 100);
            const clampedPct = Math.max(0, Math.min(100, Math.round(pct / 5) * 5));
            
            const t = state.tasks.find(x => x.id === taskId);
            if (t) {
                t.progress = clampedPct;
                saveState(true, true);
                renderAll();
                if (selectedTaskId === taskId) populateDrawer(t);
            }
        }

        function toggleTaskSelection(taskId) {
            if (selectedTaskIds.has(taskId)) {
                selectedTaskIds.delete(taskId);
            } else {
                selectedTaskIds.add(taskId);
            }
            updateBatchUI();
            renderCurrentView();
        }

        function toggleCategorySelection(catId) {
            if (selectedCategoryIds.has(catId)) {
                selectedCategoryIds.delete(catId);
            } else {
                selectedCategoryIds.add(catId);
            }
            updateBatchUI();
            renderSidebarCategories();
        }

        function toggleProjectSelection(projId) {
            if (selectedProjectIds.has(projId)) {
                selectedProjectIds.delete(projId);
            } else {
                selectedProjectIds.add(projId);
            }
            updateBatchUI();
            renderSidebarProjects();
        }

        function toggleNoteSelection(noteId) {
            if (selectedNoteIds.has(noteId)) {
                selectedNoteIds.delete(noteId);
            } else {
                selectedNoteIds.add(noteId);
            }
            updateBatchUI();
            renderNotepadTree();
        }

        function clearAllSelections() {
            selectedTaskIds.clear();
            selectedCategoryIds.clear();
            selectedProjectIds.clear();
            selectedNoteIds.clear();
            updateBatchUI();
            renderAll();
        }

        function updateBatchUI() {
            const totalCount = selectedTaskIds.size + selectedCategoryIds.size + selectedProjectIds.size + selectedNoteIds.size;
            const bar = document.getElementById('batch-actions-bar');
            const countEl = document.getElementById('batch-selected-count');
            
            if (bar) {
                if (totalCount > 0) bar.classList.remove('hidden');
                else bar.classList.add('hidden');
            }

            if (countEl) {
                countEl.innerText = `${totalCount} item(ns) selecionado(s) (${selectedTaskIds.size} tarefas, ${selectedCategoryIds.size} categorias, ${selectedProjectIds.size} projetos, ${selectedNoteIds.size} notas)`;
            }
        }

        /* Meu Dia: isMyDay === false significa "removido explicitamente" e
           tem prioridade sobre a data de vencimento, senão uma tarefa que
           vence hoje voltaria sozinha para o Meu Dia depois de removida. */
        function toggleTaskMyDay(taskId) {
            const t = state.tasks.find(x => x.id === taskId);
            if (!t) return;
            const estaNoMyDay = t.isMyDay !== false;
            t.isMyDay = !estaNoMyDay;
            saveState(true, true);
            renderAll();
            if (selectedTaskId === taskId) openTaskDetailDrawer(taskId);
            showToast(t.isMyDay ? "Adicionada ao Meu Dia." : "Removida do Meu Dia.");
        }

        function batchSetMyDay(valor) {
            if (selectedTaskIds.size === 0) {
                showToast("Selecione ao menos uma tarefa.");
                return;
            }
            let n = 0;
            state.tasks.forEach(t => {
                if (selectedTaskIds.has(t.id)) { t.isMyDay = valor; n++; }
            });
            saveState(true, true);
            clearAllSelections();
            renderAll();
            showToast(valor
                ? `${n} tarefa(s) adicionada(s) ao Meu Dia.`
                : `${n} tarefa(s) removida(s) do Meu Dia.`);
        }

        function batchMarkDone() {
            if (selectedTaskIds.size === 0) return;
            state.tasks.forEach(t => {
                if (selectedTaskIds.has(t.id)) {
                    t.progress = 100;
                    if (Array.isArray(t.steps)) t.steps.forEach(s => s.completed = true);
                }
            });
            saveState(true, true);
            clearAllSelections();
            renderAll();
            showToast("Tarefas selecionadas concluídas!");
        }

        function batchDeleteSelectedItems() {
            const total = selectedTaskIds.size + selectedCategoryIds.size + selectedProjectIds.size + selectedNoteIds.size;
            if (total === 0) return;

            if (selectedTaskIds.size > 0) {
                state.tasks = state.tasks.filter(t => !selectedTaskIds.has(t.id));
            }
            if (selectedCategoryIds.size > 0) {
                state.categories = state.categories.filter(c => !selectedCategoryIds.has(c.id));
                state.tasks.forEach(t => { if (selectedCategoryIds.has(t.categoryId)) t.categoryId = null; });
            }
            if (selectedProjectIds.size > 0) {
                state.projects = state.projects.filter(p => !selectedProjectIds.has(p.id));
                state.tasks.forEach(t => { if (selectedProjectIds.has(t.projectId)) t.projectId = null; });
            }
            if (selectedNoteIds.size > 0) {
                state.notepad = state.notepad.filter(n => !selectedNoteIds.has(n.id) && !selectedNoteIds.has(n.parentId));
            }

            clearAllSelections();
            saveState(true, true);
            renderAll();
            showToast(`${total} item(ns) excluído(s) com sucesso!`);
        }

        function exportDatabaseToCSV() {
            const rows = [];
            rows.push(["TIPO", "ID", "NOME_TITULO", "CATEGORIA_PAI", "PROJETO", "PRIORIDADE", "PROGRESSO", "DATA", "NOTAS_CONTEUDO"]);

            state.tasks.forEach(t => {
                const catName = state.categories.find(c => c.id === t.categoryId)?.name || '';
                const projName = state.projects.find(p => p.id === t.projectId)?.name || '';
                rows.push([
                    "TAREFA", t.id || '', t.title || '', catName, projName,
                    t.priority || 'Média', (t.progress || 0) + "%", t.dueDate || t.createdAt || '', t.notes || ''
                ]);
            });

            state.categories.forEach(c => rows.push(["CATEGORIA", c.id, c.name, c.icon || '', "", "", "", "", ""]));
            state.projects.forEach(p => rows.push(["PROJETO", p.id, p.name, p.icon || '', "", "", "", "", ""]));
            state.notepad.forEach(n => rows.push(["VAULT_NOTA", n.id, n.title, n.parentId || '', "", "", "", n.createdAt || '', n.content || '']));

            const csvContent = rows.map(r => r.map(cell => `"${String(cell || '').replace(/"/g, '""')}"`).join(',')).join('\n');

            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.save_file_native(csvContent, 'NEXUS_database_full.csv', 'csv').then(res => {
                    if (res && res.status === 'success') showToast("Banco de Dados exportado em CSV!");
                });
            }
        }

        function triggerImportCSV() {
            const input = document.getElementById('csvFileInput');
            if (input) input.click();
        }

        function importDatabaseFromCSVFile(event) {
            const file = event.target.files[0];
            if (!file) return;

            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    parseAndLoadCSVData(e.target.result);
                } catch (err) {
                    console.error("CSV import error:", err);
                    showToast("Erro ao importar arquivo CSV.");
                }
            };
            reader.readAsText(file, "UTF-8");
            event.target.value = '';
        }

        function parseAndLoadCSVData(csvText) {
            const lines = parseCSVLines(csvText);
            if (lines.length <= 1) return;

            for (let i = 1; i < lines.length; i++) {
                const row = lines[i];
                if (!row || row.length < 3) continue;

                const tipo = String(row[0] || '').trim().toUpperCase();
                const id = String(row[1] || '').trim();
                const title = String(row[2] || '').trim();

                if (!title) continue;

                if (tipo === 'TAREFA' || tipo === 'TASK') {
                    state.tasks.unshift({
                        id: id || ('task-' + Date.now() + '-' + i),
                        title: title,
                        notes: String(row[8] || '').trim(),
                        categoryId: state.categories[0]?.id || null,
                        projectId: null,
                        priority: String(row[5] || 'Média').trim(),
                        progress: parseInt(String(row[6] || '0').replace('%', '')) || 0,
                        isStarred: false,
                        isMyDay: true,
                        dueDate: String(row[7] || '').trim(),
                        steps: [],
                        links: [],
                        attachments: [],
                        createdAt: new Date().toISOString()
                    });
                }
            }

            saveState(true, true);
            renderAll();
            showToast("Dados do CSV importados com sucesso!");
        }

        function parseCSVLines(text) {
            const result = [];
            let row = [];
            let current = '';
            let inQuotes = false;

            for (let i = 0; i < text.length; i++) {
                const char = text[i];
                const nextChar = text[i + 1];

                if (char === '"') {
                    if (inQuotes && nextChar === '"') { current += '"'; i++; }
                    else { inQuotes = !inQuotes; }
                } else if (char === ',' && !inQuotes) {
                    row.push(current);
                    current = '';
                } else if ((char === '\r' || char === '\n') && !inQuotes) {
                    if (char === '\r' && nextChar === '\n') { i++; }
                    row.push(current);
                    if (row.some(cell => cell.trim().length > 0)) result.push(row);
                    row = [];
                    current = '';
                } else {
                    current += char;
                }
            }
            if (current || row.length > 0) {
                row.push(current);
                if (row.some(cell => cell.trim().length > 0)) result.push(row);
            }
            return result;
        }

        function renderSidebarCategories() {
            const c = document.getElementById('sidebar-categories');
            if (!c) return;
            c.innerHTML = state.categories.map(cat => {
                const isSel = selectedCategoryIds.has(cat.id);
                return `
                    <div class="group flex items-center justify-between rounded hover:bg-white/5 pr-1 ${isSel ? 'bg-sky-950/40 border border-[#2eaadc]/40' : ''}">
                        <button onclick="event.stopPropagation(); toggleCategorySelection('${cat.id}')" class="w-3.5 h-3.5 ml-1 rounded border ${isSel ? 'bg-[#2eaadc] border-[#2eaadc] text-white opacity-100' : 'border-gray-600 hover:border-sky-400 opacity-0 group-hover:opacity-100'} flex items-center justify-center transition cursor-pointer flex-shrink-0" title="Selecionar categoria">
                            ${isSel ? '<i class="fa-solid fa-check text-[8px]"></i>' : ''}
                        </button>
                        <button onclick="selectList('${cat.id}')" id="nav-${cat.id}" class="nav-btn notion-btn flex-1 flex items-center gap-2 px-2 py-1 rounded text-xs text-gray-300 cursor-pointer">
                            <i class="${cat.icon || 'fa-regular fa-folder'} text-sky-400 text-xs w-4 text-center"></i>
                            <span class="flex-1 text-left truncate">${escapeHtml(cat.name)}</span>
                        </button>
                        <div class="hidden group-hover:flex items-center gap-1">
                            <button onclick="openCategoryModal('${cat.id}')" class="text-gray-500 hover:text-white p-0.5" title="Editar Categoria"><i class="fa-solid fa-pencil text-[9px]"></i></button>
                        </div>
                    </div>
                `;
            }).join('');
        }

        /* Progresso de um projeto = média do progresso das tarefas vinculadas.
           Devolve também os contadores, usados no tooltip. */
        function getProjectProgress(projId) {
            const tarefas = state.tasks.filter(t => t.projectId === projId);
            if (tarefas.length === 0) return { pct: 0, total: 0, done: 0, vazio: true };
            const soma = tarefas.reduce((acc, t) => acc + Math.max(0, Math.min(100, Number(t.progress) || 0)), 0);
            const done = tarefas.filter(t => (Number(t.progress) || 0) >= 100).length;
            return { pct: Math.round(soma / tarefas.length), total: tarefas.length, done, vazio: false };
        }

        function renderSidebarProjects() {
            const p = document.getElementById('sidebar-projects');
            if (!p) return;
            p.innerHTML = state.projects.map(proj => {
                const isSel = selectedProjectIds.has(proj.id);
                const prog = getProjectProgress(proj.id);

                let cor = '#2eaadc';
                if (prog.pct >= 100) cor = '#10b981';
                else if (prog.pct === 0) cor = '#52525b';

                const tooltip = prog.vazio
                    ? 'Nenhuma tarefa neste projeto'
                    : `${prog.done} de ${prog.total} tarefa(s) concluída(s) — ${prog.pct}%`;

                return `
                    <div class="group rounded hover:bg-white/5 pr-1 ${isSel ? 'bg-sky-950/40 border border-[#2eaadc]/40' : ''}">
                        <div class="flex items-center justify-between min-w-0">
                            <button onclick="event.stopPropagation(); toggleProjectSelection('${proj.id}')" class="w-3.5 h-3.5 ml-1 rounded border ${isSel ? 'bg-[#2eaadc] border-[#2eaadc] text-white opacity-100' : 'border-gray-600 hover:border-sky-400 opacity-0 group-hover:opacity-100'} flex items-center justify-center transition cursor-pointer flex-shrink-0" title="Selecionar projeto">
                                ${isSel ? '<i class="fa-solid fa-check text-[8px]"></i>' : ''}
                            </button>
                            <button onclick="selectList('${proj.id}')" id="nav-${proj.id}" class="nav-btn notion-btn flex-1 min-w-0 flex items-center gap-2 px-2 py-1 rounded text-xs text-gray-300 cursor-pointer">
                                <i class="${proj.icon || 'fa-solid fa-folder-tree'} text-purple-400 text-xs w-4 text-center flex-shrink-0"></i>
                                <span class="flex-1 text-left truncate">${escapeHtml(proj.name)}</span>
                                <span class="text-[9px] font-mono flex-shrink-0 ${prog.vazio ? 'text-gray-600' : 'text-gray-400'}">${prog.vazio ? '—' : prog.pct + '%'}</span>
                            </button>
                            <div class="hidden group-hover:flex items-center gap-1 flex-shrink-0">
                                <button onclick="openProjectModal('${proj.id}')" class="text-gray-500 hover:text-white p-0.5" title="Editar Projeto"><i class="fa-solid fa-pencil text-[9px]"></i></button>
                            </div>
                        </div>
                        <div class="mx-2 mb-1 h-1 bg-white/10 rounded-full overflow-hidden" title="${escapeHtml(tooltip)}">
                            <div class="h-full rounded-full transition-all duration-300" style="width:${prog.pct}%;background-color:${cor}"></div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        function createNewTaskFromInput() {
            const input = document.getElementById('quickTaskInput');
            const title = input.value.trim();
            if (!title) return;

            const newTask = {
                id: 'task-' + Date.now(),
                title: title,
                notes: '',
                categoryId: currentFilter.startsWith('cat-') ? currentFilter : (state.categories[0]?.id || null),
                projectId: currentFilter.startsWith('proj-') ? currentFilter : null,
                priority: 'Média',
                progress: 0,
                isStarred: false,
                isMyDay: true,
                dueDate: currentFilter === 'planned' ? new Date().toISOString().split('T')[0] : '',
                steps: [],
                links: [],
                attachments: [],
                createdAt: new Date().toISOString()
            };

            state.tasks.unshift(newTask);
            saveState(true, true);
            input.value = '';
            renderAll();
        }

        function toggleTaskCompletion(taskId) {
            const t = state.tasks.find(x => x.id === taskId);
            if (t) {
                t.progress = (Number(t.progress) || 0) >= 100 ? 0 : 100;
                if (Array.isArray(t.steps)) {
                    t.steps.forEach(s => s.completed = (t.progress === 100));
                }
                saveState(true, true);
                renderAll();
            }
        }

        function toggleTaskStar(taskId) {
            const t = state.tasks.find(x => x.id === taskId);
            if (t) {
                t.isStarred = !t.isStarred;
                saveState(true, true);
                renderAll();
            }
        }

        function toggleStepDirect(taskId, stepIndex) {
            const t = state.tasks.find(x => x.id === taskId);
            if (t && Array.isArray(t.steps) && t.steps[stepIndex]) {
                t.steps[stepIndex].completed = !t.steps[stepIndex].completed;
                const total = t.steps.length;
                const done = t.steps.filter(s => s.completed).length;
                t.progress = Math.round((done / total) * 100);
                saveState(true, true);
                renderAll();
                if (selectedTaskId === taskId) populateDrawer(t);
            }
        }

        function openTaskDetailDrawer(taskId) {
            // Grava o que estava sendo digitado na tarefa ANTERIOR antes de trocar.
            if (selectedTaskId && selectedTaskId !== taskId) flushPendingDrawerEdits();

            const t = state.tasks.find(x => x.id === taskId);
            if (!t) return;                 // id inválido: não mexe na seleção atual
            selectedTaskId = taskId;
            populateDrawer(t);
            const drawer = document.getElementById('taskDetailDrawer');
            drawer.classList.remove('hidden');
            renderCurrentView();
        }

        function closeTaskDetailDrawer() {
            flushPendingDrawerEdits();      // não perde a última digitação
            selectedTaskId = null;
            const drawer = document.getElementById('taskDetailDrawer');
            drawer.classList.add('hidden');
            renderCurrentView();
        }

        function populateDrawer(t) {
            document.getElementById('detailTaskTitle').value = t.title || '';
            document.getElementById('detailTaskNotes').value = t.notes || '';
            document.getElementById('detailTaskPriority').value = t.priority || 'Média';
            document.getElementById('detailTaskDueDate').value = t.dueDate || '';
            document.getElementById('detailTaskProgress').value = Number(t.progress) || 0;
            document.getElementById('detailProgressLabel').innerText = `${Number(t.progress) || 0}%`;
            document.getElementById('detailCreatedAt').innerText = `Criado em: ${formatDateBR(t.createdAt?.split('T')[0])}`;

            const noMyDay = t.isMyDay !== false;
            const mdIcon = document.getElementById('detailMyDayIcon');
            const mdLabel = document.getElementById('detailMyDayLabel');
            const mdAction = document.getElementById('detailMyDayAction');
            if (mdLabel) mdLabel.innerText = noMyDay ? 'Está no Meu Dia' : 'Não está no Meu Dia';
            if (mdIcon) mdIcon.className = noMyDay
                ? 'fa-solid fa-sun text-amber-400 flex-shrink-0'
                : 'fa-regular fa-sun text-gray-500 flex-shrink-0';
            if (mdAction) {
                mdAction.innerText = noMyDay ? 'Remover' : 'Adicionar';
                mdAction.className = noMyDay
                    ? 'text-[10px] font-semibold text-rose-300 flex-shrink-0'
                    : 'text-[10px] font-semibold text-sky-300 flex-shrink-0';
            }

            const catSelect = document.getElementById('detailTaskCategory');
            catSelect.innerHTML = state.categories.map(c => `<option value="${c.id}" ${c.id === t.categoryId ? 'selected' : ''}>${escapeHtml(c.name)}</option>`).join('');

            const projSelect = document.getElementById('detailTaskProject');
            projSelect.innerHTML = `<option value="">Nenhum Projeto</option>` + state.projects.map(p => `<option value="${p.id}" ${p.id === t.projectId ? 'selected' : ''}>${escapeHtml(p.name)}</option>`).join('');

            const steps = Array.isArray(t.steps) ? t.steps : [];
            const stepsDone = steps.filter(s => s.completed).length;
            document.getElementById('detailStepsProgress').innerText = `${stepsDone}/${steps.length}`;
            document.getElementById('detailStepsContainer').innerHTML = steps.map((s, idx) => `
                <div class="flex items-center justify-between gap-2 p-1.5 bg-white/5 rounded">
                    <div class="flex items-center gap-2 flex-1">
                        <button onclick="toggleStepDirect('${t.id}', ${idx})" class="w-3.5 h-3.5 rounded border ${s.completed ? 'bg-[#2eaadc] border-[#2eaadc] text-white' : 'border-gray-600'} flex items-center justify-center text-[8px] cursor-pointer">
                            ${s.completed ? '<i class="fa-solid fa-check"></i>' : ''}
                        </button>
                        <span class="text-xs ${s.completed ? 'line-through text-gray-500' : 'text-gray-200'}">${escapeHtml(s.title)}</span>
                    </div>
                    <button onclick="removeStepFromDrawer(${idx})" class="text-gray-500 hover:text-rose-400 text-xs cursor-pointer"><i class="fa-regular fa-trash-can"></i></button>
                </div>
            `).join('');

            const atts = Array.isArray(t.attachments) ? t.attachments : [];
            const totalBytes = atts.reduce((acc, a) => acc + (Number(a.size) || 0), 0);

            const contador = document.getElementById('detailAttachmentsCount');
            if (contador) {
                contador.innerText = atts.length === 0
                    ? '0'
                    : `${atts.length} · ${formatarTamanho(totalBytes)}`;
            }

            const box = document.getElementById('detailAttachmentsContainer');
            if (atts.length === 0) {
                box.innerHTML = `<div class="text-[11px] text-gray-600 italic py-1">Nenhum arquivo anexado.</div>`;
            } else {
                box.innerHTML = atts.map((a, idx) => `
                    <div class="flex items-center justify-between gap-2 p-2 bg-white/5 rounded text-xs min-w-0">
                        <div class="flex items-center gap-2.5 min-w-0 flex-1 cursor-pointer hover:text-sky-300" onclick="openNativePath('${escapeJsStr(a.path)}')" title="${escapeHtml(a.path || a.name)}">
                            <i class="${iconeDoArquivo(a.name)} text-sky-400 flex-shrink-0"></i>
                            <span class="min-w-0 flex-1">
                                <span class="block truncate">${escapeHtml(a.name)}</span>
                                <span class="block text-[10px] text-gray-500 font-mono truncate">
                                    ${extensaoDoArquivo(a.name)}${a.size ? ' · ' + formatarTamanho(a.size) : ''}
                                </span>
                            </span>
                        </div>
                        <button onclick="event.stopPropagation(); removeAttachmentFromDrawer(${idx})" class="text-gray-500 hover:text-rose-400 cursor-pointer flex-shrink-0 p-1" title="Remover anexo"><i class="fa-solid fa-xmark"></i></button>
                    </div>
                `).join('');
            }
        }

        function formatarTamanho(bytes) {
            const n = Number(bytes) || 0;
            if (n < 1024) return n + ' B';
            if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
            if (n < 1024 * 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB';
            return (n / 1024 / 1024 / 1024).toFixed(2) + ' GB';
        }

        function extensaoDoArquivo(nome) {
            const m = String(nome || '').match(/\.([a-z0-9]+)$/i);
            return m ? m[1].toUpperCase() : 'ARQUIVO';
        }

        function iconeDoArquivo(nome) {
            const ext = String(nome || '').split('.').pop().toLowerCase();
            if (['pdf'].includes(ext)) return 'fa-regular fa-file-pdf';
            if (['doc','docx','odt','rtf'].includes(ext)) return 'fa-regular fa-file-word';
            if (['xls','xlsx','csv','ods'].includes(ext)) return 'fa-regular fa-file-excel';
            if (['ppt','pptx','odp'].includes(ext)) return 'fa-regular fa-file-powerpoint';
            if (['png','jpg','jpeg','gif','bmp','webp','svg','ico'].includes(ext)) return 'fa-regular fa-file-image';
            if (['zip','rar','7z','tar','gz'].includes(ext)) return 'fa-regular fa-file-zipper';
            if (['py','js','ts','json','xml','html','css','java','c','cpp','cs','sql','sh','bat'].includes(ext)) return 'fa-regular fa-file-code';
            if (['txt','md','log'].includes(ext)) return 'fa-regular fa-file-lines';
            if (['mp4','avi','mkv','mov','wmv'].includes(ext)) return 'fa-regular fa-file-video';
            if (['mp3','wav','ogg','flac'].includes(ext)) return 'fa-regular fa-file-audio';
            return 'fa-regular fa-file';
        }

        function toggleMyDayFromDrawer() {
            if (!selectedTaskId) return;
            toggleTaskMyDay(selectedTaskId);
        }

        function updateProgressFromDrawer(val) {
            if (!selectedTaskId) return;
            const t = state.tasks.find(x => x.id === selectedTaskId);
            if (t) {
                t.progress = Number(val);
                document.getElementById('detailProgressLabel').innerText = `${val}%`;
                saveState(true, true);
                renderAll();
            }
        }

        /* Os debounces guardam o ID e o texto do MOMENTO DA DIGITAÇÃO.
           Antes eles liam selectedTaskId só na hora de disparar: se você
           trocasse de tarefa ou fechasse o painel dentro do intervalo, a
           edição era gravada na tarefa errada ou simplesmente perdida. */
        let debounceDrawerTitle = null;
        let pendingTitleEdit = null;   // { id, value }

        function debouncedUpdateTaskTitle() {
            if (!selectedTaskId) return;
            pendingTitleEdit = { id: selectedTaskId, value: document.getElementById('detailTaskTitle').value };
            if (debounceDrawerTitle) clearTimeout(debounceDrawerTitle);
            debounceDrawerTitle = setTimeout(() => { commitTitleEdit(); renderCurrentView(); }, 500);
        }

        function commitTitleEdit() {
            if (debounceDrawerTitle) { clearTimeout(debounceDrawerTitle); debounceDrawerTitle = null; }
            if (!pendingTitleEdit) return;
            const t = state.tasks.find(x => x.id === pendingTitleEdit.id);
            if (t) { t.title = pendingTitleEdit.value; saveState(false); }
            pendingTitleEdit = null;
        }

        let debounceDrawerNotes = null;
        let pendingNotesEdit = null;   // { id, value }

        function debouncedUpdateTaskNotes() {
            if (!selectedTaskId) return;
            pendingNotesEdit = { id: selectedTaskId, value: document.getElementById('detailTaskNotes').value };
            if (debounceDrawerNotes) clearTimeout(debounceDrawerNotes);
            debounceDrawerNotes = setTimeout(commitNotesEdit, 600);
        }

        function commitNotesEdit() {
            if (debounceDrawerNotes) { clearTimeout(debounceDrawerNotes); debounceDrawerNotes = null; }
            if (!pendingNotesEdit) return;
            const t = state.tasks.find(x => x.id === pendingNotesEdit.id);
            if (t) { t.notes = pendingNotesEdit.value; saveState(false); }
            pendingNotesEdit = null;
        }

        // Grava agora o que estiver pendente (usado ao trocar de tarefa/visão).
        function flushPendingDrawerEdits() {
            commitTitleEdit();
            commitNotesEdit();
        }

        function updateTaskFromDrawer() {
            if (!selectedTaskId) return;
            const t = state.tasks.find(x => x.id === selectedTaskId);
            if (t) {
                t.categoryId = document.getElementById('detailTaskCategory').value || null;
                t.projectId = document.getElementById('detailTaskProject').value || null;
                t.priority = document.getElementById('detailTaskPriority').value;
                t.dueDate = document.getElementById('detailTaskDueDate').value;
                saveState(true, true);
                renderAll();
            }
        }

        function addStepFromDrawer() {
            if (!selectedTaskId) return;
            const inp = document.getElementById('newStepInput');
            const val = inp.value.trim();
            if (!val) return;
            const t = state.tasks.find(x => x.id === selectedTaskId);
            if (t) {
                if (!Array.isArray(t.steps)) t.steps = [];
                t.steps.push({ id: 'step-' + Date.now(), title: val, completed: false });
                inp.value = '';
                saveState(true, true);
                populateDrawer(t);
                renderCurrentView();
            }
        }

        function removeStepFromDrawer(idx) {
            if (!selectedTaskId) return;
            const t = state.tasks.find(x => x.id === selectedTaskId);
            if (t && Array.isArray(t.steps)) {
                t.steps.splice(idx, 1);
                saveState(true, true);
                populateDrawer(t);
                renderCurrentView();
            }
        }

        function pickAttachmentForTask() {
            if (!selectedTaskId || !window.pywebview || !window.pywebview.api) return;
            window.pywebview.api.pick_file_native().then(res => {
                if (res && res.status === 'success') {
                    const t = state.tasks.find(x => x.id === selectedTaskId);
                    if (t) {
                        if (!Array.isArray(t.attachments)) t.attachments = [];
                        t.attachments.push({ name: res.name, path: res.path, size: res.size });
                        saveState(true, true);
                        populateDrawer(t);
                        showToast("Arquivo anexado!");
                    }
                }
            });
        }

        function removeAttachmentFromDrawer(idx) {
            if (!selectedTaskId) return;
            const t = state.tasks.find(x => x.id === selectedTaskId);
            if (t && Array.isArray(t.attachments)) {
                t.attachments.splice(idx, 1);
                saveState(true, true);
                populateDrawer(t);
            }
        }

        function deleteCurrentTaskFromDrawer() {
            if (!selectedTaskId) return;
            state.tasks = state.tasks.filter(x => x.id !== selectedTaskId);
            closeTaskDetailDrawer();
            saveState(true, true);
            renderAll();
            showToast("Tarefa excluída.");
        }

        function openNativePath(p) {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.open_external_target(p);
            }
        }

        /* Filhos diretos, na ordem de criação. */
        function filhosDaNota(id) {
            return state.notepad.filter(n => n.parentId === id);
        }

        function contarDescendentes(id) {
            let total = 0;
            for (const f of filhosDaNota(id)) total += 1 + contarDescendentes(f.id);
            return total;
        }

        /* Caminho da raiz até a nota selecionada — usado para destacar o ramo. */
        function caminhoAteNota(id) {
            const caminho = new Set();
            let atual = state.notepad.find(n => n.id === id);
            let guarda = 0;
            while (atual && guarda++ < 200) {
                caminho.add(atual.id);
                atual = atual.parentId ? state.notepad.find(n => n.id === atual.parentId) : null;
            }
            return caminho;
        }

        function renderNotepadTree() {
            const container = document.getElementById('notepad-tree-container');
            if (!container) return;

            const idsExistentes = new Set(state.notepad.map(n => n.id));
            // Notas cujo pai foi apagado viram raiz, para não sumirem da árvore.
            const roots = state.notepad.filter(n => !n.parentId || !idsExistentes.has(n.parentId));
            const noCaminho = selectedNoteId ? caminhoAteNota(selectedNoteId) : new Set();

            container.innerHTML = roots.length
                ? roots.map(n => renderNoteTreeNode(n, 0, noCaminho)).join('')
                : '<div class="text-[11px] text-gray-600 italic px-2 py-2">Nenhuma nota ainda.</div>';

            atualizarBotaoExpandirTudo();
        }

        function renderNoteTreeNode(note, depth, noCaminho) {
            const children = filhosDaNota(note.id);
            const temFilhos = children.length > 0;
            const aberto = note.expanded !== false;      // padrão: aberto
            const isSel = selectedNoteId === note.id;
            const isBatchSel = selectedNoteIds.has(note.id);
            const ocultos = temFilhos && !aberto ? contarDescendentes(note.id) : 0;

            const chevron = temFilhos
                ? `<button onclick="event.stopPropagation(); toggleNoteExpanded('${note.id}')"
                        class="note-toggle ${aberto ? '' : 'recolhido'}"
                        title="${aberto ? 'Recolher' : 'Expandir'} (${children.length} subnota${children.length > 1 ? 's' : ''})">
                        <i class="fa-solid fa-chevron-down text-[8px]"></i>
                   </button>`
                : `<span class="note-toggle-vazio"></span>`;

            return `
                <div class="note-node ${noCaminho && noCaminho.has(note.id) ? 'no-caminho' : ''}">
                    <div class="note-row-wrap">
                        <div onclick="selectNote('${note.id}')" class="group notion-btn w-full flex items-center justify-between gap-1 py-1 pr-2 pl-1 rounded text-xs cursor-pointer ${isSel ? 'active' : 'text-gray-300'} ${isBatchSel ? 'bg-sky-950/40 border border-[#2eaadc]/40' : ''}">
                            <div class="flex items-center gap-1.5 truncate flex-1 min-w-0">
                                ${chevron}
                                <button onclick="event.stopPropagation(); toggleNoteSelection('${note.id}')" class="w-3.5 h-3.5 rounded border ${isBatchSel ? 'bg-[#2eaadc] border-[#2eaadc] text-white opacity-100' : 'border-gray-600 hover:border-sky-400 opacity-0 group-hover:opacity-100'} flex items-center justify-center transition cursor-pointer flex-shrink-0" title="Selecionar nota">
                                    ${isBatchSel ? '<i class="fa-solid fa-check text-[8px]"></i>' : ''}
                                </button>
                                <i class="${note.icon || 'fa-regular fa-file-lines'} text-sky-400 text-xs w-3.5 text-center flex-shrink-0"></i>
                                <span class="truncate text-xs">${escapeHtml(note.title || 'Sem título')}</span>
                                ${ocultos ? `<span class="note-badge-filhos" title="${ocultos} item(ns) recolhido(s)">${ocultos}</span>` : ''}
                            </div>
                            <div class="hidden group-hover:flex items-center gap-1 flex-shrink-0">
                                <button onclick="event.stopPropagation(); openNoteIconModalFor('${note.id}')" class="text-gray-500 hover:text-white p-0.5" title="Mudar Ícone"><i class="fa-solid fa-icons text-[9px]"></i></button>
                                <button onclick="event.stopPropagation(); addChildNote('${note.id}')" class="text-gray-500 hover:text-white p-0.5" title="Adicionar Subnota"><i class="fa-solid fa-plus text-[9px]"></i></button>
                            </div>
                        </div>
                    </div>
                    ${temFilhos && aberto
                        ? `<div class="note-children">
                               ${children.map(f => renderNoteTreeNode(f, depth + 1, noCaminho)).join('')}
                           </div>`
                        : ''}
                </div>
            `;
        }

        function toggleNoteExpanded(noteId) {
            const n = state.notepad.find(x => x.id === noteId);
            if (!n) return;
            n.expanded = (n.expanded === false);   // false -> true, qualquer outro -> false
            saveState(false);                      // o estado da árvore fica gravado
            renderNotepadTree();
        }

        /* Abre todo o caminho até uma nota, para ela nunca ficar escondida. */
        function revelarNota(noteId) {
            let n = state.notepad.find(x => x.id === noteId);
            let guarda = 0;
            let mudou = false;
            while (n && n.parentId && guarda++ < 200) {
                const pai = state.notepad.find(x => x.id === n.parentId);
                if (!pai) break;
                if (pai.expanded === false) { pai.expanded = true; mudou = true; }
                n = pai;
            }
            return mudou;
        }

        function expandirOuRecolherTudo() {
            const comFilhos = state.notepad.filter(n => filhosDaNota(n.id).length > 0);
            if (comFilhos.length === 0) return;
            const algumRecolhido = comFilhos.some(n => n.expanded === false);
            comFilhos.forEach(n => { n.expanded = algumRecolhido; });
            saveState(false);
            renderNotepadTree();
        }

        function atualizarBotaoExpandirTudo() {
            const btn = document.getElementById('btn-expandir-tudo');
            if (!btn) return;
            const comFilhos = state.notepad.filter(n => filhosDaNota(n.id).length > 0);
            const algumRecolhido = comFilhos.some(n => n.expanded === false);
            btn.innerHTML = algumRecolhido
                ? '<i class="fa-solid fa-angles-down text-[9px]"></i>'
                : '<i class="fa-solid fa-angles-up text-[9px]"></i>';
            btn.title = algumRecolhido ? 'Expandir tudo' : 'Recolher tudo';
            btn.style.display = comFilhos.length ? '' : 'none';
        }

        function selectNote(noteId) {
            const note = state.notepad.find(n => n.id === noteId);
            if (!note) return;
            selectedNoteId = noteId;

            // Se a nota estiver dentro de um ramo recolhido, abre o caminho até ela.
            if (revelarNota(noteId)) saveState(false);

            document.getElementById('noteTitleInput').value = note.title || '';
            // Sanitiza tambem na LEITURA: notas criadas em versoes anteriores,
            // ou sincronizadas de outra maquina, podem ja conter HTML perigoso.
            document.getElementById('noteEditorBody').innerHTML =
                sanitizarHtml(note.content || '');
            instalarSanitizacaoDoEditor();
            
            const btnIcon = document.getElementById('btn-current-note-icon');
            if (btnIcon) {
                btnIcon.innerHTML = `<i class="${note.icon || 'fa-regular fa-file-lines'} text-sm"></i>`;
            }

            updateWordCount();
            renderNotepadTree();
        }

        function addRootNote() {
            const newNote = {
                id: 'note-' + Date.now(),
                parentId: null,
                title: 'Nova Nota',
                icon: 'fa-regular fa-file-lines',
                content: '<p></p>',
                expanded: true,
                createdAt: new Date().toISOString()
            };
            state.notepad.push(newNote);
            // Sem isso, criar uma subnota num ramo recolhido não mostraria nada.
            const pai = state.notepad.find(n => n.id === parentId);
            if (pai) pai.expanded = true;
            saveState(true, true);
            renderNotepadTree();
            selectNote(newNote.id);
        }

        function addChildNote(parentId) {
            const newNote = {
                id: 'note-' + Date.now(),
                parentId: parentId || null,
                title: 'Nova Subnota',
                icon: 'fa-regular fa-file-lines',
                content: '<p></p>',
                expanded: true,
                createdAt: new Date().toISOString()
            };
            state.notepad.push(newNote);
            saveState(true, true);
            renderNotepadTree();
            selectNote(newNote.id);
        }

        function deleteCurrentNote() {
            if (!selectedNoteId) return;
            state.notepad = state.notepad.filter(n => n.id !== selectedNoteId && n.parentId !== selectedNoteId);
            selectedNoteId = state.notepad[0]?.id || null;
            saveState(true, true);
            renderNotepadTree();
            if (selectedNoteId) selectNote(selectedNoteId);
            else {
                document.getElementById('noteTitleInput').value = '';
                document.getElementById('noteEditorBody').innerHTML = '';
            }
        }

        let debounceNoteTitle = null;
        function saveNoteTitleLive() {
            if (debounceNoteTitle) clearTimeout(debounceNoteTitle);
            debounceNoteTitle = setTimeout(() => {
                if (!selectedNoteId) return;
                const note = state.notepad.find(n => n.id === selectedNoteId);
                if (note) {
                    note.title = document.getElementById('noteTitleInput').value;
                    saveState(false);
                    renderNotepadTree();
                }
            }, 500);
        }

        let debounceNoteContent = null;
        function saveNoteContentLive() {
            updateWordCount();
            if (debounceNoteContent) clearTimeout(debounceNoteContent);
            debounceNoteContent = setTimeout(() => {
                if (!selectedNoteId) return;
                const note = state.notepad.find(n => n.id === selectedNoteId);
                if (note) {
                    note.content = sanitizarHtml(
                        document.getElementById('noteEditorBody').innerHTML);
                    saveState(false);
                }
            }, 800);
        }

        function formatDoc(cmd, val = null) {
            document.execCommand(cmd, false, val);
            document.getElementById('noteEditorBody').focus();
            saveNoteContentLive();
        }

        function updateWordCount() {
            const text = document.getElementById('noteEditorBody').innerText || '';
            const words = text.trim() ? text.trim().split(/\s+/).length : 0;
            const chars = text.length;
            document.getElementById('note-word-count').innerText = `${words} palavras • ${chars} caracteres`;
        }

        function openNoteIconModal() {
            if (!selectedNoteId) return;
            openNoteIconModalFor(selectedNoteId);
        }

        function openNoteIconModalFor(noteId) {
            selectedNoteId = noteId;
            const note = state.notepad.find(n => n.id === noteId);
            tempNoteIcon = note?.icon || 'fa-regular fa-file-lines';

            renderIconPicker('noteIconPickerContainer', tempNoteIcon, (iconClass) => {
                tempNoteIcon = iconClass;
            });

            document.getElementById('noteIconModal').classList.remove('hidden');
        }

        function closeNoteIconModal() {
            document.getElementById('noteIconModal').classList.add('hidden');
        }

        function saveNoteIconModal() {
            if (!selectedNoteId) return;
            const note = state.notepad.find(n => n.id === selectedNoteId);
            if (note) {
                note.icon = tempNoteIcon;
                saveState(true, true);
                selectNote(selectedNoteId);
            }
            closeNoteIconModal();
            showToast("Ícone da nota atualizado!");
        }

        function renderBadges() {
            const todayStr = new Date().toISOString().split('T')[0];
            document.getElementById('badge-myday').innerText = state.tasks.filter(t => (t.isMyDay === false ? false : (t.isMyDay === true || t.dueDate === todayStr)) && (Number(t.progress) || 0) < 100).length;
            document.getElementById('badge-planned').innerText = state.tasks.filter(t => t.dueDate && (Number(t.progress) || 0) < 100).length;
            document.getElementById('badge-all').innerText = state.tasks.filter(t => (Number(t.progress) || 0) < 100).length;
        }

        function debouncedRenderTasksList() { renderTasksList(); }

        function toggleCompletedTasks() {
            document.getElementById('completed-tasks-list').classList.toggle('hidden');
            document.getElementById('completed-chevron').classList.toggle('-rotate-90');
        }

        function renderKanbanView() {
            const list = getFilteredTasks();
            const colTodo = document.getElementById('kanban-col-todo');
            const colProg = document.getElementById('kanban-col-progress');
            const colRev = document.getElementById('kanban-col-review');
            const colDone = document.getElementById('kanban-col-done');

            const todo = list.filter(t => (Number(t.progress) || 0) === 0);
            const prog = list.filter(t => (Number(t.progress) || 0) > 0 && (Number(t.progress) || 0) < 75);
            const rev = list.filter(t => (Number(t.progress) || 0) >= 75 && (Number(t.progress) || 0) < 100);
            const done = list.filter(t => (Number(t.progress) || 0) >= 100);

            document.getElementById('kanban-count-todo').innerText = todo.length;
            document.getElementById('kanban-count-progress').innerText = prog.length;
            document.getElementById('kanban-count-review').innerText = rev.length;
            document.getElementById('kanban-count-done').innerText = done.length;

            colTodo.innerHTML = todo.map(t => createKanbanCardHTML(t)).join('');
            colProg.innerHTML = prog.map(t => createKanbanCardHTML(t)).join('');
            colRev.innerHTML = rev.map(t => createKanbanCardHTML(t)).join('');
            colDone.innerHTML = done.map(t => createKanbanCardHTML(t)).join('');
        }

        let catChartInstance = null;
        let prioChartInstance = null;
        function renderChartsView() {
            const list = getFilteredTasks();
            const catCtx = document.getElementById('chartCategories')?.getContext('2d');
            const prioCtx = document.getElementById('chartPriorities')?.getContext('2d');
            if (!catCtx || !prioCtx) return;

            if (catChartInstance) catChartInstance.destroy();
            if (prioChartInstance) prioChartInstance.destroy();

            const catLabels = state.categories.map(c => c.name);
            const catData = state.categories.map(c => list.filter(t => t.categoryId === c.id).length);

            catChartInstance = new Chart(catCtx, {
                type: 'doughnut',
                data: {
                    labels: catLabels,
                    datasets: [{
                        data: catData,
                        backgroundColor: ['#2eaadc', '#7053ff', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6'],
                        borderWidth: 0
                    }]
                },
                options: { responsive: true, plugins: { legend: { labels: { color: '#8a8a8e', font: { size: 11 } } } } }
            });

            const prioLabels = ['Baixa', 'Média', 'Alta', 'Urgente'];
            const prioData = prioLabels.map(p => list.filter(t => (t.priority || 'Média') === p).length);

            prioChartInstance = new Chart(prioCtx, {
                type: 'bar',
                data: {
                    labels: prioLabels,
                    datasets: [{
                        data: prioData,
                        backgroundColor: ['#3b82f6', '#2eaadc', '#f59e0b', '#ef4444'],
                        borderRadius: 3
                    }]
                },
                options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { ticks: { color: '#71717a' }, grid: { color: '#2f2f2f' } }, x: { ticks: { color: '#8a8a8e' }, grid: { display: false } } } }
            });
        }

        function openCategoryModal(catId = null) {
            document.getElementById('editingCategoryId').value = catId || '';
            const titleEl = document.getElementById('categoryModalTitle');
            const delBtn = document.getElementById('deleteCatBtn');
            const inputEl = document.getElementById('newCategoryName');
            
            if (catId) {
                const c = state.categories.find(x => x.id === catId);
                titleEl.innerText = 'Editar Categoria';
                inputEl.value = c?.name || '';
                selectedCategoryIcon = c?.icon || 'fa-regular fa-folder';
                delBtn.classList.remove('hidden');
            } else {
                titleEl.innerText = 'Nova Categoria';
                inputEl.value = '';
                selectedCategoryIcon = 'fa-regular fa-folder';
                delBtn.classList.add('hidden');
            }

            renderIconPicker('categoryIconPicker', selectedCategoryIcon, (iconClass) => {
                selectedCategoryIcon = iconClass;
            });

            document.getElementById('categoryModal').classList.remove('hidden');
        }

        function closeCategoryModal() { document.getElementById('categoryModal').classList.add('hidden'); }

        function saveCategoryModal() {
            const catId = document.getElementById('editingCategoryId').value;
            const name = document.getElementById('newCategoryName').value.trim();
            if (!name) return;

            if (catId) {
                const c = state.categories.find(x => x.id === catId);
                if (c) {
                    c.name = name;
                    c.icon = selectedCategoryIcon;
                }
            } else {
                state.categories.push({ id: 'cat-' + Date.now(), name: name, icon: selectedCategoryIcon });
            }

            saveState(true, true);
            renderSidebarCategories();
            closeCategoryModal();
            showToast(catId ? "Categoria salva!" : "Categoria criada!");
        }

        function deleteCurrentEditingCategory() {
            const catId = document.getElementById('editingCategoryId').value;
            if (!catId) return;
            state.categories = state.categories.filter(c => c.id !== catId);
            state.tasks.forEach(t => { if (t.categoryId === catId) t.categoryId = null; });
            saveState(true, true);
            renderSidebarCategories();
            closeCategoryModal();
            renderAll();
            showToast("Categoria excluída.");
        }

        function openProjectModal(projId = null) {
            document.getElementById('editingProjectId').value = projId || '';
            const titleEl = document.getElementById('projectModalTitle');
            const delBtn = document.getElementById('deleteProjBtn');
            const inputEl = document.getElementById('newProjectName');
            
            if (projId) {
                const p = state.projects.find(x => x.id === projId);
                titleEl.innerText = 'Editar Projeto';
                inputEl.value = p?.name || '';
                selectedProjectIcon = p?.icon || 'fa-solid fa-folder-tree';
                delBtn.classList.remove('hidden');
            } else {
                titleEl.innerText = 'Novo Projeto';
                inputEl.value = '';
                selectedProjectIcon = 'fa-solid fa-folder-tree';
                delBtn.classList.add('hidden');
            }

            renderIconPicker('projectIconPicker', selectedProjectIcon, (iconClass) => {
                selectedProjectIcon = iconClass;
            });

            document.getElementById('projectModal').classList.remove('hidden');
        }

        function closeProjectModal() { document.getElementById('projectModal').classList.add('hidden'); }

        function saveProjectModal() {
            const projId = document.getElementById('editingProjectId').value;
            const name = document.getElementById('newProjectName').value.trim();
            if (!name) return;

            if (projId) {
                const p = state.projects.find(x => x.id === projId);
                if (p) {
                    p.name = name;
                    p.icon = selectedProjectIcon;
                }
            } else {
                state.projects.push({ id: 'proj-' + Date.now(), name: name, icon: selectedProjectIcon, color: '#2eaadc' });
            }

            saveState(true, true);
            renderSidebarProjects();
            closeProjectModal();
            showToast(projId ? "Projeto salvo!" : "Projeto criado!");
        }

        function deleteCurrentEditingProject() {
            const projId = document.getElementById('editingProjectId').value;
            if (!projId) return;
            state.projects = state.projects.filter(p => p.id !== projId);
            state.tasks.forEach(t => { if (t.projectId === projId) t.projectId = null; });
            saveState(true, true);
            renderSidebarProjects();
            closeProjectModal();
            renderAll();
            showToast("Projeto excluído.");
        }

        function renderIconPicker(containerId, currentSelectedIcon, onSelect) {
            const container = document.getElementById(containerId);
            if (!container) return;
            container.innerHTML = AVAILABLE_ICONS.map(ic => `
                <button onclick="event.preventDefault(); selectIconInPicker('${containerId}', '${ic}')" class="p-2 text-center rounded border transition cursor-pointer ${ic === currentSelectedIcon ? 'border-[#2eaadc] bg-[#2eaadc]/20 text-white' : 'border-white/10 text-gray-400 hover:text-white hover:bg-white/5'}">
                    <i class="${ic} text-xs"></i>
                </button>
            `).join('');

            container.dataset.selectedIcon = currentSelectedIcon;
        }

        function selectIconInPicker(containerId, iconClass) {
            const container = document.getElementById(containerId);
            if (!container) return;
            if (containerId === 'categoryIconPicker') selectedCategoryIcon = iconClass;
            if (containerId === 'projectIconPicker') selectedProjectIcon = iconClass;
            if (containerId === 'noteIconPickerContainer') tempNoteIcon = iconClass;
            renderIconPicker(containerId, iconClass);
        }

        function showToast(msg) {
            const container = document.getElementById('toastContainer');
            const toast = document.createElement('div');
            toast.className = 'px-3.5 py-2 bg-[#202020] border border-[#2f2f2f] shadow-2xl text-white rounded text-xs font-semibold flex items-center gap-2 transition-all duration-200';
            toast.innerHTML = `<i class="fa-solid fa-circle-check text-[#2eaadc]"></i> ${msg}`;
            container.appendChild(toast);
            setTimeout(() => toast.remove(), 2600);
        }

        function formatDateBR(dateStr) {
            if (!dateStr) return '';
            const p = dateStr.split('-');
            return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : dateStr;
        }

        /* ==================================================================
           CENTRAL DE NOTIFICAÇÕES & MONITORAMENTO DE PRAZOS (DEADLINE ENGINE)
           ================================================================== */
        let notifiedTaskIds = new Set();
        let lastNotifCheckDate = null;

        function getTodayDateStr() {
            const d = new Date();
            const year = d.getFullYear();
            const month = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            return `${year}-${month}-${day}`;
        }

        function calculateDaysDiff(dateStr1, dateStr2) {
            try {
                const [y1, m1, d1] = dateStr1.split('-').map(Number);
                const [y2, m2, d2] = dateStr2.split('-').map(Number);
                const dt1 = new Date(y1, m1 - 1, d1);
                const dt2 = new Date(y2, m2 - 1, d2);
                const diffTime = dt1.getTime() - dt2.getTime();
                return Math.round(diffTime / (1000 * 60 * 60 * 24));
            } catch (e) {
                return 0;
            }
        }

        function getDeadlineStatus(t, todayStr) {
            if (!t.dueDate) return null;
            const diff = calculateDaysDiff(t.dueDate, todayStr);
            if (diff < 0) {
                return { type: 'overdue', diff: Math.abs(diff), label: `Atrasada (${Math.abs(diff)}d)` };
            } else if (diff === 0) {
                return { type: 'today', diff: 0, label: 'Vence Hoje' };
            } else if (diff === 1) {
                return { type: 'tomorrow', diff: 1, label: 'Vence Amanhã' };
            } else if (diff <= 3) {
                return { type: 'soon', diff: diff, label: `Vence em ${diff}d` };
            }
            return null;
        }

        function checkDeadlinesAndNotify(forceNotify = false) {
            if (!state || !Array.isArray(state.tasks)) return;

            const today = getTodayDateStr();
            if (lastNotifCheckDate && lastNotifCheckDate !== today) {
                notifiedTaskIds.clear();
            }
            lastNotifCheckDate = today;

            const pendingTasks = state.tasks.filter(t => (Number(t.progress) || 0) < 100 && !t.completed);
            
            const overdueTasks = [];
            const todayTasks = [];
            const soonTasks = [];

            pendingTasks.forEach(t => {
                const status = getDeadlineStatus(t, today);
                if (!status) return;
                const item = { task: t, status };
                if (status.type === 'overdue') overdueTasks.push(item);
                else if (status.type === 'today') todayTasks.push(item);
                else soonTasks.push(item);
            });

            overdueTasks.sort((a, b) => a.task.dueDate.localeCompare(b.task.dueDate));
            todayTasks.sort((a, b) => (b.task.priority === 'Urgente' ? 1 : 0) - (a.task.priority === 'Urgente' ? 1 : 0));
            soonTasks.sort((a, b) => a.task.dueDate.localeCompare(b.task.dueDate));

            const totalCritical = overdueTasks.length + todayTasks.length;
            const totalAlerts = totalCritical + soonTasks.length;

            // 1. Atualizar Badge no Header (Sino)
            const badgeCount = document.getElementById('notifBadgeCount');
            const bellIcon = document.getElementById('notifBellIcon');
            const totalBadge = document.getElementById('notifTotalBadge');
            
            if (badgeCount) {
                if (totalAlerts > 0) {
                    badgeCount.innerText = totalAlerts > 99 ? '99+' : totalAlerts;
                    badgeCount.classList.remove('hidden');
                    if (totalCritical > 0) {
                        badgeCount.className = "absolute -top-1.5 -right-1.5 px-1.5 py-0.2 bg-rose-600 text-white font-bold text-[9px] rounded-full border border-[#202020] shadow-sm animate-pulse";
                        if (bellIcon) bellIcon.className = "fa-solid fa-bell text-rose-400 text-xs";
                    } else {
                        badgeCount.className = "absolute -top-1.5 -right-1.5 px-1.5 py-0.2 bg-amber-500 text-white font-bold text-[9px] rounded-full border border-[#202020] shadow-sm";
                        if (bellIcon) bellIcon.className = "fa-solid fa-bell text-amber-400 text-xs";
                    }
                } else {
                    badgeCount.classList.add('hidden');
                    if (bellIcon) bellIcon.className = "fa-regular fa-bell text-gray-400 text-xs";
                }
            }

            if (totalBadge) {
                totalBadge.innerText = `${totalAlerts} alerta(s)`;
            }

            // 2. Renderizar lista dentro do painel
            renderNotificationPanelContent(overdueTasks, todayTasks, soonTasks);

            // 3. Atualizar Badge na Barra de Tarefas do Windows
            if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.update_taskbar_badge === 'function') {
                try {
                    const desc = totalCritical > 0
                        ? `NEXUS - ${totalCritical} tarefa(s) com prazo crítico!`
                        : (totalAlerts > 0 ? `NEXUS - ${totalAlerts} tarefa(s) próximas` : "");
                    window.pywebview.api.update_taskbar_badge(totalCritical > 0 ? totalCritical : (totalAlerts > 0 ? totalAlerts : 0), desc);
                } catch (e) {
                    console.error("Erro ao atualizar taskbar badge:", e);
                }
            }

            // 4. Disparar Notificação Desktop do Windows (Toast)
            if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.send_desktop_notification === 'function') {
                const tasksToNotify = [];
                
                todayTasks.forEach(item => {
                    if (forceNotify || !notifiedTaskIds.has(item.task.id)) {
                        tasksToNotify.push({ task: item.task, type: 'today', label: 'Vence Hoje' });
                        notifiedTaskIds.add(item.task.id);
                    }
                });

                overdueTasks.slice(0, 2).forEach(item => {
                    if (forceNotify || !notifiedTaskIds.has(item.task.id)) {
                        tasksToNotify.push({ task: item.task, type: 'overdue', label: `Atrasada (${item.status.label})` });
                        notifiedTaskIds.add(item.task.id);
                    }
                });

                if (tasksToNotify.length > 0) {
                    if (tasksToNotify.length === 1) {
                        const t = tasksToNotify[0].task;
                        const titulo = tasksToNotify[0].type === 'today' 
                            ? `NEXUS: Tarefa Vencendo Hoje!` 
                            : `NEXUS: Tarefa Atrasada!`;
                        const mensagem = `${t.title}\nData Limite: ${formatDateBR(t.dueDate)} | Prioridade: ${t.priority || 'Normal'}`;
                        window.pywebview.api.send_desktop_notification(titulo, mensagem, true);
                    } else {
                        const titulo = `NEXUS: ${tasksToNotify.length} tarefas com prazo hoje ou atrasadas`;
                        const resumo = tasksToNotify.map(n => `• ${n.task.title} (${n.label})`).slice(0, 3).join('\n');
                        window.pywebview.api.send_desktop_notification(titulo, resumo, true);
                    }
                }
            }
        }

        function renderNotificationPanelContent(overdueTasks, todayTasks, soonTasks) {
            const listContainer = document.getElementById('notificationList');
            if (!listContainer) return;

            const total = overdueTasks.length + todayTasks.length + soonTasks.length;
            if (total === 0) {
                listContainer.innerHTML = `
                    <div class="py-8 text-center flex flex-col items-center justify-center text-gray-500">
                        <i class="fa-regular fa-circle-check text-2xl text-emerald-400/60 mb-2"></i>
                        <p class="font-medium text-gray-300">Tudo em dia!</p>
                        <p class="text-[11px] text-gray-500 mt-0.5">Nenhuma tarefa atrasada ou com prazo próximo.</p>
                    </div>
                `;
                return;
            }

            let html = '';

            if (overdueTasks.length > 0) {
                html += `
                    <div class="mb-2">
                        <div class="text-[10px] font-bold text-rose-400 uppercase tracking-wider px-1 mb-1 flex items-center gap-1.5">
                            <i class="fa-solid fa-triangle-exclamation"></i> Atrasadas (${overdueTasks.length})
                        </div>
                        <div class="space-y-1.5">
                            ${overdueTasks.map(item => createNotifItemHTML(item.task, 'border-rose-500/30 bg-rose-950/20 text-rose-300', item.status.label, 'text-rose-400')).join('')}
                        </div>
                    </div>
                `;
            }

            if (todayTasks.length > 0) {
                html += `
                    <div class="mb-2">
                        <div class="text-[10px] font-bold text-amber-400 uppercase tracking-wider px-1 mb-1 flex items-center gap-1.5">
                            <i class="fa-solid fa-clock"></i> Vencem Hoje (${todayTasks.length})
                        </div>
                        <div class="space-y-1.5">
                            ${todayTasks.map(item => createNotifItemHTML(item.task, 'border-amber-500/30 bg-amber-950/20 text-amber-300', item.status.label, 'text-amber-400')).join('')}
                        </div>
                    </div>
                `;
            }

            if (soonTasks.length > 0) {
                html += `
                    <div class="mb-1">
                        <div class="text-[10px] font-bold text-sky-400 uppercase tracking-wider px-1 mb-1 flex items-center gap-1.5">
                            <i class="fa-regular fa-calendar-days"></i> Próximos Dias (${soonTasks.length})
                        </div>
                        <div class="space-y-1.5">
                            ${soonTasks.map(item => createNotifItemHTML(item.task, 'border-sky-500/20 bg-sky-950/10 text-sky-300', item.status.label, 'text-sky-400')).join('')}
                        </div>
                    </div>
                `;
            }

            listContainer.innerHTML = html;
        }

        function createNotifItemHTML(task, badgeClass, statusLabel, iconColor) {
            const cat = state.categories.find(c => c.id === task.categoryId);
            const proj = state.projects.find(p => p.id === task.projectId);
            const contextText = [cat ? cat.name : null, proj ? proj.name : null].filter(Boolean).join(' • ');

            return `
                <div class="p-2 rounded bg-white/5 hover:bg-white/10 border border-white/5 transition flex items-start justify-between gap-2 group cursor-pointer" onclick="openTaskFromNotif('${task.id}')">
                    <div class="flex items-start gap-2 min-w-0 flex-1">
                        <button onclick="event.stopPropagation(); quickCompleteFromNotif('${task.id}')" class="mt-0.5 w-4 h-4 rounded-full border border-gray-600 hover:border-emerald-400 hover:bg-emerald-500/20 flex items-center justify-center transition cursor-pointer flex-shrink-0" title="Concluir tarefa agora">
                            <i class="fa-solid fa-check text-[8px] text-transparent group-hover:text-emerald-300"></i>
                        </button>
                        <div class="min-w-0 flex-1">
                            <div class="text-xs text-gray-200 font-medium truncate group-hover:text-white" title="${escapeHtml(task.title)}">${escapeHtml(task.title)}</div>
                            <div class="flex items-center gap-2 mt-1">
                                <span class="text-[9px] font-semibold px-1.5 py-0.2 rounded border ${badgeClass} whitespace-nowrap">${statusLabel}</span>
                                ${contextText ? `<span class="text-[10px] text-gray-500 truncate max-w-[150px]">${escapeHtml(contextText)}</span>` : ''}
                            </div>
                        </div>
                    </div>
                    <i class="fa-solid fa-arrow-right text-[10px] text-gray-600 group-hover:text-sky-400 mt-1 flex-shrink-0 transition"></i>
                </div>
            `;
        }

        function toggleNotificationPanel(forceState) {
            const panel = document.getElementById('notificationPanel');
            if (!panel) return;
            const isHidden = panel.classList.contains('hidden');
            const shouldShow = forceState !== undefined ? forceState : isHidden;
            if (shouldShow) {
                checkDeadlinesAndNotify(false);
                panel.classList.remove('hidden');
                panel.classList.add('flex');
            } else {
                panel.classList.add('hidden');
                panel.classList.remove('flex');
            }
        }

        function openTaskFromNotif(taskId) {
            toggleNotificationPanel(false);
            if (appMode !== 'tasks') {
                switchAppMode('tasks');
            }
            openTaskDetailDrawer(taskId);
        }

        function quickCompleteFromNotif(taskId) {
            toggleTaskCompletion(taskId);
            checkDeadlinesAndNotify(false);
            showToast("Tarefa concluída!");
        }

        function testarNotificacaoWindows() {
            if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.send_desktop_notification === 'function') {
                window.pywebview.api.send_desktop_notification(
                    "NEXUS - Teste de Notificação",
                    "As notificações do Windows estão funcionando com sucesso no NEXUS!",
                    true
                );
                showToast("Notificação enviada ao Windows!");
            } else {
                showToast("Ponte com o sistema operacional não conectada.");
            }
        }

        document.addEventListener('click', (e) => {
            const panel = document.getElementById('notificationPanel');
            const btn = document.getElementById('notifBellBtn');
            if (panel && !panel.classList.contains('hidden')) {
                if (!panel.contains(e.target) && !btn.contains(e.target)) {
                    panel.classList.add('hidden');
                    panel.classList.remove('flex');
                }
            }
        });

        /* ==================================================================
           TECLADO: Enter confirma, Esc cancela
           ------------------------------------------------------------------
           Um único handler global cobre todas as telas de criação/edição, em
           vez de espalhar onkeydown por cada input. Quem tem várias linhas
           (textarea, editor de notas) fica de fora: ali Enter é quebra de linha.
           ================================================================== */
        const MODAIS_COM_CONFIRMACAO = [
            { id: 'categoryModal', confirmar: () => saveCategoryModal(), cancelar: () => closeCategoryModal() },
            { id: 'projectModal',  confirmar: () => saveProjectModal(),  cancelar: () => closeProjectModal()  },
            { id: 'profileModal',  confirmar: () => saveProfile(),       cancelar: () => closeProfileModal()  },
            { id: 'noteIconModal', confirmar: null,                      cancelar: () => closeNoteIconModal() },
        ];

        function modalAbertoNoTopo() {
            // O último da lista que estiver visível é o que está por cima.
            for (let i = MODAIS_COM_CONFIRMACAO.length - 1; i >= 0; i--) {
                const m = MODAIS_COM_CONFIRMACAO[i];
                const el = document.getElementById(m.id);
                if (el && !el.classList.contains('hidden')) return m;
            }
            return null;
        }

        function aceitaQuebraDeLinha(el) {
            if (!el) return false;
            const tag = (el.tagName || '').toLowerCase();
            return tag === 'textarea' || el.isContentEditable === true;
        }

        document.addEventListener('keydown', (e) => {
            const alvo = e.target;

            if (e.key === 'Escape') {
                const notifPanel = document.getElementById('notificationPanel');
                if (notifPanel && !notifPanel.classList.contains('hidden')) {
                    e.preventDefault();
                    toggleNotificationPanel(false);
                    return;
                }
                const modal = modalAbertoNoTopo();
                if (modal) { e.preventDefault(); modal.cancelar(); return; }
                if (selectedTaskId) { e.preventDefault(); closeTaskDetailDrawer(); }
                return;
            }

            if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
            if (aceitaQuebraDeLinha(alvo)) return;      // notas, editor do Vault

            // 0) Tela de entrada aberta: Enter faz login.
            const gate = document.getElementById('loginGate');
            if (gate && !gate.classList.contains('hidden')) {
                e.preventDefault();
                gateEntrar();
                return;
            }

            // 1) Modal aberto: Enter salva o que está sendo criado/editado.
            const modal = modalAbertoNoTopo();
            if (modal) {
                e.preventDefault();
                if (modal.confirmar) modal.confirmar();
                else modal.cancelar();
                return;
            }

            // 2) Campos com ação própria já tratam o Enter no próprio onkeydown.
            if (alvo && (alvo.id === 'quickTaskInput' || alvo.id === 'newStepInput')) return;

            // 3) Painel de detalhes: Enter grava a edição e tira o foco do campo.
            if (alvo && alvo.id === 'detailTaskTitle') {
                e.preventDefault();
                flushPendingDrawerEdits();
                renderCurrentView();
                alvo.blur();
                showToast("Tarefa atualizada!");
                return;
            }
            if (alvo && (alvo.id === 'detailTaskDueDate' || alvo.id === 'detailTaskPriority' ||
                         alvo.id === 'detailTaskCategory' || alvo.id === 'detailTaskProject')) {
                e.preventDefault();
                updateTaskFromDrawer();
                alvo.blur();
                showToast("Tarefa atualizada!");
                return;
            }

            // 4) Vault: Enter no título confirma o nome da nota.
            if (alvo && alvo.id === 'noteTitleInput') {
                e.preventDefault();
                saveNoteTitleLive();
                alvo.blur();
                return;
            }
        });

        /* ==================================================================
           NUVEM: configuração, conta e sincronização
           ================================================================== */
        let cloudInfo = { configured: false, signedIn: false };

        function apiPronta() {
            return window.pywebview && window.pywebview.api &&
                   typeof window.pywebview.api.cloud_status === 'function';
        }

        async function atualizarStatusNuvem() {
            if (!apiPronta()) return;
            try {
                cloudInfo = await window.pywebview.api.cloud_status();
                pintarBadgeNuvem();
                pintarModalNuvem();
            } catch (e) { console.warn('cloud_status:', e); }
        }

        /* A barra do topo mostra o estado do banco NA NUVEM.
           O caminho do arquivo local não aparece mais: o banco de referência
           passou a ser o Firebase, e o disco virou apenas cache. */
        function pintarBadgeNuvem() {
            const ic = document.getElementById('cloudBadgeIcon');
            const alvo = document.getElementById('db-filepath-text');
            const ponto = document.getElementById('status-dot-indicator');
            const barra = document.getElementById('dbStatusBar');
            if (!alvo) return;

            if (!cloudInfo.signedIn) {
                if (ic) ic.className = 'fa-solid fa-cloud-arrow-up text-[11px] text-amber-400';
                if (ponto) ponto.className = 'w-2 h-2 rounded-full bg-amber-500 shadow-sm';
                alvo.innerText = 'Sem conta conectada';
                alvo.style.color = '#fbbf24';
                if (barra) barra.title = 'Clique para entrar na sua conta';
            } else {
                if (ic) ic.className = 'fa-solid fa-cloud text-[11px] text-emerald-400';
                if (ponto) ponto.className = 'w-2 h-2 rounded-full bg-emerald-500 shadow-sm';
                alvo.innerText = nomeDoBanco();
                alvo.style.color = '';
                if (barra) barra.title = `Conta: ${cloudInfo.email}`;
            }
        }

        /* Relata o que aconteceu com a nuvem, no mesmo padrão do Cogni:
           "Enviado às ...", "Atualizado às ...", "Offline (salvo local)". */
        function marcarEventoNuvem(evento) {
            const lbl = document.getElementById('status-save-label');
            const dot = document.getElementById('status-dot-indicator');
            if (!lbl) return;

            const t = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            lbl.style.color = '';

            if (evento === 'offline') {
                lbl.innerText = 'Offline (salvo local)';
                lbl.style.color = '#fbbf24';
                if (dot) dot.className = 'w-2 h-2 rounded-full bg-amber-500 shadow-sm';
                return;
            }
            if (dot) dot.className = 'w-2 h-2 rounded-full bg-emerald-500 shadow-sm';

            if (evento === 'enviado')       lbl.innerText = `Enviado às ${t}`;
            else if (evento === 'atualizado') lbl.innerText = `Atualizado às ${t}`;
            else                              lbl.innerText = 'Sincronizado';
        }

        /* Nome curto do banco a partir da URL, sem expor UID nem caminho. */
        function nomeDoBanco() {
            try {
                const m = String(cloudInfo.databaseURL || '').match(/https?:\/\/([^.]+)/);
                return m ? ('Firebase · ' + m[1]) : 'Firebase';
            } catch (e) { return 'Firebase'; }
        }

        function pintarModalNuvem() {
            const box = document.getElementById('cloudStatusBox');
            if (!box) return;

            if (!cloudInfo.configured) {
                box.innerHTML = '<span class="text-amber-300"><i class="fa-solid fa-triangle-exclamation mr-1"></i> Nenhum projeto conectado.</span> Preencha os campos abaixo para começar.';
            } else if (!cloudInfo.signedIn) {
                box.innerHTML = '<span class="text-amber-300"><i class="fa-solid fa-user-slash mr-1"></i> Nenhuma conta conectada.</span>';
            } else {
                box.innerHTML = `<span class="text-emerald-300"><i class="fa-solid fa-circle-check mr-1"></i> Conectado como <b>${escapeHtml(cloudInfo.email || '')}</b></span>
                    ${cloudInfo.lastSync ? `<br><span class="text-[10px] text-gray-500">Última sincronização: ${escapeHtml(cloudInfo.lastSync)}</span>` : ''}`;
            }

            const login = document.getElementById('cloudLoginForm');
            const logado = document.getElementById('cloudLoggedBox');
            if (login && logado) {
                login.classList.toggle('hidden', !!cloudInfo.signedIn);
                logado.classList.toggle('hidden', !cloudInfo.signedIn);
            }
            const sync = document.getElementById('cloudSyncSection');
            if (sync) sync.style.display = cloudInfo.signedIn ? '' : 'none';
        }

        function openCloudModal() {
            document.getElementById('cloudModal').classList.remove('hidden');
            document.getElementById('cloudModal').classList.add('flex');
            atualizarStatusNuvem();
        }
        function closeCloudModal() {
            document.getElementById('cloudModal').classList.add('hidden');
            document.getElementById('cloudModal').classList.remove('flex');
        }

        function _credenciais() {
            const email = document.getElementById('cloudEmail').value.trim();
            const senha = document.getElementById('cloudPassword').value;
            if (!email || !senha) { showToast('Informe e-mail e senha.'); return null; }
            return { email, senha };
        }

        async function entrarNaNuvem() {
            const c = _credenciais(); if (!c) return;
            const r = await window.pywebview.api.cloud_sign_in(c.email, c.senha);
            await _depoisDoLogin(r);
        }

        async function criarContaNaNuvem() {
            const c = _credenciais(); if (!c) return;
            const r = await window.pywebview.api.cloud_sign_up(c.email, c.senha);
            await _depoisDoLogin(r);
        }

        async function _depoisDoLogin(r) {
            if (r.status !== 'success') { showToast(r.message || 'Falha na autenticação.'); return; }
            document.getElementById('cloudPassword').value = '';
            showToast('Conectado! Sincronizando...');
            avisarMigracao(r);
            await atualizarStatusNuvem();
            // Recarrega passando pela reconciliação nuvem/local.
            isLoadedFromDisk = false; isInitializing = false;
            await initNativeApp();
            closeCloudModal();
        }

        async function sairDaNuvem() {
            if (!confirm('Sair da conta? Seus dados continuam salvos nesta máquina.')) return;

            // ORDEM IMPORTA: primeiro travar a gravacao e descartar qualquer
            // gravacao pendente. Sem isso, o timer de autosave poderia disparar
            // depois do logout e escrever os dados desta conta na pasta da
            // proxima que entrar.
            isLoadedFromDisk = false;
            dbBlocked = true;
            if (typeof saveStateTimeout !== 'undefined' && saveStateTimeout) {
                clearTimeout(saveStateTimeout);
                saveStateTimeout = null;
            }
            limparEstadoEmMemoria();

            await window.pywebview.api.cloud_sign_out();
            await atualizarStatusNuvem();
            closeCloudModal();
            closeProfileModal();
            modoLocalEscolhido = false;
            mostrarGate();
        }

        /* Zera tudo que ficou da conta anterior: estado, selecoes, avatar e
           o que esta desenhado na tela. */
        function limparEstadoEmMemoria() {
            state = { categories: [], projects: [], tasks: [], notepad: [], userProfile: {} };
            selectedTaskId = null;
            selectedNoteId = null;
            avatarDataUri = null;
            try {
                selectedTaskIds.clear();
                selectedCategoryIds.clear();
                selectedProjectIds.clear();
                selectedNoteIds.clear();
            } catch (e) {}
            try {
                const dr = document.getElementById('taskDetailDrawer');
                if (dr) dr.classList.add('hidden');
                renderProfile();
                renderAll();
            } catch (e) {}
        }

        async function enviarParaNuvem() {
            if (!confirm('Enviar os dados desta máquina para a nuvem?\n\nO que estiver na nuvem será substituído.')) return;
            const r = await window.pywebview.api.cloud_push_now();
            showToast(r.status === 'success' ? 'Enviado para a nuvem.' : ('Falhou: ' + (r.message || '')));
            await atualizarStatusNuvem();
        }

        async function baixarDaNuvem() {
            if (!confirm('Baixar os dados da nuvem?\n\nO que estiver nesta máquina será substituído.')) return;
            const r = await window.pywebview.api.cloud_pull_now();
            if (r.status !== 'success') { showToast('Falhou: ' + (r.message || '')); return; }
            isLoadedFromDisk = false; isInitializing = false;
            await initNativeApp();
            marcarEventoNuvem('atualizado');
            showToast('Dados baixados da nuvem.');
            await atualizarStatusNuvem();
        }

        /* Conflito: nunca resolve sozinho — mostra os números e deixa escolher. */
        function avisarConflitoNuvem(info) {
            const local = info.localItems, nuvem = info.cloudItems;
            setTimeout(() => {
                alert(
                    "Os dados desta máquina e os da nuvem estão diferentes.\n\n" +
                    `Nesta máquina: ${local} item(ns)\n` +
                    `Na nuvem:      ${nuvem} item(ns)\n\n` +
                    "Como um dos lados tem menos conteúdo, nada foi sobrescrito " +
                    "automaticamente para não arriscar perder trabalho.\n\n" +
                    "Abra o painel da Nuvem e escolha 'Enviar' ou 'Baixar'."
                );
                openCloudModal();
            }, 400);
        }

        /* ---------------- Tela de entrada ---------------- */
        let modoLocalEscolhido = false;

        function mostrarGate() {
            const g = document.getElementById('loginGate');
            if (!g) return;
            g.classList.remove('hidden'); g.classList.add('flex');
            setTimeout(() => { const e = document.getElementById('gateEmail'); if (e) e.focus(); }, 80);
        }
        function esconderGate() {
            const g = document.getElementById('loginGate');
            if (!g) return;
            g.classList.add('hidden'); g.classList.remove('flex');
        }
        function gateErro(msg) {
            const e = document.getElementById('gateError');
            if (!e) return;
            if (!msg) { e.classList.add('hidden'); return; }
            e.innerText = msg; e.classList.remove('hidden');
        }
        function gateOcupado(estado) {
            ['gateSignIn', 'gateSignUp'].forEach(id => {
                const b = document.getElementById(id);
                if (b) { b.disabled = estado; b.style.opacity = estado ? .55 : 1; }
            });
        }
        function gateCredenciais() {
            const email = (document.getElementById('gateEmail').value || '').trim();
            const senha = document.getElementById('gatePassword').value || '';
            if (!email || !senha) { gateErro('Informe e-mail e senha.'); return null; }
            return { email, senha };
        }

        async function gateEntrar()     { await gateAutenticar('cloud_sign_in'); }
        async function gateCriarConta() { await gateAutenticar('cloud_sign_up'); }

        async function gateAutenticar(metodo) {
            const c = gateCredenciais(); if (!c) return;
            gateErro(''); gateOcupado(true);
            try {
                const r = await window.pywebview.api[metodo](c.email, c.senha);
                if (r.status !== 'success') { gateErro(r.message || 'Falha na autenticação.'); return; }
                document.getElementById('gatePassword').value = '';
                esconderGate();
                // Descarta qualquer resquicio antes de carregar a conta nova.
                isLoadedFromDisk = false; isInitializing = false; dbBlocked = false;
                if (typeof saveStateTimeout !== 'undefined' && saveStateTimeout) {
                    clearTimeout(saveStateTimeout); saveStateTimeout = null;
                }
                limparEstadoEmMemoria();
                avisarMigracao(r);              // doNext -> NEXUS, se aplicavel
                await initNativeApp();          // carrega reconciliando com a nuvem
            } catch (e) {
                gateErro('Erro inesperado: ' + e);
            } finally {
                gateOcupado(false);
            }
        }

        function gateUsarLocal() {
            if (!confirm('Continuar sem conta?\n\nSeus dados ficarão apenas neste computador e não serão sincronizados.')) return;
            modoLocalEscolhido = true;
            esconderGate();
            isLoadedFromDisk = false; isInitializing = false;
            initNativeApp();
        }


        /* ================================================================
           ATUALIZACAO AUTOMATICA
           ================================================================
           O Python faz a checagem numa thread e guarda o resultado. O JS
           apenas consulta. Nada aqui bloqueia a interface: se o updater
           estiver indisponivel, o app funciona exatamente como antes.
        */
        let updInfo = null;
        let updPollTimer = null;

        function abrirUpdateModal() {
            const m = document.getElementById('updateModal');
            if (!m) return;
            m.classList.remove('hidden');
            m.classList.add('flex');
            mostrarDiagnosticoUpdate();
            if (updInfo) pintarUpdateModal(updInfo);
            else verificarAtualizacao(true);
        }

        function fecharUpdateModal() {
            const m = document.getElementById('updateModal');
            if (!m) return;
            m.classList.add('hidden');
            m.classList.remove('flex');
        }

        async function mostrarDiagnosticoUpdate() {
            const el = document.getElementById('updDiag');
            if (!el) return;
            try {
                const d = await window.pywebview.api.update_channel_info();
                let txt = 'canal: ' + d.channel
                    + (d.tlsVerificavel ? ' | TLS verificado' : ' | TLS SEM VERIFICACAO — atualizacao bloqueada');
                if (d.tlsDegradado) {
                    txt += ' | ATENCAO: alguma conexao de dados caiu para modo sem'
                         + ' verificacao de certificado (' + (d.tlsMotivo || '') + ')';
                }
                el.innerText = txt;
            } catch (e) { el.innerText = ''; }
        }

        /* Aviso persistente se a conexao de dados degradou. Login e atualizacao
           nunca degradam — recusam e falham. Mas os DADOS podem, para o app nao
           travar; nesse caso o usuario tem de ficar sabendo. */
        async function checarSegurancaDaConexao() {
            try {
                const st = await window.pywebview.api.security_status();
                if (!st) return;
                if (!st.tlsVerificavel) {
                    showToast('Este computador nao consegue validar certificados HTTPS. '
                        + 'Login e atualizacao ficam bloqueados por seguranca.');
                } else if (st.tlsDegradado) {
                    showToast('Aviso de seguranca: uma conexao de dados foi feita sem '
                        + 'verificar o certificado do servidor. Verifique se ha antivirus '
                        + 'ou proxy inspecionando HTTPS nesta rede.');
                }
            } catch (e) { /* diagnostico e opcional */ }
        }

        function pintarUpdateModal(info) {
            const box  = document.getElementById('updStatusBox');
            const btn  = document.getElementById('updBtnInstall');
            const nb   = document.getElementById('updNotesBox');
            const nt   = document.getElementById('updNotes');
            if (!box) return;

            if (!info) { box.innerHTML = '<span class="text-gray-500">Verificando...</span>'; return; }

            if (info.status === 'update_available') {
                box.innerHTML = '<span class="text-sky-300"><i class="fa-solid fa-circle-arrow-up mr-1"></i>'
                    + ' Versao <b>' + escapeHtml(info.latest) + '</b> disponivel</span>'
                    + '<br><span class="text-[10px] text-gray-500">Voce esta na ' + escapeHtml(info.current)
                    + (info.size ? ' &middot; download de ' + (info.size / 1048576).toFixed(1) + ' MB' : '')
                    + '</span>'
                    + (info.hasHash ? '' : '<br><span class="text-[10px] text-amber-400">Manifesto sem SHA-256: instalacao bloqueada por seguranca.</span>');
                if (btn) btn.classList.toggle('hidden', !info.hasHash);
                if (info.notes && nb && nt) { nt.innerText = info.notes; nb.classList.remove('hidden'); }
            } else if (info.status === 'up_to_date') {
                box.innerHTML = '<span class="text-emerald-300"><i class="fa-solid fa-circle-check mr-1"></i>'
                    + ' O NEXUS esta atualizado (' + escapeHtml(info.current) + ')</span>';
                if (btn) btn.classList.add('hidden');
                if (nb) nb.classList.add('hidden');
            } else {
                box.innerHTML = '<span class="text-amber-400"><i class="fa-solid fa-triangle-exclamation mr-1"></i> '
                    + escapeHtml(info.message || 'Nao foi possivel verificar.') + '</span>';
                if (btn) btn.classList.add('hidden');
            }
        }

        function pintarBadgeUpdate(info) {
            const dot = document.getElementById('updateDot');
            const lbl = document.getElementById('updateDotLabel');
            if (!dot) return;
            if (info && info.status === 'update_available') {
                if (lbl) lbl.innerText = info.latest || 'novo';
                dot.classList.remove('hidden');
                dot.classList.add('flex');
            } else {
                dot.classList.add('hidden');
                dot.classList.remove('flex');
            }
        }

        async function verificarAtualizacao(manual) {
            const btn = document.getElementById('updBtnCheck');
            try {
                if (manual && btn) { btn.disabled = true; btn.classList.add('opacity-50'); }
                const r = manual
                    ? await window.pywebview.api.update_check_now()
                    : await window.pywebview.api.update_cached();
                if (r) { updInfo = r; pintarUpdateModal(r); pintarBadgeUpdate(r); }
                if (manual && r && r.status === 'up_to_date') showToast('Nenhuma atualizacao disponivel.');
                return r;
            } catch (e) {
                if (manual) showToast('Falha ao verificar atualizacao.');
                return null;
            } finally {
                if (manual && btn) { btn.disabled = false; btn.classList.remove('opacity-50'); }
            }
        }

        async function instalarAtualizacao() {
            if (!confirm('Baixar e instalar a versao ' + ((updInfo && updInfo.latest) || 'nova') + '?\n\n'
                + 'O NEXUS vai fechar e reabrir sozinho ao final.\n'
                + 'Seus dados e sua conta permanecem intactos.')) return;
            const btn = document.getElementById('updBtnInstall');
            const box = document.getElementById('updProgressBox');
            try {
                if (btn) { btn.disabled = true; btn.classList.add('opacity-50'); }
                if (box) box.classList.remove('hidden');
                await window.pywebview.api.update_install();
                if (updPollTimer) clearInterval(updPollTimer);
                updPollTimer = setInterval(acompanharUpdate, 500);
            } catch (e) {
                showToast('Nao foi possivel iniciar a atualizacao.');
                if (btn) { btn.disabled = false; btn.classList.remove('opacity-50'); }
            }
        }

        const UPD_FASES = {
            idle: 'Aguardando', downloading: 'Baixando',
            verified: 'Integridade confirmada', installing: 'Instalando',
            error: 'Erro'
        };

        async function acompanharUpdate() {
            try {
                const p = await window.pywebview.api.update_progress();
                if (!p) return;
                const bar = document.getElementById('updBar');
                const ph  = document.getElementById('updPhase');
                const pc  = document.getElementById('updPct');
                if (bar) bar.style.width = (p.pct || 0) + '%';
                if (pc)  pc.innerText = (p.pct || 0) + '%';
                if (ph)  ph.innerText = UPD_FASES[p.fase] || p.fase || '-';

                if (p.fase === 'error') {
                    clearInterval(updPollTimer); updPollTimer = null;
                    const box = document.getElementById('updStatusBox');
                    if (box) box.innerHTML = '<span class="text-rose-400"><i class="fa-solid fa-circle-xmark mr-1"></i> '
                        + escapeHtml(p.mensagem || 'Falha na atualizacao.') + '</span>';
                    if (bar) bar.classList.replace('bg-[#2eaadc]', 'bg-rose-500');
                    const btn = document.getElementById('updBtnInstall');
                    if (btn) { btn.disabled = false; btn.classList.remove('opacity-50'); }
                } else if (p.fase === 'installing') {
                    const box = document.getElementById('updStatusBox');
                    if (box) box.innerHTML = '<span class="text-sky-300"><i class="fa-solid fa-gear fa-spin mr-1"></i> '
                        + escapeHtml(p.mensagem || 'Instalando...') + '</span>';
                }
            } catch (e) { /* app fechando durante a instalacao: normal */ }
        }

        /* Aviso de migracao doNext -> NEXUS: aparece uma vez, so se algo foi
           efetivamente migrado. Silencio quando nao ha nada a dizer. */
        async function avisarMigracao(resLogin) {
            try {
                const disco = await window.pywebview.api.migration_report();
                if (disco && disco.arquivos > 0) {
                    showToast('Migracao concluida: ' + disco.arquivos
                        + ' arquivo(s) trazido(s) do doNext. A pasta antiga foi preservada.');
                }
            } catch (e) { /* cosmetico */ }
            const mg = resLogin && resLogin.migracao;
            if (mg && mg.status === 'migrated') {
                showToast('Dados da nuvem migrados do doNext para o NEXUS ('
                    + (mg.items || 0) + ' itens). O ramo antigo virou backup.');
            } else if (mg && mg.status === 'error' && mg.message) {
                showToast('Migracao da nuvem: ' + mg.message);
            }
        }

        /* ================================================================
           SANITIZACAO DO EDITOR DE NOTAS
           ================================================================
           O editor e um contenteditable: por natureza ele guarda HTML, e esse
           HTML volta para a tela via innerHTML. Isso e necessario para negrito,
           listas e links funcionarem.

           O problema: colar texto formatado de uma pagina web traz o HTML
           daquela pagina junto — inclusive <script>, onerror=, javascript: e
           <iframe>. Esse HTML fica GRAVADO na nota, sincroniza para a nuvem e
           roda de novo toda vez que a nota e aberta, em qualquer maquina.

           Num app pywebview isso e pior do que num site: o JavaScript da pagina
           tem acesso a window.pywebview.api, ou seja, a ponte para o Python.
           De "colei um texto" ate "abriram um arquivo na minha maquina" e um
           passo curto.

           A abordagem e lista de permissao: so passam as tags e atributos que o
           editor realmente usa. O resto e removido, mas o TEXTO e preservado —
           voce nao perde conteudo, so a formatacao exotica.
        */
        const TAGS_PERMITIDAS = new Set([
            'B','STRONG','I','EM','U','S','STRIKE','DEL','INS','MARK','SMALL',
            'SUB','SUP','BR','P','DIV','SPAN','H1','H2','H3','H4','H5','H6',
            'UL','OL','LI','BLOCKQUOTE','PRE','CODE','HR','A',
            'TABLE','THEAD','TBODY','TFOOT','TR','TD','TH','CAPTION','FONT'
        ]);
        const ATRIBUTOS_PERMITIDOS = new Set([
            'href','title','colspan','rowspan','align','color','face','start','type'
        ]);

        function _urlSegura(v) {
            /* Remove espacos e caracteres de controle antes de testar: o truque
               classico e "java\tscript:alert(1)", que passa numa checagem ingenua. */
            const limpo = String(v || '').replace(/[\u0000-\u0020]/g, '');
            return /^(https?:|mailto:|#|\/|\.)/i.test(limpo);
        }

        function sanitizarHtml(sujo) {
            /* <template> monta a arvore SEM executar nada: imagens nao sao
               baixadas, scripts nao rodam, onerror nao dispara. */
            const tpl = document.createElement('template');
            tpl.innerHTML = String(sujo == null ? '' : sujo);

            const remover = [];
            const caminhar = document.createTreeWalker(
                tpl.content, NodeFilter.SHOW_ELEMENT, null, false);

            let no;
            while ((no = caminhar.nextNode())) {
                const tag = no.tagName.toUpperCase();
                if (!TAGS_PERMITIDAS.has(tag)) { remover.push(no); continue; }

                /* Copia a lista antes de mexer: remover atributo durante a
                   iteracao faz o indice pular elementos. */
                for (const attr of Array.from(no.attributes)) {
                    const nome = attr.name.toLowerCase();

                    /* on* cobre onclick, onerror, onload, onmouseover e todo o
                       resto de uma vez. E o vetor mais comum de XSS colado. */
                    if (nome.startsWith('on') || !ATRIBUTOS_PERMITIDOS.has(nome)) {
                        no.removeAttribute(attr.name);
                        continue;
                    }
                    if (nome === 'href' && !_urlSegura(attr.value)) {
                        no.removeAttribute(attr.name);
                    }
                }

                if (tag === 'A' && no.getAttribute('href')) {
                    no.setAttribute('rel', 'noopener noreferrer');
                }
            }

            /* Remove a tag mas PRESERVA o texto de dentro. Excecao: script e
               style, onde o conteudo E o codigo. */
            for (const el of remover) {
                const pai = el.parentNode;
                if (!pai) continue;
                if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE') {
                    pai.removeChild(el);
                } else {
                    while (el.firstChild) pai.insertBefore(el.firstChild, el);
                    pai.removeChild(el);
                }
            }
            return tpl.innerHTML;
        }

        /* Intercepta o colar e o arrastar: limpa ANTES de entrar no documento,
           para que o HTML sujo nunca chegue a ser gravado. */
        function instalarSanitizacaoDoEditor() {
            const ed = document.getElementById('noteEditorBody');
            if (!ed || ed.dataset.sanitizado === '1') return;
            ed.dataset.sanitizado = '1';

            ed.addEventListener('paste', function (e) {
                e.preventDefault();
                const dt = e.clipboardData || window.clipboardData;
                if (!dt) return;
                const html = dt.getData('text/html');
                const texto = dt.getData('text/plain');
                if (html) {
                    document.execCommand('insertHTML', false, sanitizarHtml(html));
                } else {
                    document.execCommand('insertText', false, texto || '');
                }
            });

            ed.addEventListener('drop', function (e) {
                const dt = e.dataTransfer;
                if (!dt) return;
                const html = dt.getData('text/html');
                if (html) {
                    e.preventDefault();
                    document.execCommand('insertHTML', false, sanitizarHtml(html));
                }
            });
        }

        function escapeHtml(str) { return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
        function escapeJsStr(str) { return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'"); }
    </script>
</body>
</html>
"""

def main():
    try:
        api = NexusDesktopAPI()
        window = webview.create_window(
            title='NEXUS',
            html=HTML_CONTENT,
            js_api=api,
            width=1320,
            height=850,
            min_size=(960, 640),
            resizable=True
        )
        api.set_window(window)
        webview.start(debug=False)
    except Exception as e:
        show_native_error_dialog("Erro ao Iniciar o NEXUS", f"Ocorreu um erro ao carregar o aplicativo:\n\n{traceback.format_exc()}")

if __name__ == '__main__':
    main()
