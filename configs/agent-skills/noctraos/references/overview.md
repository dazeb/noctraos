# NoctraOS overview

## What it is

An **AI development workstation OS** on an Ubuntu base, delivered as a bootable ISO. The Omakub-style provisioner (`install.sh`) is the engine baked into the ISO and also runs on an existing system through the one-line `boot.sh` installer. It provides an optional local Ollama stack, a six-agent Start menu, mise-managed Node, a dark + amber theme, Hermes Desktop, and **Super+Space** system search.

The audience and principles are in the repo's `docs/objectives.md` (the source of truth for product decisions).

## Principles (from `docs/objectives.md`)

1. **Muscle memory first** - everything sits where someone used to Windows expects it, without imitating Windows.
2. **No terminal required, and never forced** - the terminal is there for people who want it.
3. **AI is built in, not bolted on** - local models (Ollama), a curated agents menu, Hermes.
4. **One keybind, promoted heavily: Super+Space.**
5. **A distribution, not a script** - the deliverable is a bootable ISO.
6. **We set up the system, then you take control.** See "What stays yours" below.
Non-goals: no tiling WM, no Windows imitation. Check `docs/objectives.md` before assuming a direction.

## Flavours

One product, built per flavour. The `noc` commands, `--json` contracts, Control Panel meaning, AI stack, Super+Space results, app set, update rules and privacy statements are identical across flavours. What may differ: the base ISO and boot chain, login manager (GDM or SDDM), desktop shell/dock/start menu, file manager, theme engine, and how Super+Space is implemented (GNOME Shell extension vs KRunner).

| Flavour id | Base | Desktop | Status |
|---|---|---|---|
| `zorin` | Zorin OS 18.1 (Ubuntu 24.04) | GNOME | shipped (0.3.x, 0.4.0) |
| `kubuntu` | Kubuntu 26.04 | KDE Plasma 6 | in progress, no release |

Vocabulary: **NoctraOS** is the product (never "Zorin edition"); **base** is Zorin/Kubuntu/Ubuntu; **desktop** is `gnome` or `plasma`; **core** is everything not desktop-specific. Artifacts, release folders and update channels are per flavour and never crossed. Skipped desktop work prints `NOT APPLIED`, never a success line. Read `docs/flavours.md` before touching desktop code, `iso/`, `branding/`, releases or updates.

## What gets set up

- The desktop: dark + amber theme, dock, Start panel, Super+Space search.
- Everyday apps: browser, office, media, task manager, VS Code, Flatpak and AppImage support.
- Node.js (agent launchers and the Hermes build need it) plus terminal tools via mise (Starship, lazygit, lazydocker, Herdr).
- Hermes Desktop (free Nous tier, which is a cloud service) with a local Ollama fallback.
- Launchers for the coding agents (Codex, Claude Code, OpenCode, Grok, Gemini CLI, Qwen Code).
- VM guest tools when running inside a virtual machine.
- The `noc` CLI and the Control Panel.

## What stays yours

- **Coding agents' sign-ins, API keys, subscriptions and settings.** A launcher installs the program on first use; nothing else.
- **Languages.** Only Node. Python, Go etc. are added with `mise use -g python@3.12`.
- **AI models.** None is downloaded until the person picks one.
- **Local AI itself.** Not in the first install; set up later from the AI models page or `noc llm setup`.
- **Whether Ollama starts with the computer.** Off unless turned on (`noc llm autostart on`).
- **Git and GitHub.** Offered in the Control Panel; skippable.
- **Files, projects, settings.** Starting settings are only written when missing. Updates are built not to override a choice.

## Switched on without asking (each is changeable)

| What | Change it |
|---|---|
| Remote login (SSH server) | `noc privacy remote off` |
| Clipboard history (CopyQ) | `noc privacy clipboard clear` |
| Saved passwords not locked by a password (autologin keyring) | Privacy page explains the trade-off |
| Hermes on the Nous cloud free tier | `noc privacy hermes local` |

User-facing statement of all this: repo `docs/what-we-do.md`. Keep it and `docs/objectives.md` principle 6 current when a default changes.
