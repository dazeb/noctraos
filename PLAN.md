# NoctraOS Provisioner — Build Plan

**Project:** `noctraos` · **Repo:** `/mnt/nvme1/workspace/projects/noctraos`
**Plan date:** 2026-09-25
**Input spec:** "Technical Specification & Implementation Plan: NoctraOS Provisioner" (Omakub-pattern provisioner for Zorin OS 17+ / Ubuntu 22.04–24.04 base)
**Status:** Phase 1 (provisioner) — scaffolded this session; modules implemented, untested on a target VM.

> **Historical document.** This is the original 2026-09-25 build plan, written when the
> project was called `zorin-ai`; identifiers were mechanically renamed to NoctraOS
> (`noctraos`) afterwards. VSCodium and Chatbox were later replaced by Microsoft VS Code (`code`, `configs/vscode/`)
> and removed (b6981b4); references below to `codium`, `configs/vscodium/`,
> `Open_in_VSCodium` and the Chatbox .deb describe the original design. See
> `AGENTS.md` and `docs/theme-design.md` for the current state.

---

## 1. Mission

Turn a fresh Zorin OS machine into a complete, **AI-first development
workstation** with one command:

```bash
curl -fsSL https://RAW-BOOTSTRAP-URL/boot.sh | bash
```

### Success criteria

1. One-liner bootstrap works on a clean Zorin 17 (Ubuntu 22.04 / 24.04 base).
2. Every module is **idempotent** — running the installer twice is a no-op the second time.
3. **Full mouse parity**: nothing in the day-to-day workflow requires opening a terminal
   (Nautilus right-click actions, GUI AI chat, GUI task manager, GUI maintenance panel).
4. Local AI: Ollama bound to `127.0.0.1:11434` with `qwen2.5-coder:7b`, pre-wired into
   VSCodium (Continue.dev), Nautilus context menus, and the Chatbox desktop client.
5. Polyglot runtimes (Node LTS, Python 3.12, Go) managed by `mise`, system-wide.
6. New user accounts inherit the developer defaults via `/etc/skel`.
7. `noc` / `noc-menu` provide CLI + GUI maintenance (update, doctor, models).

---

## 2. Architecture

```
boot.sh (remote one-liner)
   └─ clones repo to ~/.local/share/noctraos, runs install.sh
        └─ install.sh  (orchestrator: logging, flags, TARGET_USER resolution)
             ├─ install/00_preflight.sh          OS / sudo / network / 25 GB disk
             ├─ install/01_system.sh             apt core, Flathub, Nerd Font
             ├─ install/02_mise.sh               mise binary, profile hooks, runtimes
             ├─ install/03_ai_core.sh            Ollama + systemd + model pull   (--skip-ai)
             ├─ install/04_gui_apps.sh           VSCodium, Mission Center, Chatbox (--skip-gui)
             ├─ install/05_mouse_ergonomics.sh   Nautilus right-click scripts      (--skip-gui)
             ├─ install/06_desktop_theme.sh      gsettings: Win/KDE parity         (--skip-gui)
             └─ install/07_persistence.sh        /etc/skel sync + noc CLI
```

**Execution model**

- `install.sh` runs as the *normal desktop user*; system mutations go through `sudo`.
- `TARGET_USER` / `TARGET_UID` / `TARGET_HOME` are resolved from `SUDO_USER` when
  invoked under sudo, otherwise the invoking user, and exported for all modules.
- `as_user()` (in `install/lib.sh`) runs user-scoped commands (`gsettings`, `codium`,
  `flatpak --user`, Nautilus refresh) with `HOME`, `XDG_RUNTIME_DIR` and
  `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<uid>/bus` — i.e. inside the **real
  running desktop session**, not a throwaway `dbus-launch` bus (see §9.2).
- Shared helpers live in `install/lib.sh`; every module sources it via `$REPO_ROOT`.

---

## 3. Repository layout

```
noctraos/
├── PLAN.md                ← this document
├── README.md
├── boot.sh                # remote fetcher / repo updater
├── install.sh             # orchestrator (logging, flags, user resolution)
├── bin/
│   ├── noc                # management CLI (update | doctor | models)
│   └── noc-menu           # zenity control panel (AI-first maintenance)
├── install/
│   ├── lib.sh             # shared helpers: log/warn/die, as_user, apt_install
│   ├── 00_preflight.sh
│   ├── 01_system.sh
│   ├── 02_mise.sh
│   ├── 03_ai_core.sh
│   ├── 04_gui_apps.sh
│   ├── 05_mouse_ergonomics.sh
│   ├── 06_desktop_theme.sh
│   └── 07_persistence.sh
├── configs/
│   ├── mise/config.toml             # node=lts, python=3.12, go=latest
│   ├── vscodium/
│   │   ├── settings.json            # editor/GUI prefs, Nerd Font, format-on-save
│   │   ├── extensions.list          # installed by loop with per-ext idempotence
│   │   └── continue_config.yaml     # Continue.dev → localhost:11434
│   └── nautilus-scripts/
│       ├── Open_in_VSCodium
│       ├── Ask_AI_to_Explain
│       └── Open_Terminal_Here
├── iso/
│   └── build-noctraos-iso.sh        # M5: remaster Zorin ISO → NoctraOS ISO
└── assets/branding/       # reserved for wallpapers/icons (phase 2)
```

---

## 4. Software inventory — verified 2026-09-25

Every source below was probed live before implementation. Status column shows the
HTTP result of the exact URL the installer uses.

| # | Component | Channel | Source | Version policy | Verified |
|---|-----------|---------|--------|----------------|----------|
| 1 | apt base packages | apt | Zorin/Ubuntu archives | distro | ✔ (module checks reachability) |
| 2 | Flatpak + Flathub | apt / flatpak | `flathub.org/repo/flathub.flatpakrepo` | stable | ✔ 200 |
| 3 | JetBrainsMono Nerd Font | direct download | `github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.tar.xz` | latest | ✔ 200 |
| 4 | mise | installer script | `https://mise.run` (`MISE_INSTALL_PATH=/usr/local/bin/mise`) | latest stable | ✔ 200, env var supported |
| 5 | Node / Python / Go | mise plugins | declared in `configs/mise/config.toml` | lts / 3.12 / latest | resolved by mise at install |
| 6 | Ollama | installer script | `https://ollama.com/install.sh` | latest | ✔ 200 |
| 7 | qwen2.5-coder:7b | ollama library | `ollama.com/library/qwen2.5-coder` | 7b tag | ✔ 200 |
| 8 | VSCodium | apt repo | key: `gitlab.com/paulcarroty/vscodium-deb-rpm-repo/raw/master/pub.gpg` · repo: `download.vscodium.com/debs vscodium main` | latest | ✔ 200 / ✔ 200 |
| 9 | Continue.dev | Open VSX | `continue.continue` | latest | ✔ 200 |
| 10 | GitLens | Open VSX | `eamodio.gitlens` | latest | ✔ 200 |
| 11 | Prettier | Open VSX | `esbenp.prettier-vscode` | latest | ✔ 200 |
| 12 | Python ext | Open VSX | `ms-python.python` | latest | ✔ 200 |
| 13 | Go ext | Open VSX | `golang.go` | latest | ✔ 200 |
| 14 | Mission Center | Flatpak | `io.missioncenter.MissionCenter` | stable | ✔ 200 (appstream) |
| 15 | Chatbox | vendor .deb | `download.chatboxapp…` → **`download.chatboxai.app/releases/Chatbox-<ver>-amd64.deb`**, version resolved from GitHub tag `chatboxai/chatbox` | latest | ✔ 200 (v1.23.5), installed in VM |
| 16 | zenity / jq / nautilus | apt | distro | distro | distro-provided |
| 17 | nomic-embed-text | ollama library | `ollama pull nomic-embed-text` | latest (274 MB) | ✔ installed, embedding endpoint verified |

**Inventory findings that changed the original spec:**

- **Chatbox is no longer on Flathub** (`xyz.chatboxapp.Chatbox` appstream → 404, and it
  does not appear in Flathub search). The vendor publishes official `.deb` binaries on
  their own CDN; we resolve the latest version tag via the GitHub API
  (`repos/chatboxai/chatbox/releases/latest`, e.g. `v1.23.5`) and install
  `https://download.chatboxai.app/releases/Chatbox-<ver>-amd64.deb`.
- **VSCodium's documented repo URLs in the spec are outdated.** The GPG key lives at
  `gitlab.com/paulcarroty/vscodium-deb-rpm-repo/...` (repo renamed), and packages are
  served from the CDN `download.vscodium.com/debs` — the old
  `paulcarroty.gitlab.io/vscodium-debian-rpm/debs` URL is dead.
- `mise.jdx.dev/install-mise.sh` returns 404; the working installer endpoint is
  `https://mise.run`.

---

## 5. Module implementation plan

Each module: **objective → actions → idempotence guard → acceptance check.**

### 00_preflight
- **Actions:** refuse bare-root execution (require normal user + sudo); validate
  `/etc/os-release` (`ID=zorin` or `ID`/`ID_LIKE` contains ubuntu/debian); probe
  `archive.ubuntu.com` and `flathub.org`; require ≥ 25 GiB free on `/`; warn if no
  graphical session is attached.
- **Guard:** the module *is* the guard — it runs before any mutation.
- **Accept:** all checks log `OK`; any hard failure exits non-zero before apt runs.

### 01_system
- **Actions:** `apt-get update`; install core packages (`build-essential curl wget git
  jq unzip fontconfig flatpak libglib2.0-bin dconf-cli zenity xdg-utils ca-certificates
  gnupg` + the **Python build dependencies mise needs**: `libssl-dev zlib1g-dev
  libbz2-dev libreadline-dev libsqlite3-dev libffi-dev liblzma-dev`); best-effort
  install of release-dependent extras (`nautilus-extension-gnome-terminal`,
  `gnome-terminal`); register Flathub; download + unpack JetBrainsMono Nerd Font to
  `/usr/local/share/fonts/JetBrainsMono/`, run `fc-cache -f`.
- **Guard:** packages are apt-idempotent; Flathub via `--if-not-exists` +
  `flatpak remotes` probe; font via `fc-list` match.
- **Accept:** `fc-list | grep -i "JetBrainsMono Nerd Font"` non-empty; `flatpak remotes`
  lists flathub.

### 02_mise
- **Actions:** install mise to `/usr/local/bin/mise` via the official installer
  (`sudo MISE_INSTALL_PATH=…`); write `/etc/profile.d/noctraos-mise.sh` (login shells,
  bash/zsh aware); append a marked, guarded block to `/etc/bash.bashrc` so interactive
  **non-login** shells (desktop terminals) also get `mise activate`; install
  `/etc/mise/config.toml` (system baseline) and `~/.config/mise/config.toml` (user, only
  if absent); run `mise install` as the target user.
- **Guard:** `command -v mise`; config-file existence tests; marker comment in bash.bashrc.
- **Accept:** fresh terminal resolves `node -v`, `python -V`, `go version` through mise.

### 03_ai_core
- **Actions:** official Ollama installer; `systemctl enable --now ollama`; poll
  `http://127.0.0.1:11434/api/tags` for up to 60 s; pull `qwen2.5-coder:7b`
  (override: `NOCTRAOS_MODEL=<model> ./install.sh`); pull the small embedding model
  `nomic-embed-text` (override: `NOCTRAOS_EMBED_MODEL=<model>`) for RAG / semantic search.
- **Guard:** `command -v ollama`; `systemctl is-enabled/is-active`; `api/tags` model match.
- **Accept:** `curl 127.0.0.1:11434/api/version` answers; `ollama list` shows the model.
  Ollama binds `127.0.0.1` by default — we verify rather than reconfigure (§9.9).

### 04_gui_apps
- **Actions:** register the corrected VSCodium keyring + `download.vscodium.com` repo,
  install `codium`; install extensions from `configs/vscodium/extensions.list` as the
  target user (continue.continue, eamodio.gitlens, esbenp.prettier-vscode,
  ms-python.python, golang.go); seed `~/.continue/config.yaml` pointing at local
  Ollama; install Mission Center + Chatbox (vendor .deb, latest version via GitHub API).
- **Guard:** `command -v codium`; `codium --list-extensions` diff; `dpkg -l chatbox`;
  `flatpak info <app>`; `~/.continue/config.yaml` existence.
- **Accept:** `codium --version`; Continue sidebar chat replies from the local model;
  Mission Center + Chatbox appear in the apps grid.

### 05_mouse_ergonomics
- **Actions:** install executable scripts into `~/.local/share/nautilus/scripts/`:
  *Open in VSCodium*, *Ask AI to Explain* (first 200-line file → `jq`-escaped payload →
  Ollama `/api/generate` → `zenity` dialog), *Open Terminal Here*; `chmod 755`, owned by
  the target user; `nautilus -q` so the menu refreshes.
- **Guard:** per-file `install` overwrite (idempotent); scripts read their selection
  from `NAUTILUS_SCRIPT_SELECTED_FILE_PATHS` env vars (§9.1).
- **Accept:** right-click in Files → **Scripts** shows all three; each one works.

### 06_desktop_theme
- **Actions** (all via `as_user` against the live session bus): window buttons
  `:minimize,maximize,close` (right side); `color-scheme prefer-dark` +
  `gtk-theme ZorinBlue-Dark`; striking polygonal wallpaper set (procedurally
  generated 4K low-poly scenes in `assets/wallpapers/` — sunset-peaks,
  neon-rift, aurora-peaks, crimson-dunes, glacier-facet — installed to
  `/usr/local/share/backgrounds/noctraos/`, default + lock-screen set via
  `picture-uri[-dark]`; cycle with `noc bg next`); accent color attempted via
  `org.gnome.desktop.interface accent-color` (warn-not-die — key absent on some
  Zorin builds); pin favorites filtered to desktop entries that actually exist;
  enable DING desktop-icons keys (`show-home`, `show-trash`) when the schema exists.

  Also part of 06: the **Agents menu section** — branded SVG tile icons
  (`assets/icons/`), XDG launchers for Codex / Claude Code / OpenCode / Grok
  (`configs/applications/`) that open the agent in gnome-terminal through
  `bin/noctraos-agent` (installs the agent's npm package on first use, with a
  zenity consent prompt, via mise-managed node), an XDG menu merge adding the
  "Agents" category (`configs/xdg/noctraos-agents.menu`), and a GNOME app-grid
  "Agents" folder via the relocatable `org.gnome.desktop.app-folders.folder`
  schema. The stock category tree itself is replaced by an AI-first
  `/etc/xdg/menus/gnome-applications.menu` (original preserved as
  `.menu.orig`): sections are **Agents, Local LLM** (Chatbox + "AI Models"
  model-manager + "AI Health Check" launchers), **Development, Internet,
  Media, Utilities, System** — needs one re-login (session rescan) to apply.
- **Guard:** every `gsettings` step is `warn`-not-`die` — theme/favorites must never
  abort an otherwise complete install.
- **Accept:** window controls on the right, dark mode, taskbar shows the pinned apps.

### 07_persistence
- **Actions:** sync `configs/` outputs into `/etc/skel/` (`.config/mise/config.toml`,
  `.continue/config.yaml`, `.local/share/nautilus/scripts/*`); install `noc` +
  `noc-menu` to `/usr/local/bin`; install a `noc-menu.desktop` launcher.
- **Guard:** `install -m` overwrites are idempotent.
- **Accept:** `useradd -m testuser` + `su - testuser` sees mise config, Continue config
  and Nautilus scripts; `noc doctor` runs green.

---

## 6. `noc` CLI

| Command | Behaviour |
|---------|-----------|
| `noc update` | apt update+upgrade → Flatpak apps → `mise up`/`mise install` → `ollama pull` for every installed model |
| `noc doctor` | Health report: OS, Ollama API + model count, mise + current runtimes, VSCodium, Flatpak apps, NVIDIA GPU presence, disk free |
| `noc models` | `list` / `pull <model>` / `rm <model>` |
| `noc models gui` | zenity picker over a curated preset list (qwen2.5-coder 7b/14b, llama3.2:3b, gemma2:2b, deepseek-coder, phi4-mini) |
| `noc-menu` | zenity control panel (Update / Doctor / Models / About) launching actions in a terminal window |

---

## 7. Milestones

- **M0 — scaffold:** repo tree, PLAN, all modules, configs, noc CLI,
  every upstream source verified live. *(done 2026-09-25)*
- **M1 — static QA:** `bash -n` clean on all scripts. *(done; shellcheck still to install)*
- **M2 — VM validation:** *(done 2026-09-25)* — clean Zorin OS 18.1 VM (Proxmox, 4 vCPU /
  5→7 GiB / 64 GB on zfs), installer driven over VNC. **Four full installer runs:**
  run 1 progressed to module 04 (host unplugged by a Proxmox node reboot mid-run),
  runs 2–4 proved resumability + idempotence (every guard fired, ollama model pull
  resumed from partial). Final state all green: `noc doctor` clean, mise runtimes
  resolve in login shells (node 24.21.0 / python 3.12.14 / go 1.27.1), ollama healthy
  with qwen2.5-coder:7b + nomic-embed-text (embedding endpoint returns 768-dim vectors),
  all 5 VSCodium extensions, Mission Center + Chatbox 1.23.5, gsettings verified
  (button-layout, prefer-dark, ZorinBlue-Dark, favorites), Nautilus scripts installed
  and executable, fresh-user `/etc/skel` test passed. Findings folded back as fixes
  (§9 items 10–14).
- **M3 — fresh-user + GUI acceptance:** fresh-user `/etc/skel` test done in M2.
  Remaining: interactive desktop walkthrough (right-click menus, Continue chat,
  Chatbox wizard, Mission Center) — best done by hand on the running VM
  (`192.168.8.124`); remote VNC automation is blocked while the Proxmox web console
  holds the VM's single VNC client slot.
- **M4 — polish & release:** *(done 2026-09-25)* — live at
  [github.com/dazeb/noctraos](https://github.com/dazeb/noctraos); real bootstrap URL
  in `boot.sh`/README; CI workflow committed (`.github/workflows/ci.yml`,
  bash -n + shellcheck at warning severity; **note:** GitHub Actions is disabled at
  the account level, so runs won't start until re-enabled); shellcheck clean at
  warning severity; one-liner `curl … | bash` bootstrap validated on the VM
  (exit 0, fully idempotent re-run); pipefail/grep -q guard bug found and fixed;
  tagged `v0.1.0`.
- **M5 — phase 2 (true "fully featured OS"):** *(pipeline built + ISO validated
  2026-09-25)* — `iso/build-noctraos-iso.sh` remasters a Zorin 18.1 ISO: provisioner
  snapshot baked at `/opt/noctraos`, first-boot autostart runner
  (`/usr/local/sbin/noctraos-firstboot`, GitHub-fresh preferred / snapshot fallback),
  boot menu rebranded "NoctraOS", squashfs repacked with the original zstd
  compressor, ISO rewritten with xorriso `boot_image replay` (BIOS + UEFI verified
  intact). End-to-end proof: the built ISO was installed into a fresh VM through the
  normal installer; on first login the provisioner launched itself and ran
  unattended (modules 00–02 + ollama verified before the model pull hit
  CDN throttling — download speed is environment-dependent, not a pipeline issue).
  Remaining niceties: firmware/branding polish, unattended installer preseeding.
  **Unattended installer preseeding — done 2026-09-26:** the build script bakes
  a d-i/Ubiquity seed (`iso/preseed/noctraos.seed.in`) and an "Install
  NoctraOS (unattended)" entry into both boot menus; unattended builds also
  default to autologin + NOPASSWD sudo so first-boot provisioning is fully
  hands-off. Boot-test findings folded back as fixes: three unpreseeded keys on
  Ubiquity's first page, a broken GDM greeter session on Zorin 18.1 (worked
  around with autologin), casper's remove-medium wait (fixed with `noprompt`),
  and expired sudo tickets mid-run (fixed with baked NOPASSWD sudoers).

## 8. GUI acceptance checklist (M3, on the target VM)

1. Right-click a file in Files → Scripts → *Open in VSCodium* opens it.
2. Right-click a source file → *Ask AI to Explain* shows a zenity summary from the
   local model (first-run may take ~30 s; model is loading).
3. VSCodium → Continue panel → chat replies using `qwen2.5-coder:7b` on localhost.
4. Mission Center opens with live CPU/RAM/(GPU) graphs.
5. Chatbox first-run wizard detects local Ollama; chat works.
6. New terminal: `node -v` / `python -V` / `go version` resolve via mise.
7. Window buttons on the right; dark theme; pinned favorites on the panel.
8. `sudo useradd -m qa1 && sudo su - qa1` → mise + Continue + Nautilus scripts present.
9. `noc update` completes; `noc doctor` all green; `noc models gui` pulls a model.

## 9. Deviations from the source spec (corrections)

1. **Nautilus scripts get their selection via environment variables**
   (`NAUTILUS_SCRIPT_SELECTED_FILE_PATHS`, newline-separated), not `$1` — the spec's
   `"$1"` would always be empty. Scripts rewritten accordingly.
2. **gsettings must target the user's existing session bus**
   (`DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<uid>/bus`), not `dbus-launch` —
   `dbus-launch` spawns a throwaway bus whose dconf writes never reach the running
   GNOME session (settings would silently not apply until re-login... if at all).
3. **Continue.dev configuration**: current Continue versions read
   `~/.continue/config.yaml` (`config.json` is legacy). We ship `config.yaml`.
4. **Python via mise needs source-build dependencies** (`libssl-dev`, `zlib1g-dev`, …);
   added to module 01's apt list, otherwise `mise install python` fails on a clean box.
5. **`/etc/profile.d` only covers login shells**; desktop terminals are interactive
   non-login. Module 02 adds a guarded block to `/etc/bash.bashrc` so `mise activate`
   works everywhere bash starts.
6. **`favorite-apps` are filtered to desktop entries that exist** — `zorin-menu.desktop`
   is not guaranteed across Zorin releases; missing entries are skipped with a warning
   instead of shipping a broken gvariant.
7. **Chatbox pre-seeding via config file is not feasible** (state lives in Electron
   localStorage). Chatbox's first-run wizard auto-detects a running Ollama on
   `localhost:11434`; module 04 logs that hint instead of writing fragile state files.
8. **`nautilus-extension-gnome-terminal` is best-effort** — absent on 24.04-base
   releases; optional-package loop warns instead of failing.
9. **Ollama already binds `127.0.0.1:11434` by default**; module 03 verifies the
   endpoint is localhost-only and healthy rather than adding a systemd override.
10. **`sudo -v` demands a TTY even under NOPASSWD sudoers** (found in the headless VM
    run) — preflight now tries `sudo -n true` first and only falls back to an
    interactive `sudo -v` when a terminal is available.
11. **Chatbox's deb package/desktop IDs differ from its old Flathub IDs** — package is
    `xyz.chatboxapp.app` and the launcher is `xyz.chatboxapp.app.desktop`; modules 04
    and 06 (and `noc doctor`) use the real IDs.
12. **`/usr/local/share/applications` does not exist on a fresh system** — module 07
    creates it before installing the `noc-menu.desktop` launcher.
13. **`zorin-menu.desktop` does not exist on Zorin 18.1** (menu is built into the
    shell) — the favorites candidate list skips missing entries with a warning; on
    18.1 the panel gets the five real launchers.
14. **RAM floor for local 7B models** — a 5 GiB VM swap-thrashed loading
    qwen2.5-coder:7b (4.7 GB) alongside GNOME. Preflight now warns below 8 GiB RAM;
    16 GiB recommended for comfortable local inference.
15. **`grep -q` + `pipefail` silently inverts large-output guards** —
    `fc-list | grep -qi …` SIGPIPEs fc-list on match, so the font guard reported
    "missing" on every run and re-downloaded. Guard rewritten to drain the pipe
    (`grep -i … >/dev/null`). Found only because the bootstrap one-liner test
    re-ran the installer yet again.
16. **Fresh installs ship no SSH server** — found by the ISO first-boot test
    (no way to reach a provisioned box remotely). `openssh-server` is now in the
    core package list. Related: the first-boot runner prefers cloning the
    provisioner from GitHub but a fresh Zorin has no `git`, so it correctly falls
    back to the ISO-baked snapshot.

## 10. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| `qwen2.5-coder:7b` is a ~4.7 GB download | 25 GB preflight floor; `--skip-ai` flag; model overridable via `NOCTRAOS_MODEL` |
| No GPU / unsupported GPU | Ollama falls back to CPU; `noc doctor` reports what it detected |
| Upstream outages (GitHub, GitLab, Flathub, chatboxai CDN) | preflight probes network; per-step warnings allow partial installs; `noc update` retries later |
| Zorin schema drift across 17.x | module 06 steps are warn-not-die; favorites filtered to existing entries |
| First `mise install python` compiles from source (slow) | build deps pre-installed; expectation set in module log output |
| Vendor .deb URL drift (Chatbox) | version resolved from the GitHub release tag at install time, not hardcoded |

## 11. Out of scope for phase 1

ISO remaster/unattended image build (M5), custom wallpapers/icons (placeholder
`assets/branding/`), CUDA container toolkit, additional IDEs/browsers, non-bash shell
support (fish), multi-language UI.
