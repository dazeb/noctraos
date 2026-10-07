"""The release site updater, run on a throwaway copy of the real site files."""
import hashlib
import importlib.util
from pathlib import Path
import re
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("update_site", ROOT / "scripts/update-site-release.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
TRACKED = ["site/download.html", "site/index.html", "site/sitemap.xml", "proxmox-install.sh", "scripts/render-social.py"]


def fixture(directory):
    root = Path(directory) / "repo"
    for rel in TRACKED:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, root / rel)
    old = re.search(r'"softwareVersion":"([0-9.]+)"', (root / "site/download.html").read_text())[1]
    torrent = next(ROOT.glob("noctraos-*-amd64.iso.torrent"))
    shutil.copy(torrent, root / torrent.name)
    release = Path(directory) / "release"
    release.mkdir()
    contents = {"noctraos-9.8.7-amd64.iso": b"i" * 2_500_000, "noctraos-9.8.7.qcow2": b"q" * 5000,
                "noctraos-9.8.7.vmdk": b"v" * 7000}
    for name, data in contents.items():
        (release / name).write_bytes(data)
    shutil.copy(torrent, release / "noctraos-9.8.7-amd64.iso.torrent")
    (release / "SHA256SUMS").write_text("".join(f"{hashlib.sha256(d).hexdigest()}  {n}\n" for n, d in contents.items()))
    return root, release, old, contents


class UpdateSiteTests(unittest.TestCase):
    def test_every_old_version_string_moves_and_hashes_follow(self):
        with tempfile.TemporaryDirectory() as directory:
            root, release, old, contents = fixture(directory)
            self.assertEqual(MODULE.update(root, "9.8.7", release, "2030-01-02"), old)
            page = (root / "site/download.html").read_text()
            for rel in TRACKED[:2] + TRACKED[3:]:
                self.assertNotIn(old, (root / rel).read_text(), rel)
            for name, data in contents.items():
                self.assertIn(f"<code>{name}</code>", page)
                self.assertIn(f"SHA-256: {hashlib.sha256(data).hexdigest()}", page)
                self.assertIn(f"/releases/v9.8.7/{name}", page)
            self.assertIn("urn:btih:" + MODULE.infohash(root / "noctraos-9.8.7-amd64.iso.torrent"), page)
            self.assertIn("VERSION='9.8.7'", (root / "proxmox-install.sh").read_text())
            self.assertEqual(sorted(p.name for p in root.glob("*.torrent")), ["noctraos-9.8.7-amd64.iso.torrent"])
            sitemap = (root / "site/sitemap.xml").read_text()
            self.assertIn("/download</loc><lastmod>2030-01-02<", sitemap)

    def test_second_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root, release, _, _ = fixture(directory)
            MODULE.update(root, "9.8.7", release, "2030-01-02")
            first = {rel: (root / rel).read_bytes() for rel in TRACKED}
            MODULE.update(root, "9.8.7", release, "2030-01-02")
            self.assertEqual(first, {rel: (root / rel).read_bytes() for rel in TRACKED})

    def test_a_page_the_updater_does_not_understand_fails_loudly(self):
        with tempfile.TemporaryDirectory() as directory:
            root, release, _, _ = fixture(directory)
            page = root / "site/download.html"
            page.write_text(page.read_text().replace('<span class="hash">', '<span class="digest">'))
            with self.assertRaises(ValueError):
                MODULE.update(root, "9.8.7", release, None)

    def test_missing_release_file_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root, release, _, _ = fixture(directory)
            (release / "noctraos-9.8.7.vmdk").unlink()
            with self.assertRaises(FileNotFoundError):
                MODULE.update(root, "9.8.7", release, None)

    def test_infohash_matches_the_published_magnet(self):
        torrent = next(ROOT.glob("noctraos-*-amd64.iso.torrent"))
        page = (ROOT / "site/download.html").read_text()
        self.assertIn(MODULE.infohash(torrent), page)


if __name__ == "__main__":
    unittest.main()
