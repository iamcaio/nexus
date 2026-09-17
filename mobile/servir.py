# -*- coding: utf-8 -*-
r"""
NEXUS Mobile - servidor local para testar o PWA.

Uso:
    cd C:\Dev\nexus\mobile
    python servir.py

Ou de qualquer lugar:
    python C:\Dev\nexus\mobile\servir.py

O que ele resolve, em relacao ao `python -m http.server`:

  1. Serve a PASTA MOBILE como raiz. Nada de listagem de diretorio e de clicar
     em "mobile/" toda vez - http://localhost:8080 ja abre o app.

  2. Abre o navegador sozinho.

  3. Mostra o IP da sua rede, para testar no celular.

  4. Desliga o cache do navegador nas respostas. Sem isso voce edita um
     arquivo, recarrega e continua vendo o antigo - e perde meia hora achando
     que o codigo esta errado quando so o cache esta velho.

  5. Serve .webmanifest com o Content-Type correto. O http.server padrao nao
     conhece essa extensao e manda application/octet-stream, o que faz o
     Chrome ignorar o manifest e o app nao ficar instalavel.
"""
import http.server
import os
import socket
import socketserver
import sys
import webbrowser

PORTA = 8080
PASTA = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):

    # O Chrome so trata como manifest se o MIME estiver certo.
    extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map)
    extensions_map.update({
        '.webmanifest': 'application/manifest+json',
        '.json': 'application/json',
        '.js': 'text/javascript',
        '.mjs': 'text/javascript',
        '.css': 'text/css',
        '.svg': 'image/svg+xml',
    })

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PASTA, **kwargs)

    def end_headers(self):
        # Sem cache: durante o desenvolvimento, cache so atrapalha.
        # Em producao o service worker cuida disso.
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        # Permite que o service worker controle a raiz inteira.
        self.send_header('Service-Worker-Allowed', '/')
        super().end_headers()

    def log_message(self, formato, *args):
        # Silencia o ruido de cada arquivo; mostra so erro.
        codigo = args[1] if len(args) > 1 else ''
        if str(codigo).startswith(('4', '5')):
            sys.stderr.write("  %s %s\n" % (codigo, args[0]))


def ip_da_rede():
    """IP da maquina na rede local, para abrir no celular."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.4)
        s.connect(('8.8.8.8', 80))   # nao envia nada; so descobre a interface
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def main():
    faltando = [n for n in ('index.html', 'app.js', 'nexus-sync.js',
                            'manifest.webmanifest', 'sw.js')
                if not os.path.exists(os.path.join(PASTA, n))]
    if faltando:
        print("Arquivos do PWA faltando em %s:" % PASTA)
        for f in faltando:
            print("   - " + f)
        return 2

    if not os.path.exists(os.path.join(PASTA, 'icons', 'icon-192.png')):
        print("AVISO: icons\\icon-192.png nao existe.")
        print("       Rode: python gerar_icones.py")
        print("       Sem os icones, o Android instala com uma letra generica.\n")

    porta = PORTA
    for tentativa in range(10):
        try:
            servidor = socketserver.TCPServer(('', porta), Handler)
            break
        except OSError:
            porta += 1
    else:
        print("Nenhuma porta livre entre %d e %d." % (PORTA, PORTA + 9))
        return 1

    servidor.allow_reuse_address = True
    url = 'http://localhost:%d' % porta
    ip = ip_da_rede()

    print()
    print("=" * 62)
    print("  NEXUS Mobile - servidor de teste")
    print("=" * 62)
    print("  pasta      %s" % PASTA)
    print("  computador %s" % url)
    if ip:
        print("  celular    http://%s:%d" % (ip, porta))
        print()
        print("  No celular, use a MESMA rede Wi-Fi.")
        print("  Pelo IP voce testa a interface e o login, mas NAO a")
        print("  instalacao nem o offline: o service worker so funciona em")
        print("  https:// ou em localhost. Para isso, publique.")
    print("=" * 62)
    print("  Ctrl+C para parar")
    print()

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nservidor encerrado.")
        servidor.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
