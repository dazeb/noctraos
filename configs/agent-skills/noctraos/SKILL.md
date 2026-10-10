---
name: noctraos
description: Complete guide to NoctraOS, the AI development workstation OS (Ubuntu base, Zorin/GNOME and Kubuntu/KDE flavours). Use for anything on a NoctraOS machine or in the noctraos repo - the `noc` CLI, Control Panel, updates and channels, rollback, local AI (Ollama, models, GPU), Hermes Desktop and the coding-agent launchers, Super+Space search, Start panel, theme and wallpapers, privacy, Git/GitHub setup, disk grow, VM guest tools, doctor/repair, app policy (Flatpak/AppImage), installer modules, ISO and release builds, and contributing to the repo.
---

# NoctraOS

NoctraOS (`noctraos`, github.com/dazeb/noctraos) is an AI development workstation delivered as a bootable ISO on an Ubuntu base. Its idea: Omarchy's "everything set up for AI work" without a tiling-WM learning curve. One product, shipped as **flavours**: `zorin` (GNOME on Zorin OS 18.1, shipped) and `kubuntu` (KDE Plasma on Kubuntu 26.04, in progress). The headline feature is **Super+Space** system search.

This skill works for any agent (Hermes, Codex, Claude Code, OpenCode, ...). It is split so you load only what the task needs. Read this page, then open the reference for your area.

## First: which situation are you in?

| You are... | Do this |
|---|---|
| Helping a person use or fix their NoctraOS machine | Use `noc` first (see [noc-cli](references/noc-cli.md)). Run `noc doctor` before guessing. |
| Working inside the noctraos git repo | Read the repo `AGENTS.md`, then [development](references/development.md). Never run `install.sh`/`boot.sh` on the dev workstation. |
| Unsure whether this is a NoctraOS machine | `test -f /etc/noctraos-release && cat /etc/noctraos-release; command -v noc` |

## Map: what to read for what

| Topic | Reference |
|---|---|
| What NoctraOS is, principles, flavours, what is set up vs what stays the user's | [overview](references/overview.md) |
| Every `noc` command, the `--json` contracts, CLI/panel parity | [noc-cli](references/noc-cli.md) |
| The Control Panel pages, setup checklist, "No, I'll do it myself" | [control-panel](references/control-panel.md) |
| apt/Flatpak/NoctraOS layer updates, channels, rollback, migrations, upstream apps | [updates](references/updates.md) |
| Ollama, models, default model, GPU stack, LLMFIT, local AI setup | [local-ai](references/local-ai.md) |
| Hermes Desktop (cloud vs local), onboarding, coding-agent launchers | [hermes-and-agents](references/hermes-and-agents.md) |
| Desktop: theme, dock, Start panel, Super+Space search, wallpapers, CopyQ, Nautilus scripts, menus | [desktop](references/desktop.md) |
| Apps and the Flatpak/AppImage-first policy, VS Code, AppManager, mise | [apps-and-policy](references/apps-and-policy.md) |
| Privacy page items, remote login, clipboard, keyring, Git/GitHub accounts | [privacy-and-accounts](references/privacy-and-accounts.md) |
| GPU, disk grow, VM guest tools, hardware | [hardware](references/hardware.md) |
| Something is broken: doctor rows, logs, known failures and fixes | [troubleshooting](references/troubleshooting.md) |
| Installer modules, `boot.sh`, first boot, ISO build, Proxmox installer, releases | [install-and-release](references/install-and-release.md) |
| Repo map, hard rules, tests, test VMs, how to ship a change | [development](references/development.md) |

## Rules that apply everywhere

1. **`noc` is the single control surface.** Everything the Control Panel does, `noc` does. Prefer `noc ...` over editing files, `gsettings` calls or `systemctl` by hand. State for scripts comes from `noc ... --json`; do not scrape text output.
2. **We set up the system, then the user takes control.** Never silently choose for them: anything that costs memory, sends data off the machine, or belongs to the person is opt-in. Do not set up sign-ins, API keys or config for the coding agents (Git name/e-mail and the GitHub sign-in are the one exception, and they are skippable).
3. **Respect skipped chores.** `noc skip list` shows what the person declined (`git`, `github`, `gpu`). Do not nag or redo them; show the terminal commands only when asked.
4. **Hermes' free tier is a cloud service.** Prompts typed to Hermes leave the machine unless it is in local mode (`noc privacy hermes local`). Never describe Hermes as local without that qualification.
5. **Updates are optional, reversible, and keep the user's choices.** Never run an update, grow a disk, install a GPU driver, or switch Hermes to cloud without the person saying yes.
6. **Never print or commit secrets.** Credentials live in `~/secrets/*` and `.env` files, not in output, logs or the repo.
7. **Name the flavour** (`zorin` or `kubuntu`) when reporting what you changed or tested. Never copy a fix between flavours; each gets its own change and test.
8. **Root work goes through the allowlisted helper** (`noc-privileged`, via pkexec or `noc`'s sudo path). Never add a verb that takes a path, URL, command or package name from the caller.
9. **Verify, then report faithfully.** Run the check (`noc doctor`, the tests, `bash -n`), say what failed, and say when something was not tested (most real-hardware paths are untested; see [development](references/development.md)).

## Quick commands

```bash
noc status --json        # versions, updates, Ollama, GPU, disk, Hermes (the Overview data)
noc doctor               # health check of the whole stack ([--json]); problems first
noc update               # apt + Flatpak + NoctraOS layer + mise + apps + models (asks; never automatic)
noc models list          # installed local models and the default
noc privacy status       # what was arranged without asking: remote login, clipboard, keyring, Hermes mode
noc skip list            # setup chores the person declined
noctraos-control        # open the Control Panel (--page overview|accounts|updates|apps|models|hardware|health|privacy|about)
```

If `noc` is missing, this is not a NoctraOS machine (or the install is broken): check `/usr/local/bin/noc`, then [troubleshooting](references/troubleshooting.md).
