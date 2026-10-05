#!/usr/bin/env python3
"""Stop the "Authentication required" keyring prompt on an autologin system.

With autologin nothing unlocks the login keyring (it is encrypted with the account password,
which is never typed), so the first app that uses the Secret Service (Hermes, Chromium, VS
Code, any browser) shows a keyring password prompt. Two things are done here, both
idempotent and both only ever adding:

* the login keyring is made an unencrypted one when it is missing or empty, so unlocking it
  needs no password and every app is covered. A keyring that holds secrets is never touched.
* Chromium (Flatpak) and VS Code additionally get `--password-store=basic` in their per-user
  flag files (they do not depend on the keyring at all).

The trade-off is the one the flags already made: secrets are stored without a password.

  seed-password-store.py HOME_DIRECTORY
"""
import json
import re
import sys
import time
from pathlib import Path

FLAG = "--password-store=basic"
# gnome-keyring's binary (encrypted) files start with this; an empty one is about 105 bytes,
# one holding even a single secret is well over 128.
ENCRYPTED_MAGIC = b"GnomeKeyring\n\r\x00\n\x00"
EMPTY_ENCRYPTED_MAX = 128


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
    # A missing file and an empty one (left by an interrupted run) are both a fresh start.
    if not path.exists() or not path.read_text().strip():
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


def login_keyring(home):
    """Give the account an unencrypted `login` keyring unless one with secrets already exists."""
    directory = home / ".local/share/keyrings"
    keyring = directory / "login.keyring"
    default = directory / "default"
    if keyring.exists():
        data = keyring.read_bytes()
        if data.startswith(ENCRYPTED_MAGIC):
            if len(data) > EMPTY_ENCRYPTED_MAX:
                return False                # encrypted and holding secrets: leave it alone
        elif data.startswith(b"[keyring]"):
            if default.exists() and default.read_text().strip() == "login":
                return False                # already ours, and already the default
        else:
            return False                    # a format we do not know: never overwrite it
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    if not keyring.exists() or keyring.read_bytes().startswith(ENCRYPTED_MAGIC):
        keyring.write_text("[keyring]\ndisplay-name=Login\nctime=%d\nmtime=0\n"
                           "lock-on-idle=false\nlock-timeout=0\n" % time.time())
        keyring.chmod(0o600)
    default.write_text("login")
    default.chmod(0o600)
    return True


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    home = Path(sys.argv[1])
    changed = [name for name, fn in (("keyring", login_keyring), ("chromium", chromium_flags),
                                     ("vscode", vscode_argv)) if fn(home)]
    # One unambiguous line the install modules read: "changed: keyring chromium" or "changed: none".
    print("keyring-free secrets changed: " + (" ".join(changed) if changed else "none"))


if __name__ == "__main__":
    main()
