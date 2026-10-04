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
   users need to learn. NoctraOS is mouse-first; everything else is reachable
   by mouse and through Super+Space itself. Everything else should feel familiar.
5. **A distribution, not a script.** The deliverable is a bootable ISO that
   installs and boots into the finished experience.

## Headline feature: Super+Space

One overlay is meant to reach the whole system: **applications, files and
folders, clipboard history, the web, browser history, and more**, with a
settings panel for sources and indexed locations. Shipped today: applications,
files and folders, clipboard history (CopyQ) and web search. **Browser history
and other sources are not built yet.** It is the main thing a new user should learn, and the reference
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
models). The draft flow is in [onboarding.md](onboarding.md); nothing is built yet.
Today the ISO first boot only runs the provisioner in a terminal.

## Delivery

- **Primary: the NoctraOS ISO** (`iso/build-noctraos-iso.sh`), including a
  fully unattended install path for testing.
- `install.sh` / `boot.sh` remain as the engine the ISO bakes in and as a way
  to provision an existing Zorin OS machine. They are no longer the
  headline product.

## Visual direction

Dark with slight orange highlights, streamlined and consistent everywhere,
derived from the Super+Space overlay (near-black surfaces, small corner
radii, monospace accents, amber for focus and selection). See
`docs/theme-design.md` and `configs/theme/palette.json`. Remaining gaps
(libadwaita apps, overview, wallpapers, boot/login/lock screens, ISO menus,
installer, stock icons) are tracked in the README roadmap.

## Non-goals

- A tiling window manager or keyboard-only workflow (that is Omarchy's lane).
- Imitating Windows' appearance.
- Supporting non-Ubuntu bases.
