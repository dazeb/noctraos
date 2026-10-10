#!/usr/bin/env python3
"""Check every apt package the provisioner asks for against Ubuntu archive indexes.

Reads data/packages.txt, fetches the binary package indexes (main + universe, amd64)
for each suite, and reports per package: available in resolute (26.04), available in
noble (24.04), or missing. Writes out/apt-check.tsv and prints a summary.

Read-only: it only downloads the public Packages.gz indexes (a few MB each).
"""
import gzip
import pathlib
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent.parent
MIRROR = "http://archive.ubuntu.com/ubuntu"
SUITES = {"resolute": "26.04", "noble": "24.04"}
POCKETS = ["", "-updates", "-security"]
COMPONENTS = ["main", "universe"]


def load_index(suite_pocket: str, component: str) -> set[str]:
    url = f"{MIRROR}/dists/{suite_pocket}/{component}/binary-amd64/Packages.gz"
    with urllib.request.urlopen(url, timeout=120) as resp:
        data = gzip.decompress(resp.read()).decode("utf-8", "replace")
    names = set()
    for line in data.splitlines():
        if line.startswith("Package: "):
            names.add(line[len("Package: "):].strip())
    return names


def suite_names(suite: str) -> set[str]:
    names: set[str] = set()
    for pocket in POCKETS:
        for comp in COMPONENTS:
            names |= load_index(f"{suite}{pocket}", comp)
            print(f"  loaded {suite}{pocket} {comp}: {len(names)} names so far", file=sys.stderr)
    return names


def main() -> int:
    wanted = []
    for raw in (HERE / "data" / "packages.txt").read_text().splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        module, pkg = raw.split(None, 1)
        wanted.append((module, pkg.strip()))

    index = {}
    for suite in SUITES:
        print(f"fetching {suite} index", file=sys.stderr)
        index[suite] = suite_names(suite)

    out = HERE / "out" / "apt-check.tsv"
    out.parent.mkdir(exist_ok=True)
    rows = ["module\tpackage\tresolute\tnoble\tverdict"]
    missing_26 = []
    for module, pkg in wanted:
        in26 = pkg in index["resolute"]
        in24 = pkg in index["noble"]
        if in26:
            verdict = "ok"
        elif in24:
            verdict = "RENAMED-OR-DROPPED (in noble only)"
            missing_26.append((module, pkg, verdict))
        else:
            verdict = "MISSING (neither suite)"
            missing_26.append((module, pkg, verdict))
        rows.append(f"{module}\t{pkg}\t{'yes' if in26 else 'no'}\t{'yes' if in24 else 'no'}\t{verdict}")
    out.write_text("\n".join(rows) + "\n")

    print(f"checked {len(wanted)} packages -> {out.relative_to(HERE)}")
    print(f"not in resolute: {len(missing_26)}")
    for module, pkg, verdict in missing_26:
        print(f"  [{module}] {pkg}: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
