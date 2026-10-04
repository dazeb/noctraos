# AGENTS.md — noctraos

Instructions for coding agents working in this repository. Read fully before
changing anything; the pitfalls section saves real debugging time.

## What this repo is

NoctraOS (`noctraos`) is an AI-ready desktop OS for **people moving from
Windows**, on an Ubuntu base (Zorin OS 18.x today) — Omarchy's idea without
the tiling-WM learning curve. It is delivered as a bootable **ISO**; the
Omakub-style provisioner (`install.sh`) is the engine baked into it. Contents:
local Ollama stack, a six-agent start menu, mise-managed runtimes, a dark +
amber theme, and the **Super+Space** system search as the headline feature.

Read `docs/objectives.md` first: it defines the audience, principles
(muscle memory over Windows imitation, no terminal required, no tiling WM),
the onboarding goal, and non-goals. Keep it current when direction changes.

The repo is **public on GitHub** (`github.com/dazeb/noctraos`) — this is a hard
requirement: the one-liner bootstrap and the ISO's first-boot fetch clone it
anonymously. Never make it private, never commit secrets.

## Repository map

```
boot.sh                     remote fetcher: clones repo to ~/.local/share/noctraos,
                            runs install.sh; env: NOCTRAOS_REPO_URL, NOCTRAOS_BRANCH, NOCTRAOS_HOME
install.sh                  orchestrator: logging, TARGET_USER resolution, flags
                            (--skip-ai, --skip-gui), runs modules 00-07 + 08
install/
  lib.sh                    shared helpers: log/warn/die, as_user(), apt_install(),
                            desktop_file_exists(). Modules MUST source it.
  00_preflight.sh           user/sudo/OS/network/25GB-disk/RAM checks
  01_system.sh              apt core + python build deps, Flathub, Nerd Font
  02_mise.sh                mise binary, profile.d + bash.bashrc hooks, runtimes,
                            Herdr, Starship, lazygit, lazydocker
  03_ai_core.sh             Ollama + qwen2.5-coder:7b + nomic-embed-text
  04_gui_apps.sh            Microsoft VS Code (apt repo) + extensions, Mission Center,
                            CopyQ; retires codium/chatbox/foot (user data kept)
  04_workstation_apps.sh    Omarchy-style Ubuntu/Flathub workstation app set
  05_mouse_ergonomics.sh    Nautilus right-click scripts
  06_desktop_theme.sh       gsettings ergonomics, wallpapers, Agents menu,
                            AI-first /etc/xdg/menus/gnome-applications.menu
  07_persistence.sh         /etc/skel defaults, zom + zom-menu install
  08_shell_theme.sh         NoctraOS-Dark shell + GTK themes (derived, not
                            shipped), white menu icons, terminal/app palette
bin/
  zom                       CLI: update | doctor | models [list|pull|rm|gui] | bg [list|next|set]
  zom-menu                  zenity control panel
  noctraos-agent            agent launcher wrapper: installs npm package on
                            first use, then execs the agent
configs/
  mise/config.toml          node=lts, python=3.12, go=latest, terminal tools
  vscode/                   settings.json, extensions.list, continue_config.yaml,
                            vscode.sources (Microsoft apt repo)
  copyq/copyq.conf          clipboard history preseed (1000 entries, silent, tray)
  autostart/copyq.desktop   CopyQ session autostart (user + /etc/skel)
  applications/             agent + Herdr + Local-LLM launchers, .directory files
  theme/                    Herdr and btop palettes
  xdg/                      gnome-applications.menu (AI-first tree), agents merge
  nautilus-scripts/         Open_in_VS_Code, Ask_AI_to_Explain, Open_Terminal_Here
assets/
  wallpapers/               5 seeded 4K JPEG scenes + generate-wallpapers.py
  icons/                    white SVG glyphs (agents, Local LLM, category tiles)
  icons/overrides/          white SVGs under STOCK icon names — these replace
                            the system category icons system-wide
iso/build-noctraos-iso.sh   ISO remaster pipeline (runs on the Proxmox node);
                            NOCTRAOS_UNATTENDED=1 + NOCTRAOS_USER/PASSWORD/…
                            bake an unattended-install seed and boot entries
iso/preseed/noctraos.seed.in  Ubiquity/d-i seed template for the above
```

## Non-negotiable rules

1. **Never run `install.sh`/`boot.sh` on the local dev workstation.** This box
   (Ubuntu 26.04, `dazeb-ubuntubox`) is for editing and static checks only.
   All runtime testing happens on the Proxmox test VM.
2. **Every module must be idempotent.** Guard every mutation (`command -v`,
   file existence, `dpkg-query`, `gsettings get`). Re-running install.sh must
   be a no-op. There is a live test VM precisely to prove this.
3. **Desktop settings are warn-not-die.** `gsettings`/theme steps must never
   abort an install (`|| warn "..."`). Core steps (apt, ollama) may die.
4. **`gs` is a trap.** Module 06 defines a local `gs()` helper for gsettings.
   Other modules must NOT call bare `gs` — it resolves to the **Ghostscript
   binary**. Use `as_user gsettings set ...` explicitly.
5. **No `grep -q` on pipes under `set -o pipefail`** for large-output
   producers (`fc-list`, …): grep exits early, SIGPIPEs the producer, and the
   guard misreads "installed" as "missing". Drain with `grep ... >/dev/null`.
6. **gsettings must target the user session bus**, never `dbus-launch`:
   `as_user` in lib.sh handles it (DBUS_SESSION_BUS_ADDRESS=/run/user/UID/bus).
7. **Verify pushes server-side**: `gh api repos/dazeb/noctraos/commits/heads/main --jq .sha`.
   A clean `git push` exit code has already lied here once — check which branch
   HEAD is on (`git status`) and confirm the remote SHA after pushing.
8. **Working tree hygiene**: commit on `main`. If `git status` shows a feature
   branch you did not intentionally create, stop and reconcile before
   committing (this bit us: 6 commits landed on a stray branch unnoticed).
9. **Do not touch other guests on the Proxmox node** (VMs 107/108/113/114,
   LXC 100-112/200/210). VM 114 (`zorin-ai-iso-test`) is ours.
10. **Nautilus scripts get selections via env vars**
    (`NAUTILUS_SCRIPT_SELECTED_FILE_PATHS`), not argv. VNC-typed text into the
    guest loses shifted characters (`& @ > :`) — route anything complex
    through SSH or an HTTP fetch from port 80 (no colon in URL).

## Environment (infrastructure)

- **Proxmox node**: `ssh root@192.168.8.195` (key auth, host "files",
  PVE 9.2.20, i7-4770K / 15 GiB RAM). Web-UI password unknown — work over SSH.
- **Test VMs**: VM 110 `zai-zerotouch-test` at `192.168.8.138` (v0.3 zero-touch
  reference; DHCP — re-scan if the lease moved) and VM 114 `zorin-ai-iso-test`
  at `192.168.8.187` (v0.2 reference). User `dazeb`, password
  `zorin-test-2026` (throwaway), our SSH key authorized on both, passwordless
  sudo via baked NOPASSWD (110) / `/etc/sudoers.d/zai-test` (114).
- **Remote testing from a cloud/CI agent (Tailscale)**: the LAN IPs above are
  not routable from outside. VM 114 is on the tailnet as `zorin-ai-iso-test`
  (`100.125.207.0`); the node is `files` (`100.83.252.94`). Nothing advertises
  `192.168.8.0/24`, so use the tailnet IPs. A cloud container has no TUN-based
  routing, so run Tailscale in userspace mode and SSH through it:
  ```bash
  tailscaled --tun=userspace-networking --state=$S/tailscaled.state --socket=$S/ts.sock &
  tailscale --socket=$S/ts.sock up --auth-key=<ephemeral, tagged key> --hostname=claude-cloud
  ssh -o ProxyCommand="tailscale --socket=$S/ts.sock nc %h %p" dazeb@100.125.207.0
  ```
  Start `tailscaled` with `setsid nohup` (plain background jobs die between
  turns; saved state rejoins without the key). Needs `openssh-client`. Auth
  keys are pasted by the user per session — never commit one, and ask the user
  to revoke it afterwards. The agent's SSH public key must be in VM 114's
  `~dazeb/.ssh/authorized_keys`; do not add keys to or touch the Proxmox node.
  Verified 2026-10-04: static checks, full `install.sh` run + idempotent
  second run, and `zom doctor` all green on VM 114 this way.
- **ISO build** runs on the node, not here. Scratch MUST be on
  `/local-zfs` (`WORK_BASE=/local-zfs/iso-build`) — pve-root has ~8 GiB free
  and the build needs ~25 GiB. The zfs pool is HDD-backed: unsquashfs and
  mksquashfs take 10-20 min each; total build ~35-45 min. Run as a
  `systemd-run --unit=<name> --collect bash -c "..."` unit (plain nohup over
  ssh dies with the session). ISOs live in `/var/lib/vz/template/iso/`.
- **RAM pressure**: the node juggles 14 GiB of allocated VMs. Don't start
  extra VMs while builds run; builds peak ~2 GiB.
- **local-zfs is nearly full** (~17 GiB free, 2026-09-26): a build's scratch
  (~15 GiB peak) fits, but delete `noctraos-iso-build.*` work dirs afterwards.
- `xorriso`, `git`, `squashfs-tools`, `openssl` are available on the node.
- **Unattended ISO build** (v0.3+): the build script clones the provisioner
  from GitHub for the squashfs, so push first; the seed template is read from
  the script's own `iso/preseed/` dir. Unattended builds imply autologin +
  NOPASSWD sudo for the created user.

## Commands

```bash
# static checks (docker shellcheck — not installed on this host)
bash -n boot.sh install.sh install/*.sh bin/* configs/nautilus-scripts/*
docker run --rm -v "$PWD:/mnt" koalaman/shellcheck:stable --severity=warning \
  boot.sh install.sh install/*.sh bin/zom bin/zom-menu bin/noctraos-agent \
  configs/nautilus-scripts/*

# wallpaper iteration (venv at ~/workspace/scratch/zorin-img-venv: pillow+numpy)
cd assets/wallpapers
~/workspace/scratch/zorin-img-venv/bin/python generate-wallpapers.py \
  --width 1920 --height 1080 --outdir /tmp/wp-preview     # fast previews
~/workspace/scratch/zorin-img-venv/bin/python generate-wallpapers.py      # 4K final

# deploy a change to the test VM (idempotent full pass)
tar czf /tmp/noctraos-repo.tgz --exclude=.git --exclude=.zcodeignore .
scp -q /tmp/noctraos-repo.tgz dazeb@192.168.8.187:/tmp/
ssh dazeb@192.168.8.187 'rm -rf ~/.local/share/noctraos && mkdir -p ~/.local/share/noctraos \
  && tar xzf /tmp/noctraos-repo.tgz -C ~/.local/share/noctraos \
  && nohup bash ~/.local/share/noctraos/install.sh > /tmp/noctraos-run.log 2>&1 &'
# headless runs need NOPASSWD sudo (already enabled on VM 114) or cached creds

# fresh-clone audit + server-side push verification
git clone -q git@github.com:dazeb/noctraos.git /tmp/noctraos-clone && find /tmp/noctraos-clone -type f | wc -l
gh api repos/dazeb/noctraos/commits/heads/main --jq '.sha[0:7] + " " + .commit.message'

# ISO build (on the node — clone fresh so the baked snapshot + seed match main)
ssh root@192.168.8.195
git clone -q --depth 1 https://github.com/dazeb/noctraos.git /local-zfs/iso-build/noctraos-src
systemd-run --unit=noctraos-iso --collect bash -c \
  "NOCTRAOS_UNATTENDED=1 NOCTRAOS_USER=dazeb NOCTRAOS_PASSWORD=zorin-test-2026 \
   WORK_BASE=/local-zfs/iso-build bash /local-zfs/iso-build/noctraos-src/iso/build-noctraos-iso.sh \
   /var/lib/vz/template/iso/Zorin-OS-18.1-Core-64-bit.iso \
   /var/lib/vz/template/iso/noctraos-18.1-amd64.iso > /root/noctraos-build.log 2>&1"
tail -f /root/noctraos-build.log
```

## Known pitfalls (each cost real debugging time)

- **xorriso refuses non-empty `-outdev`** ("media holds non-zero data"):
  the build script `rm -f`s the previous ISO before writing. Do not remove
  that line; do not silence xorriso's output.
- **`sudo -v` needs a TTY even under NOPASSWD sudoers** — headless preflight
  uses `sudo -n true` first. Keep that fallback order.
- **VS Code replaced VSCodium (b6981b4); Chatbox and Foot are retired.**
  Module 04 installs `code` from Microsoft's apt repo (key in
  `/usr/share/keyrings/microsoft.gpg`, source from `configs/vscode/vscode.sources`;
  `debconf-set-selections` stops the package adding its own repo), then
  `apt-get remove`s `codium`, `chatbox`, `xyz.chatboxapp.app` and `foot` — never
  purge/autoremove, user data stays. Legacy `Open_in_VSCodium` Nautilus scripts
  are deleted by modules 05/07. Settings and Continue config are only seeded
  when missing, so existing installs keep their old copies.
- **`zorin-menu.desktop` does not exist on Zorin 18**; favorites and menu
  code skip missing desktop entries by design.
- **`org.gnome.desktop.interface accent-color` key is absent** on Zorin 18.1 —
  the attempt warns and moves on.
- **Menu tree changes need a session rescan** (logout or reboot). Wayland has
  no in-place shell restart.
- **VNC typing into the VM console drops/mangles shifted characters** and
  rapid reconnects fail silently; vncdotool exit codes are always 1. Prefer
  SSH once sshd is up; use QEMU monitor `sendkey` for exact console input.
- **The first-boot runner falls back to the baked snapshot when `git` is
  absent** (fresh installs). Provisioner now installs openssh-server in
  module 01 for post-install remote access.
- **Unattended preseed: the first Ubiquity page stops the flow** — the
  "Updates and other software" page waits for Continue unless
  `ubiquity/download_updates`, `ubiquity/use_nonfree` and the Zorin-specific
  `ubiquity/no_zorin_os_census` are all preseeded (found in
  `usr/lib/ubiquity/plugins/ubi-prepare.py`, not in ubiquity.templates).
- **The GDM greeter is broken on Zorin 18.1**: gdm starts, the greeter's
  gnome-session cannot resolve ANY required component (org.freedesktop.systemd1
  activation fails on the greeter's private bus) → boot hangs at the splash
  forever. User sessions are fine. Unattended builds therefore default to
  autologin (writes /etc/gdm3/custom.conf in the squashfs).
- **Boot-test VMs must boot the disk first** (`--boot order="scsi0;ide2"`):
  after the unattended install reboots, a cdrom-first VM boots the installer
  ISO again instead of the new system.
- **casper waits for "remove installation medium, press ENTER"** unless the
  kernel cmdline has `noprompt` (see `casper-stop` in the squashfs) — the
  unattended boot entry carries it, so the installer auto-ejects and reboots.
- **sudo credentials expire mid-provisioner-run** (~15 min tty ticket): the
  firstboot flow blocks at the next sudo prompt. Autologin builds bake
  NOPASSWD sudoers; interactive first boots are fine (user is watching).

## Verification checklist for any change

1. `bash -n` + shellcheck (docker) clean on touched scripts.
2. Fresh-clone audit: clone from GitHub, confirm new files exist.
3. Deploy to VM 114, full installer run, confirm green + idempotent second run.
4. If menus/theme changed: reboot the VM and check the session visuals.
5. If ISO-relevant: rebuild ISO on the node, boot-test to the installer
   screen (live session gets DHCP = squashfs valid), then restore VM 114.
6. Push, then verify the remote SHA server-side.

## Current state (2026-09-26)

- `main` past v0.2.0: unattended installer preseeding shipped (v0.3.0 line).
- Renamed from `zorin-ai` to **NoctraOS** (slug `noctraos`) — clean break, no
  migration shims. Existing VMs keep their old `zorin-ai` files until reset or
  re-provisioned. Test VM names (`zorin-ai-iso-test`, `zai-zerotouch-test`) are
  unchanged. Zorin OS remains the upstream base and is named only as such.
- ISO: `zorin-ai-os-18.1-amd64.iso` on the node (pre-rename name) is the v0.3
  (unattended) build; the v0.2 image is `zorin-ai-os-18.1-v0.2.iso`. New builds
  are named `noctraos-18.1-amd64.iso`.
  pve-root is at 90% — free space before the next build.
- VM 110 `zai-zerotouch-test` (192.168.8.138, dazeb/zorin-test-2026, DHCP!):
  installed **fully zero-touch** from the v0.3 ISO on 2026-09-27 (boot →
  install → reboot → autologin → provision, no interaction; `zom doctor`
  all green). It is the v0.3 reference install. VM 114 (192.168.8.187) is
  the v0.2 reference.
- VM 114 holds Super+Space search and the Noctra start button as
  `zorin-ai-search@zorin-ai.local` / `zorin-ai-branding@zorin-ai.local`
  extensions that are NOT in the repo yet; import and rename them.
- Roadmap ideas: first-run onboarding showcasing Super+Space, theme gap list
  (see README), Aider/Goose launchers (non-npm install paths), greeter-bug
  root cause.
