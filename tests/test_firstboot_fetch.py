"""The first-boot runner baked into the ISO (iso/build-noctraos-iso.sh) must get the LATEST provisioner even when git is missing,
and fall back to the baked snapshot only when GitHub cannot be reached or the download is broken.

The runner is cut out of the build script's heredoc and run with stub curl/git on a minimal PATH; nothing touches the network.
"""
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILD = (ROOT / "iso/build-noctraos-iso.sh").read_text()


def runner_text():
    start = BUILD.index("cat > \"$SQ_ROOT/usr/local/sbin/noctraos-firstboot\" <<'EOF'\n") + len("cat > \"$SQ_ROOT/usr/local/sbin/noctraos-firstboot\" <<'EOF'\n")
    return BUILD[start:BUILD.index("\nEOF\n", start)].replace("__NOCTRAOS_BRANCH__", "main") + "\n"


def tarball(marker, with_install=True):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        files = {"noctraos-main/VERSION": marker}
        if with_install:
            files["noctraos-main/install.sh"] = "#!/bin/sh\necho latest-provisioner\n"
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class Runner:
    def __init__(self, test, github_up=True, git=False, git_clone_ok=True, payload=None):
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        self.home = d / "home"
        self.home.mkdir()
        bindir = d / "bin"
        bindir.mkdir()
        # only the tools the runner needs: no git unless asked, so "git is missing" is real
        for tool in ("bash", "tar", "gzip", "mkdir", "rm", "cp", "mv", "cat", "chmod", "dirname", "tee", "mktemp", "touch", "date", "sh"):
            path = shutil.which(tool)
            if path:
                (bindir / tool).symlink_to(path)
        self.payload = d / "payload.tgz"
        self.payload.write_bytes(payload if payload is not None else tarball("from-tarball"))
        self.calls = d / "calls.log"
        self.calls.write_text("")
        (bindir / "curl").write_text(
            '#!/bin/sh\necho "curl $*" >> "%s"\n'
            'case "$*" in *-fsSI*) [ %s = 1 ] ;; *archive*) cat "%s" ;; *) exit 22 ;; esac\n' % (self.calls, 1 if github_up else 0, self.payload))
        (bindir / "curl").chmod(0o755)
        if git:
            (bindir / "git").write_text('#!/bin/sh\necho "git $*" >> "%s"\n[ %s = 1 ] || exit 128\nmkdir -p "$7"\n'
                                        'printf "#!/bin/sh\\necho git-provisioner\\n" > "$7/install.sh"\n' % (self.calls, 1 if git_clone_ok else 0))
            (bindir / "git").chmod(0o755)
        self.runner = d / "noctraos-firstboot"
        self.runner.write_text(runner_text())
        self.env = {"PATH": str(bindir), "HOME": str(self.home)}
        self.snapshot = d / "snapshot"
        # the runner copies /opt/noctraos; stand in for it with a rewritten path
        self.snapshot.mkdir()
        (self.snapshot / "install.sh").write_text("#!/bin/sh\necho baked-snapshot\n")
        self.runner.write_text(runner_text().replace("/opt/noctraos", str(self.snapshot)))

    def run(self):
        return subprocess.run([str(shutil.which("bash")), str(self.runner)], capture_output=True, text=True, env=self.env, stdin=subprocess.DEVNULL)

    def dest(self):
        return self.home / ".local/share/noctraos"


class FirstBootFetchTests(unittest.TestCase):
    def test_no_git_downloads_the_latest_as_a_tarball(self):
        r = Runner(self, git=False)
        out = r.run()
        self.assertIn("without git", out.stdout, out.stdout + out.stderr)
        self.assertEqual((r.dest() / "VERSION").read_text(), "from-tarball")
        self.assertIn("latest-provisioner", out.stdout)                 # install.sh of the tarball is what ran
        self.assertIn("https://github.com/dazeb/noctraos/archive/refs/heads/main.tar.gz", r.calls.read_text())

    def test_git_still_wins_when_it_is_there(self):
        r = Runner(self, git=True)
        out = r.run()
        self.assertIn("fetched from GitHub (latest)", out.stdout, out.stdout + out.stderr)
        self.assertIn("git-provisioner", out.stdout)
        self.assertNotIn("archive", r.calls.read_text())

    def test_a_failing_git_clone_falls_through_to_the_tarball(self):
        r = Runner(self, git=True, git_clone_ok=False)
        out = r.run()
        self.assertIn("without git", out.stdout, out.stdout + out.stderr)
        self.assertEqual((r.dest() / "VERSION").read_text(), "from-tarball")

    def test_no_network_uses_the_baked_snapshot(self):
        r = Runner(self, github_up=False)
        out = r.run()
        self.assertIn("baked-snapshot", out.stdout, out.stdout + out.stderr)
        self.assertNotIn("archive", r.calls.read_text())

    def test_a_broken_download_uses_the_baked_snapshot_and_leaves_nothing_behind(self):
        for payload in (b"not a tarball", tarball("x", with_install=False), tarball("x")[:40]):
            r = Runner(self, payload=payload)
            out = r.run()
            self.assertIn("baked-snapshot", out.stdout, out.stdout + out.stderr)
            self.assertFalse((r.dest() / "VERSION").exists())


if __name__ == "__main__":
    unittest.main()
