# The Control Panel

`noctraos-control` is the one window for looking after a NoctraOS workstation with the mouse. It is a GUI for `noc`, nothing more: every number comes from `noc ... --json`, work runs on a thread (never blocks GTK), and every page has a "not ready yet" state (Ollama down, no network, no GPU, Hermes not installed) instead of an exception.

## Open it

Dock icon (pinned last), Start panel sliders icon, Super+Space then type "control", or `noctraos-control --page <name>`. Pages: `overview`, `accounts`, `updates`, `apps`, `models`, `hardware`, `health`, `privacy`, `about`. Keys: Ctrl+1..9 switch pages, Ctrl+R / F5 re-check, Ctrl+W / Ctrl+Q close. The "AI Health Check" and "AI Models" menu entries open it on those pages.

## Pages and the `noc` twin of each action

| Page | Shows | Actions (`noc` form) |
|---|---|---|
| Overview | Setup checklist first, then cards (version, updates, local AI, graphics, disk, Hermes mode, search index); each card opens its page | Refresh, run health check, a button per step |
| Accounts | Git name/e-mail and GitHub sign-in | `noc accounts git set`, `noc accounts github login\|logout` |
| Apps | Hermes, Ollama, AppManager, coding agents: installed vs newest | `noc apps update [app]` |
| Updates | apt, Flatpak, NoctraOS layer, mise languages, models; channel; Go back | `noc update [--only ...]`, `noc channel [stable\|nightly\|rollback]` |
| AI models | Installed models, suggestions sized to RAM/VRAM, Engine row | `noc llm setup`, `noc models pull\|rm\|default`, `noc llm start\|stop\|autostart` |
| Hardware | GPU found, RAM, disk, enlarged-disk notice | `noc gpu install`, `sudo noc disk grow` |
| Health | `noc doctor` rows | `noc repair appmanager\|vm-guest\|hermes` |
| Privacy | Hermes cloud/local, remote login, clipboard, keyring | `noc privacy hermes\|remote\|clipboard` |
| About | Version, base, diagnostics | Copy diagnostics |

The only things the panel never does on its own: install drivers, switch Hermes to the cloud, or cancel a half-finished system upgrade (an apt upgrade has no cancel; a half-finished one is worse than a slow one).

## Setup checklist

At the top of the Overview, built by `panel.setup_steps()` from `noc status --json` plus `panel.setup_extras()`. Step states: `done`, `todo`, `skipped` (a `noc skip` chore), `waiting` (cannot be done yet, e.g. Hermes while the first boot still builds it - so nothing nags). Steps that do not apply (GPU step with no usable GPU) are omitted. Local AI is an option, never a chore (`waiting`, no skip button). The weather step is optional and never counts as "left".

## Skippable chores and terminal tips

- Every setup chore (Git identity, GitHub sign-in, GPU setup) has **"No, I'll set it up myself"**, which runs `noc skip add <id>`. After that nothing nags and the page shows the commands in place of the form.
- Every action page has a quiet **Terminal** button whose tooltip lists the commands (`TERMINAL` in `control/panel.py`; a test checks each command exists). Never show a command to someone who did not ask for it.
- A new chore needs: an id in `SKIPPABLE` (both `control/panel.py` and `bin/noc`), a skip button and skipped state, a `TERMINAL` entry, a step in `setup_steps()`, and a test in `SetupChecklistTests`.

## Code layout

```
bin/noctraos-control   wrapper, pins /usr/bin/python3
control/main.py        GTK3 window, sidebar, CSS, --page, shortcuts
control/pages.py       GTK pages (slow calls on a thread with a spinner)
control/panel.py       everything testable without GTK: cards, rows, plans, progress, TERMINAL, GPU_NEEDS, LOCAL_AI_NEEDS
```

Installed to `/usr/local/share/noctraos-control`. A card is clickable only when its sidebar page exists. Tests: `tests/test_control_core.py` (no GTK), `tests/test_control_smoke.py` (drives the GTK flow with stand-ins). Full design record: `docs/control-panel.md`, `docs/control-panel-plan.md`.
