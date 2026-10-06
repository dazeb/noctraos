# NoctraOS Control Panel

The Control Panel (`noctraos-control`) is the one window for looking after a NoctraOS workstation,
with the mouse and without a terminal. It is a GUI for the `noc` command line, not a second
implementation: every number on screen comes from `noc ... --json`, so the two cannot drift.
The design record and the phase-by-phase history are in [control-panel-plan.md](control-panel-plan.md).

## Open it

- Start panel: the sliders icon in the header, next to the settings gear.
- Super+Space, then type "control".
- The "AI Health Check" and "AI Models" menu entries open it on those pages (`noctraos-control --page <name>`).

Pages: `overview`, `updates`, `models`, `hardware`, `health`, `privacy`, `about`.
Keyboard: Ctrl+1 to Ctrl+7 switch pages, Ctrl+R or F5 check again, Ctrl+W or Ctrl+Q close.

## What each page does

| Page | Shows | Actions |
|---|---|---|
| Overview | Version, updates, local AI, graphics, disk, Hermes mode, search index. Each card opens its page | Refresh, Run health check |
| Updates | System packages (count and download size), Flatpak, programming languages (mise), AI models | Tick what to update, then Update. Needs no terminal; one password prompt for the system steps |
| AI models | Installed models with size and the default; suggestions chosen from this machine's RAM and video memory | Download with a progress bar and Cancel, Remove (confirms), Make default, a custom name |
| Hardware | The GPU found, whether the stack is ready, RAM and disk | Set up the GPU, only after a summary of what will be installed and a yes |
| Health | `noc doctor` as rows, problems first | Re-check, Copy report, Fix where one exists |
| Privacy | Whether Hermes uses the Nous free tier (a cloud service) or stays local | Switch (cloud needs a confirmation), open the Search and Weather settings |
| About | Version, base system, links | Copy diagnostics |

Every page has a "not ready yet" state (no network, Ollama still starting, no GPU, Hermes not
installed). The only things the panel never does on its own: install drivers, switch Hermes to the
cloud, or cancel a half-finished system upgrade.

## How it works

```
noctraos-control (wrapper, pins /usr/bin/python3)
 └ control/main.py     window, sidebar, CSS, --page, shortcuts
    ├ control/pages.py GTK pages; slow calls run on a thread and show a spinner
    └ control/panel.py everything testable without GTK: cards, rows, plans, progress
          │
          ├ noc status | updates | doctor --json | models list|presets --json | update --json
          ├ noc-gpu detect|status --json
          ├ noctraos-hermes mode | local --no-launch | cloud
          └ pkexec noc-privileged  update <apt,flatpak> | module <name> | gpu-install <vendor>
```

### The root side

`bin/noc-privileged` is the only thing the panel runs as root, through pkexec and the polkit action
`dev.noctraos.privileged` (`auth_admin_keep`, so one prompt covers a whole update). It is an
allowlist of fixed verbs, never a shell: it takes no path, command line or package name from the
caller, clears the environment, runs only root-owned code, and re-runs install modules only from
the root-owned snapshot `/usr/local/share/noctraos/repo` that module 07 refreshes, never from the
user's editable clone. To allow another module, add it to `MODULES` in the helper and to
`tests/test_noc_privileged.py`.

### The CLI contract

These outputs are a contract; `tests/test_noc_cli.py` and `tests/test_gpu_detect.py` pin them:
`noc doctor --json`, `noc status`, `noc updates`, `noc models list|presets --json`,
`noc update --json --only <steps>` (an event stream), `noc-gpu detect|status --json`.

## Testing a change

```sh
python3 -m unittest discover -s tests        # logic, CLI contracts, the helper's allowlist, a headless GTK smoke test
```

The smoke test builds the whole window under Xvfb with every external program missing, at 1x and
2x scale, and presses the shortcuts; it is skipped where GTK or Xvfb is absent. Real behaviour is
checked on the local KVM VM (`iso/local-vm.sh`): deploy modules 06 and 07 (and 09 for the Start
panel), then **open the panel from Super+Space or the Start panel, not over SSH**. A panel started
from an SSH shell belongs to the SSH session and cannot show the polkit prompt.
