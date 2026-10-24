"""Kubuntu update catch-up, with fixed paths relocated only in disposable script copies.

The installer is a recorder, never the host installer. The real shortcut helper and
module09 run with temporary destinations and stubs; no host settings or network.
"""
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = ROOT / "migrations/system/0002_install_plasma_search.sh"
USER = ROOT / "migrations/user/0003_setup_plasma_search.sh"
SNAPSHOT = "/usr/local/share/noctraos/repo"
SETUP = "/usr/local/share/noctraos/plasma/apply-search.sh"
REQUIRED_FILES = (
    "usr/local/bin/noctraos-search",
    "usr/local/bin/noctraos-search-plasma",
    "usr/local/share/noctraos-search/browsers.py",
    "usr/local/share/noctraos-search/core.py",
    "usr/local/share/noctraos-search/krunner.py",
    "usr/local/share/noctraos-search/main.py",
    "usr/local/share/noctraos-search/preferences.py",
    "usr/share/krunner/dbusplugins/noctraos-search.desktop",
    "usr/share/dbus-1/services/org.kde.noctraos.search.service",
    "usr/share/glib-2.0/schemas/org.gnome.shell.extensions.noctraos-search.gschema.xml",
    "usr/share/glib-2.0/schemas/gschemas.compiled",
    "usr/local/share/noctraos/plasma/apply-search.sh",
    "etc/xdg/autostart/noctraos-plasma-search.desktop",
    "etc/systemd/user/noctraos-search-index.service",
    "etc/systemd/user/noctraos-search-index.timer",
)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.snapshot = self.tmp / "snapshot"
        self.snapshot.mkdir()
        self.root = self.tmp / "root"
        for name in REQUIRED_FILES:
            installed = self.root / name
            installed.parent.mkdir(parents=True, exist_ok=True)
            installed.write_text("installed fixture\n")
        self.setup = self.root / SETUP.lstrip("/")
        self.tool = self.root / "usr/local/bin/noctraos-search-plasma"
        self.write_tool(self.root / "usr/local/bin/noctraos-search", "exit 0\n")
        self.write_tool(self.tool, "exit 0\n")
        self.calls = self.tmp / "calls"
        self.marker = self.home / ".config/noctraos/plasma-search-v1"
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(self.home),
                    "NOCTRAOS_FLAVOUR": "kubuntu", "NOCTRAOS_USER": "desktop-user",
                    "DBUS_SESSION_BUS_ADDRESS": "unix:path=/test-session/bus",
                    "CALLS": str(self.calls), "EXPECTED_TOOL": str(self.tool)}
        self.write_tool(self.snapshot / "install.sh",
                        'printf "installer:%s:%s\\n" "$SUDO_USER" "$*" >> "$CALLS"\n'
                        'exit "${INSTALL_RC:-0}"\n')
        self.write_tool(self.setup, 'test "$NOCTRAOS_SEARCH_PLASMA" = "$EXPECTED_TOOL" || exit 99\n'
                        'printf "setup:%s:%s\\n" "$HOME" '
                        '"$DBUS_SESSION_BUS_ADDRESS" >> "$CALLS"\nexit "${SETUP_RC:-0}"\n')

    def write_tool(self, path, body):
        path.write_text("#!/bin/bash\n" + body)
        path.chmod(0o755)

    def run_migration(self, script, **extra):
        # Production has no caller-controlled path hooks. Relocate the constants in
        # a copy, including existence checks, so even root-run CI cannot touch /usr.
        copy = self.tmp / script.name
        copy.write_text(script.read_text().replace(SNAPSHOT, str(self.snapshot))
                        .replace("/usr/local/", str(self.root / "usr/local") + "/")
                        .replace("/usr/share/", str(self.root / "usr/share") + "/")
                        .replace("/etc/", str(self.root / "etc") + "/"))
        return subprocess.run(["/bin/bash", str(copy)], env={**self.env, **extra},
                              capture_output=True, text=True, timeout=10, check=False)

    def recorded(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_system_invokes_only_module09_for_the_updating_user(self):
        result = self.run_migration(SYSTEM)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded(), ["installer:desktop-user:--only 09_super_search.sh"])

    def test_both_scopes_skip_zorin_and_default_flavour_without_work(self):
        for script in (SYSTEM, USER):
            for flavour in ("zorin", ""):
                with self.subTest(script=script.name, flavour=flavour):
                    result = self.run_migration(script, NOCTRAOS_FLAVOUR=flavour)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("NOT APPLIED", result.stdout + result.stderr)
                    self.assertEqual(self.recorded(), [])

    def test_system_missing_or_root_desktop_user_retries_without_running(self):
        for user in ("", "root"):
            result = self.run_migration(SYSTEM, NOCTRAOS_USER=user)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("WARN", result.stdout + result.stderr)
            self.assertEqual(self.recorded(), [])

    def test_missing_system_installer_retries_but_missing_user_helper_is_nonfatal(self):
        (self.snapshot / "install.sh").unlink()
        self.setup.unlink()
        for script, expected in ((SYSTEM, 1), (USER, 0)):
            result = self.run_migration(script)
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertIn("WARN", result.stdout + result.stderr)
            self.assertEqual(self.recorded(), [])

    def test_desktop_failures_warn_instead_of_aborting_update(self):
        for script, extra in ((SYSTEM, {"INSTALL_RC": "1"}), (USER, {"SETUP_RC": "1"})):
            result = self.run_migration(script, **extra)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("WARN", result.stdout + result.stderr)

    def test_incomplete_system_installation_retries_even_if_module_returns_success(self):
        for name in REQUIRED_FILES:
            installed = self.root / name
            content = installed.read_bytes()
            mode = installed.stat().st_mode
            installed.unlink()
            for rc in ("0", "1"):
                with self.subTest(missing=name, module_rc=rc):
                    result = self.run_migration(SYSTEM, INSTALL_RC=rc)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn("retry", result.stdout + result.stderr)
            installed.write_bytes(content)
            installed.chmod(mode)
        result = self.run_migration(SYSTEM)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_nonexecutable_search_wrapper_retries(self):
        self.tool.chmod(0o644)
        result = self.run_migration(SYSTEM, INSTALL_RC="1")
        self.assertEqual(result.returncode, 1, result.stderr)

    def test_caller_snapshot_and_helper_paths_are_ignored(self):
        evil = self.tmp / "caller-code"
        evil.mkdir()
        self.write_tool(evil / "install.sh", 'echo UNTRUSTED >> "$CALLS"\n')
        self.write_tool(evil / "apply-search.sh", 'echo UNTRUSTED >> "$CALLS"\n')
        for script in (SYSTEM, USER):
            result = self.run_migration(script, NOCTRAOS_SNAPSHOT=str(evil),
                                        NOCTRAOS_SEARCH_PLASMA=str(evil / "apply-search.sh"))
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded(), ["installer:desktop-user:--only 09_super_search.sh",
                                          f"setup:{self.home}:unix:path=/test-session/bus"])

    def real_setup(self):
        self.setup.write_text((ROOT / "configs/plasma/apply-search.sh").read_text())
        self.write_tool(self.tool, 'echo "$*" >> "$CALLS"\nexit "${SHORTCUT_RC:-0}"\n')

    def test_user_catches_up_once_and_preserves_settings_and_marker(self):
        self.real_setup()
        settings = self.home / ".config/kglobalshortcutsrc"
        settings.parent.mkdir()
        settings.write_text("[krunner]\nRun Command=Alt+F2,Alt+Space,My shortcut\n")
        before = settings.read_bytes()
        self.assertEqual(self.run_migration(USER).returncode, 0)
        self.assertTrue(self.marker.is_file())
        self.marker.write_text("user's existing marker\n")
        stamp = self.marker.stat().st_mtime_ns
        self.assertEqual(self.run_migration(USER).returncode, 0)
        self.assertEqual(self.recorded(), ["--setup"])
        self.assertEqual(settings.read_bytes(), before)
        self.assertEqual(self.marker.read_text(), "user's existing marker\n")
        self.assertEqual(self.marker.stat().st_mtime_ns, stamp)

    def test_user_without_a_session_keeps_marker_absent_for_autostart_retry(self):
        self.real_setup()
        result = self.run_migration(USER, SHORTCUT_RC="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.run_migration(USER).returncode, 0)
        self.assertTrue(self.marker.is_file())
        self.assertEqual(self.recorded(), ["--setup", "--setup"])

    def test_existing_xdg_marker_prevents_any_shortcut_call(self):
        config = self.tmp / "custom-config"
        marker = config / "noctraos/plasma-search-v1"
        marker.parent.mkdir(parents=True)
        marker.write_text("keep\n")
        result = self.run_migration(USER, XDG_CONFIG_HOME=str(config))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.recorded(), [])
        self.assertEqual(marker.read_text(), "keep\n")

    def test_real_module_is_network_free_and_idempotent_in_a_stub_root(self):
        dest = self.root
        for name in REQUIRED_FILES:
            (dest / name).unlink()
        tools = self.tmp / "tools"
        tools.mkdir()
        log = self.tmp / "module-calls"
        q = shlex.quote
        # Any attempted network/package command fails and is visible in the log.
        for name in ("apt-get", "apt", "curl", "wget", "git", "pip", "npm"):
            self.write_tool(tools / name, 'echo "FORBIDDEN:$0 $*" >> "$MODULE_CALLS"\nexit 99\n')
        self.write_tool(tools / "plasmashell", "exit 0\n")
        self.write_tool(tools / "sudo", 'echo "sudo:$*" >> "$MODULE_CALLS"\n'
                        'case "$1" in install|systemctl|glib-compile-schemas) exec "$@" ;; *) exit 99 ;; esac\n')
        self.write_tool(tools / "glib-compile-schemas", 'touch "$1/gschemas.compiled"\n')
        timer = dest / "etc/systemd/user/timers.target.wants/noctraos-search-index.timer"
        self.write_tool(tools / "systemctl", f'mkdir -p {q(str(timer.parent))}\n'
                        f'ln -s ../noctraos-search-index.timer {q(str(timer))}\n')
        lib = self.tmp / "lib.sh"
        lib.write_text(f'source {q(str(ROOT / "install/lib.sh"))}\n'
                       'as_user() { echo "shortcut:$*" >> "$MODULE_CALLS"; }\n')
        module = self.tmp / "module09.sh"
        module.write_text((ROOT / "install/desktop/plasma/09_super_search.sh").read_text()
                          .replace('source "$REPO_ROOT/install/lib.sh"', f'source {q(str(lib))}')
                          .replace("/usr/local/", str(dest / "usr/local") + "/")
                          .replace("/usr/share/", str(dest / "usr/share") + "/")
                          .replace("/etc/", str(dest / "etc") + "/"))
        self.write_tool(self.snapshot / "install.sh",
                        'test "$*" = "--only 09_super_search.sh" || exit 99\n'
                        f'exec /bin/bash {q(str(module))}\n')
        self.env.update(PATH=f"{tools}:/usr/bin:/bin", MODULE_CALLS=str(log),
                        REPO_ROOT=str(ROOT), TARGET_USER="desktop-user", TARGET_UID="1000",
                        TARGET_HOME=str(self.home), XDG_CURRENT_DESKTOP="KDE")
        result = self.run_migration(SYSTEM)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("WARN", result.stdout + result.stderr)
        self.assertNotIn("FORBIDDEN:", log.read_text())
        for path in ("usr/local/share/noctraos-search/krunner.py",
                     "usr/local/bin/noctraos-search-plasma",
                     "usr/share/krunner/dbusplugins/noctraos-search.desktop",
                     "usr/share/dbus-1/services/org.kde.noctraos.search.service",
                     "etc/xdg/autostart/noctraos-plasma-search.desktop"):
            self.assertTrue((dest / path).is_file(), path)
        before = {p: p.stat().st_mtime_ns for p in dest.rglob("*") if p.is_file()}
        log.write_text("")
        result = self.run_migration(SYSTEM)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("WARN", result.stdout + result.stderr)
        self.assertNotIn("sudo:", log.read_text())
        self.assertNotIn("FORBIDDEN:", log.read_text())
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in dest.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
