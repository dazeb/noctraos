#!/usr/bin/env python3
"""Write the ISO torrent for a release (needs `torf`; iso/build-release.sh installs it in a throwaway venv).

    scripts/make-torrent.py <iso> <version> <out.torrent>

Same shape as every release so far: 4 MiB pieces, the four public trackers, and the ISO on
dl.noctraos.dev as the web seed (so the torrent works before anyone is seeding).
"""
import sys

import torf

TRACKERS = [["http://tracker.opentrackr.org:1337/announce"], ["udp://tracker.opentrackr.org:1337/announce"],
            ["udp://open.demonii.com:1337/announce"], ["udp://tracker.openbittorrent.com:80/announce"]]


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    iso, version, out = sys.argv[1:]
    name = f"noctraos-{version}-amd64.iso"
    torrent = torf.Torrent(path=iso, trackers=TRACKERS, piece_size=4 * 1024 * 1024, private=False,
                           comment=f"Noctra OS {version} amd64 installer ISO - https://noctraos.dev",
                           webseeds=[f"https://dl.noctraos.dev/releases/v{version}/{name}"],
                           created_by="noctraos release pipeline")
    torrent.name = name
    torrent.generate()
    torrent.write(out, overwrite=True)
    print(f"{out}: {torrent.infohash}")


if __name__ == "__main__":
    main()
