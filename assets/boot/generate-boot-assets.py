#!/usr/bin/env python3
"""generate-boot-assets.py — NoctraOS boot-chain artwork.

Renders every image the boot screens need from configs/theme/palette.json and
the Noctra "N" mark (assets/icons/noctraos-start.svg geometry):

  plymouth/noctraos/   boot throbber (mark + wordmark + blinking cursor),
                       password-prompt pieces
  grub/noctraos/       logo, square 9-slice pixmaps, monospace .pf2 fonts
  isolinux/splash.png  640x480 background for the BIOS menu

Outputs are committed, so building an ISO needs none of this. Re-run after
changing the palette or the mark:

  python3 generate-boot-assets.py --font /path/to/JetBrainsMono-Regular.ttf \
      --bold-font /path/to/JetBrainsMono-Bold.ttf

Requires pillow; grub-mkfont (package grub-common) for the .pf2 fonts.
"""
import argparse
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
PALETTE = json.loads((HERE.parent.parent / "configs/theme/palette.json").read_text())["colors"]

# The Noctra "N" mark, in the 64x64 box of assets/icons/noctraos-start.svg.
MARK = [
    [(8, 8), (20, 8), (44, 40), (44, 22), (56, 15), (56, 56), (44, 56), (20, 24), (20, 56), (8, 56)],
    [(44, 13), (56, 6), (56, 12), (44, 19)],
]
FRAMES = 30  # two-step plays at 30 fps: 15 frames cursor on, 15 off => 1 Hz blink


def rgb(name):
    return tuple(int(PALETTE[name][i:i + 2], 16) for i in (1, 3, 5))


def mark(size, colour):
    """The N mark on a transparent square canvas, drawn 4x and downsampled."""
    scale = 4
    big = Image.new("RGBA", (size * scale,) * 2, (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    for poly in MARK:
        draw.polygon([(x * size * scale / 64, y * size * scale / 64) for x, y in poly], fill=colour)
    return big.resize((size, size), Image.LANCZOS)


def lockup(font_path, cursor_on, height=120, mark_px=88, text_px=44):
    """Mark + 'noctraos' + block cursor, centred on a transparent canvas."""
    font = ImageFont.truetype(font_path, text_px)
    text = "noctraos"
    text_w = int(font.getlength(text))
    cursor_w, cursor_h, gap = int(text_px * 0.55), int(text_px * 0.95), 28
    width = mark_px + gap + text_w + 10 + cursor_w
    canvas = Image.new("RGBA", (width + 40, height), (0, 0, 0, 0))
    canvas.alpha_composite(mark(mark_px, rgb("accent") + (255,)), (20, (height - mark_px) // 2))
    draw = ImageDraw.Draw(canvas)
    text_x = 20 + mark_px + gap
    baseline_y = height // 2 + int(text_px * 0.36)
    draw.text((text_x, baseline_y), text, font=font, fill=rgb("foreground") + (255,), anchor="ls")
    if cursor_on:
        cx = text_x + text_w + 10
        draw.rectangle([cx, baseline_y - cursor_h + 4, cx + cursor_w, baseline_y + 4], fill=rgb("accent") + (255,))
    return canvas


def box(w, h, fill, border=None):
    image = Image.new("RGBA", (w, h), fill + (255,))
    if border:
        ImageDraw.Draw(image).rectangle([0, 0, w - 1, h - 1], outline=border + (255,))
    return image


def plymouth(out, font_path):
    out.mkdir(parents=True, exist_ok=True)
    for index in range(FRAMES):
        lockup(font_path, index < FRAMES // 2).save(out / f"throbber-{index:02d}.png")
    box(305, 34, rgb("raised"), rgb("border")).save(out / "entry.png")
    box(10, 10, rgb("accent")).save(out / "bullet.png")
    # lock: square padlock body + shackle
    lock = Image.new("RGBA", (35, 34), (0, 0, 0, 0))
    draw = ImageDraw.Draw(lock)
    draw.rectangle([6, 15, 28, 31], fill=rgb("accent") + (255,))
    draw.rectangle([10, 3, 24, 15], outline=rgb("accent") + (255,), width=3)
    lock.save(out / "lock.png")
    # capslock: arrow over a bar
    caps = Image.new("RGBA", (35, 34), (0, 0, 0, 0))
    draw = ImageDraw.Draw(caps)
    draw.polygon([(17, 3), (30, 18), (22, 18), (22, 26), (12, 26), (12, 18), (4, 18)], fill=rgb("foreground") + (255,))
    draw.rectangle([12, 29, 22, 32], fill=rgb("foreground") + (255,))
    caps.save(out / "capslock.png")
    # keyboard: outlined key grid
    keys = Image.new("RGBA", (28, 12), (0, 0, 0, 0))
    draw = ImageDraw.Draw(keys)
    draw.rectangle([0, 0, 27, 11], outline=rgb("muted") + (255,))
    for row, y in enumerate((3, 7)):
        for x in range(3, 25, 4):
            draw.point((x, y), fill=rgb("muted") + (255,))
    keys.save(out / "keyboard.png")


def grub(out, font_path, bold_path, make_fonts):
    out.mkdir(parents=True, exist_ok=True)
    lockup(font_path, True, height=112, mark_px=80, text_px=40).save(out / "logo.png")
    bg, border, panel, accent = rgb("background"), rgb("border"), rgb("panel"), rgb("accent")

    def solid(name, colour, size=(8, 8)):
        Image.new("RGBA", size, colour + (255,)).save(out / name)

    # menu frame: 1 px border around the panel colour (9-slice)
    for part, size, colour in [("c", (8, 8), panel), ("n", (8, 1), border), ("s", (8, 1), border),
                               ("w", (1, 8), border), ("e", (1, 8), border), ("nw", (1, 1), border),
                               ("ne", (1, 1), border), ("sw", (1, 1), border), ("se", (1, 1), border)]:
        solid(f"menu_{part}.png", colour, size)
    # selected row: flat accent bar, dark text on top
    solid("select_c.png", accent)
    if make_fonts:
        for source, size, label in [(font_path, 16, "regular16"), (font_path, 13, "regular13"), (bold_path, 22, "bold22")]:
            subprocess.run(["grub-mkfont", "-s", str(size), "-o", str(out / f"jetbrains-{label}.pf2"), source], check=True)


def isolinux(out, font_path):
    out.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (640, 480), rgb("background"))
    canvas = lockup(font_path, True, height=64, mark_px=48, text_px=26)
    image.paste(canvas, (22, 18), canvas)
    ImageDraw.Draw(image).line([(30, 82), (610, 82)], fill=rgb("border"), width=1)
    image.save(out / "splash.png")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", required=True, help="JetBrains Mono Regular .ttf")
    parser.add_argument("--bold-font", required=True, help="JetBrains Mono Bold .ttf")
    parser.add_argument("--no-pf2", action="store_true", help="skip grub-mkfont")
    args = parser.parse_args()
    plymouth(HERE / "plymouth/noctraos", args.bold_font)
    grub(HERE / "grub/noctraos", args.font, args.bold_font, not args.no_pf2)
    isolinux(HERE / "isolinux", args.bold_font)


if __name__ == "__main__":
    main()
