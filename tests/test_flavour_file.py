"""The flavour file (docs/flavours.md): noctraos_flavour in install/lib.sh, how install.sh and module 07 use it, and the
migrations that only apply to the zorin flavour. Nothing here touches the real /etc."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "install/lib.sh"


def flavour(file_text=None, env_value=None):
    """Run noctraos_flavour with a temporary flavour file (absent when file_text is None)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "flavour"
        if file_text is not None:
            path.write_text(file_text)
        env = {k: v for k, v in os.environ.items() if k != "NOCTRAOS_FLAVOUR"}
        env.update(NOCTRAOS_FLAVOUR_FILE=str(path), REPO_ROOT=str(ROOT), TARGET_USER="tester", TARGET_UID="1000",
                   TARGET_HOME=tmp)
        if env_value is not None:
            env["NOCTRAOS_FLAVOUR"] = env_value
        return subprocess.run(["bash", "-c", f'source "{LIB}"; noctraos_flavour'], capture_output=True, text=True, env=env)


class FlavourLookupTests(unittest.TestCase):
    def test_no_file_and_no_variable_is_zorin(self):
        r = flavour()
        self.assertEqual((r.returncode, r.stdout), (0, "zorin\n"))

    def test_the_file_names_the_flavour(self):
        r = flavour("kubuntu\n")
        self.assertEqual((r.returncode, r.stdout), (0, "kubuntu\n"))

    def test_the_variable_names_it_when_there_is_no_file(self):
        r = flavour(env_value="kubuntu")
        self.assertEqual((r.returncode, r.stdout), (0, "kubuntu\n"))

    def test_a_variable_that_agrees_with_the_file_is_fine(self):
        self.assertEqual(flavour("zorin\n", "zorin").stdout, "zorin\n")

    def test_a_variable_that_contradicts_the_file_is_refused(self):
        r = flavour("zorin\n", "kubuntu")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("this machine is the zorin flavour", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_an_unknown_flavour_is_refused(self):
        for file_text, env_value in (("fedora\n", None), (None, "gnome")):
            r = flavour(file_text, env_value)
            self.assertNotEqual(r.returncode, 0, (file_text, env_value))
            self.assertIn("unknown NoctraOS flavour", r.stderr)


class InstallerWiringTests(unittest.TestCase):
    def test_install_sh_resolves_and_exports_the_flavour_before_any_module(self):
        text = (ROOT / "install.sh").read_text()
        resolve = text.index('NOCTRAOS_FLAVOUR="$(noctraos_flavour)"')
        self.assertLess(resolve, text.index("run_module 01b_vm_guest.sh"))
        self.assertLess(resolve, text.index('run_module "$ONLY"'))
        self.assertIn("export NOCTRAOS_FLAVOUR NOCTRAOS_FLAVOUR_GIVEN", text)

    def test_module_07_records_the_flavour_only_when_it_was_given_and_never_overwrites(self):
        text = (ROOT / "install/07_persistence.sh").read_text()
        self.assertIn('if [ ! -f /etc/noctraos/flavour ] && [ -n "${NOCTRAOS_FLAVOUR_GIVEN:-}" ]; then', text)


class ZorinOnlyMigrationTests(unittest.TestCase):
    def run_migration(self, name, flavour_value, extra_env=None):
        env = {**os.environ, "NOCTRAOS_FLAVOUR": flavour_value, **(extra_env or {})}
        return subprocess.run(["bash", str(ROOT / "migrations" / name)], capture_output=True, text=True, env=env)

    def test_the_dock_pin_is_not_applied_and_counts_as_done_off_zorin(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            # a gsettings that would fail the way it does without the GNOME schema; it must not even be called
            (bin_dir / "gsettings").write_text("#!/bin/sh\necho called >> \"$0.log\"\nexit 1\n")
            (bin_dir / "gsettings").chmod(0o755)
            r = self.run_migration("user/0001_pin_control_panel.sh", "kubuntu",
                                   {"PATH": f"{bin_dir}:{os.environ['PATH']}"})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("NOT APPLIED on the kubuntu flavour", r.stdout)
            self.assertFalse((bin_dir / "gsettings.log").exists())

    def test_the_ownership_repair_is_not_applied_off_zorin(self):
        r = self.run_migration("system/0001_restore_ownership.sh", "kubuntu", {"NOCTRAOS_SNAPSHOT": str(ROOT)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("NOT APPLIED on the kubuntu flavour", r.stdout)


if __name__ == "__main__":
    unittest.main()
