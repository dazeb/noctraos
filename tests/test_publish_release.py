"""iso/publish-release.sh with rclone, curl and gh stubbed: resume after a partial upload, refuse a
different build of the same version, and never overwrite. No network, no bucket."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "iso/publish-release.sh"
VERSION = (ROOT / "VERSION").read_text().strip()
NAMES = [f"noctraos-{VERSION}-amd64.iso", f"noctraos-{VERSION}.qcow2", f"noctraos-{VERSION}.vmdk"]

RCLONE = r'''#!/usr/bin/env bash
# stub: lsf prints $STUB_REMOTE_LISTING (or fails), cat prints $STUB_REMOTE/<name>, copyto logs
case "$1" in
  lsf) [ -z "${STUB_LSF_FAIL:-}" ] || exit 1; cat "$STUB_LISTING" ;;
  cat) cat "$STUB_REMOTE/$(basename "$2")" ;;
  copyto) echo "$3" >> "$STUB_LOG" ;;
esac
'''
CURL = r'''#!/usr/bin/env bash
cat "$STUB_REL/$(basename "${@: -1}")"
'''
GH = r'''#!/usr/bin/env bash
[ "$1 $2" = "release view" ] && exit 1
echo "gh $*" >> "$STUB_LOG"
'''


def run(listing, remote_files=None, lsf_fail=False, edit=None):
    with tempfile.TemporaryDirectory() as directory:
        d = Path(directory)
        rel = d / "build/release" / f"v{VERSION}"
        rel.mkdir(parents=True)
        for name in NAMES:
            (rel / name).write_bytes(name.encode() * 3)
        (rel / f"noctraos-{VERSION}-amd64.iso.torrent").write_bytes(b"t")
        (rel / "BUILD-INFO.txt").write_text("login: noctraos\n")
        (rel / "SHA256SUMS").write_text("".join(
            f"{__import__('hashlib').sha256((rel / n).read_bytes()).hexdigest()}  {n}\n" for n in NAMES))
        remote = d / "remote"
        remote.mkdir()
        for name, data in (remote_files or {}).items():
            (remote / name).write_bytes(data(rel) if callable(data) else data)
        (d / "listing").write_text(listing(rel) if callable(listing) else listing)
        bin_dir = d / "bin"
        bin_dir.mkdir()
        for tool, body in (("rclone", RCLONE), ("curl", CURL), ("gh", GH)):
            (bin_dir / tool).write_text(body)
            (bin_dir / tool).chmod(0o755)
        if edit:
            edit(rel)
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "R2_ACCESS_KEY_ID": "x",
               "R2_SECRET_ACCESS_KEY": "x", "R2_ENDPOINT": "x", "R2_BUCKET": "b", "STUB_LISTING": str(d / "listing"),
               "STUB_REMOTE": str(remote), "STUB_LOG": str(d / "log"), "STUB_REL": str(rel),
               "STUB_LSF_FAIL": "1" if lsf_fail else ""}
        result = subprocess.run(["bash", str(SCRIPT), str(d / "build")], capture_output=True, text=True, env=env)
        log = (d / "log").read_text().splitlines() if (d / "log").exists() else []
        return result, log


def listing_of(names):
    return lambda rel: "".join(f"{n}|{(rel / n).stat().st_size}\n" for n in names)


class PublishTests(unittest.TestCase):
    def test_fresh_release_uploads_files_then_checksums_then_creates_the_release(self):
        result, log = run("")
        self.assertEqual(result.returncode, 0, result.stderr)
        uploads = [line for line in log if not line.startswith("gh ")]
        self.assertEqual([Path(u).name for u in uploads], NAMES + ["SHA256SUMS"])
        self.assertTrue(any(line.startswith("gh release create") for line in log))

    def test_resumes_after_a_partial_upload_without_reuploading(self):
        done = NAMES[:2]
        result, log = run(listing_of(done))
        self.assertEqual(result.returncode, 0, result.stderr)
        uploads = [Path(line).name for line in log if not line.startswith("gh ")]
        self.assertEqual(uploads, [NAMES[2], "SHA256SUMS"])

    def test_a_different_build_of_the_same_version_is_refused(self):
        result, log = run(lambda rel: f"{NAMES[0]}|12345\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not overwriting", result.stderr)
        self.assertEqual(log, [])

    def test_different_checksums_are_refused(self):
        result, log = run(listing_of(NAMES + ["SHA256SUMS"]), remote_files={"SHA256SUMS": b"other  file\n"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("differs", result.stderr)
        self.assertEqual(log, [])

    def test_a_failed_listing_is_never_treated_as_empty(self):
        result, log = run("", lsf_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not list", result.stderr)
        self.assertEqual(log, [])

    def test_a_rehearsal_cannot_be_published(self):
        result, log = run("", edit=lambda rel: (rel / "BUILD-INFO.txt").write_text("rehearsal: yes\n"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rehearsal", result.stderr)
        self.assertEqual(log, [])


if __name__ == "__main__":
    unittest.main()
