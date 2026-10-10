# Troubleshooting

Start with `noc doctor` (`--json` for scripts). Rows are `ok`, `warn`, `fail` or `info`. `info` means optional or intentionally off (stopped Ollama that is not set to autostart; Python or Go absent) - never treat it as a failure. Some rows are fixable: `noc repair appmanager|vm-guest|hermes`. The Health page shows the same rows with a Fix button where one exists.

## Where to look

| What | Where |
|---|---|
| Provisioner run | `/tmp/noctraos-run.log` for a manual run; the first-boot runner logs per its autostart; `install.sh` writes a log (see module output) |
| NoctraOS updater | `/var/log/noctraos/` (e.g. `migrate.log`); state `/var/lib/noctraos`; `noc-selfupdate status` |
| Update migrations | per-user `~/.local/state/noctraos/migrations` (and `failed/`) |
| Upstream app versions | `~/.local/state/noctraos/apps.json`, cache `~/.cache/noctraos/upstream.json` |
| Hermes | `~/.hermes` (config, sessions, `SOUL.md`); `noctraos-hermes status` |
| Ollama | `systemctl status ollama`, `journalctl -u ollama`; `curl 127.0.0.1:11434/api/tags` |
| The person's choices | `~/.config/noctraos/` (`model`, `skipped`, `no-update-check`, `no-vm-guest`) |

## Known failures and the real cause

- **Software Updater freezes / "Failed to execute program org.debian.apt: Permission denied"** on images up to 0.4.0: the ISO was repacked with `mksquashfs -all-root`, so `/usr/lib/dbus-1.0/dbus-daemon-launch-helper` is root:root instead of root:messagebus (also lost: `/etc/shadow`, `crontab`, polkit, the man cache). Repaired on installed systems by `migrations/system/0001_restore_ownership.sh` (NoctraOS system only; only files still exactly root:root; restores setuid/setgid modes), delivered by an update. Never repack with `-all-root`.
- **No IP shown in Proxmox for a fresh VM:** guest agent missing or Proxmox VM agent option off; see [hardware](hardware.md).
- **Super+Space or the Start panel missing after the first login:** GNOME Shell scans extensions once at start. Log out and in. (Baked into new ISOs, so only `boot.sh` installs on an existing system need it.)
- **Windows have a dark wedge in the top-left corner:** a per-corner radius not clamped; fixed in theme build (`RADIUS_DECLARATION`).
- **Python GUI app dies with `No module named 'gi'` at autostart:** it used `#!/usr/bin/env python3` and picked a mise python. Pin `#!/usr/bin/python3`.
- **CopyQ records nothing on Wayland:** it must run with `QT_QPA_PLATFORM=xcb`.
- **"Authentication required" keyring prompt in Hermes/VS Code/browsers:** keyring already holds secrets so it was not reset; see [privacy-and-accounts](privacy-and-accounts.md).
- **Hermes Desktop renders blank on a VM:** Electron needs `--no-sandbox --disable-dev-shm-usage` (wrapper seeds it when it detects a VM).
- **`hermes update` fails with a tag:** it treats the tag as a branch; use `noctraos-hermes update`. An old Hermes tag fails with the current installer.
- **A second `install.sh` fails the 25 GiB preflight** after Hermes' ~5 GiB build: run single modules (`install.sh --only <module>`) or grow the disk.
- **Preflight "Only N GiB free" on an enlarged VM disk:** use `noc disk grow` ([hardware](hardware.md)).
- **`sudo -v` fails headless even with NOPASSWD:** the preflight uses `sudo -n true` first; keep that order.
- **sudo credentials expire mid-run (~15 min):** interactive first boots block at the next prompt; autologin builds bake NOPASSWD.
- **Ollama starts at boot unexpectedly on a new install:** it should not; the vendor installer enables it and `ollama_boot_restore` turns it off - check `systemctl is-enabled ollama`.
- **GDM greeter hangs at the splash (Zorin 18.1):** the greeter's gnome-session cannot resolve components; user sessions are fine; unattended builds use autologin.
- **GitHub login says "already logged in" / refuses:** `GH_TOKEN`/`GITHUB_TOKEN` is set in the environment; `noc accounts` strips them, a bare `gh auth login` does not.
- **`gh pr edit` fails on the repo:** GitHub's classic-projects deprecation error; use `gh api -X PATCH repos/OWNER/REPO/pulls/N -F body=@file`.
- **A long background job dies at about 10 minutes** when started from a tool call: run it as a `systemd-run --user` unit and watch its log. Never `pkill -f <pattern>` when your own command line contains the pattern.

## Before you "fix" anything on a person's machine

Run `noc doctor`, prefer `noc repair` / the panel's Fix, back up before editing, never `purge`/`autoremove`, and ask before anything that needs sudo, downloads gigabytes, changes the update channel, or switches Hermes to cloud.
