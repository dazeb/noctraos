# NoctraOS Control Panel

The Control Panel (`noctraos-control`) is the one window for looking after a NoctraOS workstation,
with the mouse and without a terminal. It is a GUI for the `noc` command line, not a second
implementation: every number on screen comes from `noc ... --json`, so the two cannot drift.
The design record and the phase-by-phase history are in [control-panel-plan.md](control-panel-plan.md).

## Open it

- **The dock.** The NoctraOS Control Panel icon is pinned to the taskbar (last, after the Terminal). A fresh install pins it in
  module 06; accounts made earlier get it once from `migrations/user/0001_pin_control_panel.sh`, and unpinning it sticks.
  It opens on the Overview, whose first card is the setup checklist.
- Start panel: the sliders icon in the header, next to the settings gear.
- Super+Space, then type "control".
- The "AI Health Check" and "AI Models" menu entries open it on those pages (`noctraos-control --page <name>`).

Pages: `overview`, `accounts`, `updates`, `apps`, `models`, `hardware`, `health`, `privacy`, `about`.
Keyboard: Ctrl+1 to Ctrl+9 switch pages, Ctrl+R or F5 check again, Ctrl+W or Ctrl+Q close.

## What each page does

| Page | Shows | Actions |
|---|---|---|
| Overview | **Setup checklist** first: Git name and e-mail, GitHub sign-in, GPU for local AI, a local model, meeting Hermes, the Start panel weather. Finished steps are only counted; what is left (and what you skipped, so the way back stays in sight) has a row and a button. Then the cards: version, updates, local AI, graphics, disk, Hermes mode, search index; each opens its page | Refresh, Run health check, a button per step |
| Accounts | The two first-time chores that stop a newcomer's first `git commit` and `git push`: the name and e-mail Git signs work with, and signing in to GitHub (a code to paste in the browser; no terminal, no password typed). Offers GitHub's private e-mail address | Save, Sign in, Use my GitHub details, Sign out, No I'll set it up myself (each chore) |
| Apps | Hermes, Ollama, AppManager and the coding agents: installed version, newest upstream release, when it last changed, an Update button ([updates.md](updates.md#apps-that-come-straight-from-their-publishers-hermes-ollama-coding-agents)) | Check now, Update |
| Updates | System packages (count and download size), Flatpak, NoctraOS features (signed rolling updates, [updates.md](updates.md)), programming languages (mise), AI models | Tick what to update, then Update. Needs no terminal; one password prompt for the system steps. Below the list: which NoctraOS update is installed, the update channel (Stable or Nightly) and Go back to the previous update |
| AI models | Installed models with size and the default; suggestions chosen from this machine's RAM and video memory. Until local AI is set up (it is not part of the first install), the page says so | Set up local AI… (summary and a yes, then the engine, the GPU driver if there is one, and LLMFIT; no model is downloaded), Download with a progress bar and Cancel, Remove (confirms), Make default, a custom name |
| Hardware | The GPU found, whether the stack is ready, RAM and disk; a notice when the disk is bigger than the system uses | Set up the GPU, or use all of an enlarged disk, each only after a summary of what will change and a yes; or "No, I'll set up the GPU myself" |
| Health | `noc doctor` as rows, problems first | Re-check, Copy report, Fix where one exists |
| Privacy | Whether Hermes uses the Nous free tier (a cloud service) or stays local; whether remote login (the SSH server) is on; how many copies CopyQ has saved on disk; whether the saved-password store is locked by a password | Switch Hermes (cloud needs a confirmation), turn remote login off or on (one password prompt, on needs a confirmation), clear the clipboard history (confirms), open Passwords and Keys, open the Search and Weather settings |
| About | Version, base system, links | Copy diagnostics |

Every page has a "not ready yet" state (no network, Ollama still starting, no GPU, Hermes not
installed). The only things the panel never does on its own: install drivers, switch Hermes to the
cloud, or cancel a half-finished system upgrade.

## The setup checklist

Everything the Welcome app and the first boot ask for lives in one list at the top of the Overview, so nobody has to remember
where a skipped step was. `panel.setup_steps()` builds it from `noc status --json` plus `panel.setup_extras()` (GPU stack state,
whether Hermes' first-run chat happened, the weather city). A step is `done`, `todo`, `skipped` (a `noc skip` chore) or
`waiting` (cannot be done yet, for example Hermes while the first boot still builds it, so nothing nags). Steps that do not
apply, like the GPU step on a machine with no usable GPU, are left out. The weather step is optional and never counts as "left".
A new chore needs a step in `setup_steps()` and a test in `SetupChecklistTests`.

## Doing it yourself

The panel is mouse first and the terminal a close second. Nothing here is mandatory, and nothing needs the panel:

- **"No, I'll set it up myself".** Every setup chore the panel offers (the Git name and e-mail, the GitHub sign-in, the GPU
  setup; the Welcome app's "Set up Git and GitHub" too) has this button. It changes nothing on the system. It is remembered
  by `noc skip` (`~/.config/noctraos/skipped`, one id per line), so the Overview card, the page headline and the Welcome app
  stop asking, and the page shows the terminal commands in place of the form. "Set it up here after all" takes it back.
  Nothing is hidden for good: a chore that is already done is never shown as skipped.
- **The Terminal button.** Every page with an action has a small, quiet *Terminal* button. Hovering it lists the commands for
  that page's actions; clicking it copies them. People who never look never see a command. The table is `TERMINAL` in
  `control/panel.py`; `tests/test_control_core.py` fails if a tip names a command or sub-command that does not exist.

```sh
noc skip                      # what you skipped
noc skip add github           # git | github | gpu
noc skip rm github            # ask again
```

Adding a setup chore to the panel means: an id in `SKIPPABLE` (panel.py) and `SKIPPABLE` (`bin/noc`), a skip button and a
skipped state on its page, a `TERMINAL` entry. Actions that are already opt-in (updates, apps, models, privacy) need only the
Terminal button.

## The terminal does everything the panel does

The panel is a front end for `noc`, so a machine whose panel breaks (no display, a GTK problem) still has every option. Each
panel action and the command that does the same:

| Panel | `noc` |
|---|---|
| Updates: update | `noc update [--only apt,flatpak,noctraos,mise,apps,models]` |
| Updates: channel, Go back | `noc channel [stable\|nightly]`, `noc channel rollback` |
| Apps: Update | `noc apps update [app,app]` (Ollama and AppManager ask for sudo) |
| AI models: Set up local AI, Download, Remove, Make default | `noc llm setup`, `noc models pull <model>`, `noc models rm <model>`, `noc models default <model>` |
| Hardware: GPU setup, Use all the disk space | `noc gpu install`, `sudo noc disk grow` |
| Health: Fix | `noc repair appmanager\|vm-guest\|hermes` (the doctor row says which) |
| Privacy: Hermes, Remote login, Clipboard history | `noc privacy hermes local\|cloud`, `noc privacy remote on\|off`, `noc privacy clipboard clear` |
| Accounts | `noc accounts git set`, `noc accounts github login\|logout` |
| "No, I'll do it myself" | `noc skip add\|rm <id>` |

`noc privacy status [--json]` is also what the Privacy page reads, so the page and the terminal cannot disagree. The panel's root
steps go through `noc-privileged` (pkexec, no terminal) and `noc` reaches the same code through `sudo`.
`tests/test_noc_cli.py` (`PanelParityTests`) fails when a root verb, an allowed module or a Health fix has no `noc` command, so a
panel feature cannot be added without its terminal twin. Search settings and the weather city are windows of their own
(`noctraos-search --settings`, `noctraos-weather --setup`).

## How it works

```
noctraos-control (wrapper, pins /usr/bin/python3)
 └ control/main.py     window, sidebar, CSS, --page, shortcuts
    ├ control/pages.py GTK pages; slow calls run on a thread and show a spinner
    └ control/panel.py everything testable without GTK: cards, rows, plans, progress
          │
          ├ noc status | updates | doctor --json | models list|presets --json | update --json | skip list --json
          ├ noc privacy status --json | clipboard clear | hermes local|cloud
          ├ noc-gpu detect|status --json
          └ pkexec noc-privileged  update <apt,flatpak> | module <name> | gpu-install <vendor> | disk-grow | remote-access <on|off>
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
`noc update --json --only <steps>` (an event stream), `noc privacy status --json`, `noc-gpu detect|status --json`.

## Testing a change

```sh
python3 -m unittest discover -s tests        # logic, CLI contracts, the helper's allowlist, a headless GTK smoke test
```

The smoke test builds the whole window under Xvfb with every external program missing, at 1x and
2x scale, and presses the shortcuts; it is skipped where GTK or Xvfb is absent. Real behaviour is
checked on the local KVM VM (`iso/local-vm.sh`): deploy modules 06 and 07 (and 09 for the Start
panel), then **open the panel from Super+Space or the Start panel, not over SSH**. A panel started
from an SSH shell belongs to the SSH session and cannot show the polkit prompt.
