"""Exercise theme composition against disposable files, never system themes."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build-desktop-theme.py"
SPEC = importlib.util.spec_from_file_location("desktop_theme", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DesktopThemeTests(unittest.TestCase):
    def test_compose_preserves_base_assets_and_is_a_noop_on_second_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, output = root / "base", root / "output"
            base.mkdir()
            original = "button { border-radius: 0px 12px 3px 999px; }\n"
            (base / "gtk.css").write_text(original)
            (base / "gtk-dark.css").write_text(original)
            (base / "assets").mkdir()
            (base / "assets/check.svg").write_bytes(b"test asset")
            overlay = root / "override.css"
            overlay.write_text("/* custom controls */\n")
            MODULE.compose(base, output, overlay, "gtk.css")
            self.assertEqual((base / "gtk.css").read_text(), original)
            self.assertEqual((output / "assets/check.svg").read_bytes(), b"test asset")
            self.assertIn("0px 4px 3px 4px", (output / "gtk.css").read_text())
            self.assertIn("custom controls", (output / "gtk-dark.css").read_text())
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in output.rglob("*") if p.is_file()}
            MODULE.compose(base, output, overlay, "gtk.css")
            self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before})
            overlay.write_text("/* updated controls */\n")
            MODULE.compose(base, output, overlay, "gtk.css")
            self.assertNotIn("custom controls", (output / "gtk.css").read_text())
            self.assertEqual((output / "gtk.css").read_text().count("updated controls"), 1)

    def test_missing_base_never_creates_a_partial_theme(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                MODULE.compose(root / "missing", root / "output", root / "overlay", "gtk.css")
            self.assertFalse((root / "output").exists())

    def test_refuses_to_modify_base_in_place(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "gtk.css").write_text("button {}")
            with self.assertRaises(ValueError):
                MODULE.compose(root, root, root / "overlay", "gtk.css")
            self.assertEqual((root / "gtk.css").read_text(), "button {}")

    def test_existing_output_symlink_does_not_patch_the_base_theme(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, output = root / "base", root / "output"
            base.mkdir()
            output.mkdir()
            (base / "gtk.css").write_text("button { border-radius: 12px; }")
            (output / "gtk.css").symlink_to(base / "gtk.css")
            overlay = root / "overlay.css"
            overlay.write_text("/* custom */")
            MODULE.compose(base, output, overlay, "gtk.css", radius=6)
            self.assertFalse((output / "gtk.css").is_symlink())
            self.assertIn("6px", (output / "gtk.css").read_text())
            self.assertIn("12px", (base / "gtk.css").read_text())


    def test_recolor_is_property_aware_and_leaves_unmapped_colors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            palette = root / "palette.json"
            palette.write_text('{"colors": {"accent": "#e68e0d", "foreground": "#bebebe", "panel": "#0d0d0d"}}')
            remap = root / "remap.json"
            remap.write_text('{"hex": {"#bde6fb": {"color": "foreground", "default": "accent"}, '
                             '"#161c1f": "panel"}, "rgb": {"189, 230, 251": "255, 255, 255"}}')
            css = MODULE.recolor(
                ".a { color: #BDE6FB; background-color: #bde6fb; border: 1px solid #bde6fb; "
                "x: rgba(189, 230, 251, 0.5); y: #fb7c7c; z: #161c1f; }",
                MODULE.load_remap(remap, palette))
            self.assertIn("color: #bebebe;", css)             # text keeps a readable colour
            self.assertIn("background-color: #e68e0d;", css)  # fills take the accent
            self.assertIn("1px solid #e68e0d", css)
            self.assertIn("rgba(255, 255, 255, 0.5)", css)
            self.assertIn("y: #fb7c7c", css)                  # unmapped colours are untouched
            self.assertIn("z: #0d0d0d", css)


if __name__ == "__main__":
    unittest.main()
