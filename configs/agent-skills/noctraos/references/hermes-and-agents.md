# Hermes Desktop and the coding agents

## Hermes Desktop

Preinstalled by `install/11_hermes.sh` (runs **last**; 25+ minutes, no sudo; builds the Electron app locally with `hermes desktop --build-only` because upstream disabled Linux desktop release builds; adds about 5 GiB). Launcher/installer: `noctraos-hermes`.

```
noctraos-hermes                  launch (installs first if missing)
noctraos-hermes install          idempotent: runtime + desktop app + model defaults
noctraos-hermes update           move to the newest release (old code restored on failure)
noctraos-hermes local [--no-launch]   local-only: Ollama primary, Nous free tier off (persistent)
noctraos-hermes cloud            back to the Nous free tier (never touches a provider the user set)
noctraos-hermes mode             print cloud | local | other
noctraos-hermes ready            exit 0 when runtime and desktop app are both built
noctraos-hermes status
```

`noc privacy hermes local|cloud|status` is the same switch with the panel's confirmation rules.

### Truths to keep straight

- **The free tier is a cloud service: prompts leave the machine.** "Local AI" in the README and Welcome app refers to the Ollama model. Hermes resolves to the Nous cloud unless local-only. Switching to cloud needs an explicit confirmation. A user's own provider is `mode: other` and is never overridden.
- The free tier exists only when `HERMES_GUEST_ONBOARDING=1` (the wrapper exports it); the desktop mints an anonymous identity, no signup. **Never set `model.provider`** for the user: an explicit provider beats the free tier. `model.provider: "auto"` is Hermes' stock default, not an explicit choice. A bare `fallback_providers` entry does not rescue a machine with no identity and no network, so the wrapper makes Ollama the primary only in that offline-first-launch case.
- Ollama is a `fallback_providers` entry when the free tier is unreachable. Default model follows the one-default-model rule ([local-ai](local-ai.md)).
- Write Hermes config with `hermes config set` (a value starting with `--` is parsed as a CLI option; pass lists as JSON, e.g. `'["--flag"]'`), never by editing `config.yaml`. **Never** run `hermes config set` with a temp `HERMES_HOME` on a box with Hermes installed: it rewrites the shared launcher in the checkout to point at the temp tools dir.
- On a VM, Electron needs `--no-sandbox --disable-dev-shm-usage` or the renderer crash-loops; the wrapper seeds `desktop.electron_flags` when `systemd-detect-virt` says VM. Launching over SSH needs the Xwayland auth file and `env -u SSH_CONNECTION -u SSH_CLIENT -u SSH_TTY`. The `--password-store=basic` flag on Hermes' Electron does **not** stop its keyring prompt.
- `hermes desktop` writes its own launcher each run; the wrapper hides it and sets `desktop.manage_launcher_entry=false`.
- Data lives in `~/.hermes` (config, memories, sessions, `SOUL.md`) and survives updates.

### First-run onboarding

`configs/hermes/onboarding.md` is exported as `HERMES_EPHEMERAL_SYSTEM_PROMPT` until `~/.hermes/.noctraos-onboarded` exists (the prompt tells the agent to create it). There is no separate greeting turn: Hermes Desktop opens with its own guided intro, so the prompt starts the tour from the user's first reply. Flow: who the user is (saved to USER.md via the memory tool), who the agent should be (a "## How I should be" section appended to `~/.hermes/SOUL.md`; protected file, so Hermes asks to approve), then only an **offer** of the tour. Declining or finishing creates the marker.

### Skills in Hermes

Hermes loads skills from `~/.hermes/skills`, and follows symlinks there. The shared layout is a relative symlink `~/.hermes/skills/<name> -> ../../.agents/skills/<name>` (how `baoyu-youtube-transcript` and others are wired), so one copy in the global agents folder serves every agent. `noc agent-skills install` makes that link for this skill; no Hermes setting is written. `skills.external_dirs` can also point at `~/.agents/skills`, but that pulls in every skill in the folder, so it is the person's choice, not ours. Project-local `.hermes/skills` and `.agents/skills` load only when the repo root is in `skills.trusted_project_dirs`. Check with `hermes skills list`.

## Coding-agent launchers

Codex, Claude Code, OpenCode, Grok, Gemini CLI and Qwen Code get a **launcher and nothing more** (Start panel "Agents" menu, `configs/applications/`). `bin/noctraos-agent` installs the npm package on first use, then execs it. Signing in, API keys, subscriptions and each tool's settings are the person's own: never build sign-in or config setup for them in the panel or installer. Versions follow npm `latest` via `noc apps`; agents are installed unpinned.

Roadmap ideas (not built): Aider/Goose launchers, a "pause and ask" step before an agent sends files off the device, folder-scoped revocable agent permissions with a log of what left the device, push-to-talk dictation for Super+Space.
