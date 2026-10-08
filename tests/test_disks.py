"""iso/disks.sh: pick the fastest candidate disk that is a Linux filesystem with room, never NTFS/tmpfs, never a full one."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DISKS = ROOT / "iso/disks.sh"


def sh(expr, **env):
    return subprocess.run(["bash", "-c", f'source "{DISKS}"; {expr}'], capture_output=True, text=True,
                          env={**os.environ, **env})


class DiskTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(dir=ROOT)   # not /tmp: that is tmpfs here, which the policy refuses
        self.addCleanup(self._t.cleanup)
        self.a = Path(self._t.name) / "a"
        self.b = Path(self._t.name) / "b"
        self.a.mkdir()
        self.b.mkdir()
        # Wherever the checkout lives (tmpfs under /tmp, ext4, overlayfs in CI), these directories must count as a real
        # disk: accept their filesystem explicitly, and say so, instead of depending on the checkout's location.
        self.fs = subprocess.run(["stat", "-f", "-c", "%T", str(self.a)], capture_output=True, text=True).stdout.strip()
        self.extra = {"NOCTRAOS_EXTRA_FS": self.fs}

    def test_first_usable_candidate_wins(self):
        r = sh("fast_disk", NOCTRAOS_DISK_CANDIDATES=f"{self.a} {self.b}", NOCTRAOS_MIN_FREE_GB="0", **self.extra)
        self.assertEqual(r.stdout, str(self.a))
        r = sh("fast_disk", NOCTRAOS_DISK_CANDIDATES=f"{self.b} {self.a}", NOCTRAOS_MIN_FREE_GB="0", **self.extra)
        self.assertEqual(r.stdout, str(self.b))

    def test_missing_unwritable_and_full_disks_are_skipped(self):
        r = sh("fast_disk", NOCTRAOS_DISK_CANDIDATES=f"/nonexistent {self.a}", NOCTRAOS_MIN_FREE_GB="0", **self.extra)
        self.assertEqual(r.stdout, str(self.a))
        r = sh("fast_disk", NOCTRAOS_DISK_CANDIDATES=f"{self.a} {self.b}", NOCTRAOS_MIN_FREE_GB="99999999", **self.extra)
        self.assertEqual(r.stdout, os.environ["HOME"])           # nothing has room: falls back to HOME, loudly
        self.assertIn("no candidate disk", r.stderr)

    def test_a_non_linux_filesystem_is_never_chosen(self):
        if not os.path.isdir("/dev/shm"):
            self.skipTest("no tmpfs")
        if self.fs == "tmpfs":
            self.skipTest("this checkout is on tmpfs itself, so tmpfs cannot stand in for the 'not a real disk' case")
        r = sh("fast_disk", NOCTRAOS_DISK_CANDIDATES=f"/dev/shm {self.a}", NOCTRAOS_MIN_FREE_GB="0", **self.extra)
        self.assertEqual(r.stdout, str(self.a))
        self.assertNotEqual(sh("require_linux_fs /dev/shm").returncode, 0)

    def test_extra_filesystems_are_opt_in(self):
        self.assertNotEqual(sh("require_linux_fs /dev/shm").returncode, 0)
        self.assertEqual(sh("require_linux_fs /dev/shm", NOCTRAOS_EXTRA_FS="tmpfs").returncode, 0)
        self.assertNotEqual(sh("require_linux_fs /dev/shm", NOCTRAOS_EXTRA_FS="xfs vfat").returncode, 0)

    def test_fast_dir_appends_the_name(self):
        r = sh("fast_dir noctraos-vm", NOCTRAOS_DISK_CANDIDATES=f"{self.a}", NOCTRAOS_MIN_FREE_GB="0", **self.extra)
        self.assertEqual(r.stdout, f"{self.a}/noctraos-vm")

    def test_a_directory_that_does_not_exist_yet_is_judged_by_its_parent(self):
        self.assertEqual(sh(f"require_free_gb '{self.a}/new/dir' 0").returncode, 0)
        r = sh(f"require_free_gb '{self.a}/new/dir' 99999999")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("free space", r.stderr)

    def test_the_default_order_puts_the_measured_fastest_disk_first(self):
        text = DISKS.read_text()
        self.assertIn('NOCTRAOS_DISK_CANDIDATES:-/run/media/dazeb/2tb /mnt/nvme1', text)


if __name__ == "__main__":
    unittest.main()
