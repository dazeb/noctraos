"""bin/noc-selfupdate + scripts/make-update.py end to end in a sandbox: real ed25519 signing (ssh-keygen -Y),
file:// mirrors, a throwaway git repo as the source of bundles, NOC_UPDATE_ROOT as the machine. Nothing here
touches the network or the real system."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "bin/noc-selfupdate"
MAKE = ROOT / "scripts/make-update.py"
HAVE_SSH_KEYGEN = shutil.which("ssh-keygen") is not None


def sh(*argv, cwd=None, env=None, input=None):
    return subprocess.run([str(a) for a in argv], capture_output=True, text=True, cwd=cwd, env=env, input=input)


@unittest.skipUnless(HAVE_SSH_KEYGEN, "ssh-keygen is needed to sign and verify")
class Sandbox(unittest.TestCase):
    """One 'machine' (sandbox root), one 'publisher' (a git repo + a key), one or more mirrors."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.machine = self.tmp / "machine"
        self.repo = self.tmp / "repo"
        self.mirror = self.tmp / "mirror"
        self.home = self.tmp / "home"
        for d in (self.machine / "etc", self.machine / "usr/local/share/noctraos", self.home):
            d.mkdir(parents=True)
        (self.machine / "etc/machine-id").write_text("0123456789abcdef0123456789abcdef\n")
        self.key = self.tmp / "key"
        sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", self.key, "-C", "test")
        pub = (self.tmp / "key.pub").read_text().strip()
        (self.machine / "usr/local/share/noctraos/update-signers").write_text(
            f'release@noctraos.dev namespaces="noctraos-update" {pub}\n')
        self.write_config()
        self.init_repo()
        self.env = {**os.environ, "NOC_UPDATE_ROOT": str(self.machine), "NOC_UPDATE_USER_HOME": str(self.home),
                    "NOC_UPDATE_REFRESH_CMD": 'echo refreshed >> "$SNAPSHOT/../refresh.log"', "NOC_UPDATE_SMOKE": "ok"}
        self.serial = 0

    def tearDown(self):
        self._tmp.cleanup()

    # -- publisher side
    def write_config(self, channel="stable", mirrors=None):
        mirrors = mirrors or [f"file://{self.mirror}"]
        (self.machine / "etc/noctraos").mkdir(exist_ok=True)
        (self.machine / "etc/noctraos/update.json").write_text(json.dumps({"channel": channel, "mirrors": mirrors}))

    def git(self, *a):
        r = sh("git", "-C", self.repo, *a)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def init_repo(self):
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        self.commit({"VERSION": "9.9.1\n", "install.sh": "#!/bin/sh\n", "install/lib.sh": "# lib\n",
                     "install/07_persistence.sh": "#!/bin/sh\n", "bin/noc": "#!/bin/sh\necho v1\n",
                     "migrations/system/0001_first.sh": "#!/bin/sh\necho ran >> \"$NOCTRAOS_SNAPSHOT/../system-ran\"\n",
                     "migrations/user/0001_first.sh": "#!/bin/sh\necho ran >> \"$HOME/user-ran\"\n"})

    def commit(self, files, remove=()):
        for name, text in files.items():
            p = self.repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
            if text.startswith("#!"):
                p.chmod(0o755)
        for name in remove:
            (self.repo / name).unlink()
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "c", "--allow-empty")

    def publish(self, channel="stable", rollout=100, mirror=None, key=None, expires_days=30, notes="Test update.",
                relogin=False, serial=None, extra=()):
        mirror = mirror or self.mirror
        self.serial = serial or self.serial + 1
        menv = {**os.environ, "NOC_UPDATE_REPO": str(self.repo)}
        r = sh(sys.executable, MAKE, "bundle", "--ref", "HEAD", "--serial", self.serial, "--out", mirror, env=menv)
        self.assertEqual(r.returncode, 0, r.stderr)
        args = [sys.executable, MAKE, "manifest", "--bundle-json", mirror / "bundle.json", "--channel", channel,
                "--rollout", rollout, "--key", key or self.key, "--out", mirror, "--expires-days", expires_days,
                "--notes", notes, *extra]
        if relogin:
            args.append("--relogin")
        r = sh(*args, env=menv)
        self.assertEqual(r.returncode, 0, r.stderr)

    # -- client side
    def client(self, *a, user="tester"):
        env = {**self.env, "SUDO_USER": user}
        return sh(sys.executable, CLIENT, *a, env=env)

    def check(self):
        r = self.client("check", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def state(self):
        return json.loads((self.machine / "var/lib/noctraos/update-state.json").read_text())

    def snap(self, name=""):
        return self.machine / "usr/local/share/noctraos/repo" / name


class ApplyTests(Sandbox):
    def test_a_signed_update_is_checked_applied_and_migrated_once(self):
        self.publish()
        c = self.check()
        self.assertEqual(c["status"], "available")
        self.assertEqual(c["available"]["serial"], 1)
        self.assertEqual(c["installed"]["serial"], 0)
        r = self.client("apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Updated to NoctraOS 9.9.1 (update 1)", r.stdout)
        self.assertEqual(self.snap("VERSION").read_text().strip(), "9.9.1")
        self.assertEqual(self.state()["serial"], 1)
        self.assertEqual((self.machine / "usr/local/share/noctraos/refresh.log").read_text().count("refreshed"), 1)
        self.assertEqual((self.machine / "usr/local/share/noctraos/system-ran").read_text().count("ran"), 1)
        self.assertEqual((self.home / "user-ran").read_text().count("ran"), 1)
        # nothing newer: a second apply changes nothing and re-runs nothing
        r = self.client("apply")
        self.assertEqual(r.returncode, 0)
        self.assertEqual((self.machine / "usr/local/share/noctraos/system-ran").read_text().count("ran"), 1)
        self.assertEqual(self.check()["status"], "current")

    def test_only_new_migrations_run_on_the_next_update(self):
        self.publish()
        self.client("apply")
        self.commit({"migrations/system/0002_second.sh": "#!/bin/sh\necho two >> \"$NOCTRAOS_SNAPSHOT/../system-ran\"\n"})
        self.publish()
        self.assertEqual(self.client("apply").returncode, 0)
        ran = (self.machine / "usr/local/share/noctraos/system-ran").read_text().split()
        self.assertEqual(ran, ["ran", "two"])
        self.assertEqual(self.state()["serial"], 2)
        self.assertEqual(self.state()["previous"]["serial"], 1)

    def test_a_failed_migration_is_recorded_and_tried_again_without_blocking_the_update(self):
        self.commit({"migrations/system/0002_flaky.sh":
                     "#!/bin/sh\n[ -e \"$NOCTRAOS_SNAPSHOT/../fixed\" ] || exit 3\necho ok >> \"$NOCTRAOS_SNAPSHOT/../flaky-ok\"\n"})
        self.publish()
        r = self.client("apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("0002_flaky.sh", r.stdout)
        self.assertEqual(self.state()["serial"], 1)
        self.assertEqual(self.check()["failed_migrations"], ["0002_flaky.sh"])
        (self.machine / "usr/local/share/noctraos/fixed").write_text("")
        self.assertEqual(self.client("migrate", "--scope", "system").returncode, 0)
        self.assertEqual(self.check()["failed_migrations"], [])
        self.assertTrue((self.machine / "usr/local/share/noctraos/flaky-ok").exists())

    def test_relogin_note_is_shown_and_flagged(self):
        self.publish(relogin=True)
        r = self.client("apply")
        self.assertIn("Sign out and back in", r.stdout)
        self.assertTrue(self.check()["relogin_required"])

    def test_staged_rollout_holds_back_until_the_machine_is_in(self):
        self.publish(rollout=0)
        self.assertEqual(self.check()["status"], "staged")
        r = self.client("apply")
        self.assertEqual(r.returncode, 0)
        self.assertFalse(self.snap().exists())
        self.publish(rollout=100, serial=1)   # same serial widened to everyone
        self.assertEqual(self.check()["status"], "available")

    def test_rollout_buckets_differ_per_serial_and_spread_out(self):
        sys.path.insert(0, str(ROOT / "bin"))
        from importlib.machinery import SourceFileLoader
        mod = SourceFileLoader("selfupdate", str(CLIENT)).load_module()
        os.environ["NOC_UPDATE_ROOT"] = str(self.machine)
        try:
            buckets = {mod.machine_bucket(s) for s in range(1, 40)}
        finally:
            os.environ.pop("NOC_UPDATE_ROOT", None)
        self.assertTrue(all(0 <= b < 100 for b in buckets))
        self.assertGreater(len(buckets), 20)


class RefusalTests(Sandbox):
    def untouched(self, r):
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertFalse(self.snap().exists(), "the snapshot must not have been created")
        self.assertFalse((self.machine / "var/lib/noctraos/update-state.json").exists())

    def test_a_tampered_manifest_is_refused(self):
        self.publish()
        m = self.mirror / "stable/manifest.json"
        data = json.loads(m.read_text())
        data["bundle"]["sha256"] = "0" * 64
        m.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
        r = self.client("apply")
        self.untouched(r)
        self.assertEqual(self.check()["status"], "unverified")

    def test_a_manifest_signed_by_another_key_is_refused(self):
        other = self.tmp / "other"
        sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", other)
        self.publish(key=other)
        self.untouched(self.client("apply"))

    def test_a_bundle_that_does_not_match_the_signed_hash_is_refused(self):
        self.publish()
        bundle = self.mirror / "bundles/noctraos-1.tar.gz"
        data = bundle.read_bytes()
        bundle.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        r = self.client("apply")
        self.untouched(r)
        self.assertIn("matches the signed manifest", r.stderr)

    def test_an_expired_manifest_is_never_applied(self):
        self.publish(expires_days=-1)
        self.assertEqual(self.check()["status"], "expired")
        r = self.client("apply")
        self.assertFalse(self.snap().exists())
        self.assertIn("out of date", r.stdout)

    def test_a_manifest_for_another_channel_is_refused(self):
        self.publish(channel="nightly")
        (self.mirror / "stable").mkdir(exist_ok=True)
        for f in ("manifest.json", "manifest.json.sig"):
            shutil.copy(self.mirror / "nightly" / f, self.mirror / "stable" / f)
        self.untouched(self.client("apply"))

    def test_an_older_serial_is_never_installed(self):
        self.publish()
        self.client("apply")
        self.commit({"VERSION": "9.9.0\n"})
        old = self.tmp / "oldmirror"
        self.publish(mirror=old, serial=1)   # same serial: current
        self.write_config(mirrors=[f"file://{old}"])
        self.assertEqual(self.check()["status"], "current")
        self.assertEqual(self.client("apply").returncode, 0)
        self.assertEqual(self.state()["serial"], 1)

    def test_http_mirrors_are_not_accepted(self):
        self.write_config(mirrors=["http://example.com/updates"])
        r = self.client("check", "--json")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("https://", r.stderr)

    def test_unknown_channel_is_refused(self):
        self.write_config(channel="beta")
        self.assertNotEqual(self.client("check", "--json").returncode, 0)


class BundleSafetyTests(Sandbox):
    def crafted(self, members):
        """A bundle with hand-made members, correctly hashed and signed: the unpacker is the only defence."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as t:
            for name, kind, payload in members:
                info = tarfile.TarInfo(name)
                if kind == "file":
                    info.size = len(payload)
                    t.addfile(info, io.BytesIO(payload))
                elif kind == "symlink":
                    info.type, info.linkname = tarfile.SYMTYPE, payload
                    t.addfile(info)
        data = buf.getvalue()
        (self.mirror / "bundles").mkdir(parents=True, exist_ok=True)
        (self.mirror / "bundles/noctraos-1.tar.gz").write_bytes(data)
        info = {"serial": 1, "version": "9.9.1", "commit": "x", "path": "bundles/noctraos-1.tar.gz",
                "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        (self.mirror / "bundle.json").write_text(json.dumps(info))
        r = sh(sys.executable, MAKE, "manifest", "--bundle-json", self.mirror / "bundle.json", "--channel", "stable",
               "--key", self.key, "--out", self.mirror)
        self.assertEqual(r.returncode, 0, r.stderr)

    def apply_refused(self, members, text):
        self.crafted(members)
        r = self.client("apply")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn(text, r.stderr)
        self.assertFalse(self.snap().exists())

    def test_path_traversal_is_refused(self):
        self.apply_refused([("../evil", "file", b"x")], "unsafe path")

    def test_absolute_paths_are_refused(self):
        self.apply_refused([("/etc/passwd", "file", b"x")], "unsafe path")

    def test_symlinks_are_refused(self):
        self.apply_refused([("bin/noc", "symlink", "/etc/shadow")], "plain file")

    def test_files_outside_the_allowed_layout_are_refused(self):
        self.apply_refused([("etc/cron.d/evil", "file", b"x")], "outside the allowed layout")

    def test_a_bundle_whose_metadata_disagrees_with_the_manifest_is_refused(self):
        self.apply_refused([("VERSION", "file", b"9.9.1\n"), (".update.json", "file", b'{"serial": 7}')],
                           "does not match the manifest")


class RollbackTests(Sandbox):
    def test_a_failed_smoke_test_puts_the_previous_version_back(self):
        self.publish()
        self.client("apply")
        self.commit({"bin/noc": "#!/bin/sh\necho v2\n", "VERSION": "9.9.2\n"})
        self.publish()
        self.env["NOC_UPDATE_SMOKE"] = "fail"
        r = self.client("apply")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("rolled back", r.stderr)
        self.assertEqual(self.snap("VERSION").read_text().strip(), "9.9.1")
        self.assertEqual(self.state()["serial"], 1)
        self.assertFalse((self.snap().parent / "repo.failed").exists())
        # the failed update is held: not offered again, but the next one is
        self.assertEqual(self.check()["status"], "held")
        self.env["NOC_UPDATE_SMOKE"] = "ok"
        self.assertEqual(self.client("apply").returncode, 0)
        self.assertEqual(self.state()["serial"], 1)
        self.commit({"VERSION": "9.9.3\n"})
        self.publish()
        self.assertEqual(self.check()["status"], "available")
        self.assertEqual(self.client("apply").returncode, 0)
        self.assertEqual(self.state()["serial"], 3)
        # refreshes: first update, the failed one, its undo, and the later good update (the held one ran nothing)
        self.assertEqual((self.machine / "usr/local/share/noctraos/refresh.log").read_text().count("refreshed"), 4)

    def test_a_failed_refresh_rolls_back_too(self):
        self.publish()
        self.client("apply")
        self.commit({"VERSION": "9.9.2\n"})
        self.publish()
        self.env["NOC_UPDATE_REFRESH_CMD"] = 'test "$(cat "$SNAPSHOT/VERSION")" = 9.9.1'
        r = self.client("apply")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.snap("VERSION").read_text().strip(), "9.9.1")

    def test_the_first_update_failing_leaves_no_half_installed_snapshot_state(self):
        self.publish()
        self.env["NOC_UPDATE_SMOKE"] = "fail"
        r = self.client("apply")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual((self.state()["serial"], self.state()["held"]), (0, 1))   # nothing installed, update held
        self.assertFalse(self.snap().exists())

    def test_rollback_command_restores_the_previous_snapshot_and_serial(self):
        self.publish()
        self.client("apply")
        self.commit({"VERSION": "9.9.2\n"})
        self.publish()
        self.client("apply")
        self.assertEqual(self.snap("VERSION").read_text().strip(), "9.9.2")
        r = self.client("rollback")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.snap("VERSION").read_text().strip(), "9.9.1")
        self.assertEqual(self.state()["serial"], 1)
        self.assertNotEqual(self.client("rollback").returncode, 0)   # only one step back
        self.assertEqual(self.check()["status"], "held")             # the update we left is not offered again

    def test_an_interrupted_swap_is_recovered_on_the_next_run(self):
        self.publish()
        self.client("apply")
        snap = self.snap()
        os.rename(snap, str(snap) + ".prev")   # crashed between the two renames
        (Path(str(snap) + ".new")).mkdir()
        r = self.client("apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.snap("VERSION").read_text().strip(), "9.9.1")
        self.assertFalse(Path(str(snap) + ".new").exists())


class MirrorTests(Sandbox):
    def test_the_highest_verified_serial_wins_and_a_dead_mirror_is_survivable(self):
        stale, fresh = self.tmp / "stale", self.tmp / "fresh"
        self.publish(mirror=stale)
        self.commit({"VERSION": "9.9.2\n"})
        self.publish(mirror=fresh)
        self.write_config(mirrors=[f"file://{self.tmp}/dead", f"file://{stale}", f"file://{fresh}"])
        c = self.check()
        self.assertEqual(c["status"], "available")
        self.assertEqual(c["available"]["serial"], 2)
        self.assertEqual(self.client("apply").returncode, 0)
        self.assertEqual(self.state()["serial"], 2)

    def test_a_bad_bundle_on_one_mirror_falls_through_to_the_next(self):
        a, b = self.tmp / "a", self.tmp / "b"
        self.publish(mirror=a)
        shutil.copytree(a, b)
        (a / "bundles/noctraos-1.tar.gz").write_bytes(b"garbage")
        self.write_config(mirrors=[f"file://{a}", f"file://{b}"])
        self.assertEqual(self.client("apply").returncode, 0)
        self.assertEqual(self.state()["serial"], 1)

    def test_nothing_reachable_is_reported_as_offline_not_current(self):
        self.write_config(mirrors=[f"file://{self.tmp}/nowhere"])
        c = self.check()
        self.assertEqual(c["status"], "unreachable")
        self.assertFalse(c["online"])


class HttpTests(Sandbox):
    """The real HTTP path, against a throwaway server on 127.0.0.1 (the only plain-http host test mode allows)."""

    def serve(self, directory):
        import functools
        import http.server
        import threading
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
        handler.log_message = lambda *a, **k: None
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}"

    def test_an_empty_channel_is_current_not_offline(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        self.write_config(mirrors=[self.serve(empty)])
        c = self.check()
        self.assertEqual((c["status"], c["online"]), ("current", True))
        self.assertIn("published", c["detail"])
        r = self.client("apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("No NoctraOS updates have been published", r.stdout)

    def test_a_host_that_answers_403_for_a_missing_manifest_counts_as_nothing_published(self):
        """S3-style storage (the Hetzner bucket) says 403, not 404, for a key that does not exist."""
        import http.server
        import threading

        class Forbidden(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_error(403)

            def log_message(self, *a):
                pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Forbidden)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.write_config(mirrors=[f"http://127.0.0.1:{server.server_address[1]}"])
        c = self.check()
        self.assertEqual((c["status"], c["online"]), ("current", True))
        self.assertIn("published", c["detail"])

    def test_one_mirror_saying_nothing_is_published_is_enough_when_another_is_unreachable(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        self.write_config(mirrors=[self.serve(empty), "http://127.0.0.1:9"])   # 404 here, unreachable there
        self.assertEqual(self.check()["status"], "current")                       # a mirror that answers is enough

    def test_a_server_that_is_down_is_offline(self):
        self.write_config(mirrors=["http://127.0.0.1:9"])
        c = self.check()
        self.assertEqual((c["status"], c["online"]), ("unreachable", False))

    def test_an_update_applies_over_http(self):
        self.publish()
        self.write_config(mirrors=[self.serve(self.mirror)])
        self.assertEqual(self.check()["status"], "available")
        r = self.client("apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.state()["serial"], 1)


class ConfigTests(Sandbox):
    def test_set_channel_persists_and_validates(self):
        self.assertEqual(self.client("set-channel", "nightly").returncode, 0)
        self.assertEqual(json.loads((self.machine / "etc/noctraos/update.json").read_text())["channel"], "nightly")
        self.assertEqual(self.check()["channel"], "nightly")
        self.assertNotEqual(self.client("set-channel", "../x").returncode, 0)

    def test_serial_helper_continues_from_the_highest_manifest(self):
        self.publish(channel="nightly")
        self.publish(channel="stable", serial=7)
        r = sh(sys.executable, MAKE, "serial", self.mirror / "nightly/manifest.json", self.mirror / "stable/manifest.json",
               self.mirror / "missing.json")
        self.assertEqual(r.stdout.strip(), "8")

    def test_promotion_keeps_the_bundle_and_serial(self):
        self.publish(channel="nightly")
        n = json.loads((self.mirror / "nightly/manifest.json").read_text())
        r = sh(sys.executable, MAKE, "manifest", "--from-manifest", self.mirror / "nightly/manifest.json", "--channel",
               "stable", "--rollout", "10", "--key", self.key, "--out", self.mirror)
        self.assertEqual(r.returncode, 0, r.stderr)
        s = json.loads((self.mirror / "stable/manifest.json").read_text())
        self.assertEqual((s["serial"], s["bundle"], s["rollout"]["percent"], s["channel"]),
                         (n["serial"], n["bundle"], 10, "stable"))
        self.assertEqual(self.check()["channel"], "stable")


class BuildTests(unittest.TestCase):
    def test_the_three_item_lists_agree(self):
        """The bundle, the client's allowlist and module 07's snapshot must name the same top-level items."""
        client = _list_from(CLIENT.read_text(), "BUNDLE_ITEMS")
        make = _list_from(MAKE.read_text(), "ITEMS")
        module = (ROOT / "install/07_persistence.sh").read_text()
        line = next(l for l in module.splitlines() if l.startswith("for item in "))
        shell = line[len("for item in "):].split(";")[0].split()
        self.assertEqual(client, make)
        self.assertEqual(sorted(client), sorted(shell))

    def test_the_real_tree_bundles_reproducibly_without_symlinks(self):
        if not HAVE_SSH_KEYGEN:
            self.skipTest("no ssh-keygen")
        with tempfile.TemporaryDirectory() as d:
            for n in ("a", "b"):
                r = sh(sys.executable, MAKE, "bundle", "--ref", "HEAD", "--serial", "1", "--out", Path(d) / n)
                self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((Path(d) / "a/bundles/noctraos-1.tar.gz").read_bytes(),
                             (Path(d) / "b/bundles/noctraos-1.tar.gz").read_bytes())
            with tarfile.open(Path(d) / "a/bundles/noctraos-1.tar.gz") as t:
                names = t.getnames()
                self.assertIn(".update.json", names)
                self.assertIn("bin/noc", names)
                self.assertFalse([n for n in names if n.startswith(("assets/promo", "assets/social", "tests", "docs"))])
                self.assertTrue(all(m.isfile() or m.isdir() for m in t.getmembers()))


def _list_from(text, name):
    import ast
    start = text.index(f"{name} = [")
    return ast.literal_eval(text[start + len(name) + 3:text.index("]", start) + 1])


if __name__ == "__main__":
    unittest.main()
