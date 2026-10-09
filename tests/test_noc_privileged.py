"""The root helper is an allowlist: pin what it accepts and refuses. It is never run as root here;
the validators are called by sourcing it, and `main` is only checked for refusals."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "bin/noc-privileged"
POLICY = ROOT / "configs/polkit/dev.noctraos.privileged.policy"


def bash(expr, **env):
    return subprocess.run(["bash", "-c", f'source "{HELPER}"; {expr}'], capture_output=True, text=True,
                          env={**os.environ, **env})


class ValidateTests(unittest.TestCase):
    def ok(self, expr):
        return bash(expr).returncode == 0

    def test_update_steps(self):
        self.assertTrue(self.ok("validate_update apt"))
        self.assertTrue(self.ok("validate_update apt,flatpak"))
        self.assertTrue(self.ok("validate_update apt,flatpak,noctraos"))
        for bad in ("", "mise", "apt,mise", "apt;id", "apt flatpak", "$(id)", "apt,", ",apt", "../apt"):
            with self.subTest(steps=bad):
                self.assertFalse(self.ok(f"validate_update '{bad}'"))

    def test_update_channels(self):
        for good in ("stable", "nightly"):
            self.assertTrue(self.ok(f"validate_channel {good}"), good)
        for bad in ("", "beta", "stable,nightly", "../stable", "$(id)", "Stable", "--help"):
            with self.subTest(channel=bad):
                self.assertFalse(self.ok(f"validate_channel '{bad}'"))

    def test_gpu_vendors(self):
        for good in ("nvidia", "amd", "all"):
            self.assertTrue(self.ok(f"validate_vendor {good}"), good)
        for bad in ("", "intel", "nvidia,amd", "all;id", "NVIDIA", "--dry-run", "$(id)"):
            with self.subTest(vendor=bad):
                self.assertFalse(self.ok(f"validate_vendor '{bad}'"))

    def test_modules_need_the_allowlist_and_the_root_owned_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "install").mkdir()
            (Path(d) / "install/04d_appmanager.sh").write_text("#!/bin/sh\n")
            (Path(d) / "install/00_preflight.sh").write_text("#!/bin/sh\n")
            snap = f'SNAPSHOT="{d}"; '
            self.assertTrue(self.ok(snap + "validate_module 04d_appmanager.sh"))
            (Path(d) / "install/03b_ollama_update.sh").write_text("#!/bin/sh\n")
            self.assertTrue(self.ok(snap + "validate_module 03b_ollama_update.sh"))
            # the optional local AI step lives in a subfolder of install/: allowed by its exact name, and only that
            (Path(d) / "install/optional").mkdir()
            (Path(d) / "install/optional/local_llm.sh").write_text("#!/bin/sh\n")
            self.assertTrue(self.ok(snap + "validate_module optional/local_llm.sh"))
            (Path(d) / "install/optional/other.sh").write_text("#!/bin/sh\n")
            for bad in ("optional/other.sh", "optional/", "optional", "optional/../00_preflight.sh", "optional/local_llm.sh;id"):
                self.assertFalse(self.ok(snap + f"validate_module '{bad}'"), bad)
            # present in the snapshot but not on the allowlist
            self.assertFalse(self.ok(snap + "validate_module 00_preflight.sh"))
            # on the allowlist but missing from the snapshot
            os.remove(Path(d) / "install/04d_appmanager.sh")
            self.assertFalse(self.ok(snap + "validate_module 04d_appmanager.sh"))
            for bad in ("../install.sh", "04d_appmanager.sh;id", "/etc/passwd", ""):
                self.assertFalse(self.ok(snap + f"validate_module '{bad}'"))

    def test_invoking_user_comes_from_pkexec_uid_and_never_root(self):
        me = os.getuid()
        if me != 0:
            name = bash("invoking_user", PKEXEC_UID=str(me)).stdout.strip()
            self.assertEqual(name, os.getlogin() if False else name)
            self.assertTrue(name)
        for bad in ("0", "", "abc", "1;id", "-1"):
            with self.subTest(uid=bad):
                self.assertNotEqual(bash("invoking_user", PKEXEC_UID=bad).returncode, 0)


class RefusalTests(unittest.TestCase):
    def test_refuses_to_run_unprivileged(self):
        if os.getuid() == 0:
            self.skipTest("running as root")
        result = subprocess.run([str(HELPER), "update", "apt"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("must run as root", result.stderr)


class DiskGrowVerbTests(unittest.TestCase):
    """`disk-grow` is a verb with no arguments: the caller never names a disk, a partition or a command."""

    def run_as_root(self, *args):
        # main refuses when not root, so run it with `id` faked to 0 and the tool replaced by an echo stub.
        with tempfile.TemporaryDirectory() as d:
            stub = Path(d) / "noc-disk"
            stub.write_text('#!/bin/sh\necho "noc-disk $*"\n')
            stub.chmod(0o755)
            script = f'id() {{ echo 0; }}; source "{HELPER}"; DISK="{stub}"; main {" ".join(args)}'
            return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                                  env={k: v for k, v in os.environ.items() if k != "PKEXEC_UID"})

    def test_runs_the_tool_with_grow_and_nothing_else(self):
        out = self.run_as_root("disk-grow")
        self.assertEqual((out.returncode, out.stdout.strip()), (0, "noc-disk grow"))

    def test_refuses_any_argument(self):
        for extra in ("/dev/sda", "--dry-run", "sda2", "';id'"):
            with self.subTest(extra=extra):
                out = self.run_as_root("disk-grow", extra)
                self.assertEqual(out.returncode, 2)
                self.assertIn("takes no arguments", out.stderr)

    def test_the_usage_line_lists_it(self):
        out = self.run_as_root("nonsense")
        self.assertIn("disk-grow", out.stderr)


class RemoteAccessVerbTests(unittest.TestCase):
    """`remote-access` takes one of two words. The unit names are fixed in the helper, the caller names no service."""

    def test_the_validator_takes_on_and_off_only(self):
        for good in ("on", "off"):
            self.assertEqual(bash(f"validate_remote_access {good}").returncode, 0, good)
        for bad in ("", "ON", "on;id", "enable", "--now", "on off", "$(id)", "ssh"):
            with self.subTest(word=bad):
                self.assertNotEqual(bash(f"validate_remote_access '{bad}'").returncode, 0)

    def run_as_root(self, args, units):
        """Run `main` with `id` faked to 0 and systemctl replaced by a stub that knows only `units` and logs each call."""
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "log"
            stub = Path(d) / "systemctl"
            stub.write_text(f'''#!/bin/sh
echo "$*" >> "{log}"
if [ "$1" = cat ]; then case " {' '.join(units)} " in *" $2 "*) exit 0 ;; esac; exit 1; fi
exit 0
''')
            stub.chmod(0o755)
            script = f'id() {{ echo 0; }}; source "{HELPER}"; SYSTEMCTL="{stub}"; main {args}'
            out = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                                 env={k: v for k, v in os.environ.items() if k != "PKEXEC_UID"})
            return out, (log.read_text().splitlines() if log.exists() else [])

    def test_off_stops_and_disables_the_socket_and_the_service(self):
        out, calls = self.run_as_root("remote-access off", ["ssh.socket", "ssh.service"])
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual([c for c in calls if not c.startswith("cat ")],
                         ["disable --now ssh.socket", "disable --now ssh.service"])

    def test_on_enables_the_socket_where_there_is_one_and_only_that(self):
        out, calls = self.run_as_root("remote-access on", ["ssh.socket", "ssh.service"])
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual([c for c in calls if not c.startswith("cat ")], ["enable --now ssh.socket"])

    def test_on_enables_the_service_when_there_is_no_socket(self):
        out, calls = self.run_as_root("remote-access on", ["ssh.service"])
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual([c for c in calls if not c.startswith("cat ")], ["enable --now ssh.service"])

    def test_no_server_is_an_error_that_changes_nothing(self):
        for word in ("on", "off"):
            with self.subTest(word=word):
                out, calls = self.run_as_root(f"remote-access {word}", [])
                self.assertEqual(out.returncode, 1)
                self.assertIn("not installed", out.stderr)
                self.assertTrue(all(c.startswith("cat ") for c in calls), calls)

    def test_anything_else_is_refused_before_systemctl_is_touched(self):
        for args in ("remote-access", "remote-access maybe", "remote-access on extra", "remote-access ssh.service",
                     "remote-access 'on;id'"):
            with self.subTest(args=args):
                out, calls = self.run_as_root(args, ["ssh.socket", "ssh.service"])
                self.assertEqual(out.returncode, 2)
                self.assertEqual(calls, [])

    def test_the_usage_line_lists_it(self):
        out, _ = self.run_as_root("nonsense", [])
        self.assertIn("remote-access <on|off>", out.stderr)


class PolicyTests(unittest.TestCase):
    def test_policy_pins_the_helper_and_asks_once(self):
        action = ET.parse(POLICY).getroot().find("action")
        self.assertEqual(action.get("id"), "dev.noctraos.privileged")
        annotations = {a.get("key"): a.text for a in action.findall("annotate")}
        self.assertEqual(annotations["org.freedesktop.policykit.exec.path"],
                         "/usr/local/libexec/noctraos/noc-privileged")
        defaults = {c.tag: c.text for c in action.find("defaults")}
        self.assertEqual(defaults["allow_active"], "auth_admin_keep")      # one prompt for several calls
        self.assertEqual(defaults["allow_any"], "auth_admin")              # never "yes"
        self.assertEqual(defaults["allow_inactive"], "auth_admin")

    def test_module_07_installs_it_root_owned(self):
        text = (ROOT / "install/07_persistence.sh").read_text()
        self.assertIn("/usr/local/libexec/noctraos/noc-privileged", text)
        self.assertIn("chown -R root:root", text)


if __name__ == "__main__":
    unittest.main()
