#!/usr/bin/env python3
"""Compose an installed Zorin theme and our overrides, writing only changes."""
import argparse
import os
from pathlib import Path
import re
import shutil
import tempfile


def compose(base, output, overlay, css_name, radius=4):
    if not (base / css_name).is_file():
        raise FileNotFoundError(f"Base stylesheet missing: {base / css_name}")
    if base.resolve() == output.resolve():
        raise ValueError("The base theme and custom theme must be different directories")
    if not 0 <= radius <= 16:
        raise ValueError("The corner radius must be between 0 and 16 px")
    with tempfile.TemporaryDirectory(prefix="zorin-ai-theme-") as tmp:
        stage = Path(tmp) / "theme"
        shutil.copytree(base, stage)
        # Clamp each px radius, including multi-value declarations. Keep small radii.
        for css_path in stage.glob("*.css"):
            css = re.sub(
                r"border-radius\s*:[^;]+;",
                lambda match: re.sub(r"\b(\d+)px\b",
                                     lambda value: f"{min(int(value[1]), radius)}px", match[0]),
                css_path.read_text(),
            )
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
    args = parser.parse_args()
    compose(args.base, args.output, args.overlay, args.css_name, args.radius)


if __name__ == "__main__":
    main()
