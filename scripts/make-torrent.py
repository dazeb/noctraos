#!/usr/bin/env python3
"""Write the ISO torrent for a release (needs `torf`; iso/build-release.sh installs it in a throwaway venv).

    scripts/make-torrent.py <iso> <version> <out.torrent> [flavour]

Same shape as every release so far: 4 MiB pieces, the four public trackers, and the ISO on
the Hetzner release bucket as the web seed (so the torrent works before anyone is seeding). The torrent is named after the ISO;
a flavour other than zorin is served from its own folder, releases/v<version>/<flavour>/ (docs/flavours.md rule 8).
"""
import os
import sys

import torf

TRACKERS = [["http://tracker.opentrackr.org:1337/announce"], ["udp://tracker.opentrackr.org:1337/announce"],
            ["udp://open.demonii.com:1337/announce"], ["udp://tracker.openbittorrent.com:80/announce"]]


def main():
    if len(sys.argv) not in (4, 5):
        sys.exit(__doc__)
    iso, version, out = sys.argv[1:4]
    flavour = sys.argv[4] if len(sys.argv) == 5 else "zorin"
    name = os.path.basename(iso)
    folder = f"v{version}" if flavour == "zorin" else f"v{version}/{flavour}"
    torrent = torf.Torrent(path=iso, trackers=TRACKERS, piece_size=4 * 1024 * 1024, private=False,
                           comment=f"Noctra OS {version} amd64 installer ISO - https://noctraos.dev",
                           webseeds=[f"https://noctraos-releases.fsn1.your-objectstorage.com/releases/{folder}/{name}"],
                           created_by="noctraos release pipeline")
    torrent.name = name
    torrent.generate()
    torrent.write(out, overwrite=True)
    print(f"{out}: {torrent.infohash}")


if __name__ == "__main__":
    main()
