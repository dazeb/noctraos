"""VM guest tools: install/01b_vm_guest.sh picks the right packages for the hypervisor, never touches bare metal, is idempotent,
and the doctor row, the install order, the panel's Fix button and the root helper's allowlist all agree with it.

Nothing real runs: systemd-detect-virt, dpkg-query, apt-get, apt-cache, sudo and systemctl are stubs on PATH that record what was asked.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "install/01b_vm_guest.sh"
NOC = ROOT / "bin/noc"

# What each hypervisor must end up with, in install order: the first package is the one `noc doctor` looks for.
EXPECTED = {
    "kvm": ["qemu-guest-agent", "spice-vdagent"],
    "qemu": ["qemu-guest-agent", "spice-vdagent"],
    "vmware": ["open-vm-tools", "open-vm-tools-desktop"],
    "oracle": ["virtualbox-guest-utils", "virtualbox-guest-x11"],
    "microsoft": ["linux-tools-virtual", "linux-cloud-tools-virtual"],
}


class Machine:
    """A pretend machine: which hypervisor it runs on, which packages it already has, and a log of what the module did."""

    def __init__(self, test, virt="none", installed=(), available=None):
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        self.log = self.dir / "calls.log"
        self.log.write_text("")
        self.have = self.dir / "installed"
        self.have.write_text("\n".join(installed) + "\n")
        self.known = self.dir / "available"
        self.known.write_text("\n".join(available) + "\n" if available is not None else "*\n")
        self.stub("systemd-detect-virt", f'[ "$1" = "--vm" ] || exit 2\necho {virt}\n[ {virt} != none ]')
        self.stub("dpkg-query", f'grep -Fx "$3" "{self.have}" >/dev/null && echo "install ok installed" || exit 1')
        self.stub("apt-cache", f'grep -Fx "$2" "{self.known}" >/dev/null || grep -Fx "*" "{self.known}" >/dev/null')
        self.stub("apt-get", f'echo "apt-get $*" >> "{self.log}"\nfor p; do :; done\necho "$p" >> "{self.have}"')
        self.stub("systemctl", f'echo "systemctl $*" >> "{self.log}"')
        self.stub("sudo", 'while [ "${1#*=}" != "$1" ]; do shift; done\nexec "$@"')

    def stub(self, name, script):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + script + "\n")
        path.chmod(0o755)

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith("NOCTRAOS_")}
        env.update(PATH=f"{self.bin}:{os.environ['PATH']}", REPO_ROOT=str(ROOT), TARGET_USER="tester",
                   TARGET_UID="1000", TARGET_HOME=str(self.dir))
        env.update(extra)
        return env

    def run_module(self, **extra):
        return subprocess.run(["bash", str(MODULE)], capture_output=True, text=True, env=self.env(**extra))

    def installs(self):
        return [line.split()[-1] for line in self.log.read_text().splitlines() if line.startswith("apt-get install")]

    def started(self):
        return [line for line in self.log.read_text().splitlines() if line.startswith("systemctl")]


def function_output(expr):
    """Run a shell function from the module (it only defines functions when sourced)."""
    env = {**os.environ, "REPO_ROOT": str(ROOT), "TARGET_USER": "t", "TARGET_UID": "1", "TARGET_HOME": "/tmp"}
    return subprocess.run(["bash", "-c", f'source "{MODULE}"; {expr}'], capture_output=True, text=True, env=env, check=True).stdout.split()


class PackageMapTests(unittest.TestCase):
    def test_each_hypervisor_gets_its_guest_tools(self):
        for virt, packages in EXPECTED.items():
            self.assertEqual(function_output(f"vm_guest_packages {virt}"), packages, virt)

    def test_unknown_hosts_get_nothing(self):
        for virt in ("none", "", "parallels", "xen", "docker", "wsl"):
            self.assertEqual(function_output(f"vm_guest_packages '{virt}'"), [], virt)

    def test_all_is_every_set_once(self):
        got = function_output("vm_guest_packages all")
        self.assertEqual(sorted(got), sorted({p for v in ("kvm", "vmware", "oracle", "microsoft") for p in EXPECTED[v]}))
        self.assertEqual(len(got), len(set(got)))

    def test_the_doctor_row_checks_the_first_package_of_each_set(self):
        for virt, packages in EXPECTED.items():
            out = subprocess.run(["bash", "-c", f'source "{NOC}"; vm_guest_primary {virt}'], capture_output=True, text=True).stdout.strip()
            self.assertEqual(out, packages[0], virt)
        for virt in ("none", "", "parallels"):
            out = subprocess.run(["bash", "-c", f'source "{NOC}"; vm_guest_primary "{virt}"'], capture_output=True, text=True).stdout.strip()
            self.assertEqual(out, "", virt)


class ModuleTests(unittest.TestCase):
    def test_bare_metal_installs_nothing(self):
        m = Machine(self, virt="none")
        result = m.run_module()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(m.installs(), [])
        self.assertIn("Bare metal", result.stdout)

    def test_kvm_installs_the_agent_and_starts_it(self):
        m = Machine(self, virt="kvm")
        result = m.run_module()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(m.installs(), ["qemu-guest-agent", "spice-vdagent"])
        self.assertEqual(m.started(), ["systemctl start qemu-guest-agent"])

    def test_the_second_run_changes_nothing(self):
        m = Machine(self, virt="vmware")
        self.assertEqual(m.run_module().returncode, 0)
        self.assertEqual(m.installs(), ["open-vm-tools", "open-vm-tools-desktop"])
        again = m.run_module()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(m.installs(), ["open-vm-tools", "open-vm-tools-desktop"])       # no new installs
        self.assertIn("already installed", again.stdout)

    def test_only_what_is_missing_is_installed(self):
        m = Machine(self, virt="kvm", installed=["qemu-guest-agent"])
        m.run_module()
        self.assertEqual(m.installs(), ["spice-vdagent"])

    def test_a_package_the_release_lacks_is_skipped_not_fatal(self):
        m = Machine(self, virt="oracle", available=["virtualbox-guest-utils"])
        result = m.run_module()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(m.installs(), ["virtualbox-guest-utils"])
        self.assertIn("not available", result.stderr)

    def test_a_failing_install_warns_and_goes_on(self):
        m = Machine(self, virt="kvm")
        m.stub("apt-get", f'echo "apt-get $*" >> "{m.log}"\nexit 100')
        result = m.run_module()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(m.installs(), ["qemu-guest-agent", "spice-vdagent"])             # the second was still tried
        self.assertIn("failed to install", result.stderr)

    def test_all_installs_every_set_whatever_the_host_is(self):
        m = Machine(self, virt="none")
        result = m.run_module(NOCTRAOS_VM_GUEST="all")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(m.installs()), sorted(function_output("vm_guest_packages all")))
        self.assertEqual(m.started(), [])                      # no agent is started for a host it may not even be on

    def test_parallels_only_points_at_parallels_tools(self):
        m = Machine(self, virt="parallels")
        result = m.run_module()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(m.installs(), [])
        self.assertIn("Parallels Tools", result.stderr)


class WiringTests(unittest.TestCase):
    def test_install_runs_it_after_the_system_base_and_never_fatally(self):
        install = (ROOT / "install.sh").read_text()
        self.assertLess(install.index("run_module 01_system.sh"), install.index("run_module 01b_vm_guest.sh"))
        self.assertLess(install.index("run_module 01b_vm_guest.sh"), install.index("run_module 02_mise.sh"))
        self.assertRegex(install, r"run_module 01b_vm_guest\.sh \\\n\s+\|\| warn")
        # --skip-gui must not skip it: the agent is not part of the desktop
        self.assertLess(install.index("run_module 01b_vm_guest.sh"), install.index('if [ "$SKIP_GUI" -eq 1 ]'))

    def test_the_root_helper_and_the_panel_know_the_module(self):
        import re
        helper = (ROOT / "bin/noc-privileged").read_text()
        self.assertIn("01b_vm_guest.sh", re.search(r"^MODULES=\((.*)\)", helper, re.M).group(1).split())
        import sys
        sys.path.insert(0, str(ROOT / "control"))
        import panel
        self.assertEqual(panel.fix_command("module:01b_vm_guest.sh"), [panel.PKEXEC, panel.HELPER, "module", "01b_vm_guest.sh"])

    def test_proxmox_vms_get_the_agent_channel(self):
        self.assertIn("--agent enabled=1", (ROOT / "proxmox-install.sh").read_text())

    def test_image_sysprep_carries_every_agent(self):
        self.assertIn("NOCTRAOS_VM_GUEST=all", (ROOT / "iso/vm-sysprep.sh").read_text())

    def test_the_module_is_executable_like_its_siblings(self):
        self.assertTrue(os.access(MODULE, os.X_OK))


class DoctorRowTests(unittest.TestCase):
    """`noc doctor --json` inside a pretend VM: a row that says whether the agent is there and, when it is not, offers the fix."""

    def doctor(self, virt, installed):
        m = Machine(self, virt=virt, installed=installed)
        env = {**m.env(), "HOME": str(m.dir), "XDG_CONFIG_HOME": str(m.dir / ".config"), "NOC_OLLAMA_URL": "http://127.0.0.1:9", "NOC_TEST_HOOKS": "1"}
        out = subprocess.run([str(NOC), "doctor", "--json"], capture_output=True, text=True, env=env, timeout=180).stdout
        import json
        return {r["id"]: r for r in json.loads(out)}

    def test_missing_agent_warns_with_the_panel_fix(self):
        row = self.doctor("kvm", [])["vm-guest"]
        self.assertEqual((row["status"], row["fix"]), ("warn", "module:01b_vm_guest.sh"))
        self.assertIn("qemu-guest-agent", row["detail"])

    def test_present_agent_is_ok(self):
        row = self.doctor("vmware", ["open-vm-tools"])["vm-guest"]
        self.assertEqual((row["status"], row["fix"]), ("ok", None))

    def test_bare_metal_has_no_row(self):
        self.assertNotIn("vm-guest", self.doctor("none", []))

    def test_parallels_is_information_only(self):
        row = self.doctor("parallels", [])["vm-guest"]
        self.assertEqual((row["status"], row["fix"]), ("info", None))


if __name__ == "__main__":
    unittest.main()
