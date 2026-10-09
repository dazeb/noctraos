"""VM guest tools: install/01b_vm_guest.sh picks the right packages for the hypervisor, never touches bare metal, is idempotent,
and the doctor row, the install order, the panel's Fix button and the root helper's allowlist all agree with it.

Nothing real runs: systemd-detect-virt, dpkg-query, apt-get, apt-cache, sudo and systemctl are stubs on PATH that record what was asked.
"""
import getpass
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
        env.update(PATH=f"{self.bin}:{os.environ['PATH']}", REPO_ROOT=str(ROOT), TARGET_USER=getpass.getuser(),
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

    def test_a_fresh_install_refreshes_the_package_index_once_when_the_agent_is_not_found(self):
        m = Machine(self, virt="kvm", available=[])
        result = m.run_module()
        self.assertEqual(result.returncode, 0, result.stderr)
        updates = [l for l in m.log.read_text().splitlines() if l.startswith("apt-get update")]
        self.assertEqual(len(updates), 1)
        self.assertEqual(m.installs(), [])                                      # still not available: skipped, not fatal
        self.assertIn("not available", result.stderr)

    def test_nothing_is_refreshed_when_everything_is_already_there(self):
        m = Machine(self, virt="kvm", installed=["qemu-guest-agent", "spice-vdagent"])
        m.run_module()
        self.assertNotIn("apt-get update", m.log.read_text())

    def test_skip_does_nothing(self):
        m = Machine(self, virt="kvm")
        result = m.run_module(NOCTRAOS_VM_GUEST="skip")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(m.log.read_text(), "")

    def test_remove_uninstalls_and_remembers_the_choice(self):
        m = Machine(self, virt="kvm", installed=["qemu-guest-agent", "spice-vdagent"])
        result = m.run_module(NOCTRAOS_VM_GUEST="remove")
        self.assertEqual(result.returncode, 0, result.stderr)
        removes = [l for l in m.log.read_text().splitlines() if l.startswith("apt-get remove")]
        self.assertEqual(len(removes), 1)
        self.assertIn("qemu-guest-agent spice-vdagent", removes[0])
        self.assertNotIn("purge", m.log.read_text())
        self.assertTrue((m.dir / ".config/noctraos/no-vm-guest").exists())

    def test_a_remembered_choice_stops_every_later_run_until_the_file_is_removed(self):
        m = Machine(self, virt="kvm")
        (m.dir / ".config/noctraos").mkdir(parents=True)
        (m.dir / ".config/noctraos/no-vm-guest").write_text("")
        result = m.run_module()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(m.log.read_text(), "")
        self.assertIn("turned off by you", result.stdout)
        (m.dir / ".config/noctraos/no-vm-guest").unlink()
        m.run_module()
        self.assertEqual(m.installs(), ["qemu-guest-agent", "spice-vdagent"])    # rm brings it back

    def test_a_disk_image_build_ignores_the_choice(self):
        m = Machine(self, virt="none")
        (m.dir / ".config/noctraos").mkdir(parents=True)
        (m.dir / ".config/noctraos/no-vm-guest").write_text("")
        m.run_module(NOCTRAOS_VM_GUEST="all")
        self.assertTrue(m.installs())

    def test_kvm_without_the_host_channel_says_how_to_turn_it_on(self):
        m = Machine(self, virt="kvm")
        result = m.run_module(NOC_QGA_CHANNEL=str(m.dir / "no-such-channel"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("QEMU Guest Agent > Enabled", result.stderr)
        quiet = m.run_module(NOC_QGA_CHANNEL=str(m.log))                          # any existing path stands in for the channel
        self.assertNotIn("Guest Agent > Enabled", quiet.stderr)


class WiringTests(unittest.TestCase):
    def test_install_runs_it_first_and_never_fatally(self):
        install = (ROOT / "install.sh").read_text()
        # before the preflight: a setup that stops early (small disk, no network) must still leave a VM the host can see
        self.assertLess(install.index("run_module 01b_vm_guest.sh"), install.index("run_module 00_preflight.sh"))
        self.assertRegex(install, r"run_module 01b_vm_guest\.sh \\\n\s+\|\| warn")
        # --skip-gui must not skip it: the agent is not part of the desktop
        self.assertLess(install.index("run_module 01b_vm_guest.sh"), install.index('if [ "$SKIP_GUI" -eq 1 ]'))

    def test_the_iso_bakes_in_the_kvm_agent(self):
        build = (ROOT / "iso/build-noctraos-iso.sh").read_text()
        self.assertIn('source "$(cd "$(dirname "$0")" && pwd)/bake-guest-tools.sh"', build)
        self.assertIn('bake_guest_tools "$SQ_ROOT"', build)

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

    def doctor(self, virt, installed, marker=False, **extra):
        m = Machine(self, virt=virt, installed=installed)
        if marker:
            (m.dir / ".config/noctraos").mkdir(parents=True)
            (m.dir / ".config/noctraos/no-vm-guest").write_text("")
        env = {**m.env(), "HOME": str(m.dir), "XDG_CONFIG_HOME": str(m.dir / ".config"), "NOC_OLLAMA_URL": "http://127.0.0.1:9", "NOC_TEST_HOOKS": "1", **extra}
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

    def test_agent_installed_but_no_host_channel_explains_proxmox(self):
        row = self.doctor("kvm", ["qemu-guest-agent"], NOC_QGA_CHANNEL="/nonexistent/channel")["vm-guest"]
        self.assertEqual((row["status"], row["fix"]), ("warn", None))
        self.assertIn("QEMU Guest Agent > Enabled", row["detail"])

    def test_agent_installed_with_the_channel_is_ok(self):
        row = self.doctor("kvm", ["qemu-guest-agent"], NOC_QGA_CHANNEL="/dev/null")["vm-guest"]
        self.assertEqual(row["status"], "ok")

    def test_a_removed_agent_is_not_nagged_about(self):
        row = self.doctor("kvm", [], marker=True)["vm-guest"]
        self.assertEqual((row["status"], row["fix"]), ("info", None))
        self.assertIn("turned off by you", row["detail"])

    def test_bare_metal_has_no_row(self):
        self.assertNotIn("vm-guest", self.doctor("none", []))

    def test_parallels_is_information_only(self):
        row = self.doctor("parallels", [])["vm-guest"]
        self.assertEqual((row["status"], row["fix"]), ("info", None))


class BakeTests(unittest.TestCase):
    """iso/bake-guest-tools.sh: the agent goes into the image through the image's own apt, and a failure never stops the build."""

    SCRIPT = ROOT / "iso/bake-guest-tools.sh"

    def bake(self, chroot_exit=0, preinstalled=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        root = d / "root"
        (root / "etc").mkdir(parents=True)
        (root / "var/lib/apt/lists").mkdir(parents=True)
        (root / "var/lib/apt/lists/stale").write_text("x")
        (root / "etc/resolv.conf").write_text("image resolver\n")
        if preinstalled:
            (root / "usr/sbin").mkdir(parents=True)
            (root / "usr/sbin/qemu-ga").write_text("")
            (root / "usr/sbin/qemu-ga").chmod(0o755)
        bindir = d / "bin"
        bindir.mkdir()
        log = d / "chroot.log"
        stub = bindir / "chroot"
        stub.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexit {chroot_exit}\n')
        stub.chmod(0o755)
        result = subprocess.run(["bash", "-c", f'source "{self.SCRIPT}"; bake_guest_tools "{root}"'], capture_output=True, text=True,
                                env={**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"})
        return root, log, result

    def test_installs_the_agent_in_the_image_and_restores_the_resolver(self):
        root, log, result = self.bake()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("apt-get install -y --no-install-recommends qemu-guest-agent", log.read_text())
        self.assertEqual((root / "etc/resolv.conf").read_text(), "image resolver\n")
        self.assertFalse((root / "etc/resolv.conf.noctraos-bak").exists())
        self.assertEqual(list((root / "var/lib/apt/lists").iterdir()), [])

    def test_a_failed_bake_warns_and_does_not_fail_the_build(self):
        _, _, result = self.bake(chroot_exit=100)
        self.assertEqual(result.returncode, 0)
        self.assertIn("WARNING", result.stderr)

    def test_an_image_that_has_it_is_left_alone(self):
        _, log, result = self.bake(preinstalled=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(log.exists())


if __name__ == "__main__":
    unittest.main()
