#!/usr/bin/env python3
"""initrd-theme.py — swap the Plymouth theme inside a casper initrd.

usage: initrd-theme.py <initrd> <theme-dir> <theme-name>

The live ISO's splash comes from the initrd, not from the squashfs, so
rebranding the squashfs alone leaves the stock logo on screen for the whole
live boot. An Ubuntu initrd is a few uncompressed "early" cpio archives
(microcode) followed by one compressed main archive; only the main archive is
rewritten, the early part is copied byte for byte.

Only the two-step splash module is present in the initrd, so <theme-dir> must
be a two-step theme (see assets/boot/plymouth/noctraos).
"""
import os
import shutil
import subprocess
import sys
import tempfile

CPIO_MAGIC = b"070701"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
GZIP_MAGIC = b"\x1f\x8b"


def align4(n):
    return (n + 3) & ~3


def main_archive_offset(data):
    """Offset of the first byte after the uncompressed early cpio archives."""
    pos = 0
    while data[pos:pos + 6] == CPIO_MAGIC:
        while True:
            if data[pos:pos + 6] != CPIO_MAGIC:
                raise SystemExit("initrd: corrupt early cpio archive")
            filesize = int(data[pos + 54:pos + 62], 16)
            namesize = int(data[pos + 94:pos + 102], 16)
            name = data[pos + 110:pos + 110 + namesize - 1]
            pos = align4(align4(pos + 110 + namesize) + filesize)
            if name == b"TRAILER!!!":
                break
        while pos < len(data) and data[pos] == 0:
            pos += 1
    return pos


def run(cmd, **kwargs):
    subprocess.run(cmd, check=True, **kwargs)


def main():
    initrd, theme_dir, theme = sys.argv[1:4]
    with open(initrd, "rb") as handle:
        data = handle.read()
    offset = main_archive_offset(data)
    magic = data[offset:offset + 4]
    if magic == ZSTD_MAGIC:
        decompress, compress = ["zstd", "-dc"], ["zstd", "-T0", "-12", "-q"]
    elif magic[:2] == GZIP_MAGIC:
        decompress, compress = ["gzip", "-dc"], ["gzip", "-9"]
    else:
        raise SystemExit(f"initrd: unknown main archive compression {magic.hex()}")

    work = tempfile.mkdtemp(prefix="noctraos-initrd.")
    try:
        root = os.path.join(work, "root")
        os.mkdir(root)
        packed = os.path.join(work, "main.bin")
        with open(packed, "wb") as handle:
            handle.write(data[offset:])
        with open(packed, "rb") as source:
            unpack = subprocess.Popen(decompress, stdin=source, stdout=subprocess.PIPE)
            run(["cpio", "-idm", "--quiet", "--no-absolute-filenames"], stdin=unpack.stdout, cwd=root)
            if unpack.wait() != 0:
                raise SystemExit("initrd: decompression failed")

        themes = os.path.join(root, "usr/share/plymouth/themes")
        if not os.path.isdir(themes):
            raise SystemExit("initrd: no plymouth themes directory — wrong initrd?")
        for stale in os.listdir(themes):
            path = os.path.join(themes, stale)
            if stale.startswith("zorin-logo"):
                shutil.rmtree(path)
        target = os.path.join(themes, theme)
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(theme_dir, target)
        link = os.path.join(themes, "default.plymouth")
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(f"/usr/share/plymouth/themes/{theme}/{theme}.plymouth", link)

        listing = subprocess.run(["find", ".", "-mindepth", "1", "-printf", "%P\\0"], cwd=root,
                                 check=True, stdout=subprocess.PIPE).stdout
        names = b"\0".join(sorted(filter(None, listing.split(b"\0")))) + b"\0"
        out = os.path.join(work, "main.new")
        with open(out, "wb") as handle:
            pack = subprocess.Popen(["cpio", "--null", "-o", "-H", "newc", "--quiet", "--owner=0:0"],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=root)
            squash = subprocess.Popen(compress, stdin=pack.stdout, stdout=handle)
            pack.stdout.close()
            pack.stdin.write(names)
            pack.stdin.close()
            if pack.wait() != 0 or squash.wait() != 0:
                raise SystemExit("initrd: repack failed")
        with open(initrd + ".new", "wb") as handle:
            handle.write(data[:offset])
            with open(out, "rb") as packed_new:
                shutil.copyfileobj(packed_new, handle)
        os.replace(initrd + ".new", initrd)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
