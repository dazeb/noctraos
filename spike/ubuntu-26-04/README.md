# Spike: NoctraOS on Ubuntu 26.04 ("resolute")

Status: investigation only. Uncommitted, unpushed, on branch `claude/ubuntu-26-bleeding-edge-9fac30`.
Delete this directory to abandon the spike. Nothing under `install/`, `iso/` or `configs/` is changed.

## Verified facts (2026-10-09)

- **No Zorin 26.04 base exists yet.** Zorin 18.1 is the current release (Ubuntu 24.04). Zorin 19 (on 26.04)
  is speculated, not announced. The only 26.04 base available now is **stock Ubuntu 26.04**, which means
  dropping Zorin's layer, or waiting.
- **The 26.04 ISO is already on disk and verified.** `/run/media/dazeb/2tb/UserData/Downloads/ubuntu-26.04-desktop-amd64.iso`
  matches the SHA-256 for `ubuntu-26.04-desktop-amd64.iso` in Canonical's `releases.ubuntu.com/resolute/SHA256SUMS`.
  Disk identifies as `Ubuntu 26.04 "Resolute Raccoon" - Release amd64 (20260423.1)`. (A 26.04.1 point release also
  exists; it is the newer choice for a build.)
- **Dev box is already Ubuntu 26.04.1 LTS** with GNOME Shell 50.1 and kernel 7.0. Useful as a reference, but the repo
  rule is that `install.sh` never runs here; runtime tests go in a VM.
- **The three GNOME extensions pin `"shell-version": ["46"]`.** GNOME 50 needs them ported and tested.
- **Apt:** 77 packages the provisioner asks for were checked against the resolute and noble indexes
  (`scripts/check-apt-packages.py`, output `out/apt-check.tsv`). 73 are available on resolute. Four are not:
  - `libfuse2`: expected. The provisioner already prefers `libfuse2t64`.
  - `code`: comes from Microsoft's repo, not the Ubuntu archive. Microsoft's `dists/stable` answers (HTTP 200); not yet confirmed for resolute.
  - `nautilus-extension-gnome-terminal`: GNOME Terminal is replaced by Ptyxis on 26.04 (Ptyxis 50.1 is on the dev box). Module 01 already treats this package as optional.
  - `tldr`: present in noble only. `tealdeer` is the likely replacement; not yet confirmed.
- **Zorin references: 103** (`scripts/zorin-couplings.sh` → `out/zorin-couplings.tsv`). Grouped:
  - ISO remaster tooling only, which disappears on a stock-base build: `iso/rebrand-labels.sh` 17, `iso/boot-theme.sh` 11, `iso/strip-census.sh` 7, `iso/build-local.sh` 3, `iso/setup-release-runner.sh` 3, `iso/build-release.sh` 2, `iso/build-nightly.sh` 1, `iso/initrd-theme.py` 1. About 45.
  - Install-side, these need real work: `install/04c_app_policy.sh` 16, the shell theme (`configs/theme/gnome-shell.css(.in)` 22, `install/08_shell_theme.sh` 6, `scripts/build-desktop-theme.py` 2), `branding/setup-branding.py` 2, `install/06`, `install/10`, `install/00` and `install/01` 1–2 each, `control/pages.py` 1.
- **Hard dependency, Zorin Taskbar:** `branding/setup-branding.py` reads the `org.gnome.shell.extensions.zorin-taskbar` schema
  to build the dock. Stock Ubuntu has no such schema; it has Ubuntu Dock (`dash-to-dock`). The dock layout must be rewritten.
- **Hard dependency, Zorin Menu:** `extensions/noctraos-start` hooks Zorin's menu API (`menuButtons`), and
  `extensions/noctraos-branding/stylesheet.css` styles `.zorin-menu`/`.zorintaskbarMainPanel`. Without Zorin these need
  removing or rewriting.
- **Unattended install is preseed/ubiquity today** (`iso/build-noctraos-iso.sh` writes `preseed/noctraos.seed`, boot args
  `maybe-ubiquity`). Ubuntu 26.04 is expected to use the newer subiquity/autoinstall installer. I could not confirm this from
  the ISO (the manifests I could read do not list the installer package). **Unverified**: confirm in the VM.
- **Tooling on this box:** qemu and OVMF are present, so the local KVM test bed works. `xorriso`, `genisoimage` and `isoinfo`
  are missing and need root. No passwordless sudo here. `bsdtar` was installed without root into `~/.local/spike-tools`.

## Not verified (must be tested, not assumed)

- GNOME 50 extension API breakage (the three extensions load and run).
- Whether the 26.04 desktop installer accepts an autoinstall seed, and its exact form.
- A ROCm repo for `resolute` (`bin/noc-gpu` maps the codename, but the repo itself is unchecked).
- The provisioner run on 26.04 end to end, with a second run for idempotence.

## Handoff plan

Lanes come from `jev lane classify`. Items that need a design choice stay with the lead; mechanical items go to Sonnet.

| # | Work | Lane | Why |
|---|------|------|-----|
| 1 | Resolve the 4 apt gaps (`tldr`→`tealdeer`, Microsoft `code` on resolute, Ptyxis/nautilus integration) and update package lists with version guards | small | Mechanical, fully specified by `out/apt-check.tsv` |
| 2 | Bump extension `shell-version` to 50 and port each extension to GNOME 50 APIs; test in a VM | high | API breakage is unknown; needs runtime checks |
| 3 | Replace the Zorin Taskbar dock layout in `branding/setup-branding.py` with Ubuntu Dock settings | medium | Clear target, one file, schema-level |
| 4 | Rewrite or remove the Start panel (`noctraos-start`) and the `.zorin-menu` styling | high | Design choice; hooks private-looking APIs |
| 5 | Derive the shell and GTK theme from Yaru instead of ZorinGrey (`build-desktop-theme.py`, `08_shell_theme.sh`) | medium | Parameterize an existing script; tests exist |
| 6 | Remove the Zorin-only retire/remove entries and make the rest conditional (`04c_app_policy.sh`) | small | Mechanical |
| 7 | Replace the preseed unattended path with autoinstall for 26.04, and write a stock-base build script | escalate | Installer format unverified; touches the release pipeline |
| 8 | Change the CI images and the local ISO build base from `ubuntu:24.04` to `ubuntu:26.04` | small | One-line changes once 7 is decided |
| 9 | KVM test: install 26.04 in the local VM, run the provisioner, run it again, `noc doctor` | medium | Mechanical once the seed works; needs item 7 |
| 10 | **Decision for you**: Zorin-based 26.04 (wait for Zorin 19) vs a stock-Ubuntu 26.04 variant | — | Changes branding, credits and what is built |

Recommended order: 10 (decision) → 9-spike with the stock ISO to find real failures → 1, 3, 5, 6 in parallel → 2 and 4 → 7 → 8.

## Decision (2026-10-09): stock Ubuntu 26.04 base with KDE Plasma

- **Base:** stock Ubuntu 26.04 (the ISO on disk, verified). **Desktop:** KDE Plasma.
- **Lubuntu rejected for Plasma.** Lubuntu ships LXQt (`lubuntu-desktop` 26.04.3 in the index). Plasma comes from Kubuntu,
  or from `kubuntu-desktop` on a stock install.
- **Plasma packages available on resolute** (`apt-cache show`, dev box): `kubuntu-desktop` 1.496, `plasma-desktop` 6.6.4,
  `plasma-workspace` 6.6.4, `kwin-wayland` 6.6.4, `plasma-nm` 6.6.4, `sddm` 0.21.0, `konsole` 25.12.3, `dolphin` 25.12.3.

### What the switch does to the plan

GNOME-coupled lines (counted with grep): `install/06_desktop_theme.sh` 22, `install/08_shell_theme.sh` 13,
`install/09_super_search.sh` 5, `install/05_mouse_ergonomics.sh` 7 (Nautilus scripts), `install/07_persistence.sh` 5,
`install/04c_app_policy.sh` 6, `branding/setup-branding.py`, and the three GNOME Shell extensions. The Shell-extension work
(handoff items 2 and 4 below) is replaced by a Plasma port: KWin/Plasma config for layout and panel, Kickoff for the start
menu, and a global shortcut for Super+Space search (the search app's engine is Python and is not GNOME-tied; its UI is).

Reusable with little or no change: the apt lists, `02_mise`, `02b_gpu_drivers` and `bin/noc-gpu`, `03_ai_core`, `03b`,
`04d_appmanager`, `11_hermes`, the Control Panel (GTK3 runs on Plasma), `bin/noc`, the release and update tooling.

### Revised handoff (replaces the table above for Plasma)

| # | Work | Lane | Notes |
|---|------|------|-------|
| 1 | Apt gaps and package lists for the Plasma image (`kubuntu-desktop`, `sddm`, drop GNOME-only packages) | small | `out/apt-check.tsv` plus the Plasma names above |
| 2 | Replace the GNOME dock/top bar layout (`branding/setup-branding.py`) with Plasma panel config | high | Design choice: panel layout and what to keep of the look |
| 3 | Port Super+Space search to a Plasma global shortcut and the search UI | high | Keyboard-shortcut behaviour is user-visible |
| 4 | Port the start menu (`noctraos-start`) to Kickoff config | medium | Clear target once the layout is decided |
| 5 | Plasma theme derived from Breeze (replaces ZorinGrey in `build-desktop-theme.py` and `08_shell_theme.sh`) | medium | Parameterize an existing script |
| 6 | Rewrite the GNOME settings in `05`, `06`, `07` as `kwriteconfig6`/`plasma` calls, idempotent | medium | Mechanical, but many call sites |
| 7 | Installer path: autoinstall for 26.04 (verify subiquity seed) and a stock-base build | escalate | Unverified; touches the release pipeline |
| 8 | ISO choice: Kubuntu 26.04 ISO (clean Plasma) vs stock ISO plus `kubuntu-desktop` (leaves GNOME installed) | — | Needs a download for Kubuntu, so it needs your OK |
| 9 | KVM test of the provisioner on 26.04 with Plasma, plus a second run for idempotence | medium | Needs items 7 and 8 |
| 10 | CI images and ISO build base to `ubuntu:26.04` | small | After item 7 |

## ISO chosen (2026-10-09): Kubuntu 26.04.1

- File: `kubuntu-26.04.1-desktop-amd64.iso` (5,072,990,208 bytes, about 5.1 GB).
- Source: `https://cdimage.ubuntu.com/kubuntu/releases/resolute/release/`, checksum from that directory's `SHA256SUMS`.
- Location: `/run/media/dazeb/2tb/noctraos-spike/iso/` (spike only; not in the repo).
- Status: downloaded (5,072,990,208 bytes) and SHA-256 verified against the published SHA256SUMS (831e4d4b…90b8).
- This replaces item 8 in the revised handoff: the Kubuntu ISO gives a clean Plasma install with no GNOME left behind.

## VM install and provisioner run (2026-10-09)

Test VM: `/run/media/dazeb/2tb/noctraos-spike/vm-kubuntu26` (48 GB disk, 7 GiB RAM, `-vga std`).
Guest: Kubuntu 26.04.1 LTS, kernel 7.0.0-30, Minimal Installation, user `noctraos`, hostname `kubuntu26-spike`.
Access: `iso/local-vm.sh ssh` (port 2222). Test-only passwordless sudo is set in `/etc/sudoers.d/noctraos`.

### Install problems
- **Autoinstall seed ignored.** `/cdrom/autoinstall.yaml` and `autoinstall` on the kernel line were present, but the
  Kubuntu (Calamares) installer opened the normal wizard. Installed by clicking through. Untested route: a NoCloud
  `cidata` disk.
- **Boot stops at the splash.** SDDM starts, but KWin cannot take the GPU (`Failed to open drm node`, `No render
  nodes`, `atomic commit failed: Permission denied`). The VM uses `bochs-drm` (`-vga std`). The greeter draws nothing
  on tty1. Console login on tty3 works. Not fixed. Candidates: `-vga virtio`, or a non-graphical target for tests.
- **First boot asks for the installation medium.** Eject through the QEMU monitor (`eject -f c0`) and press Enter.

### Provisioner results (`install.sh`, `--skip-ai --skip-gpu`)
| Module | Result | Notes |
|---|---|---|
| 00_preflight | pass | RAM warning: 7 GiB |
| 01_system | pass | `nautilus-extension-gnome-terminal` absent (optional; Ptyxis replaces GNOME Terminal) |
| 02_mise | pass | |
| 04_gui_apps | pass | VS Code, CopyQ, keyring step |
| 04_workstation_apps (04b) | **FAIL, rc=100** | `tldr` passes `apt-cache show` but has no candidate on resolute, so `apt-get install` aborts the module. Pre-check must test `apt-cache policy` candidate. VM-only workaround: removed `tldr`, then rc=0. |
| 04c_app_policy | pass | |
| 04d_appmanager | pass | |
| 05_mouse_ergonomics | pass | Nautilus scripts installed |
| 06_desktop_theme | pass with warning | gsettings writes succeed (`prefer-dark` set), but Plasma ignores them. Silent no-op. |
| 07_persistence | pass | |
| 08_shell_theme | pass with 4 warnings | Zorin GTK bases, ZorinGrey icons and ZorinBlue shell CSS all skipped, so no theme applied |
| 09_super_search | **false success** | Logs "installed, takes effect after sign out/in". Files go to `/usr/share/gnome-shell/extensions`, but there is no `gnome-shell` here, so nothing loads. |
| 10_boot_theme | pass | |
| 02b_gpu_drivers, 03_ai_core | not run | `--skip-gpu`, `--skip-ai` |
| 11_hermes, Flatpak apps | not run | 25+ min; Flatpak downloads are several GB |

### What this means for the handoff
- Fix the 04b guard (use `apt-cache policy` candidate, not `show`). Small, same-file change. Re-check every apt list.
- Modules 06, 08 and 09 need Plasma equivalents. They must check their desktop (`gnome-shell` present, Zorin base
  present) and fail loudly when the target is missing. Currently they report success.
- Warn-not-die is hiding real no-ops on Plasma. Decide which GNOME settings to port (kwriteconfig6) and which to drop.
- Display stack in the VM needs a separate fix before any GUI-level test.

## Progress: display, guards and patches (2026-10-09, later)

### Display: fixed for login, not yet visible from the host
- `-vga std` (bochs-drm) and `-vga virtio` (virtio-gpu, no GL) both leave KWin without a render node. The greeter
  draws a background but no login form.
- `-device virtio-vga-gl -display egl-headless` gives the guest `/dev/dri/renderD128`. SDDM greeter connects, login
  works, and a Plasma session starts (plasmashell, kwin_wayland, krunner under user `noctraos`, tty2).
- **Caveat:** the host screenshot (`qemu screendump`) does not read the egl-headless surface, so it shows the
  background only. Verify the desktop from inside the guest instead (logind sessions, `journalctl`).
- Spike launcher: `scripts/local-vm-vga.sh` (copy of `iso/local-vm.sh` with `VGA_ARGS` and `DISPLAY_MODE`). The repo's
  `iso/local-vm.sh` is unchanged.
- Snapshot before this change: `qemu-img snapshot -l` shows `after-first-provision`.

### Patches (Sonnet work, then verified on the VM)
- `patched/04b-apt-candidate-guard.patch`: the 04b pre-check uses `apt-cache policy` candidate instead of
  `apt-cache show`. Verified: `tldr` is skipped with a warning, the rest of the module installs (rc=0).
- `patched/desktop-detect.patch`: `desktop_is_gnome` in `install/lib.sh`, with guards in 06, 08 and 09. Superseded by
  the next patch.
- `patched/verified/kubuntu-desktop-guard.patch`: the final combined patch, taken from the VM copy after testing.
  It includes a detector fix: a set `XDG_CURRENT_DESKTOP` without GNOME now means not GNOME, even with `gnome-shell`
  on PATH. Unit-tested on the VM with a fake `gnome-shell`: KDE → NOT_GNOME, GNOME → GNOME, unset → binary check.
  It dry-runs cleanly from a clean repo copy.

### Results after the guards (VM, rc=0 on both runs)
| Module | Result |
|---|---|
| 04_workstation_apps | pass: `tldr` skipped with WARN, the rest installed |
| 06_desktop_theme | `NOT APPLIED on this desktop: GNOME gsettings theme settings` |
| 08_shell_theme | `NOT APPLIED: GNOME shell and GTK theme (Plasma theme port pending)` |
| 09_super_search | `NOT APPLIED: ... (this desktop is unknown)` over SSH; the message should read the desktop from the session, not only `XDG_CURRENT_DESKTOP` |

Idempotent: a second run gives the same results.

### Sonnet deliverables
- `plasma-port-plan.md` (239 lines, file-by-file port plan). Every KDE config key and tool name is UNVERIFIED. The
  verified part is the package table: `plasma-desktop`, `plasma-workspace` and `kwin-wayland` at 6.6.6 in the
  archive, `kf6-breeze-icon-theme` 6.24.0, and `libkf6config-bin` (likely `kwriteconfig6`).
- Key findings from the plan: the search backend (`search/main.py --query`) ports to a KRunner runner bound to
  Meta+Space; the Noctra start panel hooks Zorin Menu's private API and cannot port as-is (stock Kickoff recommended);
  the three GNOME Shell extensions do not port; Control Panel (GTK3) should run as-is.

### Still open
- Plasma port itself: panels/dock layout, Super+Space binding, Kickoff, Breeze theme. Large; the plan rates the
  installer and ISO pipeline "escalate".
- Installer route: Calamares ignores the autoinstall seed. Options: keep the golden snapshot for repeat installs, or
  switch to a NoCloud route if the Kubuntu installer supports it (unverified).
- Module 11 (Hermes), the Flatpak apps, and the GPU and AI modules have not been run on Kubuntu.
- Two Plasma log warnings to check later: kicker reports `libreoffice-startcenter.desktop` as invalid (a stale launcher
  after the apt removal), and a KRunner Teardown D-Bus call with no matching slot.

## Shipped to main (2026-10-09)
- PR #93 (`fix/desktop-guards-apt-candidate`, merge commit `549f0b2`): the apt candidate check in 04b and the
  `desktop_is_gnome()` guards in 06, 08 and 09. Only product files; the spike stays here and untracked.
- `origin/main` has an existing failing unit test: `LocalLlmTests.test_fit_says_how_to_get_llmfit_when_it_is_missing`
  (PR 90). Not caused by #93. Needs its own fix.
- The Kubuntu Plasma port is not in #93 and still needs its own plan and work.
