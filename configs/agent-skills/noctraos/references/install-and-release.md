# Install, ISO and releases

## Ways onto a machine

1. **ISO** (new machines): boots the Zorin-based installer with NoctraOS branding; the provisioner finishes on first boot.
2. **VM images** (QCOW2, VMDK): provisioned disks exported from a build VM.
3. **`proxmox-install.sh`**: one command on a Proxmox VE node; downloads the release qcow2 or ISO, checks it against `SHA256SUMS`, builds a UEFI VM with the guest agent on. `NOCTRAOS_*` env vars answer every prompt.
4. **One-line installer** onto an existing Zorin/Ubuntu system: `boot.sh` clones the repo to `~/.local/share/noctraos` and runs `install.sh`. Env: `NOCTRAOS_REPO_URL`, `NOCTRAOS_BRANCH`, `NOCTRAOS_HOME`. The repo is **public** on GitHub (`github.com/dazeb/noctraos`) because bootstrap and first boot clone it anonymously. Never make it private; never commit secrets.

## `install.sh` and modules

Orchestrator: logging, `TARGET_USER` resolution, flags `--skip-gui`, `--only <module>`. Module order: `01b 00 01 02 04 04_workstation 04c 04d 05 06 08 09 10 07 11`. The first run **never downloads a model**; local AI is `noc llm setup` later.

| Module | Job |
|---|---|
| `01b_vm_guest` | hypervisor guest tools, first, no-op on bare metal |
| `00_preflight` | user/sudo/OS/network/25 GB disk/RAM checks (`sudo -n true` first) |
| `01_system` | apt core, Flathub, Nerd Font, openssh-server, Flatpak/AppImage prerequisites |
| `02_mise` | mise, Node LTS, Herdr, Starship, lazygit, lazydocker |
| `04_gui_apps`, `04_workstation_apps` | VS Code + extensions, Mission Center, CopyQ; the Flatpak/apt workstation set |
| `04c_app_policy`, `04d_appmanager` | app policy; AppImage manager |
| `05_mouse_ergonomics` | Nautilus right-click scripts |
| `06_desktop_theme` | gsettings, wallpapers, Agents menu, AI-first menu |
| `08_shell_theme` | NoctraOS-Dark shell + GTK themes |
| `09_super_search` | Shell extensions, search app, schemas, help page, index timer, autostarts |
| `10_boot_theme` | Plymouth + GRUB for non-ISO installs |
| `07_persistence` | `/etc/skel` defaults, `noc` + Control Panel + privileged helper + updater, root-owned snapshot |
| `11_hermes` | Hermes Desktop (last; 25+ min) |
| `optional/local_llm` | GPU stack, Ollama, LLMFIT; run by `noc llm setup` |
| `03b_ollama_update` | Ollama to newest upstream (root, via panel) |

Module rules: source `install/lib.sh`; **idempotent** (guard every mutation); desktop settings **warn-not-die**; `grep -q` on a pipe under `pipefail` is a bug for big producers (drain with `grep ... >/dev/null`); gsettings via `as_user` (user session bus, never `dbus-launch`); never bare `gs`.

## First boot (ISO)

The first-boot runner fetches the latest provisioner **without needing git**: `git clone` if available, else a curl tarball of the branch, and the baked snapshot only if GitHub is unreachable or the download is broken (`tests/test_firstboot_fetch.py`). The ISO bakes the Shell extensions, search app, schemas (`iso/bake-shell.sh`) and `qemu-guest-agent` (`iso/bake-guest-tools.sh`). `iso/strip-census.sh` removes Zorin's census; `iso/rebrand-labels.sh` renames user-facing Zorin strings (installer name comes from `/cdrom/.disk/info`, regex `s/^Zorin[- ]OS/NoctraOS/`).

## Building an ISO

- Preferred: **local** `iso/build-local.sh` (about 2-3 minutes per ISO, Docker, builds into `<dir>/work` on an ext4 drive). Build on the fastest local disk (`iso/disks.sh`, `NOCTRAOS_DISK_CANDIDATES`; the 2 TB Crucial P310 first). `iso/build-local.sh` fails if a release ISO has a seed or unattended entry.
- On the Proxmox node (older flow): `iso/build-noctraos-iso.sh`, scratch on `/local-zfs` (HDD-backed, 35-45 min); do not build and run VMs there at once.
- Release vs unattended: a release build has no seed, no password hash, no unattended entry (an unattended entry wipes the disk). `NOCTRAOS_UNATTENDED=1` + `NOCTRAOS_USER/PASSWORD` bake a seed (`iso/preseed/noctraos.seed.in`) and imply autologin + NOPASSWD sudo. Output is `noctraos-<VERSION>-amd64.iso`; VERSION must match `bin/noc`.
- **Never repack the squashfs with `-all-root`**; the build checks the launch helper's group after unpacking and repacking. xorriso refuses a non-empty `-outdev`, so the script `rm -f`s the previous ISO (keep that line). The live boot verifies `/cdrom/md5sum.txt`; the build writes it after moving the new squashfs in. casper waits for "remove installation medium" unless the cmdline has `noprompt`. Unattended Ubiquity needs `ubiquity/download_updates`, `use_nonfree` and `no_zorin_os_census` preseeded.
- `iso/vm-sysprep.sh` runs in a fully provisioned VM before exporting its disk (strips machine id, SSH host keys, Hermes identity/history, logs; refuses bare metal).

## Release pipeline

A release is a tag: `git tag vX.Y.Z origin/main && git push gitlab vX.Y.Z`. `.gitlab-ci.yml` runs `release-build` (`iso/build-release.sh`), `release-publish` (`iso/publish-release.sh`) and `release-site` (`scripts/release-site-pr.sh`) on the `noctraos-release` runner on the workstation (`iso/setup-release-runner.sh`).

- Release runner is ref-protected; `v*` tags are protected. Never add `tags: [noctraos-release]` to a job that runs on branches.
- `build-release.sh` builds from GitHub `main` and refuses a tag that is not main's head or a VERSION that is not the tag. Rehearse the final `main`: `RELEASE_REHEARSAL=1 REHEARSAL_BRANCH=main iso/build-release.sh <dir>` (about 42 min, publishes nothing).
- **Do not merge to GitHub `main` while a release build runs** (tag push to `release-build` success, about 90 minutes).
- `publish-release.sh` never overwrites `releases/vX/` and verifies through the public hostname (`https://dl.noctraos.dev/releases/vX/`). Hetzner mirror via `RELEASE_STORE=hetzner`. A failed publish is safe to retry. S3-style storage answers 403, not 404, for a missing key.
- The site is changed only by `scripts/update-site-release.py` (run `tests/test_update_site_release.py` if you restructure `site/download.html`). Social cards/favicons: `scripts/render-social.py`.
- Run the whole test suite **as root in a container with a real clone** before tagging (GitLab runs as root; some tests behave differently): use `git clone --no-hardlinks` into a directory you mount, push `main` to GitLab (`git push gitlab <branch>`), and wait for green.
- Stacked PRs: retarget each to `main` before merging it. Do not move a published tag; fixes go in the next version.
- Details: `docs/release-runbook.md`, `docs/updates.md`, `docs/release-notes/`.
