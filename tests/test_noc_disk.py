"""bin/noc-disk: notice a disk that is bigger than the system partition and plan how to use the space.
Layout comes from a fake sysfs tree (sectors of 512 bytes) and nothing is ever resized: `grow` is only run with
--dry-run or with its commands and geteuid faked, so this is safe as any user (and as root in CI)."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "bin/noc-disk"
GIB = 1024 ** 3
SEC = GIB // 512   # sectors per GiB

loader = importlib.machinery.SourceFileLoader("noc_disk", str(TOOL))
spec = importlib.util.spec_from_loader("noc_disk", loader)
noc_disk = importlib.util.module_from_spec(spec)
loader.exec_module(noc_disk)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n")


class Disk:
    """A fake /sys/class/block with one disk and its partitions, as the kernel lays it out."""

    def __init__(self, test, disk="sda", disk_gib=64):
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        self.sys = Path(self.tmp.name)
        self.name = disk
        write(self.sys / "devices" / disk / "size", disk_gib * SEC)

    def part(self, number, start_gib, size_gib, sep=""):
        name = f"{self.name}{sep}{number}"
        node = self.sys / "devices" / self.name / name
        write(node / "partition", number)
        write(node / "start", int(start_gib * SEC))
        write(node / "size", int(size_gib * SEC))
        return name

    def link(self):
        """/sys/class/block/<name> are symlinks into devices/<disk>/..."""
        block = self.sys / "block"
        block.mkdir(exist_ok=True)
        for p in (self.sys / "devices").rglob("*"):
            if p.is_dir() and not (block / p.name).exists():
                (block / p.name).symlink_to(p)
        return block

    def analyse(self, device, fstype="ext4", fs_gib=None):
        block = self.link()
        fs = None if fs_gib is None else int(fs_gib * GIB)
        return noc_disk.analyse(f"/dev/{device}", fstype, fs, sysfs=str(block))


def ext4_fits(partition_gib):
    return partition_gib * 0.97   # what statvfs reports for a healthy ext4


class AnalyseTests(unittest.TestCase):
    def setUp(self):
        self.d = Disk(self)

    def test_enlarged_disk_has_room_to_grow(self):
        self.d.part(1, 0.001, 0.001)
        root = self.d.part(2, 0.01, 31.5)
        st = self.d.analyse(root, fs_gib=ext4_fits(31.5))
        self.assertTrue(st["supported"] and st["can_grow"])
        self.assertEqual((st["disk"], st["partition_number"], st["fstype"]), ("/dev/sda", 2, "ext4"))
        self.assertEqual(st["disk_bytes"], 64 * GIB)
        self.assertAlmostEqual(st["unallocated_bytes"] / GIB, 64 - 31.51, delta=0.05)
        self.assertEqual(st["fs_slack_bytes"], 0)
        self.assertEqual(st["expandable_bytes"], st["unallocated_bytes"])

    def test_full_disk_has_nothing_to_grow(self):
        root = self.d.part(2, 0.01, 63.98)
        st = self.d.analyse(root, fs_gib=ext4_fits(63.98))
        self.assertTrue(st["supported"])
        self.assertFalse(st["can_grow"])
        self.assertEqual(st["reason"], "")

    def test_alignment_slack_is_not_an_enlarged_disk(self):
        root = self.d.part(2, 0.01, 63.2)       # 0.8 GiB left over: below the 1 GiB bar
        self.assertFalse(self.d.analyse(root, fs_gib=ext4_fits(63.2))["can_grow"])

    def test_partition_already_grown_but_filesystem_not(self):
        """The state after a restart that was needed: the table is saved, the filesystem still has the old size."""
        root = self.d.part(2, 0.01, 63.98)
        st = self.d.analyse(root, fs_gib=31)
        self.assertTrue(st["can_grow"])
        self.assertEqual(st["unallocated_bytes"] // GIB, 0)
        self.assertAlmostEqual(st["fs_slack_bytes"] / GIB, 63.98 - 31, delta=0.01)

    def test_a_partition_behind_the_system_one_blocks_it(self):
        root = self.d.part(2, 0.01, 20)
        self.d.part(3, 21, 8)
        st = self.d.analyse(root, fs_gib=ext4_fits(20))
        self.assertFalse(st["supported"] or st["can_grow"])
        self.assertIn("sda3", st["reason"])

    def test_a_partition_before_it_is_fine(self):
        self.d.part(1, 0.01, 0.5)
        root = self.d.part(2, 1, 20)
        self.assertTrue(self.d.analyse(root, fs_gib=ext4_fits(20))["can_grow"])

    def test_lvm_or_encryption_is_left_alone(self):
        block = self.d.link()
        (self.d.sys / "devices" / "dm-0").mkdir()
        write(self.d.sys / "devices" / "dm-0" / "size", 10 * SEC)
        (block / "dm-0").symlink_to(self.d.sys / "devices" / "dm-0")
        # findmnt says /dev/mapper/vg-root; realpath() turns that into /dev/dm-0, which has no "partition" file
        st = noc_disk.analyse("/dev/dm-0", "ext4", 10 * GIB, sysfs=str(block))
        self.assertFalse(st["supported"])
        self.assertIn("not on a plain partition", st["reason"])

    def test_unknown_filesystem_is_left_alone(self):
        root = self.d.part(2, 0.01, 20)
        st = self.d.analyse(root, fstype="ntfs", fs_gib=19)
        self.assertFalse(st["supported"])
        self.assertIn("ntfs", st["reason"])

    def test_nvme_partition_names(self):
        d = Disk(self, disk="nvme0n1")
        root = d.part(3, 1, 30, sep="p")
        st = d.analyse(root, fs_gib=ext4_fits(30))
        self.assertEqual((st["disk"], st["partition_number"], st["can_grow"]), ("/dev/nvme0n1", 3, True))

    def test_unknown_device(self):
        st = noc_disk.analyse("", "ext4", None, sysfs=str(self.d.link()))
        self.assertFalse(st["supported"])
        self.assertTrue(st["reason"])


class StatusCliTests(unittest.TestCase):
    def run_tool(self, d, *args, **extra):
        block = d.link()
        env = {**os.environ, "NOC_DISK_SYSFS": str(block), "NOC_DISK_ROOT": "/dev/sda2",
               "NOC_DISK_FSTYPE": "ext4", "NOC_DISK_FS_BYTES": str(int(30 * GIB)), **extra}
        return subprocess.run([str(TOOL), *args], capture_output=True, text=True, env=env)

    def disk(self):
        d = Disk(self)
        d.part(2, 0.01, 31.5)
        return d

    def test_status_json_keys(self):
        out = self.run_tool(self.disk(), "status", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        st = json.loads(out.stdout)
        for key in ("supported", "reason", "device", "disk", "partition_number", "fstype", "disk_bytes",
                    "partition_bytes", "fs_bytes", "unallocated_bytes", "fs_slack_bytes", "expandable_bytes", "can_grow"):
            self.assertIn(key, st)
        self.assertTrue(st["can_grow"])

    def test_status_text_names_the_unused_space(self):
        out = self.run_tool(self.disk(), "status").stdout
        self.assertIn("not in use yet", out)
        self.assertIn("Control Panel", out)


class GrowPlanTests(unittest.TestCase):
    """--dry-run prints the exact commands without running any of them."""

    def plan(self, d, fstype="ext4", fs_gib=30, root_part="sda2"):
        block = d.link()
        env = {**os.environ, "NOC_DISK_SYSFS": str(block), "NOC_DISK_ROOT": f"/dev/{root_part}",
               "NOC_DISK_FSTYPE": fstype, "NOC_DISK_FS_BYTES": str(int(fs_gib * GIB))}
        return subprocess.run([str(TOOL), "grow", "--dry-run"], capture_output=True, text=True, env=env)

    def setup_disk(self, root_gib=31.5):
        d = Disk(self)
        d.part(1, 0.001, 0.001)
        d.part(2, 0.01, root_gib)
        return d

    def test_ext4_plan(self):
        out = self.plan(self.setup_disk())
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = [l.strip() for l in out.stdout.splitlines() if "would run" in l]
        self.assertEqual(lines, ["would run: sfdisk --no-reread --relocate gpt-bak-std /dev/sda",
                                 "would run: sfdisk --no-reread -N 2 /dev/sda",
                                 "would run: partx -u /dev/sda",
                                 "would run: resize2fs /dev/sda2"])

    def test_other_filesystems_use_their_own_grower(self):
        self.assertIn("xfs_growfs /", self.plan(self.setup_disk(), fstype="xfs").stdout)
        self.assertIn("btrfs filesystem resize max /", self.plan(self.setup_disk(), fstype="btrfs").stdout)

    def test_filesystem_only_plan_skips_the_partition_table(self):
        d = self.setup_disk(root_gib=63.98)
        out = self.plan(d, fs_gib=31)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("sfdisk", out.stdout)
        self.assertIn("resize2fs /dev/sda2", out.stdout)

    def test_nothing_to_do_exits_2(self):
        out = self.plan(self.setup_disk(root_gib=63.98), fs_gib=ext4_fits(63.98))
        self.assertEqual(out.returncode, 2)
        self.assertNotIn("would run", out.stdout)

    def test_blocked_layout_exits_2(self):
        d = self.setup_disk(root_gib=20)
        d.part(3, 21, 8)
        out = self.plan(d)
        self.assertEqual(out.returncode, 2)
        self.assertIn("comes after", out.stdout)


class GrowRunTests(unittest.TestCase):
    """The real code path with every external command faked: order, privilege and exit codes."""

    def run_grow(self, euid=0, partition_after=None, fail_on=None):
        d = Disk(self)
        d.part(1, 0.001, 0.001)
        d.part(2, 0.01, 31.5)
        block = d.link()
        calls = []

        def fake_run(argv, **kw):
            calls.append(list(argv))
            if argv[0] == "sfdisk" and "-J" in argv:
                return subprocess.CompletedProcess(argv, 0, json.dumps({"partitiontable": {"label": "gpt"}}), "")
            if fail_on and argv[0] == fail_on[0] and fail_on[1] in argv:
                return subprocess.CompletedProcess(argv, 1, "", "boom")
            if argv[0] == "partx" and partition_after is not None:
                write(block / "sda2" / "size", int(partition_after * SEC))
            return subprocess.CompletedProcess(argv, 0, "", "")

        env = {"NOC_DISK_SYSFS": str(block), "NOC_DISK_ROOT": "/dev/sda2", "NOC_DISK_FSTYPE": "ext4",
               "NOC_DISK_FS_BYTES": str(30 * GIB)}
        with mock.patch.dict(os.environ, env), mock.patch.object(noc_disk.os, "geteuid", return_value=euid), \
                mock.patch.object(noc_disk.subprocess, "run", side_effect=fake_run), \
                mock.patch.object(noc_disk, "status", wraps=noc_disk.status):
            code = noc_disk.grow()
        return code, calls

    def test_not_root_changes_nothing(self):
        code, calls = self.run_grow(euid=1000)
        self.assertEqual(code, noc_disk.EXIT_FAILED)
        self.assertEqual(calls, [])

    def test_success_runs_the_steps_in_order(self):
        code, calls = self.run_grow(partition_after=63.98)
        self.assertEqual(code, noc_disk.EXIT_OK)
        order = [c[0] + (" " + c[1] if c[0] == "sfdisk" else "") for c in calls]
        self.assertEqual([c[0] for c in calls if c[0] != "sfdisk"], ["partx", "resize2fs"])
        self.assertEqual(calls[-1], ["resize2fs", "/dev/sda2"])
        self.assertLess(order.index("partx"), order.index("resize2fs"))

    def test_a_kernel_that_keeps_the_old_size_asks_for_a_restart_and_leaves_the_filesystem_alone(self):
        code, calls = self.run_grow(partition_after=31.5)
        self.assertEqual(code, noc_disk.EXIT_RESTART)
        self.assertNotIn("resize2fs", [c[0] for c in calls])

    def test_a_failing_step_stops_the_run(self):
        code, calls = self.run_grow(fail_on=("sfdisk", "-N"))
        self.assertEqual(code, noc_disk.EXIT_FAILED)
        self.assertNotIn("resize2fs", [c[0] for c in calls])


class NotifyTests(unittest.TestCase):
    def run_notify(self, state, can_grow=True, action="open"):
        sent = []

        def fake_run(argv, **kw):
            sent.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, action + "\n", "")

        st = {"can_grow": can_grow, "expandable_bytes": 33 * GIB + 1}
        with mock.patch.dict(os.environ, {"NOC_DISK_STATE": str(state)}), \
                mock.patch.object(noc_disk, "status", return_value=st), \
                mock.patch.object(noc_disk.subprocess, "run", side_effect=fake_run), \
                mock.patch.object(noc_disk.subprocess, "Popen") as popen:
            noc_disk.notify()
        return sent, popen

    def test_tells_once_per_amount_and_opens_the_panel_on_request(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "sub" / "notified"
            sent, popen = self.run_notify(state)
            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0][0], "notify-send")
            self.assertIn("Your files are not touched", " ".join(sent[0]))
            self.assertEqual(popen.call_args[0][0], ["/usr/local/bin/noctraos-control", "--page", "hardware"])
            sent, popen = self.run_notify(state)          # same amount: stay quiet
            self.assertEqual(sent, [])

    def test_dismissed_notice_does_nothing_and_no_space_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            sent, popen = self.run_notify(Path(d) / "n", action="")
            self.assertEqual(len(sent), 1)
            popen.assert_not_called()
            sent, _ = self.run_notify(Path(d) / "m", can_grow=False)
            self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
