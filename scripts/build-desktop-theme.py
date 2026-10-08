#!/usr/bin/env python3
"""Compose an installed Zorin theme and our overrides, writing only changes."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


# border-radius, border-top-left-radius and the -gtk-outline-* variants, with their values.
RADIUS_DECLARATION = re.compile(r"(?:border|-gtk-outline)(?:-(?:top|bottom)-(?:left|right))?-radius\s*:[^;]+;")


def load_remap(remap_path, palette_path):
    """Resolve a recolour map to literal values.

    {"hex": {"#rrggbb": role | {"color": role, "default": role}}, "rgb": {triple: triple}}
    where role is a palette.json colour name and the object form picks the text
    colour for the `color` property and the default for every other property.
    """
    remap = json.loads(Path(remap_path).read_text())
    colors = json.loads(Path(palette_path).read_text())["colors"]
    hexes = {}
    for key, value in remap["hex"].items():
        if isinstance(value, str):
            value = {"default": value}
        hexes[key.lower()] = {name: colors[role] for name, role in value.items()}
    return hexes, remap["rgb"]


def recolor(css, remap):
    hexes, rgbs = remap

    def declaration(match):
        prop, value = match[1], match[2]

        def swap(color):
            choice = hexes.get(color[0].lower())
            if not choice:
                return color[0]
            return choice.get("color" if prop.strip() == "color" else "default") or choice["default"]
        return f"{prop}:{re.sub(r'#[0-9a-fA-F]{6}' + chr(92) + 'b', swap, value)};"
    css = re.sub(r"([\w-]+)\s*:([^;{}]*#[0-9a-fA-F]{6}\b[^;{}]*);", declaration, css)

    def named_color(match):
        # @define-color NAME VALUE; text-like names take the text variant.
        name, value = match[1], match[2]
        role = "color" if re.search(r"fg|text|title", name) else "default"

        def swap(color):
            choice = hexes.get(color[0].lower())
            return (choice.get(role) or choice["default"]) if choice else color[0]
        return f"@define-color {name} {re.sub(r'#[0-9a-fA-F]{6}' + chr(92) + 'b', swap, value)};"
    css = re.sub(r"@define-color\s+(\S+)\s+([^;]*#[0-9a-fA-F]{6}\b[^;]*);", named_color, css)
    for old, new in rgbs.items():
        css = re.sub(r"rgba\(\s*" + re.sub(r",\s*", r",\\s*", re.escape(old).replace(r"\ ", " ")) + r"\s*,",
                     f"rgba({new},", css)
    return css


def compose(base, output, overlay, css_name, radius=4, remap=None):
    if not (base / css_name).is_file():
        raise FileNotFoundError(f"Base stylesheet missing: {base / css_name}")
    if base.resolve() == output.resolve():
        raise ValueError("The base theme and custom theme must be different directories")
    if not 0 <= radius <= 16:
        raise ValueError("The corner radius must be between 0 and 16 px")
    with tempfile.TemporaryDirectory(prefix="noctraos-theme-") as tmp:
        stage = Path(tmp) / "theme"
        shutil.copytree(base, stage)
        # Clamp each px radius, including multi-value declarations and the per-corner
        # longhands (Zorin rounds a headerbar with `border-top-left-radius`). Keep small radii.
        for css_path in stage.glob("*.css"):
            css = re.sub(
                RADIUS_DECLARATION,
                lambda match: re.sub(r"\b(\d+)px\b",
                                     lambda value: f"{min(int(value[1]), radius)}px", match[0]),
                css_path.read_text(),
            )
            if remap and css_path.name in {css_name, "gtk-dark.css"}:
                css = recolor(css, remap)
            if css_path.name in {css_name, "gtk-dark.css"}:
                css += "\n" + overlay.read_text()
            css_path.write_text(css)
        for source in stage.rglob("*"):
            if not source.is_file():
                continue
            target = output / source.relative_to(stage)
            data = source.read_bytes()
            if not target.is_symlink() and target.is_file() and target.read_bytes() == data:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # Replace the file atomically. Never follow a copied theme symlink
            # back into the base theme, or expose partially written CSS.
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp_file:
                temporary = Path(tmp_file.name)
                try:
                    tmp_file.write(data)
                    tmp_file.flush()
                    temporary.chmod(0o644)
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
            print(f"Updated {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--css-name", required=True)
    parser.add_argument("--radius", type=int, default=4)
    parser.add_argument("--remap", type=Path, help="recolour map applied to the base stylesheet")
    parser.add_argument("--palette", type=Path, help="palette.json (required with --remap)")
    args = parser.parse_args()
    remap = load_remap(args.remap, args.palette) if args.remap else None
    compose(args.base, args.output, args.overlay, args.css_name, args.radius, remap)


if __name__ == "__main__":
    main()
