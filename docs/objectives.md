# NoctraOS objectives

Single source of truth for what NoctraOS is for. `README.md` and `AGENTS.md`
summarise it; if they disagree with this file, this file wins.

## What we are building

An AI-ready desktop OS for **people moving from Windows**, on an Ubuntu base
(Zorin OS 18.x today). It does what [Omarchy](https://omarchy.org) does for
developers who live in a tiling window manager — a complete, opinionated,
AI-first workstation out of the box — but without the learning curve.
Omarchy's window manager and keyboard-driven workflow shut out beginners; we
keep a conventional desktop and make it powerful instead.

## Principles

1. **Muscle memory first.** Everything sits where someone switching from
   Windows expects it: taskbar and start button, window buttons, a task
   manager (Mission Center), Files, a system tray. We follow users' habits;
   we do not clone Windows' look.
2. **No terminal required.** The terminal is there for those who want it
   (the agents live in it), but nothing day-to-day depends on it.
3. **AI is built in, not bolted on.** Local models (Ollama), a curated agents
   menu, an editor wired to local AI, and file actions such as *Ask AI to
   Explain*.
4. **One keybind, promoted heavily: Super+Space.** It is the only shortcut
   users need to learn. NoctraOS is AI-first; everything else is reachable
   by mouse and through Super+Space itself. Everything else should feel familiar.
5. **A distribution, not a script.** The deliverable is a bootable ISO that
   installs and boots into the finished experience.

## Headline feature: Super+Space

One overlay is meant to reach the whole system: **applications, files and
folders, clipboard history, the web, browser history, and more**, with a
settings panel for sources and indexed locations. Shipped today: applications,
files and folders, clipboard history (CopyQ), web search, and **opt-in browser
history** (Chromium family and Firefox). Other sources are not built yet.

### Browser history is opt-in and set up after first use

A new user has no browser configured at first login, so onboarding cannot ask.
Instead, once a supported browser has history on the account, the Super+Space
overlay shows a small "Finish setup" notice: *search your browser history too?
Choose your browser.* **Set up** opens a short dialog (which browser(s), and
"Search my history" or "No thanks"); **Not now** dismisses it for good. The
choice is reversible in Search settings. History is copied into the user's
private cache (`~/.cache/noctraos-search/history`, mode 0700) and searched
locally; nothing is uploaded. It is the main thing a new user should learn, and the reference
for the visual theme.

Status: in the repo and installed by `install/09_super_search.sh` — two GNOME
Shell extensions (`extensions/noctraos-search@noctraos.local`, the overlay;
`extensions/noctraos-branding@noctraos.local`, the Noctra start button), the
search app in `search/` (user-owned SQLite index, CopyQ bridge, settings
window) and a systemd user timer that refreshes the file index. It takes over
Super+Space and moves the input-source switch to Shift+Super+Space. Verified
on VM 114 (clean install, idempotent re-run, extensions ACTIVE after a session
restart). Not yet verified on a fresh ISO install.

## Onboarding

First login must put Super+Space front and center: show the shortcut, let the
user try it right there, and show what it can find (apps, files, clipboard,
web). Then a short tour of the other things a switcher needs to know (start
button, Mission Center as the task manager, the agents menu, local AI
models). The flow is in [onboarding.md](onboarding.md) and a first version is built:
`noctraos-welcome` replaces Zorin's tour, shows once per account, and the ISO first boot
starts it while the provisioner runs, so the provisioner terminal is no longer the whole
first-boot experience. Not built yet: the prefilled search examples and a provisioner log panel
(a status line stands in), and it has not been seen running during provisioning on a
from-scratch install. Being honest about where AI runs is part of the brief: the screen says
the local model stays on the computer and that Hermes' free tier is a cloud service, with a
local-only choice.

## Delivery

- **Primary: the NoctraOS ISO** (`iso/build-noctraos-iso.sh`, driven by
  `iso/build-local.sh`). The published ISO is the interactive **release** build,
  which carries no unattended seed or password. A separate **appliance** build
  (unattended, throwaway credentials) exists only to produce the downloadable VM
  disk and is never published.
- For 0.3.0: a **VM disk image** (qcow2/vmdk, sysprepped with
  `iso/vm-sysprep.sh`) for people who would rather try it in a hypervisor. It is a
  trial appliance: autologin and passwordless sudo, which the download page must say.
- `install.sh` / `boot.sh` remain as the engine the ISO bakes in and as a way
  to provision an existing Zorin OS machine. They are no longer the
  headline product.
- Version 0.3.0 is **published**: the ISO, the VM disks and their checksums are on the download
  page. What is left is the `v0.3.0` git tag and GitHub release; see
  [release-runbook.md](release-runbook.md).

## Visual direction

Dark with slight orange highlights, streamlined and consistent everywhere,
derived from the Super+Space overlay (near-black surfaces, **sharp corners —
0 px in the shell, dock, menus and Start panel; the Super+Space overlay and our
own GTK windows still use 2 px, a known inconsistency**, monospace accents,
amber for focus and selection). See [theme-design.md](theme-design.md) and
`configs/theme/palette.json`. The shell, GTK apps, boot chain and installer are
themed; the remaining gaps (the lock and login screens, libadwaita/GTK 4 apps,
some stock icons) are tracked in the coverage table in `theme-design.md`.

## Decisions

- **Stay on GNOME** (Zorin base) until the current experience is complete.
  Moving to KDE Plasma was considered and deferred; revisit with a time-boxed
  spike only after the GNOME work is done.
- **Autologin keyring prompt: fixed for every app.** Autologin never unlocks the
  account's keyring, so Hermes, browsers and VS Code asked for a password on first
  use. Setup now gives the account an unencrypted login keyring while it is empty
  (and Chromium and VS Code also keep a non-keyring password store). Secrets in it
  are stored without a password, an accepted trade-off. A keyring that already
  holds secrets is left alone and can still prompt (see `AGENTS.md`).
- **Flatpak and AppImage first.** apt is for CLI tools, system tools and
  host-integration apps; the app set and the removals are in `install/04c_app_policy.sh`.
- **Be honest about where AI runs.** The local Ollama model stays on the computer;
  Hermes' free tier is a cloud service and is described as one everywhere.
- **Target desktop layout** is in [desktop-layout.md](desktop-layout.md).

## Non-goals

- A tiling window manager or keyboard-only workflow (that is Omarchy's lane).
- Imitating Windows' appearance.
- Supporting non-Ubuntu bases.
