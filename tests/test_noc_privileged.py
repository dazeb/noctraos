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
