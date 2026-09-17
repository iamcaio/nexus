# -*- coding: utf-8 -*-
r"""
NEXUS Mobile - gera os PNGs do manifest.

Uso:
    cd C:\Dev\nexus\mobile
    pip install Pillow
    python gerar_icones.py

Gera em icons\:
    icon-192.png            atalho na tela inicial
    icon-512.png            splash e loja
    icon-maskable-512.png   Android recorta em circulo/squircle; esta versao
                            tem margem extra para o "N" nao ser cortado

Prioridade da fonte:
    1. ..\nexus.ico   - o icone que voce ja usa no desktop, para o app ficar
                        igual nos dois lugares
    2. desenho interno - se o .ico nao existir ou nao abrir

Sem Pillow instalado o script explica o que fazer e sai sem erro fatal.
"""
import os
import sys

DESTINO = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icons')
ICO_DESKTOP = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'nexus.ico')

TAMANHOS = [
    ('icon-192.png', 192, 0.00),
    ('icon-512.png', 512, 0.00),
    # 20% de margem: a "area segura" que o Android garante nao recortar
    ('icon-maskable-512.png', 512, 0.20),
]


def desenhar_fallback(tamanho, Image, ImageDraw):
    """Desenha o icone do zero: fundo escuro, quadrado colorido, letra N."""
    img = Image.new('RGBA', (tamanho, tamanho), (25, 25, 25, 255))
    d = ImageDraw.Draw(img)
    m = int(tamanho * 0.11)
    d.rounded_rectangle([m, m, tamanho - m, tamanho - m],
                        radius=int(tamanho * 0.17), fill=(46, 170, 220, 255))
    # "N" com tres retangulos - nao depende de fonte instalada
    l = int(tamanho * 0.075)          # espessura do traco
    x0, x1 = int(tamanho * 0.34), int(tamanho * 0.66) - l
    y0, y1 = int(tamanho * 0.33), int(tamanho * 0.67)
    branco = (255, 255, 255, 255)
    d.rectangle([x0, y0, x0 + l, y1], fill=branco)
    d.rectangle([x1, y0, x1 + l, y1], fill=branco)
    d.line([x0 + l // 2, y0, x1 + l // 2, y1], fill=branco, width=l)
    return img


def main():
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Pillow nao esta instalado.\n")
        print("    pip install Pillow")
        print("    python gerar_icones.py\n")
        print("Alternativa sem Python: abra icons\\icon.svg em")
        print("https://realfavicongenerator.net e baixe os PNGs.")
        return 2

    os.makedirs(DESTINO, exist_ok=True)

    base = None
    if os.path.exists(ICO_DESKTOP):
        try:
            ico = Image.open(ICO_DESKTOP)
            # .ico guarda varias resolucoes; pega a maior disponivel
            if hasattr(ico, 'ico'):
                maior = max(ico.ico.sizes())
                ico.size = maior
                ico = ico.ico.getimage(maior)
            base = ico.convert('RGBA')
            print("origem: nexus.ico (%dx%d)" % base.size)
        except Exception as e:
            print("nao consegui ler nexus.ico (%s); usando desenho interno" % e)

    for nome, tam, margem in TAMANHOS:
        if base is not None:
            interno = int(tam * (1 - margem * 2))
            img = Image.new('RGBA', (tam, tam), (25, 25, 25, 255))
            red = base.resize((interno, interno), Image.LANCZOS)
            desloc = (tam - interno) // 2
            img.paste(red, (desloc, desloc), red)
        else:
            img = desenhar_fallback(tam, Image, ImageDraw)
            if margem:
                interno = int(tam * (1 - margem * 2))
                fundo = Image.new('RGBA', (tam, tam), (25, 25, 25, 255))
                red = img.resize((interno, interno), Image.LANCZOS)
                d = (tam - interno) // 2
                fundo.paste(red, (d, d), red)
                img = fundo

        caminho = os.path.join(DESTINO, nome)
        img.save(caminho, 'PNG', optimize=True)
        print("  %-26s %dx%d  %d bytes"
              % (nome, tam, tam, os.path.getsize(caminho)))

    print("\nPronto. Os tres PNGs estao em icons\\.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
