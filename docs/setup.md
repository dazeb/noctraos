# Setup and maintenance

[← Back to NoctraOS](../README.md)

For downloads and checksums, start at [noctraos.dev/download](https://noctraos.dev/download).
This guide covers provisioning an existing machine, configuration, GPU setup,
ISO builds, and day-to-day maintenance.

## Install on Proxmox VE

One command on the Proxmox host (as root, Proxmox VE 8 or 9) creates a ready UEFI VM, either from
the ready-made VM disk (signs in as `noctraos` / `noctraos`, trial use) or from the installer ISO
with an empty disk. It asks for RAM, cores and storage, checks the download against `SHA256SUMS`,
and removes a half-made VM if anything fails.

```sh
bash <(curl -sSfL https://raw.githubusercontent.com/dazeb/noctraos/main/proxmox-install.sh)
```

Every question can be answered through environment variables instead (`NOCTRAOS_MODE`,
`NOCTRAOS_RAM`, `NOCTRAOS_CORES`, `NOCTRAOS_STORAGE`, ...; see the top of the script).

## Provision an existing machine

Use a supported base system and check the [requirements](#requirements) first.
This changes the machine; use a disposable VM for development and testing.

```bash
curl -fsSL https://raw.githubusercontent.com/dazeb/noctraos/main/boot.sh | bash
```

To read the scripts before running them:

```bash
git clone https://github.com/dazeb/noctraos.git
cd noctraos
./boot.sh
```

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

- Zorin OS 18.1 Core (Ubuntu 24.04 LTS based; see [credits](../README.md#credits-and-license)).
  *Tested on this base; other Ubuntu-based systems are untested,
  and the theme step needs the base's own shell and GTK themes. The provisioner
  accepts any Ubuntu-based `/etc/os-release`.*
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

`iso/build-noctraos-iso.sh` remasters the base system's stock live ISO (see
[the base-system credits](../README.md#credits-and-license)). The easy way to run
it is `iso/build-local.sh`, which does the build in a privileged Docker container
on a workstation (about 2 minutes per ISO, work directory an ext4 image file so
an NTFS drive can host it):

```bash
iso/build-local.sh <dir> [release|appliance|both]    # default: release
# put Zorin-OS-18.1-Core-64-bit.iso in <dir>/in/ first; results land in <dir>/out/
```

It builds from a **fresh clone of GitHub `main`**, exactly like the first-boot
runner does, so push first. There are two kinds of ISO:

| Target | What it is | Output |
|---|---|---|
| `release` | The interactive installer. No unattended seed, no password hash, no unattended boot entry — the run **fails** if any of those is found. This is what gets published. | `noctraos-<VERSION>-amd64.iso` + `.sha256` |
| `appliance` | Unattended install, user `noctraos` / password `noctraos`, autologin and passwordless sudo. Only a means to build the downloadable VM disk. **Never publish it.** | `noctraos-<VERSION>-appliance-build.iso` |

`<VERSION>` comes from the `VERSION` file (it must match `bin/noc`; CI checks
this), not from the base ISO.

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
sudo ./iso/build-noctraos-iso.sh <base-iso> noctraos-amd64.iso
# needs: xorriso, squashfs-tools, git, openssl, python3, zstd, cpio, root, ~25 GiB scratch (WORK_BASE=…)
```

Two ways to install the result:

- **Interactive** (the release ISO) — boot it and click through
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
upload, tag, website) are in the [release runbook](release-runbook.md).

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
- **An app asks for a keyring password** — setup gives your account an unencrypted
  login keyring (while it is empty), so Hermes, browsers and VS Code do not ask. The
  catch: secrets in it are stored without a password. A keyring that already holds
  secrets is left as it is and can still prompt.
- **An AppImage does not start** — FUSE 2 is preinstalled; double-click it to
  install through AppManager, or mark it executable and run it.
- **Software Updater shows a large update on first login, in the base system's
  wording** — known and not addressed yet.
