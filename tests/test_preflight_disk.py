"""The first-boot preflight offers to use the unused disk space, and says up front when that installs a package. This runs the
real disk-space block of install/00_preflight.sh under a pseudo-terminal (the prompt only appears on a terminal) with a stub
`noc-disk` and the answer "n", so nothing is ever changed."""
import os
from pathlib import Path
import pty
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "install/00_preflight.sh").read_text()


def disk_block():
    start = SCRIPT.index('log "Checking disk space..."')
    end = SCRIPT.index('log "OK: ${avail_gb}GiB free on /"')
    return SCRIPT[start:end]


def run_block(status_json, answer="n\n"):
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "repo"
        (repo / "bin").mkdir(parents=True)
        (repo / "bin/noc-disk").write_text(f"#!/usr/bin/env python3\nprint({status_json!r})\n")
        harness = Path(d) / "harness.sh"
        harness.write_text(
            'REPO_ROOT="%s"; TARGET_HOME="%s"\nlog() { echo "LOG: $*"; }\nwarn() { echo "WARN: $*"; }\n'
            'die() { echo "DIE: $*"; exit 1; }\ndf() { echo "Avail"; echo "18G"; }\nsudo() { echo "SUDO-WOULD-RUN: $*"; return 0; }\n%s\n'
            'echo "CONTINUED"\n' % (repo, d, disk_block()))
        pid, fd = pty.fork()
        if pid == 0:
            os.execvp("bash", ["bash", str(harness)])
        os.write(fd, answer.encode())
        out = b""
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
        os.waitpid(pid, 0)
        return re.sub(r"\x1b\[[0-9;]*m", "", out.decode(errors="replace")).replace("\r", "")


GROWABLE = ('{"can_grow": true, "expandable_bytes": %d, "needs_fdisk": %s}')


class PreflightDiskTests(unittest.TestCase):
    def test_the_fdisk_install_is_disclosed_before_the_question(self):
        out = run_block(GROWABLE % (33 * 2**30, "true"))
        self.assertIn("The disk has 33GiB", out)
        self.assertIn("installs a small partition tool (fdisk)", out)
        self.assertIn("needs the internet", out)
        self.assertIn("system libraries", out)
        self.assertLess(out.index("fdisk"), out.index("[Y/n]"))

    def test_nothing_about_packages_when_sfdisk_is_already_there(self):
        out = run_block(GROWABLE % (33 * 2**30, "false"))
        self.assertIn("[Y/n]", out)
        self.assertNotIn("fdisk", out)

    def test_answering_no_changes_nothing(self):
        out = run_block(GROWABLE % (33 * 2**30, "true"), answer="n\n")
        self.assertNotIn("SUDO-WOULD-RUN", out)
        self.assertIn("DIE: Only 18GiB free", out)

    def test_answering_yes_runs_the_grow_through_sudo(self):
        out = run_block(GROWABLE % (33 * 2**30, "true"), answer="y\n")
        self.assertIn("SUDO-WOULD-RUN: python3", out)
        self.assertIn("noc-disk grow", out)

    def test_no_offer_at_all_when_there_is_nothing_to_grow(self):
        out = run_block('{"can_grow": false, "expandable_bytes": 0, "needs_fdisk": false}')
        self.assertNotIn("[Y/n]", out)
        self.assertIn("DIE: Only 18GiB free", out)


if __name__ == "__main__":
    unittest.main()
