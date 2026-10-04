# NoctraOS

**An AI-ready desktop for people moving from Windows — Omarchy's idea, on an Ubuntu base, without the learning curve.**

NoctraOS is a complete, opinionated workstation: a local LLM stack, a start
menu built around AI agents, polyglot runtimes, and a dark theme with amber
highlights. Everything is where a Windows user expects it (taskbar, start
button, window buttons, a task manager), so there is nothing to relearn —
except one new idea, **Super+Space**, which searches your whole system
(apps, files, clipboard history, the web) from a single keystroke.

The product is a **bootable ISO**; the same idempotent provisioner also runs
on an existing [Zorin OS](https://zorin.com) 18.x machine. See
[the objectives](docs/objectives.md) for who this is for and where it is going.

It follows the [Omakub](https://omakub.org) pattern for provisioning with one
deliberate difference: **full mouse parity**. Nothing in the day-to-day
workflow requires opening a terminal — unless you want to, because the
terminal is where the agents live.

Provision an existing Zorin OS 18.x machine:

```bash
curl -fsSL https://raw.githubusercontent.com/dazeb/noctraos/main/boot.sh | bash
```

Prefer to review first: `git clone https://github.com/dazeb/noctraos && cd noctraos && ./boot.sh`

---

## What you get

| Area | Software |
|------|----------|
| Local AI | [Ollama](https://ollama.com) on `127.0.0.1:11434` with `qwen2.5-coder:7b` (coding) and `nomic-embed-text` (embeddings for RAG) |
| GPU acceleration | Auto-detects NVIDIA and AMD GPUs at onboarding: NVIDIA → signed Ubuntu driver + CUDA toolkit, AMD → ROCm (see [GPU setup](#gpu-setup)) |
| Agents menu | **Codex, Claude Code, OpenCode, Grok, Gemini CLI, Qwen Code** — each launches in a terminal and installs itself on first use (with your consent) |
| Local LLM menu | **AI Models** manager and **AI Health Check**; editor chat through Continue |
| Editor | [Microsoft VS Code](https://code.visualstudio.com) + Continue.dev (pre-wired to local Ollama), GitLens, Prettier, Python, Go |
| Agent sessions | [Herdr](https://herdr.dev) persistent workspaces, installed through mise and launched from Development |
| Workstation apps | Chromium, Obsidian, LocalSend, Pinta, Moonlight, LibreOffice, MPV, Kdenlive, OBS Studio, Flameshot, Xournal++, Evince, GNOME Disks, and Sushi preview |
| Developer tools | btop, bat, eza, fd-find, fzf, ripgrep, zoxide, neovim, tmux, Starship, lazygit, lazydocker, GitHub CLI, Docker/Compose, clang, Ruby, ffmpeg, ImageMagick, yt-dlp, tldr |
| Task manager | Mission Center (Flathub) — the familiar Task-Manager role: CPU/RAM/GPU and running apps |
| Runtimes | [mise](https://mise.jdx.dev) managing Node LTS, Python 3.12, Go — system-wide, for every user |
| Mouse ergonomics | Nautilus right-click: *Open in VS Code*, *Ask AI to Explain* (sends the file to local Ollama, answers in a dialog), *Open Terminal Here* |
| **Super+Space search** | One overlay that searches apps, files and folders, CopyQ clipboard history, the web, and (opt-in, offered after first browser use) your Chromium/Firefox browser history; settings in *Search settings* (the gear). Installed by module 09 |
| Clipboard | [CopyQ](https://hluk.github.io/CopyQ/) permanent clipboard history — tray-resident, survives reboots, searchable, image support, 1000 entries |
| Desktop | NoctraOS-Dark shell theme, AI-first start menu, white menu icons, neon polygonal 4K wallpapers, dark mode, minimize/maximize/close window buttons, pinned taskbar |
| Maintenance | `noc` CLI + `noc-menu` GUI panel |
| Persistence | New user accounts inherit the whole setup via `/etc/skel` |
| Bootable ISO | Build a **NoctraOS** image with everything baked in (see below) |

### The start menu, rebuilt AI-first

The stock GNOME category tree (Accessories, Graphics, Office…) is replaced:

```
Agents  →  Codex · Claude Code · OpenCode · Grok · Gemini CLI · Qwen Code
Local LLM  →  AI Models · AI Health Check
Development  →  VS Code …
Internet  ·  Media  ·  Utilities  ·  System
```

Everything still lives in **All Apps** and search — only the category browsing
is curated.

## The look

The main desktop design follows **Omarchy Matte Black**: charcoal surfaces,
restrained borders, amber focus and active states, sharp (0 px) corners, and
JetBrains Mono in the shell and terminals. GNOME remains the desktop.

- **NoctraOS-Dark** derives from the installed Zorin Shell and GTK themes, then
  applies our overrides to panels, menus, quick settings, notifications,
  dialogs, buttons, entries, and selection states.
- **One palette** in `configs/theme/palette.json` generates the shell/GTK CSS,
  VS Code defaults, Herdr configuration, and btop theme. GNOME Terminal reads
  the same palette. Edit it and run `python3 scripts/render-theme.py`; use
  `--check` to verify that committed outputs match.
- **White menu icons and polygonal 4K wallpapers** retain the workstation's
  identity. Cycle the wallpapers with `noc bg next`.
- Existing VS Code settings are left intact (including comments and custom
  colors). Herdr is upgraded only when it matches our previous factory default.
  User GTK CSS is untouched; libadwaita, Qt, and sandboxed apps may retain
  their own styles.

See [the theme design](docs/theme-design.md) for the reference, scope, and next
surfaces. Chatbox, VSCodium, and Foot are removed by the GUI module if their
apt packages are installed; personal settings and chat data are retained.
GNOME Terminal remains the default terminal.

The [Omarchy comparison](docs/omarchy-parity.md) maps its current application
manifest to the Zorin/Ubuntu equivalents and lists desktop-specific limits.

## Maintenance

```bash
noc update        # apt + Flatpak apps + mise runtimes + AI model refresh
noc doctor        # health check: OS, Ollama + models, mise runtimes, editors, GPU, disk
noc models list   # local models
noc models pull <model>   # e.g. noc models pull llama3.2:3b
noc models gui    # pick from a curated list (zenity)
noc bg next       # cycle the wallpaper set
noc gpu detect    # what GPU you have and what would be installed
noc gpu install   # (re)run GPU driver + CUDA/ROCm setup — safe to repeat
noc gpu status --smoke   # verify driver, CUDA/ROCm, and run a real device probe
noc-menu          # all of the above, mouse-driven
```

Agents are managed from the **Agents** menu; each entry checks for its CLI and
offers a one-click npm install the first time you use it (node comes from mise).

## Requirements

- Zorin OS 18.x (Ubuntu 24.04 base). *Tested on Zorin OS 18.1; 17.x is
  untested but the provisioner accepts any `zorin`/Ubuntu-based `/etc/os-release`.*
- A user with sudo (headless/SSH runs need passwordless sudo or cached credentials)
- ≥ 25 GB free disk (models + runtimes); **8 GB RAM minimum**, 16 GB
  recommended for 7B-class local models (you get a warning below that)
- Internet access (Ubuntu archive + Flathub + GitHub reachability is checked)

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
(headless-ish: skips GUI apps, Nautilus scripts, theme, shell reskin),
`--skip-gpu` (no GPU driver / CUDA / ROCm step).

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

`iso/build-noctraos-iso.sh` remasters a stock Zorin live ISO:

1. extracts the ISO tree and unpacks `casper/filesystem.squashfs`
2. bakes in a snapshot of this provisioner at `/opt/noctraos`
3. adds `/usr/local/sbin/noctraos-firstboot` + an autostart entry so the
   provisioner runs on the user's **first desktop login** after installation
   (it prefers a fresh clone from GitHub and falls back to the baked snapshot
   when offline)
4. generates an unattended-install seed from `iso/preseed/noctraos.seed.in`
   (baked at `/preseed/noctraos.seed`) and adds an **"Install NoctraOS
   (unattended)"** entry to the BIOS + UEFI boot menus
5. themes the boot chain (`iso/boot-theme.sh`, artwork in `assets/boot/`): the
   BIOS (isolinux) and UEFI (GRUB) menus, the live-boot Plymouth splash inside
   `casper/initrd.zstd`, the installed system's splash and GRUB theme, and a dark
   live/installer session
6. resquashes with the original compressor and rewrites the ISO preserving BIOS +
   UEFI boot equipment, with a correct `md5sum.txt` (the live boot checks it)
7. prints the new sha256

```bash
sudo ./iso/build-noctraos-iso.sh Zorin-OS-18.1-Core-64-bit.iso noctraos-18.1-amd64.iso
# needs: xorriso, squashfs-tools, git, openssl, python3, zstd, cpio, root, ~25 GiB scratch (WORK_BASE=…)
```

Two ways to install the result:

- **Interactive** — boot it like normal Zorin and click through the installer
  ("Try or Install NoctraOS"). On first login a terminal appears, asks once
  for your sudo password, and builds the workstation.
- **Fully unattended** — pick "Install NoctraOS (unattended)" (or build with
  `NOCTRAOS_UNATTENDED=1` to make it the default with a 5 s timeout). The OS
  installs hands-off (locale, keyboard, whole-disk partitioning, user, GRUB —
  all preseeded), reboots straight into the new system, and the provisioner
  starts on its own.

Unattended builds default to **autologin + passwordless sudo** for the created
user (appliance semantics — the firstboot provisioning runs with zero
interaction). Set `NOCTRAOS_AUTOLOGIN=0` to keep a locked-down first boot.

Build-time knobs (all optional): `NOCTRAOS_UNATTENDED`, `NOCTRAOS_AUTOLOGIN`,
`NOCTRAOS_USER` (default `noctraos`), `NOCTRAOS_FULLNAME`, `NOCTRAOS_HOSTNAME`
(default `noctraos`), `NOCTRAOS_PASSWORD` (default `noctraos`),
`NOCTRAOS_LOCALE` (`en_US.UTF-8`), `NOCTRAOS_KEYMAP` (`us`),
`NOCTRAOS_TIMEZONE` (`UTC`).

> **Heads-up:** the baked seed contains the created user's password hash —
> anyone holding the ISO can read it. Bake throwaway credentials only.

## Architecture

```
boot.sh ──► install.sh ──► modules 00–08
                            │
   00 preflight             │  user / OS / network / disk / RAM guards
   01 system                │  apt core, Flathub, Nerd Fonts
   02 mise                  │  runtime manager, login + interactive shells
   03 ai core               │  Ollama daemon, coding + embedding models
   04 gui apps              │  VS Code (+5 extensions), Mission Center, CopyQ
   05 mouse ergonomics      │  Nautilus right-click scripts
   06 desktop theme         │  ergonomics gsettings, wallpapers, Agents menu,
                            │  AI-first application menu tree
   07 persistence           │  /etc/skel defaults, noc CLI
   08 shell theme           │  Omarchy-inspired shell/GTK, white icons, app palette
```

**Idempotence is the contract**: every module guards every mutation, so the
installer can be re-run after a crash, an OS update, or just to catch up —
and the ISO's first-boot runner relies on exactly that.

`gsettings`/dconf work is executed against the user's **real desktop session
bus** (`/run/user/<uid>/bus`), so theme changes apply to the running session
rather than a throwaway bus.

## Repository layout

```
boot.sh                  remote fetcher
install.sh               orchestrator (--skip-ai, --skip-gui)
install/                 modules 00–08 + lib.sh (shared helpers)
bin/                     noc, noc-menu, noctraos-agent
configs/                 mise, VS Code, Continue.dev, .desktop launchers,
                         XDG menu tree, Nautilus scripts
extensions/              GNOME Shell extensions: Super+Space search, Noctra start button
search/                  search app (index, clipboard bridge, settings window)
assets/wallpapers/       generator + 5 seeded 4K scenes
assets/icons/            white SVG glyphs (+ overrides/ for stock icon names)
iso/                     build script + preseed template for unattended installs
```

## Troubleshooting

- **Menu changes didn't appear** — the shell caches the menu tree per session;
  log out/in (or reboot).
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

## Status & roadmap

Tested end-to-end on Zorin OS 18.1 (clean VM, full install, idempotent re-runs,
first-boot provisioning from the ISO, unattended install from the custom ISO).
Current release: **v0.3.0**.

On the roadmap, in priority order: a first-run
onboarding flow that puts Super+Space front and center
([draft](docs/onboarding.md)); the target desktop layout ([mockup](docs/desktop-layout.md)); the full-ISO
experience (boot, installer, login); the dark + amber reskin built around the
Super+Space look; more agent launchers (Aider, Goose — non-npm install
paths). Reskin items still to do before it is consistent everywhere: libadwaita/GTK 4 apps,
the login and lock screens, the installer's own artwork and slideshow, and the
remaining stock icons. The boot menus and splash are themed but have only been
seen under QEMU so far. See [the theme design](docs/theme-design.md).

## License

Not yet selected — all rights reserved until then. Agent names and logos
belong to their respective projects; NoctraOS ships none of them, only
launchers.
