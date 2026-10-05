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

    def test_recolor_handles_named_colors_by_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            palette = root / "palette.json"
            palette.write_text('{"colors": {"accent": "#e68e0d", "foreground": "#bebebe", "background": "#121212"}}')
            remap = root / "remap.json"
            remap.write_text('{"hex": {"#d8c4f1": {"color": "foreground", "default": "accent"}, '
                             '"#28232d": "background"}, "rgb": {}}')
            css = MODULE.recolor(
                "@define-color window_fg_color #d8c4f1;\n@define-color accent_bg_color #d8c4f1;\n"
                "@define-color window_bg_color #28232d;\n", MODULE.load_remap(remap, palette))
            self.assertIn("window_fg_color #bebebe;", css)    # text-like name keeps a readable colour
            self.assertIn("accent_bg_color #e68e0d;", css)    # everything else takes the accent
            self.assertIn("window_bg_color #121212;", css)


class PasswordStoreTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "seed_password_store", Path(__file__).resolve().parents[1] / "scripts/seed-password-store.py")
        self.seed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.seed)

    def test_creates_both_files_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.assertTrue(self.seed.chromium_flags(home) and self.seed.vscode_argv(home))
            self.assertFalse(self.seed.chromium_flags(home) or self.seed.vscode_argv(home))
            flags = (home / ".var/app/org.chromium.Chromium/config/chromium-flags.conf").read_text()
            self.assertEqual(flags, "--password-store=basic\n")

    def test_keeps_existing_flags_and_comments(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            conf = home / ".var/app/org.chromium.Chromium/config/chromium-flags.conf"
            conf.parent.mkdir(parents=True)
            conf.write_text("--enable-features=Foo\n")
            argv = home / ".vscode/argv.json"
            argv.parent.mkdir(parents=True)
            argv.write_text("// header comment\n{\n\t// note\n\t\"enable-crash-reporter\": true\n}\n")
            self.seed.chromium_flags(home)
            self.seed.vscode_argv(home)
            self.assertEqual(conf.read_text(), "--enable-features=Foo\n--password-store=basic\n")
            text = argv.read_text()
            self.assertIn("// header comment", text)
            self.assertIn('"password-store": "basic",', text)
            self.assertIn('"enable-crash-reporter": true', text)

    def keyring_file(self, home, content):
        path = home / ".local/share/keyrings/login.keyring"
        path.parent.mkdir(parents=True)
        path.write_bytes(content)
        return path

    def test_keyring_is_created_unencrypted_and_made_the_default(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.assertTrue(self.seed.login_keyring(home))
            keyring = home / ".local/share/keyrings/login.keyring"
            self.assertTrue(keyring.read_text().startswith("[keyring]\n"))
            self.assertEqual((home / ".local/share/keyrings/default").read_text(), "login")
            self.assertEqual(keyring.stat().st_mode & 0o777, 0o600)
            self.assertEqual(keyring.parent.stat().st_mode & 0o777, 0o700)
            self.assertFalse(self.seed.login_keyring(home))        # idempotent

    def test_empty_encrypted_keyring_is_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            empty = self.seed.ENCRYPTED_MAGIC + b"\x00" * 90         # about the size of an empty one
            keyring = self.keyring_file(home, empty)
            self.assertTrue(self.seed.login_keyring(home))
            self.assertTrue(keyring.read_bytes().startswith(b"[keyring]"))

    def test_keyring_holding_secrets_is_never_touched(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            full = self.seed.ENCRYPTED_MAGIC + b"\x01" * 400
            keyring = self.keyring_file(home, full)
            self.assertFalse(self.seed.login_keyring(home))
            self.assertEqual(keyring.read_bytes(), full)
            self.assertFalse((home / ".local/share/keyrings/default").exists())

    def test_unknown_keyring_format_is_never_touched(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            keyring = self.keyring_file(home, b"something else entirely")
            self.assertFalse(self.seed.login_keyring(home))
            self.assertEqual(keyring.read_bytes(), b"something else entirely")

    def test_existing_unencrypted_keyring_is_kept_and_made_default(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            body = b"[keyring]\ndisplay-name=Login\n\n[1]\nitem-type=0\nsecret=keep-me\n"
            keyring = self.keyring_file(home, body)
            self.assertTrue(self.seed.login_keyring(home))          # default file was missing
            self.assertEqual(keyring.read_bytes(), body)             # contents untouched
            self.assertEqual((home / ".local/share/keyrings/default").read_text(), "login")
            self.assertFalse(self.seed.login_keyring(home))

    def test_an_empty_argv_json_is_treated_as_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            argv = home / ".vscode/argv.json"
            argv.parent.mkdir(parents=True)
            argv.write_text("")
            self.assertTrue(self.seed.vscode_argv(home))
            self.assertIn('"password-store": "basic"', argv.read_text())
            self.assertFalse(self.seed.vscode_argv(home))


if __name__ == "__main__":
    unittest.main()
