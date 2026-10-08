"""The ISO bakes the Shell extensions in so the first session already has Super+Space and the
Start panel (GNOME Shell only scans for extensions when it starts)."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BAKE = ROOT / "iso/bake-shell.sh"


def bake(root):
    return subprocess.run(["bash", "-c", f'source "{BAKE}"; bake_shell "{root}" "{ROOT}"'],
                          capture_output=True, text=True, env=os.environ)


@unittest.skipUnless(shutil.which("glib-compile-schemas"), "needs glib-compile-schemas")
class BakeShellTests(unittest.TestCase):
    def test_bakes_everything_module_09_installs_and_compiles_schemas(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = bake(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            extensions = root / "usr/share/gnome-shell/extensions"
            for source in (ROOT / "extensions").iterdir():
                for file in source.iterdir():
                    self.assertTrue((extensions / source.name / file.name).is_file(), file)
            for path in ("usr/local/bin/noctraos-search", "usr/local/bin/noctraos-weather",
                         "usr/local/share/noctraos/setup-branding.py",
                         "usr/local/share/noctraos/help/index.html",
                         "usr/local/share/noctraos-search/main.py",
                         "usr/share/glib-2.0/schemas/gschemas.compiled",
                         "etc/xdg/autostart/noctraos-search-setup.desktop",
                         "etc/xdg/autostart/noctraos-branding.desktop"):
                self.assertTrue((root / path).is_file(), path)
            self.assertTrue(os.access(root / "usr/local/bin/noctraos-search", os.X_OK))
            # The search extension's schema must be in the compiled cache (first-used is read at startup).
            compiled = (root / "usr/share/glib-2.0/schemas/gschemas.compiled").read_bytes()
            self.assertIn(b"org.gnome.shell.extensions.noctraos-search", compiled)
            self.assertIn(b"first-used", compiled)

    def test_a_missing_extension_fails_the_build(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns(".git", "site", "assets", "docs", "tests"))
            shutil.rmtree(repo / "extensions/noctraos-start@noctraos.local")
            result = subprocess.run(["bash", "-c", f'source "{BAKE}"; bake_shell "{directory}/root" "{repo}"'],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("noctraos-start@noctraos.local", result.stderr)


if __name__ == "__main__":
    unittest.main()
