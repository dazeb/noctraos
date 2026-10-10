# The `noc` CLI

`noc` (`bin/noc`, installed to `/usr/local/bin/noc`) is the management CLI and the **single implementation** of every action. The Control Panel is a GUI that calls it. Version is in `VERSION` and must match `bin/noc` and `bin/noc-gpu`.

## Commands

| Command | What it does |
|---|---|
| `noc update [--json] [--only apt,flatpak,noctraos,mise,apps,models]` | Update the stack. Never automatic. `--json` uses `sudo -n` and fails with a message rather than hanging when no credential is cached. |
| `noc updates` | JSON: what an update would do (counts, apt download size, online). |
| `noc channel [stable\|nightly\|rollback]` | Show or set the NoctraOS update channel; `rollback` restores the previous NoctraOS layer. |
| `noc apps [--json] [--refresh]` / `noc apps update [app,app]` | Tracked upstream apps (Hermes, Ollama, AppManager, coding agents): installed vs newest release. Ollama and AppManager ask for sudo. |
| `noc doctor [--json]` | Health check of the whole stack, problems first. |
| `noc repair <appmanager\|vm-guest\|hermes>` | Re-run what `noc doctor` found missing. |
| `noc status` | Overview data as JSON (versions, updates, Ollama, GPU, disk, Hermes, `skipped`, `ollama.autostart`, `disk.can_grow`). |
| `noc models list [--json] \| default [name] \| presets [--json] \| pull <model> \| rm <model>` | Local models. `default` writes `~/.config/noctraos/model`. |
| `noc llm setup \| fit \| start \| stop \| autostart [on\|off]` | Optional local AI (see [local-ai](local-ai.md)). |
| `noc gpu detect \| install \| status` | NVIDIA CUDA / AMD ROCm (or Vulkan) for local LLMs. |
| `noc disk status \| grow` | Use space when the system disk was enlarged. |
| `noc privacy status [--json] \| remote [on\|off] \| clipboard [clear] \| hermes [status\|local\|cloud]` | What the installer arranged without asking. |
| `noc accounts status [--json] \| git set --name N --email E \| github login\|logout\|suggest` | Git identity and GitHub sign-in with no terminal needed. |
| `noc skip list [--json] \| add <git\|github\|gpu> \| rm <id>` | Setup chores the person declined (`~/.config/noctraos/skipped`). |
| `noc agent-skills install [--dry-run] \| status [--json] \| remove \| on` | Install this skill into `~/.agents/skills` and link it for Hermes and Claude Code; `remove` switches it off. |
| `noc bg list \| set <file> \| next` | Wallpapers from `/usr/local/share/backgrounds/noctraos` (GNOME `gsettings`). |

Helper programs behind it (all in `bin/`): `noc-gpu`, `noc-disk`, `noc-accounts`, `noc-agent-skills`, `noc-upstream`, `noc-selfupdate`, `noc-privileged`, `noctraos-hermes`, `noctraos-agent`.

## The `--json` contract

`noc doctor --json`, `status --json`, `models list --json`, `models presets --json`, `privacy status --json`, `skip list --json`, `accounts status --json`, `apps --json`, and the `update --json` event stream are a **contract** for the Control Panel. Their keys are pinned by `tests/test_noc_cli.py` and `tests/test_gpu_detect.py`. Add keys freely; do not rename or remove any. `noc-gpu status --json` rows are parsed from its text output, so keep the `OK` / `!!` / `..` markers.

## Parity rule

"Everything the Control Panel can do, `noc` can do." When adding a panel action: put the logic in `bin/noc` first, make the panel call it, add the `noc` form to `TERMINAL` in `control/panel.py` and to the table in `docs/control-panel.md`. `PanelParityTests` fails when a `noc-privileged` verb, an allowed module or a Health fix has no `noc` command.

## Precedence and files

- Default model: `NOCTRAOS_MODEL`, then `~/.config/noctraos/model`, then `qwen2.5-coder:7b`.
- `NOC_OLLAMA_URL` overrides the Ollama URL (default `http://127.0.0.1:11434`).
- State: `~/.config/noctraos/` (model, skipped, `no-update-check`, `no-vm-guest`), `~/.local/state/noctraos/` (apps.json, migrations), system state `/var/lib/noctraos`, logs `/var/log/noctraos`, channel config `/etc/noctraos/update.json`.
- As root, `noc` ignores `NOC_SELFUPDATE` / `NOC_UPSTREAM` / `NOC_ACCOUNTS` overrides and uses the installed copies; tests set `NOC_TEST_HOOKS=1`.

## Root actions

`noc` reaches root work through `sudo` to the allowlisted `/usr/local/libexec/noctraos/noc-privileged`; the panel reaches the same code through `pkexec` (polkit action `dev.noctraos.privileged`, `auth_admin_keep`). Verbs: `update apt,flatpak,noctraos`, `update-channel`, `update-rollback`, `module <name>`, `gpu-install <vendor>`, `disk-grow`, `remote-access <on|off>`, `ollama-service <start|stop>`, `ollama-autostart <on|off>`. Modules are run only from the root-owned snapshot `/usr/local/share/noctraos/repo`, never from a user-writable clone.
