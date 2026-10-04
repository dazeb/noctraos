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
4. **One new idea, promoted heavily: Super+Space.** Search the whole system
   from one keystroke. Everything else should feel familiar.
5. **A distribution, not a script.** The deliverable is a bootable ISO that
   installs and boots into the finished experience.

## Headline feature: Super+Space

One overlay searches **applications, files and folders, clipboard history
(CopyQ), and the web**, with a settings panel for sources and indexed
locations. It is the main thing a new user should learn, and the reference
for the visual theme.

Status: built and running on test VM 114 as two GNOME Shell extensions plus
an indexer (`zorin-ai-search`, `zorin-ai-branding`), but **not yet in this
repo** — to be imported and renamed to `noctraos`.

## Onboarding

First login must put Super+Space front and center: show the shortcut, let the
user try it right there, and show what it can find (apps, files, clipboard,
web). Then a short tour of the other things a switcher needs to know (start
button, Mission Center as the task manager, the agents menu, local AI
models). Flow, copy and implementation are still to be designed. Today the
ISO first boot only runs the provisioner in a terminal.

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
