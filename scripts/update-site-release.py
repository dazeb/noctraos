#!/usr/bin/env python3
"""Point the website, the Proxmox script and the social-card source at a new release.

    scripts/update-site-release.py <version> <release-dir> [--kubuntu <release-dir>] [--root <repo>] [--date YYYY-MM-DD]

<release-dir> is what iso/build-release.sh wrote: noctraos-<v>-amd64.iso, noctraos-<v>.qcow2,
noctraos-<v>.vmdk, noctraos-<v>-amd64.iso.torrent. The ISO and disks are only measured (size and
SHA-256 come from SHA256SUMS when it is there, else are computed); nothing is copied except the
torrent, which lives in the repo root so its raw.githubusercontent.com link works.

--kubuntu adds the kubuntu flavour (KDE Plasma, marked preview) from its own release folder (noctraos-<v>-kubuntu-amd64.iso,
-kubuntu.qcow2, -kubuntu.vmdk, -kubuntu-amd64.iso.torrent), linked from releases/v<v>/kubuntu/ (docs/flavours.md rule 8).
The page holds that section between the PLASMA_START and PLASMA_END markers and this script writes all of it; without
--kubuntu the section is emptied, so the page never links a flavour this release does not have.

It rewrites, in place and only these files:
  site/download.html          version strings, the four file rows (size, SHA-256), torrent + magnet, the kubuntu section
  site/index.html             version strings
  site/sitemap.xml            lastmod of / and /download
  proxmox-install.sh          VERSION
  scripts/render-social.py    the version shown on the cards (rerun it afterwards to redraw the PNGs)
  noctraos-<old>*-amd64.iso.torrent  removed, the new ones added (root and site/)
The previous version is read from the page itself (softwareVersion), never guessed. Anything it
cannot find raises instead of leaving a half-updated site. Idempotent: a second run changes nothing.
"""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import sys
import urllib.parse

TRACKERS = ["http://tracker.opentrackr.org:1337/announce", "udp://tracker.opentrackr.org:1337/announce",
            "udp://open.demonii.com:1337/announce", "udp://tracker.openbittorrent.com:80/announce"]
DOWNLOAD = "https://dl.noctraos.dev/releases"
PLASMA_START = "<!-- kubuntu flavour: written by scripts/update-site-release.py -->"
PLASMA_END = "<!-- /kubuntu flavour -->"
LOGIN = ('<span class="login">Signs in automatically as <code>noctraos</code> (password <code>noctraos</code>). '
         'Trial use only.</span>')


def human_size(n):
    """Decimal units, one decimal for GB (3890413568 -> '3.9 GB'), whole KB for small files."""
    if n >= 1e9:
        return f"{n / 1e9:.1f} GB"
    if n >= 1e6:
        return f"{n / 1e6:.1f} MB"
    return f"{round(n / 1e3)} KB"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def read_sums(release):
    sums = {}
    path = release / "SHA256SUMS"
    if path.is_file():
        for line in path.read_text().splitlines():
            parts = line.split()
            if len(parts) == 2:
                sums[parts[1].lstrip("*")] = parts[0]
    return sums


def infohash(torrent):
    """SHA-1 of the bencoded `info` dict, found by walking the bencoding (no third-party code)."""
    data = torrent.read_bytes()

    def skip(i):
        c = data[i:i + 1]
        if c == b"i":
            return data.index(b"e", i) + 1
        if c in (b"l", b"d"):
            i += 1
            while data[i:i + 1] != b"e":
                i = skip(i)
            return i + 1
        colon = data.index(b":", i)
        return colon + 1 + int(data[i:colon])

    i = 1
    while data[i:i + 1] != b"e":
        colon = data.index(b":", i)
        end = colon + 1 + int(data[i:colon])
        key = data[colon + 1:end]
        value_end = skip(end)
        if key == b"info":
            return hashlib.sha1(data[end:value_end]).hexdigest()
        i = value_end
    raise ValueError(f"{torrent} has no info dictionary")


def magnet(version, btih, iso=None, folder=None):
    iso = iso or f"noctraos-{version}-amd64.iso"
    folder = folder or f"v{version}"
    q = lambda s: urllib.parse.quote(s, safe="")  # noqa: E731
    parts = [f"xt=urn:btih:{btih}", f"dn={iso}"] + [f"tr={q(t)}" for t in TRACKERS]
    parts.append(f"ws={q(f'{DOWNLOAD}/{folder}/{iso}')}")
    return "magnet:?" + "&amp;".join(parts)


def sub_once(pattern, repl, text, what, flags=0):
    new, count = re.subn(pattern, lambda m: repl(m) if callable(repl) else repl, text, flags=flags)
    if count != 1:
        raise ValueError(f"expected exactly one {what}, found {count}")
    return new


def measure(release, version, part):
    """The three downloads of one flavour (name -> (size, SHA-256)) and its torrent; raises if one is missing."""
    names = (f"noctraos-{version}{part}-amd64.iso", f"noctraos-{version}{part}.qcow2", f"noctraos-{version}{part}.vmdk")
    sums = read_sums(release)
    files = {}
    for name in names:
        path = release / name
        if not path.is_file():
            raise FileNotFoundError(path)
        files[name] = (path.stat().st_size, sums.get(name) or sha256(path))
    torrent = release / f"{names[0]}.torrent"
    if not torrent.is_file():
        raise FileNotFoundError(torrent)
    return files, torrent


def file_cell(title, name, size, digest=None):
    hash_span = f'<span class="hash">SHA-256: {digest}</span>' if digest else ""
    return f'<td><strong>{title}</strong><br><code>{name}</code> <span class="size">{size}</span>{hash_span}</td>'


def plasma_section(version, files, torrent):
    """The whole kubuntu section of the download page, from the measured files."""
    base = f"{DOWNLOAD}/v{version}/kubuntu"
    (iso, (iso_size, iso_hash)), (qcow2, (q_size, q_hash)), (vmdk, (v_size, v_hash)) = files.items()
    link = magnet(version, infohash(torrent), iso, f"v{version}/kubuntu")
    rows = [
        f'<tr>{file_cell("Installer", iso, human_size(iso_size), iso_hash)}<td>Installing on a PC. Copy it to a USB stick '
        f'and start your PC from it.</td><td><a class="btn primary" href="{base}/{iso}">ISO</a></td></tr>',
        f'<tr>{file_cell("Torrent", torrent.name, human_size(torrent.stat().st_size))}<td>The same installer, shared '
        f'peer-to-peer.</td><td><a class="btn ghost" href="{torrent.name}" download>.torrent</a> '
        f'<a class="btn ghost" href="{link}">Magnet</a></td></tr>',
        f'<tr>{file_cell("Virtual machine disk", qcow2, human_size(q_size), q_hash)}<td>Running Noctra in KVM, QEMU or '
        f'Proxmox.{LOGIN}</td><td><a class="btn ghost" href="{base}/{qcow2}">QCOW2</a></td></tr>',
        f'<tr>{file_cell("Virtual machine disk", vmdk, human_size(v_size), v_hash)}<td>Running Noctra in VMware or '
        f'VirtualBox.{LOGIN}</td><td><a class="btn ghost" href="{base}/{vmdk}">VMDK</a></td></tr>',
        f'<tr><td><strong>Checksums</strong><br><code>SHA256SUMS</code></td><td>The checksums of the KDE Plasma files '
        f'(a separate list from the one above).</td><td><a class="btn ghost" href="{base}/SHA256SUMS">SHA256SUMS</a></td></tr>',
    ]
    body = "\n".join(f"          {row}" for row in rows)
    return f"""{PLASMA_START}
<section id="plasma">
  <div class="wrap">
    <div class="head"><h2>KDE Plasma edition (preview)</h2><p class="lede">The same Noctra OS {version} on Kubuntu 26.04 LTS with the KDE Plasma desktop. It is a preview: the Plasma port is not finished, so Super+Space search and the Start panel are not there yet and some settings still look like stock Kubuntu. Try it in a virtual machine.</p></div>
    <div class="scroll">
      <table>
        <thead><tr><th>File</th><th>Use it for</th><th>Download</th></tr></thead>
        <tbody>
{body}
        </tbody>
      </table>
    </div>
    <p class="note"><strong>Preview means less tested.</strong> The KDE Plasma edition has run in virtual machines only. Use the GNOME edition above for anything you rely on, and <a href="https://github.com/dazeb/noctraos/issues">tell us what you find</a>.</p>
  </div>
</section>
{PLASMA_END}"""


def update(root, version, release, date, kubuntu=None):
    root, release = Path(root), Path(release)
    page = root / "site/download.html"
    html = page.read_text()
    old = re.search(r'"softwareVersion":"([0-9.]+)"', html)
    if not old:
        raise ValueError("site/download.html has no softwareVersion")
    old = old[1]

    files, torrent = measure(release, version, "")
    torrent_name = torrent.name
    plasma = measure(Path(kubuntu), version, "-kubuntu") if kubuntu else None
    # The kubuntu section is rewritten whole, so take it out first: the GNOME rows and magnet below must each match once.
    span = re.compile(re.escape(PLASMA_START) + r".*?" + re.escape(PLASMA_END), re.S)
    if len(span.findall(html)) != 1:
        raise ValueError("expected exactly one kubuntu section (its two markers) in site/download.html")
    html = span.sub(lambda m: PLASMA_START + "\n" + PLASMA_END, html)

    def version_strings(text):
        # every old version number, including inside file names and the tag, becomes the new one
        return re.sub(rf"(?<![0-9.]){re.escape(old)}(?![0-9])", version, text)

    if old != version:
        html = version_strings(html)
    # file rows: <code>NAME</code> <span class="size">SIZE</span><span class="hash">SHA-256: HASH</span>
    for name, (size, digest) in files.items():
        html = sub_once(rf'(<code>{re.escape(name)}</code> <span class="size">)[^<]*(</span><span class="hash">SHA-256: )[0-9a-f]{{64}}',
                        lambda m, s=size, d=digest: f"{m[1]}{human_size(s)}{m[2]}{d}", html, f"row for {name}")
    html = sub_once(rf'(<code>{re.escape(torrent_name)}</code> <span class="size">)[^<]*(</span>)',
                    lambda m: f"{m[1]}{human_size(torrent.stat().st_size)}{m[2]}", html, "torrent size")
    html = sub_once(r'href="magnet:\?[^"]*"', f'href="{magnet(version, infohash(torrent))}"', html, "magnet link")
    if plasma:
        html = html.replace(PLASMA_START + "\n" + PLASMA_END, plasma_section(version, *plasma))
    page.write_text(html)

    index = root / "site/index.html"
    text = index.read_text()
    index.write_text(version_strings(text) if old != version else text)
    if old != version and old in index.read_text():
        raise ValueError(f"site/index.html still mentions {old}")

    proxmox = root / "proxmox-install.sh"
    proxmox.write_text(sub_once(r"^VERSION='[0-9.]+'", f"VERSION='{version}'", proxmox.read_text(), "VERSION line", re.M))

    social = root / "scripts/render-social.py"
    text = social.read_text()
    social.write_text(version_strings(text) if old != version else text)

    if date:
        sitemap = root / "site/sitemap.xml"
        text = sitemap.read_text()
        for path in ("", "download"):
            text = sub_once(rf"(<loc>https://noctraos\.dev/{path}</loc><lastmod>)[0-9-]+(</lastmod>)",
                            lambda m: f"{m[1]}{date}{m[2]}", text, f"sitemap entry /{path}")
        sitemap.write_text(text)

    # one copy in the repo root (the GitHub release notes link it) and one in site/, served from the site's own
    # origin so the download button works with the `download` attribute
    torrents = [torrent] + ([plasma[1]] if plasma else [])
    for folder in (root, root / "site"):
        for stale in folder.glob("noctraos-*-amd64.iso.torrent"):
            if stale.name not in {t.name for t in torrents}:
                stale.unlink()
        for t in torrents:
            shutil.copyfile(t, folder / t.name)
    return old


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version")
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("--kubuntu", type=Path, help="the kubuntu flavour's release folder (KDE Plasma preview section)")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--date", help="lastmod for the sitemap (YYYY-MM-DD)")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version):
        sys.exit(f"not a version: {args.version}")
    try:
        old = update(args.root, args.version, args.release_dir, args.date, args.kubuntu)
    except (ValueError, FileNotFoundError) as error:
        sys.exit(f"update-site-release: {error}")
    print(f"site updated: {old} -> {args.version}")


if __name__ == "__main__":
    main()
