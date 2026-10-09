"""Images built before the fix were repacked with `mksquashfs -all-root`: every file root:root. That left the D-Bus launch helper
unusable by the bus, so the Software Updater's apt daemon never started and the updater froze. These tests pin the build fix, the
manifest of stock owners, and the migration that repairs machines already installed from such an image. The migration runs on a
temp tree with the owner it treats as "flattened" set to the current user, so nothing here needs root."""
import grp
import os
from pathlib import Path
import pwd
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs/ownership/zorin-18.1-core.tsv"
MIGRATION = ROOT / "migrations/system/0001_restore_ownership.sh"
BUILD = ROOT / "iso/build-noctraos-iso.sh"


def entries():
    rows = []
    for line in MANIFEST.read_text().splitlines():
        if line and not line.startswith("#"):
            path, user, group, flag = (line.split("\t") + [""])[:4]
            rows.append((path, user, group, flag))
    return rows


class BuildTests(unittest.TestCase):
    text = BUILD.read_text()

    def test_the_image_is_not_flattened_to_root(self):
        code = "\n".join(l for l in self.text.splitlines() if not l.lstrip().startswith("#"))
        self.assertNotIn("-all-root", code)
        self.assertNotIn("-force-uid", code)
        self.assertNotIn("-force-gid", code)

    def test_the_build_checks_ownership_before_and_after_the_repack(self):
        self.assertIn("unpacking lost file ownership", self.text)
        self.assertIn("the repacked squashfs lost file ownership", self.text)
        repack = self.text.index('mksquashfs "$SQ_ROOT"')           # the command, not the `need mksquashfs` line
        self.assertLess(self.text.index("unpacking lost file ownership"), repack)
        self.assertGreater(self.text.index("the repacked squashfs lost file ownership"), repack)


class ManifestTests(unittest.TestCase):
    def test_every_line_is_well_formed(self):
        rows = entries()
        self.assertGreater(len(rows), 40)
        for path, user, group, flag in rows:
            self.assertTrue(path.startswith("/"), path)
            self.assertNotIn("..", path)
            self.assertTrue(user and group, path)
            self.assertIn(flag, ("", "R"), path)
        self.assertEqual(len({r[0] for r in rows}), len(rows), "a path is listed twice")

    def test_the_entries_that_broke_the_updater_and_the_login_are_there(self):
        want = {"/usr/lib/dbus-1.0/dbus-daemon-launch-helper": ("root", "messagebus"), "/etc/shadow": ("root", "shadow"),
                "/usr/bin/crontab": ("root", "crontab"), "/usr/sbin/unix_chkpwd": ("root", "shadow"),
                "/var/lib/polkit-1": ("root", "polkitd"), "/etc/ssl/private": ("root", "ssl-cert")}
        have = {p: (u, g) for p, u, g, _ in entries()}
        for path, owner in want.items():
            self.assertEqual(have.get(path), owner, path)

    def test_it_agrees_with_the_dpkg_overrides_the_image_ships(self):
        """Every statoverride Zorin ships (user, group, mode, path) is in the manifest with the same owner."""
        have = {p: (u, g) for p, u, g, _ in entries()}
        for path, owner in (("/var/lib/geoclue", ("geoclue", "geoclue")), ("/var/log/hp/tmp", ("root", "lp")),
                            ("/usr/bin/crontab", ("root", "crontab")), ("/etc/ssl/private", ("root", "ssl-cert")),
                            ("/usr/lib/dbus-1.0/dbus-daemon-launch-helper", ("root", "messagebus"))):
            self.assertEqual(have[path], owner)

    def test_the_man_cache_is_one_recursive_rule(self):
        rows = [r for r in entries() if r[0].startswith("/var/cache/man")]
        self.assertEqual(rows, [("/var/cache/man", "man", "man", "R")])

    def test_nothing_volatile_or_personal_is_listed(self):
        for path, *_ in entries():
            self.assertFalse(path.startswith(("/run/", "/home/", "/tmp/", "/proc/")), path)


class MigrationTests(unittest.TestCase):
    """The tree stands in for /, `chown` is a recorder, and "flattened" is whatever owner the temp files have."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tree = Path(self.tmp.name) / "root"
        self.snap = Path(self.tmp.name) / "snap"
        (self.snap / "configs/ownership").mkdir(parents=True)
        self.me = f"{pwd.getpwuid(os.getuid()).pw_name}:{grp.getgrgid(os.getgid()).gr_name}"
        self.log = Path(self.tmp.name) / "chown.log"
        recorder = Path(self.tmp.name) / "chown-recorder"
        recorder.write_text(f'#!/bin/sh\nfor a in "$@"; do echo "$a"; done >> "{self.log}"\n')
        recorder.chmod(0o755)
        self.recorder = recorder
        failing = Path(self.tmp.name) / "chown-failing"
        failing.write_text('#!/bin/sh\necho "chown: Operation not permitted" >&2\nexit 1\n')
        failing.chmod(0o755)
        self.failing = failing
        # by default this is a NoctraOS system built from a flattened image: the release file, and a canary still flattened
        self.release = self.tree / "etc/noctraos-release"
        self.release.parent.mkdir(parents=True, exist_ok=True)
        self.release.write_text("NoctraOS 0.4.0\n")
        self.make("/usr/bin/crontab", 0o2755)

    def manifest(self, text):
        (self.snap / "configs/ownership/zorin-18.1-core.tsv").write_text(text)

    def make(self, path, mode, kind="f"):
        p = self.tree / path.lstrip("/")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.mkdir(exist_ok=True) if kind == "d" else p.touch()
        p.chmod(mode)
        return p

    def run_migration(self, **extra):
        env = {**os.environ, "NOC_TEST_HOOKS": "1", "NOCTRAOS_SNAPSHOT": str(self.snap), "NOC_OWNERSHIP_ROOT": str(self.tree),
               "NOC_OWNERSHIP_FLATTENED": self.me, "NOC_OWNERSHIP_CHOWN": str(self.recorder), "NOC_OWNERSHIP_NO_LOOKUP": "1", **extra}
        return subprocess.run(["bash", str(MIGRATION)], capture_output=True, text=True, env=env)

    def chowned(self):
        return self.log.read_text().split() if self.log.exists() else []

    def test_a_flattened_file_gets_its_owner_and_keeps_its_setuid_bit(self):
        helper = self.make("/usr/lib/dbus-1.0/dbus-daemon-launch-helper", 0o4754)
        self.manifest("/usr/lib/dbus-1.0/dbus-daemon-launch-helper\troot\tmessagebus\t\n")
        out = self.run_migration()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("root:messagebus", self.chowned())
        self.assertIn(str(helper), self.chowned())
        self.assertEqual(stat.S_IMODE(helper.stat().st_mode), 0o4754)      # chown drops it; the migration puts it back
        self.assertIn("restored the owner of 1 ", out.stdout)

    def test_a_file_with_an_owner_someone_chose_is_left_alone(self):
        """On an otherwise flattened system, a file whose group was changed on purpose is not touched."""
        others = [g for g in os.getgroups() if g != os.getgid()]
        if not others:
            self.skipTest("this account is in no second group to give the file")
        chosen = self.make("/var/log/btmp", 0o660)
        os.chown(chosen, -1, others[0])
        self.manifest("/var/log/btmp\troot\tutmp\t\n/usr/bin/crontab\troot\tcrontab\t\n")
        out = self.run_migration()
        self.assertNotIn(str(chosen), self.chowned())
        self.assertIn(str(self.tree / "usr/bin/crontab"), self.chowned())      # the flattened one was repaired
        self.assertIn("restored the owner of 1 ", out.stdout)

    def test_missing_paths_and_comments_are_skipped(self):
        self.manifest("# a comment\n\n/not/there\troot\tshadow\t\n")
        out = self.run_migration()
        self.assertEqual((out.returncode, self.chowned()), (0, []))

    def test_a_recursive_rule_covers_the_tree(self):
        a = self.make("/var/cache/man/fr/cat1", 0o755, "d")
        b = self.make("/var/cache/man/fr/index.db", 0o644)
        self.manifest("/var/cache/man\tman\tman\tR\n")
        out = self.run_migration()
        self.assertEqual(out.returncode, 0, out.stderr)
        for p in (a, b, self.tree / "var/cache/man"):
            self.assertIn(str(p), self.chowned())

    def test_unknown_users_are_skipped_not_guessed(self):
        self.make("/etc/shadow", 0o640)
        self.manifest("/etc/shadow\tno-such-user-xyz\tno-such-group-xyz\t\n")
        out = self.run_migration(NOC_OWNERSHIP_NO_LOOKUP="")      # real lookup: neither exists
        self.assertEqual(self.chowned(), [])

    def test_a_system_that_never_was_flattened_is_left_alone(self):
        """Stock Ubuntu with the one-line installer, or an image built after the fix: no canary is root:root there."""
        self.make("/etc/ssl/private", 0o710, "d")
        self.manifest("/etc/ssl/private\troot\tssl-cert\t\n/usr/bin/crontab\troot\tcrontab\t\n")
        out = self.run_migration(NOC_OWNERSHIP_FLATTENED="nobody:nogroup")      # no canary has the flattened owner
        self.assertEqual((out.returncode, self.chowned()), (0, []))
        self.assertIn("already have their owners", out.stdout)

    def test_a_system_that_is_not_noctraos_is_left_alone_even_if_a_canary_is_root_owned(self):
        self.release.unlink()
        self.manifest("/usr/bin/crontab\troot\tcrontab\t\n")
        out = self.run_migration()
        self.assertEqual((out.returncode, self.chowned()), (0, []))
        self.assertIn("already have their owners", out.stdout)

    def test_any_one_flattened_canary_is_enough(self):
        (self.tree / "usr/bin/crontab").unlink()
        self.make("/usr/sbin/unix_chkpwd", 0o2755)
        self.manifest("/usr/sbin/unix_chkpwd\troot\tshadow\t\n")
        out = self.run_migration()
        self.assertIn("root:shadow", self.chowned())
        self.assertIn("restored the owner of 1 ", out.stdout)

    def test_a_failed_change_makes_the_migration_fail_so_the_updater_retries_it(self):
        self.make("/usr/lib/dbus-1.0/dbus-daemon-launch-helper", 0o4754)
        self.make("/etc/shadow", 0o640)
        self.manifest("/usr/lib/dbus-1.0/dbus-daemon-launch-helper\troot\tmessagebus\t\n/etc/shadow\troot\tshadow\t\n")
        out = self.run_migration(NOC_OWNERSHIP_CHOWN=str(self.failing))
        self.assertEqual(out.returncode, 1)
        self.assertIn("could not change the owner of /usr/lib/dbus-1.0/dbus-daemon-launch-helper", out.stdout)
        self.assertIn("could not change the owner of /etc/shadow", out.stdout)       # it kept going after the first failure
        self.assertIn("tried again at the next update", out.stdout)

    def test_a_failed_recursive_change_fails_too(self):
        self.make("/var/cache/man/fr/index.db", 0o644)
        self.manifest("/var/cache/man\tman\tman\tR\n")
        out = self.run_migration(NOC_OWNERSHIP_CHOWN=str(self.failing))
        self.assertEqual(out.returncode, 1)
        self.assertIn("could not change every owner below /var/cache/man", out.stdout)

    def test_success_still_exits_zero(self):
        self.manifest("/usr/bin/crontab\troot\tcrontab\t\n")
        self.assertEqual(self.run_migration().returncode, 0)

    def test_no_manifest_is_not_an_error(self):
        out = self.run_migration()
        self.assertEqual(out.returncode, 0)
        self.assertIn("nothing to do", out.stdout)

    def test_the_stand_ins_are_ignored_without_the_test_switch(self):
        self.make("/etc/shadow", 0o640)
        self.manifest("/etc/shadow\troot\tshadow\t\n")
        env = {k: v for k, v in os.environ.items() if k != "NOC_TEST_HOOKS"}
        env.update(NOCTRAOS_SNAPSHOT=str(self.snap), NOC_OWNERSHIP_ROOT=str(self.tree), NOC_OWNERSHIP_CHOWN=str(self.recorder),
                   NOC_OWNERSHIP_FLATTENED=self.me, NOC_OWNERSHIP_NO_LOOKUP="1")
        subprocess.run(["bash", str(MIGRATION)], capture_output=True, text=True, env=env)
        self.assertEqual(self.chowned(), [])        # a real run looks at the real / and the real chown, not these


if __name__ == "__main__":
    unittest.main()
