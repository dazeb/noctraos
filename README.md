# NoctraOS

**An AI-ready desktop for people moving from Windows — Omarchy's idea, on an Ubuntu base, without the learning curve.**

NoctraOS is a complete, opinionated workstation: a local LLM stack, a Start
panel built around AI agents, a first-run welcome, polyglot runtimes, and a dark
theme with amber highlights. Everything is where a Windows user expects it (a
dock with a Start button, window buttons, a task manager), so there is nothing to
relearn — except one new idea, **Super+Space** (the Windows key and Space), which
searches your whole system (apps, files, clipboard history, the web, and
optionally your browser history) from a single keystroke.

The product is a **bootable ISO**; the same idempotent provisioner also runs on
an existing [Zorin OS](https://zorin.com) 18.x machine. See
[the objectives](docs/objectives.md) for who this is for and where it is going.

It follows the [Omakub](https://omakub.org) pattern for provisioning, with one
deliberate difference: **no terminal required**. Nothing in the day-to-day
workflow needs one — unless you want it, because the terminal is where the agents
live.

Provision an existing Zorin OS 18.x machine:

```bash
curl -fsSL https://raw.githubusercontent.com/dazeb/noctraos/main/boot.sh | bash
```

Prefer to review first: `git clone https://github.com/dazeb/noctraos && cd noctraos && ./boot.sh`

> **Release status:** the current version is **0.3.0** (`VERSION`), but the
> installer ISO and the VM disk are **not published yet** — build the ISO
> yourself ([below](#building-the-noctraos-iso)). What is left to ship is in the
> [release runbook](docs/release-runbook.md).

---

## What you get

| Area | Software |
|------|----------|
| First run | **NoctraOS Welcome** (`noctraos-welcome`) replaces Zorin's tour: four short screens — what NoctraOS is, *press Windows+Space* (it moves on when you do), where familiar things are, and your AI. Shown once per account; on the ISO it opens while setup is still running. Reopen it any time from the Start menu. See [onboarding](docs/onboarding.md) |
| **Super+Space search** | One overlay that searches apps, files and folders, CopyQ clipboard history, the web, and (opt-in, offered after first browser use) your Chromium/Firefox browser history; settings in *Search settings* (the gear). Installed by module 09 |
| Start panel and dock | The **N** Start button opens a sharp, monospace panel above a centred dock: your name and an opt-in weather readout, the pinned **Agents** row, **recent files**, *All apps*, a settings gear and a "New users start here" help page. The top bar keeps the clock, tray and a Show Desktop button. See [desktop layout](docs/desktop-layout.md) |
| Local AI | [Ollama](https://ollama.com) on `127.0.0.1:11434` with `qwen2.5-coder:7b` (coding) and `nomic-embed-text` (embeddings for RAG) |
| GPU acceleration | Auto-detects NVIDIA and AMD GPUs at onboarding: NVIDIA → signed Ubuntu driver + CUDA toolkit, AMD → ROCm (see [GPU setup](#gpu-setup)) |
| Agents menu | **Hermes** (desktop app, preinstalled, free to start with no signup — its free tier runs on Nous Research's cloud, so prompts leave the computer; one click for local-only, and the local Ollama model is the offline fallback) plus **Codex, Claude Code, OpenCode, Grok, Gemini CLI, Qwen Code** — each launches in a terminal and installs itself on first use (with your consent) |
| Local LLM menu | **AI Models** manager and **AI Health Check**; editor chat through Continue |
| Editor | [Microsoft VS Code](https://code.visualstudio.com) + Continue.dev (pre-wired to local Ollama), GitLens, Prettier, Python, Go |
| Agent sessions | [Herdr](https://herdr.dev) persistent workspaces, installed through mise and launched from Development |
| Workstation apps | **Flatpak first**: Chromium, Obsidian, LocalSend, Pinta, Moonlight, LibreOffice, VLC, MPV, Kdenlive, OBS Studio, gThumb, Evince, Flameshot, Xournal++, and Mission Center. From apt: GNOME Disks, Sushi preview, GNOME Tweaks, CUPS printing, Tesseract OCR. See [app policy](#app-policy) |
| Developer tools | btop, bat, eza, fd-find, fzf, ripgrep, zoxide, tmux, Starship, lazygit, lazydocker, GitHub CLI, Docker/Compose, clang, Ruby, ffmpeg, ImageMagick, yt-dlp, tldr |
| Task manager | Mission Center (Flathub) — the familiar Task-Manager role: CPU/RAM/GPU and running apps |
| Runtimes | [mise](https://mise.jdx.dev) managing Node LTS, Python 3.12, Go — system-wide, for every user |
| Mouse ergonomics | Nautilus right-click: *Open in VS Code*, *Ask AI to Explain* (sends the file to local Ollama, answers in a dialog), *Open Terminal Here* |
| AppImages | [AppManager](https://github.com/kem-a/AppManager) — double-click any `.AppImage` for a drag-and-drop install window (menu entry, icon, auto-updates); FUSE 2 is preinstalled so other AppImages run too. Installed by module 04d (`04d_appmanager.sh`) |
| Clipboard | [CopyQ](https://hluk.github.io/CopyQ/) permanent clipboard history — tray-resident, survives reboots, searchable, image support, 1000 entries. Runs as an X11 client on purpose: as a native Wayland client it records nothing on GNOME |
| Appearance | **NoctraOS Appearance** (`noctraos-appearance`): wallpaper and fonts, applied immediately, every font setting resettable. The theme and layout are fixed, so there is no theme switcher |
| Desktop | NoctraOS-Dark shell and GTK themes, sharp (0 px) corners, white menu icons, six polygonal 4K wallpapers, dark mode, minimize/maximize/close window buttons, JetBrains Mono |
| Boot chain | Plymouth splash, GRUB and isolinux menus, and a dark installer, in the NoctraOS palette (ISO, and module 10 for other installs) |
| Maintenance | `noc` CLI + `noc-menu` GUI panel |
| Persistence | New user accounts inherit the whole setup via `/etc/skel` |
| Bootable ISO | Build a **NoctraOS** image with everything baked in (see below) |

### The menu, rebuilt AI-first

The stock GNOME category tree (Accessories, Graphics, Office…) is replaced. The
Start panel shows the pinned Agents row and recent files; **All apps** shows the
curated tree:

```
Agents  →  Hermes · Codex · Claude Code · OpenCode · Grok · Gemini CLI · Qwen Code
Local LLM  →  AI Models · AI Health Check
Development  →  VS Code · Herdr …
Internet  ·  Media  ·  Utilities  ·  System
```

Everything still lives in **All Apps** and search — only the category browsing
is curated.

### App policy

Flatpak (Flathub) and AppImage first; apt is for CLI tools, system tools and
apps that need deep host integration (VS Code, CopyQ, Docker). Module 04c
enforces it:

- once an app's Flatpak is installed, the apt copy is retired (LibreOffice,
  VLC, MPV, OBS Studio, Kdenlive, gThumb, Evince, Flameshot, Xournal++);
- apps we do not ship are removed: Brave, Brasero, Rhythmbox, Videos, GNOME
  Tour, Weather, Evolution, Zorin Appearance, Zorin Connect, Web Apps, Windows
  App Support, Neovim; Chatbox, VSCodium and Foot are removed by module 04;
- removals are plain `apt-get remove` (no purge, no autoremove, user data stays),
  and each is simulated first and skipped if apt would also remove the desktop;
- launchers that only confuse are hidden with a `NoDisplay=true` copy in
  `/usr/local/share/applications` (delete the file to undo). Vim cannot be
  removed (Zorin's `zorin-os-minimal` depends on it), so only its launcher is hidden;
- no snaps.

## The look

The main desktop design follows **Omarchy Matte Black**: charcoal surfaces,
restrained borders, amber focus and active states, sharp (0 px) corners, and
JetBrains Mono in the shell and terminals. GNOME remains the desktop.

- **NoctraOS-Dark** derives from the installed Zorin Shell and GTK themes
  (recoloured from Zorin's blue at build time), then applies our overrides to
  panels, menus, quick settings, notifications, dialogs, buttons, entries, and
  selection states. The original system themes are never patched in place.
- **One palette** in `configs/theme/palette.json` generates the shell/GTK CSS,
  VS Code defaults, Herdr configuration, and btop theme. GNOME Terminal reads
  the same palette. Edit it and run `python3 scripts/render-theme.py`; use
  `--check` to verify that committed outputs match.
- **White menu icons and polygonal 4K wallpapers** retain the workstation's
  identity. Cycle the wallpapers with `noc bg next`, or pick one in
  *NoctraOS Appearance*.
- Existing VS Code settings are left intact (including comments and custom
  colors). Herdr is upgraded only when it matches our previous factory default.
  User GTK CSS is untouched; libadwaita, Qt, and sandboxed apps may retain
  their own styles.

See [the theme design](docs/theme-design.md) for the reference, per-surface
coverage, and what is still unthemed (the lock screen and login screen). GNOME
Terminal remains the default terminal.

The [Omarchy comparison](docs/omarchy-parity.md) maps its current application
manifest to the Zorin/Ubuntu equivalents and lists desktop-specific limits.

## Maintenance

```bash
noc update        # apt + Flatpak apps + mise runtimes + AI model refresh
noc doctor        # health check: OS, Ollama + models, mise runtimes, VS Code, search, Hermes, AppManager, GPU, disk
noc models list   # local models
noc models pull <model>   # e.g. noc models pull llama3.2:3b
noc models rm <model>
noc models gui    # pick from a curated list (zenity)
noc bg list|next|set <name>   # the wallpaper set
noc gpu detect    # what GPU you have and what would be installed
noc gpu install   # (re)run GPU driver + CUDA/ROCm setup — safe to repeat
noc gpu status --smoke   # verify driver, CUDA/ROCm, and run a real device probe
noc-menu          # update, health check, models, GPU — mouse-driven
```

Hermes has its own launcher, also available from the Agents menu:
`noctraos-hermes` (launch), `local` (local-only: Ollama primary, free tier off,
persistent), `status`, `ready`, `install`.

Agents are managed from the **Agents** menu; each CLI agent checks for its
command and offers a one-click npm install the first time you use it (node comes
from mise).

## Requirements

- Zorin OS 18.x (Ubuntu 24.04 base). *Tested on Zorin OS 18.1; 17.x is
  untested but the provisioner accepts any `zorin`/Ubuntu-based `/etc/os-release`.*
- A user with sudo (headless/SSH runs need passwordless sudo or cached credentials)
- ≥ 25 GB free disk (models + runtimes); a re-run of an already provisioned machine
  needs only 8 GB. The Hermes Desktop build adds about 5 GB. **8 GB RAM minimum**,
  16 GB recommended for 7B-class local models (you get a warning below that)
- Internet access (Ubuntu archive + Flathub + GitHub reachability is checked)
- Setup takes roughly 25 to 40 minutes on first run; most of it is the Ollama model
  download and the Hermes Desktop (Electron) build

## Configuration

Environment variables, all optional:

| Variable | Default | Purpose |
|----------|---------|---------|
| `NOCTRAOS_MODEL` | `qwen2.5-coder:7b` | Coding model pulled by module 03 |
| `NOCTRAOS_EMBED_MODEL` | `nomic-embed-text` | Embedding model for RAG |
| `NOCTRAOS_REPO_URL` | `https://github.com/dazeb/noctraos.git` | Source repo (boot.sh + ISO first-boot) |
| `NOCTRAOS_BRANCH` | `main` | Branch to pull |
| `NOCTRAOS_HOME` | `~/.local/share/noctraos` | Provisioner install location |
| `NOCTRAOS_LOG` | `/tmp/noctraos-install-<ts>.log` | Installer log path |
| `NOCTRAOS_OLLAMA_URL` | `http://localhost:11434` | Endpoint used by the *Ask AI to Explain* script |

Installer flags: `--skip-ai` (no Ollama/model downloads), `--skip-gui`
(headless-ish: skips GUI apps, app policy, Nautilus scripts, themes, search,
boot theme and Hermes), `--skip-gpu` (no GPU driver / CUDA / ROCm step), and
`--only <module>` (run one module with the full environment, then stop — e.g.
`bash ~/.local/share/noctraos/install.sh --only 04d_appmanager.sh` to retry a
flaky download).

GPU variables (read by `noc gpu install`): `NOCTRAOS_GPU_PROFILE=runtime|full`
(default `full`; `runtime` = libraries only, no compilers/SDK),
`NOCTRAOS_GPU_VENDORS=nvidia|amd|all`, `NOCTRAOS_CUDA_VERSION` (e.g. `12.9`),
`NOCTRAOS_ROCM_VERSION` (e.g. `7.2.4`; re-runs otherwise keep the release already
installed, so they work offline and never jump a ROCm major), and
`NOCTRAOS_GPU_FORCE_ROCM=1` to try ROCm on an AMD model the installer does not recognise.

## GPU setup

Onboarding (module `02b_gpu_drivers`, before Ollama) reads `lspci`, works out
which vendor and generation each GPU is, and installs only what that hardware
can use. Run it again any time with `noc gpu install`; `--dry-run` shows every
action first. Machines with no NVIDIA/AMD GPU (VMs, Intel-only) are skipped.

| Detected | Installed |
|----------|-----------|
| NVIDIA Turing or newer (RTX 20xx → 50xx, A/H/B-series) | Ubuntu's **signed** driver via `ubuntu-drivers` (open kernel modules where recommended) + the newest CUDA 13.x toolkit |
| NVIDIA Maxwell / Pascal / Volta (GTX 9xx/10xx, Titan V) | Driver branch 580 (the last to support them) + **CUDA 12.9**; CUDA 13 dropped these chips |
| NVIDIA Kepler or older | Nothing — too old for CUDA or Ollama; stays on nouveau/CPU |
| AMD with ROCm support (RX 7000/9000, RX 6800/6900, Strix Halo, Instinct) | In-kernel `amdgpu` + ROCm from AMD's apt repo (HIP SDK), `render`/`video` groups |
| AMD RX 6500/6600/6700 (Navi 22/23/24) | Same, plus `HSA_OVERRIDE_GFX_VERSION=10.3.0` for the Ollama service |
| AMD integrated / older (APUs, RDNA1, Vega 10, Polaris) or any model not positively recognised | Mesa Vulkan only — ROCm doesn't support them; llama.cpp's Vulkan backend works |

Design choices worth knowing:

- **NVIDIA driver and CUDA come from different places on purpose.** The driver is
  Ubuntu's prebuilt, kernel-matched, Secure-Boot-signed package. The CUDA toolkit
  comes from NVIDIA's apt repo, with that repo's driver packages pinned off
  (`/etc/apt/preferences.d/noctraos-cuda-toolkit-only`) so it can never swap the
  driver underneath you. No DKMS in the normal case, so no MOK enrolment prompt.
- **CUDA is matched to the driver and GPU.** CUDA 13 needs driver ≥ 580; older
  drivers get CUDA 12.x. Nothing is installed if a working driver or `nvcc` is
  already there (including a hand-installed one) — it is left alone.
- **AMD uses the inbox kernel driver**, no `amdgpu-dkms`. The ROCm repo is pinned
  to the newest release that exists for your Ubuntu codename, so `apt upgrade`
  never jumps a ROCm major version.
- **A reboot is needed after the first NVIDIA driver install** (the kernel module
  loads on boot); AMD needs a re-login for the new groups. The installer says so
  and sets Ubuntu's `reboot-required` flag. Ollama picks the GPU up automatically
  afterwards.
- GPU failure never blocks the rest of onboarding; it warns and carries on.
- Tools land on `PATH` via `/etc/profile.d/noctraos-gpu.sh` (`CUDA_HOME`,
  `/usr/local/cuda/bin`, `/opt/rocm/bin`).

## Building the NoctraOS ISO

`iso/build-noctraos-iso.sh` remasters a stock Zorin live ISO. The easy way to run
it is `iso/build-local.sh`, which does the build in a privileged Docker container
on a workstation (about 2 minutes per ISO, work directory an ext4 image file so
an NTFS drive can host it):

```bash
iso/build-local.sh <dir> [release|appliance|both]    # default: release
# <dir>/in/Zorin-OS-18.1-Core-64-bit.iso must exist first; results land in <dir>/out/
```

It builds from a **fresh clone of GitHub `main`**, exactly like the first-boot
runner does, so push first. There are two kinds of ISO:

| Target | What it is | Output |
|---|---|---|
| `release` | The interactive installer. No unattended seed, no password hash, no unattended boot entry — the run **fails** if any of those is found. This is what gets published. | `noctraos-<VERSION>-amd64.iso` + `.sha256` |
| `appliance` | Unattended install, user `noctraos` / password `noctraos`, autologin and passwordless sudo. Only a means to build the downloadable VM disk. **Never publish it.** | `noctraos-<VERSION>-appliance-build.iso` |

`<VERSION>` comes from the `VERSION` file (it must match `bin/noc`; CI checks
this), not from the Zorin base ISO.

What the build does (`iso/build-noctraos-iso.sh`, also usable directly on a node
with root and ~25 GiB scratch):

1. extracts the ISO tree and unpacks `casper/filesystem.squashfs`
2. bakes in a snapshot of this provisioner at `/opt/noctraos`
3. adds `/usr/local/sbin/noctraos-firstboot` + an autostart entry so the
   provisioner runs on the user's **first desktop login** after installation
   (it prefers a fresh clone from GitHub and falls back to the baked snapshot
   when offline). The runner also opens the NoctraOS Welcome while setup runs
4. only when `NOCTRAOS_UNATTENDED=1`: generates an unattended-install seed from
   `iso/preseed/noctraos.seed.in` (baked at `/preseed/noctraos.seed`) and adds an
   **"Install NoctraOS (unattended)"** entry to the BIOS + UEFI boot menus
5. themes the boot chain (`iso/boot-theme.sh`, artwork in `assets/boot/`): the
   BIOS (isolinux) and UEFI (GRUB) menus, the live-boot Plymouth splash inside
   `casper/initrd.zstd`, the installed system's splash and GRUB theme, and a dark
   live/installer session with NoctraOS wording and pictures
6. resquashes with the original compressor and rewrites the ISO preserving BIOS +
   UEFI boot equipment, with a correct `md5sum.txt` (the live boot checks it)
7. prints the new sha256

Direct use:

```bash
sudo ./iso/build-noctraos-iso.sh Zorin-OS-18.1-Core-64-bit.iso noctraos-amd64.iso
# needs: xorriso, squashfs-tools, git, openssl, python3, zstd, cpio, root, ~25 GiB scratch (WORK_BASE=…)
```

Two ways to install the result:

- **Interactive** (the release ISO) — boot it like normal Zorin and click through
  the installer ("Try or Install NoctraOS"). On first login the Welcome opens and
  a terminal asks once for your sudo password, then builds the workstation.
- **Fully unattended** (builds with `NOCTRAOS_UNATTENDED=1`) — pick "Install
  NoctraOS (unattended)", which is the default with a 5 s timeout. The OS
  installs hands-off (locale, keyboard, whole-disk partitioning, user, GRUB —
  all preseeded), reboots straight into the new system, and the provisioner
  starts on its own. It **wipes the disk without asking.**

Unattended builds default to **autologin + passwordless sudo** for the created
user (appliance semantics — the firstboot provisioning runs with zero
interaction, and the GDM greeter is broken on this base anyway). Set
`NOCTRAOS_AUTOLOGIN=0` to keep a locked-down first boot.

Build-time knobs (all optional): `NOCTRAOS_UNATTENDED`, `NOCTRAOS_AUTOLOGIN`,
`NOCTRAOS_USER` (default `noctraos`), `NOCTRAOS_FULLNAME`, `NOCTRAOS_HOSTNAME`
(default `noctraos`), `NOCTRAOS_PASSWORD` (default `noctraos`),
`NOCTRAOS_LOCALE` (`en_US.UTF-8`), `NOCTRAOS_KEYMAP` (`us`),
`NOCTRAOS_TIMEZONE` (`UTC`).

> **Heads-up:** an unattended seed contains the created user's password hash —
> anyone holding the ISO can read it. Bake throwaway credentials only, and never
> publish an unattended ISO.

### Testing and VM images

- `iso/local-vm.sh` is a local KVM test VM (UEFI, user-mode networking, no root,
  no host changes): `start [iso]`, `shot`, `click`, `key`, `ssh`, `scp`.
- `iso/vm-sysprep.sh` runs inside a fully provisioned VM before its disk is
  exported as a downloadable image: it strips the machine id, SSH host keys,
  Hermes identity and history, logs and caches, and refuses to run on bare metal.
- `iso/pve-console-shot.py` grabs console frames from a Proxmox VM through the API.

The ordered steps from a fresh build to a published release (test, VM disk,
upload, tag, website) are in the [release runbook](docs/release-runbook.md).

## Architecture

```
boot.sh ──► install.sh ──► modules, in this order
                            │
   00 preflight             │  user / OS / network / disk (25 GB; 8 GB on a re-run) / RAM guards
   01 system                │  apt core, Flathub, FUSE, Nerd Fonts
   02 mise                  │  runtime manager, login + interactive shells, Herdr, Starship, lazygit, lazydocker
   02b gpu drivers          │  NVIDIA driver + CUDA / AMD ROCm (non-fatal; bin/noc-gpu)
   03 ai core               │  Ollama daemon, coding + embedding models
   04 gui apps              │  VS Code (+ extensions), Continue, Mission Center, CopyQ; retires VSCodium/Chatbox/Foot
   04 workstation apps      │  Ubuntu apt tools + the Flathub app set
   04c app policy           │  Flatpak/AppImage first: retire apt copies and unwanted apps, hide junk launchers
   04d appmanager           │  AppManager (AppImage installer/updater; non-fatal)
   05 mouse ergonomics      │  Nautilus right-click scripts
   06 desktop theme         │  gsettings ergonomics, wallpapers, Agents menu, AI-first menu tree
   08 shell theme           │  NoctraOS-Dark shell/GTK, white icons, app palette
   09 super search          │  Super+Space overlay, Noctra Start panel + branding extensions, index timer
   10 boot theme            │  Plymouth splash + GRUB theme for non-ISO installs
   07 persistence           │  /etc/skel defaults, noc / noc-menu / noc-gpu
   11 hermes                │  Hermes Desktop runtime + app (25+ min, no sudo, so it runs last)
```

(`--skip-gui` skips 04 through 06 and 08 through 10, and 11.)

**Idempotence is the contract**: every module guards every mutation, so the
installer can be re-run after a crash, an OS update, or just to catch up —
and the ISO's first-boot runner relies on exactly that.

`gsettings`/dconf work is executed against the user's **real desktop session
bus** (`/run/user/<uid>/bus`), so theme changes apply to the running session
rather than a throwaway bus.

## Repository layout

```
boot.sh                  remote fetcher
install.sh               orchestrator (--skip-ai, --skip-gui, --skip-gpu, --only <module>)
install/                 modules 00–11 + lib.sh (shared helpers)
bin/                     noc, noc-gpu, noc-menu, noctraos-agent, noctraos-hermes, noctraos-welcome,
                         noctraos-appearance, noctraos-search, noctraos-weather
branding/                setup-branding.py: the dock and top-bar layout, once per account
configs/                 mise, VS Code, Continue.dev, CopyQ, Hermes onboarding prompt, .desktop launchers,
                         autostart, gsettings schemas, systemd units, theme palette, XDG menu tree, Nautilus scripts
extensions/              GNOME Shell extensions: Super+Space search, Noctra Start panel, branding (top bar)
search/                  search app (index, clipboard bridge, browser history, settings window)
help/                    the "New users start here" page the Start panel opens
scripts/                 render-theme.py, build-desktop-theme.py, seed-password-store.py
assets/wallpapers/       generator + six seeded 4K scenes
assets/icons/            white SVG glyphs (+ overrides/ for stock icon names, noctraos-theme/ icon theme)
assets/boot/             Plymouth, GRUB, isolinux and installer artwork + generator
iso/                     ISO build (build-noctraos-iso.sh, build-local.sh), boot theming, preseed template,
                         local test VM, VM sysprep, Proxmox console helper
tests/                   unit tests: theme composition, GPU detection
site/                    the project website (Cloudflare Workers static assets, see wrangler.jsonc)
docs/                    objectives, onboarding, desktop layout, theme design, Omarchy comparison, release runbook
```

## Testing

```bash
bash -n boot.sh install.sh install/*.sh bin/noc bin/noc-gpu bin/noc-menu bin/noctraos-agent \
  bin/noctraos-hermes bin/noctraos-search configs/nautilus-scripts/*          # syntax (the other bin/ files are Python)
python3 -m unittest discover -s tests -v                                       # theme composition + GPU detection
python3 scripts/render-theme.py --check                                        # committed theme outputs match palette.json
```

CI runs the same checks: `.gitlab-ci.yml` (the homelab GitLab and its Docker runner;
GitHub Actions is not available on this account) does `bash -n` and shellcheck at
warning severity, the `VERSION` / `bin/noc` / `bin/noc-gpu` match, the unit tests and
the theme check, and can deploy `site/` to Cloudflare from `main`.
`.github/workflows/ci.yml` carries the shell and version checks only. Never run
`install.sh` on a development workstation: it changes the machine. Runtime
testing happens in a VM (`iso/local-vm.sh`); see [AGENTS.md](AGENTS.md).

## Troubleshooting

- **Menu changes didn't appear** — the shell caches the menu tree per session, and
  a newly installed Shell extension loads at the next login on Wayland;
  log out/in (or reboot). Super+Space says so in the Welcome during first-boot setup.
- **"Ask AI to Explain" is slow the first time** — the model loads into RAM on
  first use (~30 s warm-up; longer on CPU-only machines).
- **Ollama runs on CPU** — expected with no supported GPU. Run `noc gpu detect`
  to see what was found. After a first NVIDIA install, reboot; after an AMD
  install, log out/in. `noc gpu status --smoke` proves the GPU is usable.
- **NVIDIA driver installed but `nvidia-smi` fails** — you haven't rebooted yet,
  or Secure Boot blocked an unsigned (DKMS) module; `noc gpu status` says which.
- **Installer says sudo is required over SSH** — headless runs need
  passwordless sudo or recently cached credentials; interactive runs can just
  type the password.
- **An agent isn't installed yet** — launch it from the Agents menu and accept
  the install prompt; it needs node (included) and internet.
- **The Hermes buttons in the Welcome are disabled** — Hermes' runtime and desktop
  app are still being built (25 to 40 minutes on first setup, last module).
  `noctraos-hermes status` shows where it is; launching Hermes from the Agents
  menu later installs whatever is missing.
- **Hermes and privacy** — the local Ollama model never leaves the computer, but
  Hermes' free tier is a cloud service. For local-only use pick *Hermes, local only*
  in the Welcome, or run `noctraos-hermes local` (undo: `hermes config set model.provider auto`).
- **A browser asks for a keyring password** — Chromium and VS Code are set up to
  avoid it. Browsers you install yourself (Brave, Chrome, Edge) still prompt,
  because autologin leaves the login keyring locked.
- **An AppImage does not start** — FUSE 2 is preinstalled; double-click it to
  install through AppManager, or mark it executable and run it.
- **Software Updater shows a large update in Zorin wording on first login** —
  known and not addressed yet.

## Status & roadmap

Version **0.3.0**. The provisioner has been run on Zorin OS 18.1 in a VM: full install,
idempotent re-runs, first-boot provisioning from the ISO, and an unattended install from
the custom ISO. **Those runs predate PR #17** (app policy, AppManager, the Welcome and
Appearance apps, Hermes changes); every ISO built so far was made before it, so the
current `main` has not been through that full cycle and the ISOs must be rebuilt and
re-tested. The 0.3.0 release itself is **not published** — no tag, no GitHub release,
no downloadable ISO or VM disk yet; the [release runbook](docs/release-runbook.md) is
the ordered list of what is left.

Not yet verified: the Welcome running during first-boot provisioning on a
from-scratch install, a full interactive install of the release ISO, the exported
VM disk booting, and the boot menus and splash on real hardware (they have only
been seen under QEMU).

On the roadmap, roughly in priority order:

- finish shipping 0.3.0 (above);
- Welcome: prefilled search examples (needs a D-Bus `Open(query)` on the search
  extension) and a provisioner log panel — [onboarding](docs/onboarding.md);
- a faster first boot: a prebuilt Hermes Desktop AppImage instead of a 25 to 40
  minute local Electron build, and eventually models baked into the image;
- Start panel: an apps list and a settings page for customisation —
  [desktop layout](docs/desktop-layout.md);
- more agent launchers (Aider, Goose — non-npm install paths);
- reskin gaps: libadwaita/GTK 4 apps, the lock and login screens, and the
  remaining stock icons — [theme design](docs/theme-design.md).

## Documentation

| Document | What it covers |
|---|---|
| [docs/objectives.md](docs/objectives.md) | Who NoctraOS is for and the principles; wins over this README if they disagree |
| [docs/onboarding.md](docs/onboarding.md) | The first-run Welcome, the shortcut audit, the clipboard decision |
| [docs/desktop-layout.md](docs/desktop-layout.md) | Top bar, dock and the Start panel |
| [docs/theme-design.md](docs/theme-design.md) | Palette, per-surface coverage, remaining gaps |
| [docs/omarchy-parity.md](docs/omarchy-parity.md) | Omarchy app manifest mapped to Zorin/Ubuntu |
| [docs/release-runbook.md](docs/release-runbook.md) | Ordered handoff for shipping 0.3.0 |
| [AGENTS.md](AGENTS.md) | Rules, infrastructure and known pitfalls for coding agents |
| [PLAN.md](PLAN.md) | The original build plan (historical) |

## License

Not yet selected — all rights reserved until then. Agent names and logos
belong to their respective projects; NoctraOS ships none of them, only
launchers.
