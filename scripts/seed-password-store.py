#!/usr/bin/env python3
"""Make Chromium (Flatpak) and VS Code store secrets without the login keyring.

With autologin the login keyring is never unlocked, so the first Chromium or
VS Code start shows an "Authentication required" prompt. Both accept
`--password-store=basic`; this writes it into their per-user flag files.
Idempotent, keeps existing content, and only adds the flag.

  seed-password-store.py HOME_DIRECTORY
"""
import json
import re
import sys
from pathlib import Path

FLAG = "--password-store=basic"


def chromium_flags(home):
    """Flathub Chromium reads one flag per line from chromium-flags.conf."""
    path = home / ".var/app/org.chromium.Chromium/config/chromium-flags.conf"
    lines = path.read_text().splitlines() if path.exists() else []
    if any(line.strip() == FLAG for line in lines):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([*lines, FLAG]) + "\n")
    return True


def vscode_argv(home):
    """VS Code's argv.json is JSON with comments; add the key without parsing it."""
    path = home / ".vscode/argv.json"
    entry = '"password-store": "basic"'
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{\n\t" + entry + "\n}\n")
        return True
    text = path.read_text()
    if re.search(r'^\s*"password-store"\s*:', text, re.MULTILINE):
        return False
    updated, count = re.subn(r"^\{[ \t]*\n?", "{\n\t" + entry + ",\n", text, count=1, flags=re.MULTILINE)
    if not count:
        raise ValueError(f"{path} has no top-level object to extend")
    stripped = re.sub(r"^\s*//.*$", "", updated, flags=re.MULTILINE)
    json.loads(re.sub(r",(\s*[}\]])", r"\1", stripped))  # must still parse (comments and trailing commas aside)
    path.write_text(updated)
    return True


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    home = Path(sys.argv[1])
    changed = [name for name, fn in (("chromium", chromium_flags), ("vscode", vscode_argv)) if fn(home)]
    print("password-store=basic set for: " + (", ".join(changed) if changed else "nothing to change"))


if __name__ == "__main__":
    main()
