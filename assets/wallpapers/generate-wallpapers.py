#!/usr/bin/env python3
"""generate-wallpapers.py — NoctraOS wallpaper set: striking polygonal.

Renders low-poly landscape wallpapers: faceted mountain layers with vivid
palette-mapped elevation shading, flat sun discs, aurora ribbons and star
fields over saturated gradient skies. Deterministic (seeded) so builds are
reproducible.

Usage:
  python3 generate-wallpapers.py [--outdir DIR] [--width W] [--height H]
                                 [--seed N] [--only NAME]

Scenes default to 3840x2160 JPEG (quality 92). Requires: pillow, numpy.
"""
import argparse
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 3840, 2160
COLS = 56  # facet columns — resolution-independent look


# ---------------------------------------------------------------- noise utils
def value_noise_1d(n, rng, octaves=6, persistence=0.5, base_freq=4):
    """Fractal 1D value noise in [0, 1], length n, smooth (cubic) interp."""
    total = np.zeros(n)
    amp, freq = 1.0, base_freq
    norm = 0.0
    for _ in range(octaves):
        pts = rng.random(freq + 2) * 2 - 1
        x = np.linspace(0, freq, n)
        idx = np.clip(x.astype(int), 0, freq)
        frac = x - idx
        smooth = frac * frac * (3 - 2 * frac)
        vals = pts[idx] * (1 - smooth) + pts[idx + 1] * smooth
        total += vals * amp
        norm += amp
        amp *= persistence
        freq *= 2
    total /= norm
    return (total - total.min()) / (total.max() - total.min() + 1e-9)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lerp_rgb(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def palette_at(stops, t):
    """stops: list of (pos 0..1, (r,g,b)); t clamped to [0,1]."""
    t = min(max(t, 0.0), 1.0)
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if t <= p1:
            span = (p1 - p0) or 1.0
            return lerp_rgb(c0, c1, (t - p0) / span)
    return stops[-1][1]


def sky_gradient(w, h, stops):
    cols = np.zeros((h, w, 3), dtype=np.float64)
    ys = np.linspace(0, 1, h)
    for ch in range(3):
        vals = np.interp(ys, [p for p, _ in stops], [c[ch] for _, c in stops])
        cols[:, :, ch] = vals[:, None]
    return Image.fromarray(cols.astype(np.uint8))


# ---------------------------------------------------------------- scene parts
def draw_stars(img, rng, density=110, max_y=0.55):
    arr = np.asarray(img).copy()
    h, w, _ = arr.shape
    count = int(w * h / 1e6 * density)
    xs = (rng.random(count) * w).astype(int)
    ys = (rng.random(count) * h * max_y).astype(int)
    bright = rng.random(count)
    for x, y, b in zip(xs, ys, bright):
        v = 120 + int(b * 135)
        arr[y, x] = np.maximum(arr[y, x], v)
    out = Image.fromarray(arr)
    return out


def draw_sun(img, cx, cy, r, color, glow=0.75, glow_color=None):
    """Flat disc with a soft radial glow."""
    gc = glow_color or color
    glow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    gd.ellipse([cx - r * 3.2, cy - r * 3.2, cx + r * 3.2, cy + r * 3.2],
               fill=gc + (int(120 * glow),))
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(r * 1.1))
    img = Image.alpha_composite(img.convert("RGBA"), glow_layer)
    disc = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dd = ImageDraw.Draw(disc)
    dd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (255,))
    return Image.alpha_composite(img, disc).convert("RGB")


def draw_aurora(img, rng, bands, seed_phase=0.0):
    """Wavy glowing ribbons. bands: list of (center_y, thickness, color)."""
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    for i, (cy, th, color) in enumerate(bands):
        band = Image.new("RGBA", img.size, (0, 0, 0, 0))
        bd = ImageDraw.Draw(band)
        n = value_noise_1d(w // 8, rng, octaves=4, base_freq=3)
        xs = np.linspace(0, w, w // 8)
        wave = cy * h + (n - 0.5) * h * 0.10
        top = wave - th * h / 2
        bot = wave + th * h / 2
        pts = [(int(x), int(y)) for x, y in zip(xs, top)]
        pts += [(int(x), int(y)) for x, y in zip(xs[::-1], bot[::-1])]
        alpha = 120 - i * 25
        bd.polygon(pts, fill=color + (alpha,))
        band = band.filter(ImageFilter.GaussianBlur(h * 0.02))
        overlay = Image.alpha_composite(overlay, band)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def facet_layer(img, rng, base_y, amp, elev_stops, light_k=0.55, cols=COLS,
                rows=6, jitter=0.12):
    """One faceted mountain silhouette — a real triangulated mesh.

    The ridge line y(x) = base_y*h - e(x)*amp*h (e in [0,1]) forms the top
    vertex row; `rows` more rows interpolate down to the canvas bottom. Each
    grid cell splits into two triangles with alternating diagonals, colored
    by mean vertex elevation through `elev_stops`, slope-lit from the left.
    Interior vertices share an x-jitter so columns look organic, not striped.
    """
    w, h = img.size
    d = ImageDraw.Draw(img)
    e = value_noise_1d(cols + 1, rng, octaves=5, persistence=0.6,
                       base_freq=3 + rng.integers(0, 3))
    e = (e - e.min()) / (e.max() - e.min() + 1e-9)
    cell = w / cols

    # vertex grid: (rows+1) x (cols+1), shared x-jitter per column
    xj = np.zeros(cols + 1)
    xj[1:-1] = (rng.random(cols - 1) - 0.5) * 0.5 * cell
    vx = np.array([i * cell + xj[i] for i in range(cols + 1)])
    vy = np.zeros((rows + 1, cols + 1))
    vt = np.zeros((rows + 1, cols + 1))
    vy[0] = [base_y * h - float(ei) * amp * h for ei in e]
    vt[0] = e
    fade = 0.92  # elevation falloff per row toward the valley floor
    for r in range(1, rows + 1):
        f = r / rows
        vy[r] = vy[0] + (h - vy[0]) * f
        vt[r] = e * max(0.0, 1.0 - f * fade * 1.05)

    for i in range(cols):
        for r in range(rows):
            quad = [(vx[i], vy[r, i]), (vx[i + 1], vy[r, i + 1]),
                    (vx[i + 1], vy[r + 1, i + 1]), (vx[i], vy[r + 1, i])]
            vidx = [(r, i), (r, i + 1), (r + 1, i + 1), (r + 1, i)]
            if (i + r) % 2 == 0:
                tris = ((0, 1, 2), (0, 2, 3))
            else:
                tris = ((0, 1, 3), (1, 2, 3))
            for t_idx in tris:
                pts = [quad[k] for k in t_idx]
                t_avg = sum(vt[vidx[k]] for k in t_idx) / 3.0
                base = np.array(palette_at(elev_stops, t_avg), dtype=np.float64)
                dy = quad[1][1] - quad[0][1]  # + if right vertex is lower
                b = 1.0 + np.clip(dy / (cell * 1.2), -1, 1) * light_k
                b *= 1.0 + (rng.random() - 0.5) * 2 * jitter
                col = tuple(int(np.clip(c * b, 0, 255)) for c in base)
                d.polygon(pts, fill=col)

    # crisp highlight along the ridge crest
    for i in range(cols):
        d.line([(vx[i], vy[0, i]), (vx[i + 1], vy[0, i + 1])],
               fill=palette_at(elev_stops, min(e[i] + 0.2, 1.0)), width=3)
    return img


def shift_palette(stops, toward, t):
    """Atmospheric shift: blend every stop toward `toward` by fraction t."""
    return [(p, lerp_rgb(c, toward, t)) for p, c in stops]


def finish(img, vignette=0.12, grain=0.006):
    arr = np.asarray(img).astype(np.float64)
    h, w, _ = arr.shape
    rng = np.random.default_rng(77)
    arr += rng.normal(0, grain * 255, (h, w, 1))
    yy, xx = np.ogrid[:h, :w]
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    arr *= (1 - vignette * np.clip(d - 0.55, 0, 1) ** 1.5)[:, :, None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


# ------------------------------------------------------------------- scenes
def scene_sunset_peaks(w, h, seed):
    rng = np.random.default_rng(seed)
    img = sky_gradient(w, h, [(0.0, hex_rgb("0d001a")), (0.36, hex_rgb("3d0a5c")),
                              (0.60, hex_rgb("7a1fff")), (0.80, hex_rgb("ff2d95")),
                              (1.0, hex_rgb("ff5fd2"))])
    img = draw_sun(img, w * 0.62, h * 0.60, int(h * 0.13),
                   hex_rgb("ffb3e6"), glow_color=hex_rgb("ff2d95"))
    horizon = hex_rgb("ff5fd2")
    facet_layer(img, rng, base_y=0.74, amp=0.16, cols=COLS,
                elev_stops=shift_palette(
                    [(0.0, hex_rgb("2a0a3f")), (0.55, hex_rgb("6b1fc9")),
                     (1.0, hex_rgb("ff2d95"))], horizon, 0.40))
    facet_layer(img, rng, base_y=0.86, amp=0.20, cols=COLS,
                elev_stops=shift_palette(
                    [(0.0, hex_rgb("0a0014")), (0.55, hex_rgb("3d0a5c")),
                     (0.85, hex_rgb("a124ff")), (1.0, hex_rgb("ff5fd2"))],
                    horizon, 0.15))
    facet_layer(img, rng, base_y=1.04, amp=0.24, cols=COLS,
                elev_stops=[(0.0, hex_rgb("05000a")), (0.5, hex_rgb("1f0530")),
                            (0.8, hex_rgb("7a1fff")), (1.0, hex_rgb("ff2d95"))])
    return finish(img)


def scene_neon_rift(w, h, seed):
    rng = np.random.default_rng(seed)
    img = sky_gradient(w, h, [(0.0, hex_rgb("02010f")), (0.42, hex_rgb("14042e")),
                              (0.66, hex_rgb("3d0a5c")), (0.85, hex_rgb("8a1fff")),
                              (1.0, hex_rgb("ff2d95"))])
    img = draw_stars(img, rng, density=90, max_y=0.5)
    img = draw_sun(img, w * 0.30, h * 0.58, int(h * 0.10),
                   hex_rgb("ff2d95"), glow_color=hex_rgb("a124ff"))
    green = hex_rgb("39ff88")
    facet_layer(img, rng, base_y=0.72, amp=0.15, cols=COLS,
                elev_stops=shift_palette(
                    [(0.0, hex_rgb("0a0218")), (0.6, hex_rgb("3d0a5c")),
                     (1.0, hex_rgb("a124ff"))], green, 0.30))
    facet_layer(img, rng, base_y=0.90, amp=0.22, cols=COLS,
                elev_stops=[(0.0, hex_rgb("04010a")), (0.5, hex_rgb("1f0530")),
                            (0.85, hex_rgb("7a1fff")), (1.0, hex_rgb("39ff88"))])
    return finish(img)


def scene_aurora_peaks(w, h, seed):
    rng = np.random.default_rng(seed)
    img = sky_gradient(w, h, [(0.0, hex_rgb("030614")), (0.55, hex_rgb("081226")),
                              (1.0, hex_rgb("0d1b33"))])
    img = draw_stars(img, rng, density=150, max_y=0.75)
    img = draw_aurora(img, rng, bands=[
        (0.30, 0.10, hex_rgb("2bd97f")),
        (0.42, 0.07, hex_rgb("27c8d8")),
        (0.22, 0.05, hex_rgb("8f4fd1")),
    ])
    snow = hex_rgb("dff5ff")
    facet_layer(img, rng, base_y=0.76, amp=0.14, cols=COLS,
                elev_stops=shift_palette(
                    [(0.0, hex_rgb("10233d")), (0.6, hex_rgb("1d3d5f")),
                     (1.0, hex_rgb("4a7ba6"))], snow, 0.30))
    facet_layer(img, rng, base_y=0.98, amp=0.22, cols=COLS,
                elev_stops=[(0.0, hex_rgb("060d1a")), (0.5, hex_rgb("12283f")),
                            (0.8, hex_rgb("27506e")), (1.0, hex_rgb("bfe8ff"))])
    return finish(img, vignette=0.15)


def scene_crimson_dunes(w, h, seed):
    rng = np.random.default_rng(seed)
    img = sky_gradient(w, h, [(0.0, hex_rgb("0f0018")), (0.45, hex_rgb("4a0a3c")),
                              (0.70, hex_rgb("c02472")), (0.88, hex_rgb("ff2d95")),
                              (1.0, hex_rgb("ff7ae0"))])
    img = draw_sun(img, w * 0.72, h * 0.66, int(h * 0.09),
                   hex_rgb("ffffff"), glow_color=hex_rgb("ff2d95"))
    facet_layer(img, rng, base_y=0.80, amp=0.10, cols=COLS, light_k=0.35,
                elev_stops=shift_palette(
                    [(0.0, hex_rgb("3d0a3c")), (1.0, hex_rgb("c02472"))],
                    hex_rgb("ff2d95"), 0.35))
    facet_layer(img, rng, base_y=0.98, amp=0.16, cols=COLS, light_k=0.35,
                elev_stops=[(0.0, hex_rgb("0a0014")), (0.6, hex_rgb("2a0a3f")),
                            (1.0, hex_rgb("a1246e"))])
    return finish(img, vignette=0.14)


def scene_glacier_facet(w, h, seed):
    rng = np.random.default_rng(seed)
    img = sky_gradient(w, h, [(0.0, hex_rgb("0a0118")), (0.45, hex_rgb("2a0a4a")),
                              (0.75, hex_rgb("5c1fa8")), (1.0, hex_rgb("9a4bff"))])
    img = draw_sun(img, w * 0.40, h * 0.34, int(h * 0.08),
                   hex_rgb("f2eaff"), glow_color=hex_rgb("a24bff"))
    ice = hex_rgb("e8d9ff")
    facet_layer(img, rng, base_y=0.74, amp=0.14, cols=COLS,
                elev_stops=shift_palette(
                    [(0.0, hex_rgb("1a0530")), (0.6, hex_rgb("4a1a8c")),
                     (1.0, hex_rgb("a24bff"))], ice, 0.25))
    facet_layer(img, rng, base_y=0.96, amp=0.20, cols=COLS,
                elev_stops=[(0.0, hex_rgb("08010f")), (0.5, hex_rgb("2a0a4a")),
                            (0.85, hex_rgb("7a3ff2")), (1.0, hex_rgb("e8d9ff"))])
    return finish(img)


SCENES = {
    "sunset-peaks": scene_sunset_peaks,
    "neon-rift": scene_neon_rift,
    "aurora-peaks": scene_aurora_peaks,
    "crimson-dunes": scene_crimson_dunes,
    "glacier-facet": scene_glacier_facet,
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outdir", default=os.path.dirname(os.path.abspath(__file__)))
    p.add_argument("--width", type=int, default=W)
    p.add_argument("--height", type=int, default=H)
    p.add_argument("--seed", type=int, default=20260925)
    p.add_argument("--only", choices=sorted(SCENES))
    args = p.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    names = [args.only] if args.only else sorted(SCENES)
    for name in names:
        out = os.path.join(args.outdir, f"noctraos-{name}-{args.height}p.jpg")
        img = SCENES[name](args.width, args.height, args.seed)
        img.save(out, "JPEG", quality=92, optimize=True, progressive=True)
        print(f"{out}  ({os.path.getsize(out) // 1024} KiB)")


if __name__ == "__main__":
    main()
