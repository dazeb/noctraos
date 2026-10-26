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
    shutil.copy(torrent, root / "site" / torrent.name)
    release = Path(directory) / "release"
    release.mkdir()
    contents = {"noctraos-9.8.7-amd64.iso": b"i" * 2_500_000, "noctraos-9.8.7.qcow2": b"q" * 5000,
                "noctraos-9.8.7.vmdk": b"v" * 7000}
    for name, data in contents.items():
        (release / name).write_bytes(data)
    shutil.copy(torrent, release / "noctraos-9.8.7-amd64.iso.torrent")
    (release / "SHA256SUMS").write_text("".join(f"{hashlib.sha256(d).hexdigest()}  {n}\n" for n, d in contents.items()))
    return root, release, old, contents


def kubuntu_fixture(directory):
    torrent = next(ROOT.glob("noctraos-*-amd64.iso.torrent"))
    release = Path(directory) / "release-kubuntu"
    release.mkdir()
    contents = {"noctraos-9.8.7-kubuntu-amd64.iso": b"k" * 3_100_000, "noctraos-9.8.7-kubuntu.qcow2": b"Q" * 6000,
                "noctraos-9.8.7-kubuntu.vmdk": b"V" * 8000}
    for name, data in contents.items():
        (release / name).write_bytes(data)
    # a different torrent from the GNOME one, so the two magnets differ
    data = torrent.read_bytes().replace(b"noctraos-", b"noctraoz-", 1)
    (release / "noctraos-9.8.7-kubuntu-amd64.iso.torrent").write_bytes(data)
    (release / "SHA256SUMS").write_text("".join(f"{hashlib.sha256(d).hexdigest()}  {n}\n" for n, d in contents.items()))
    return release, contents


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
            self.assertEqual(sorted(p.name for p in (root / "site").glob("*.torrent")), ["noctraos-9.8.7-amd64.iso.torrent"])
            self.assertIn('href="noctraos-9.8.7-amd64.iso.torrent" download', page)
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

    def test_gnome_links_move_from_the_old_host_to_the_download_host(self):
        with tempfile.TemporaryDirectory() as directory:
            root, release, _, _ = fixture(directory)
            page = root / "site/download.html"
            page.write_text(page.read_text().replace(MODULE.DOWNLOAD + "/", "https://dl.noctraos.dev/releases/"))
            MODULE.update(root, "9.8.7", release, None)
            text = page.read_text()
            self.assertNotIn("dl.noctraos.dev", text)
            self.assertIn(MODULE.DOWNLOAD + "/v9.8.7/noctraos-9.8.7-amd64.iso", text)

    def test_missing_release_file_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root, release, _, _ = fixture(directory)
            (release / "noctraos-9.8.7.vmdk").unlink()
            with self.assertRaises(FileNotFoundError):
                MODULE.update(root, "9.8.7", release, None)

    def test_kubuntu_section_links_its_own_folder_and_keeps_both_torrents(self):
        with tempfile.TemporaryDirectory() as directory:
            root, release, old, _ = fixture(directory)
            kubuntu, contents = kubuntu_fixture(directory)
            MODULE.update(root, "9.8.7", release, None, kubuntu)
            page = (root / "site/download.html").read_text()
            section = page[page.index(MODULE.PLASMA_START):page.index(MODULE.PLASMA_END)]
            self.assertIn("preview", section)
            for name, data in contents.items():
                self.assertIn(f"/releases/v9.8.7/kubuntu/{name}", section)
                self.assertIn(f"SHA-256: {hashlib.sha256(data).hexdigest()}", section)
            self.assertIn("/releases/v9.8.7/kubuntu/SHA256SUMS", section)
            self.assertIn("ws=https%3A%2F%2Fnoctraos-releases.fsn1.your-objectstorage.com%2Freleases%2Fv9.8.7%2Fkubuntu%2Fnoctraos-9.8.7-kubuntu-amd64.iso", section)
            self.assertIn("urn:btih:" + MODULE.infohash(kubuntu / "noctraos-9.8.7-kubuntu-amd64.iso.torrent"), section)
            # the GNOME magnet still points at the GNOME ISO, outside the section
            rest = page.replace(section, "")
            self.assertIn("urn:btih:" + MODULE.infohash(release / "noctraos-9.8.7-amd64.iso.torrent"), rest)
            self.assertNotIn(old, page)
            want = ["noctraos-9.8.7-amd64.iso.torrent", "noctraos-9.8.7-kubuntu-amd64.iso.torrent"]
            self.assertEqual(sorted(p.name for p in root.glob("*.torrent")), want)
            self.assertEqual(sorted(p.name for p in (root / "site").glob("*.torrent")), want)

    def test_kubuntu_second_run_changes_nothing_and_a_gnome_only_run_empties_the_section(self):
        with tempfile.TemporaryDirectory() as directory:
            root, release, _, _ = fixture(directory)
            kubuntu, _ = kubuntu_fixture(directory)
            MODULE.update(root, "9.8.7", release, None, kubuntu)
            first = {rel: (root / rel).read_bytes() for rel in TRACKED}
            MODULE.update(root, "9.8.7", release, None, kubuntu)
            self.assertEqual(first, {rel: (root / rel).read_bytes() for rel in TRACKED})
            MODULE.update(root, "9.8.7", release, None)
            page = (root / "site/download.html").read_text()
            self.assertIn(MODULE.PLASMA_START + "\n" + MODULE.PLASMA_END, page)
            self.assertNotIn("kubuntu", page.lower().replace(MODULE.PLASMA_START.lower(), "").replace(MODULE.PLASMA_END.lower(), ""))
            self.assertEqual([p.name for p in root.glob("*kubuntu*.torrent")], [])

    def test_a_page_without_the_kubuntu_markers_fails_loudly(self):
        with tempfile.TemporaryDirectory() as directory:
            root, release, _, _ = fixture(directory)
            page = root / "site/download.html"
            page.write_text(page.read_text().replace(MODULE.PLASMA_END, ""))
            with self.assertRaises(ValueError):
                MODULE.update(root, "9.8.7", release, None)

    def test_infohash_matches_the_published_magnet(self):
        torrent = next(ROOT.glob("noctraos-*-amd64.iso.torrent"))
        page = (ROOT / "site/download.html").read_text()
        self.assertIn(MODULE.infohash(torrent), page)

    def test_the_site_serves_its_own_copy_of_the_torrent(self):
        torrent = next(ROOT.glob("noctraos-*-amd64.iso.torrent"))
        copy = ROOT / "site" / torrent.name
        self.assertTrue(copy.is_file(), "site/ has no copy of the torrent")
        self.assertEqual(copy.read_bytes(), torrent.read_bytes())
        self.assertIn(f'href="{torrent.name}" download', (ROOT / "site/download.html").read_text())


if __name__ == "__main__":
    unittest.main()
