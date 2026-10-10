# Updates

Updates are **optional, signed, staged, reversible, and keep the person's choices**. NoctraOS updates never install by themselves; a daily check may only tell the person one is waiting (`touch ~/.config/noctraos/no-update-check` stops the reminder). Full design: repo `docs/updates.md`.

## Layers

| Layer | How it updates | `noc update --only` |
|---|---|---|
| Ubuntu/Zorin base packages | apt | `apt` |
| Flatpak apps | Flatpak | `flatpak` |
| **The NoctraOS layer** (install modules, theme, Shell extensions, search, Control Panel, `noc`, `noc-gpu`) | signed rolling update | `noctraos` |
| Languages | mise | `mise` |
| Hermes, Ollama, AppManager, coding agents | their publisher's release channel | `apps` |
| AI models | Ollama | `models` |
| Base release upgrade (Zorin 18 to the next) | not covered; a separate future feature | - |

Root steps (`apt,flatpak,noctraos`) run first with one prompt; the user's own steps then run through `noc update --json`. There is no cancel for apt.

## The NoctraOS layer (signed rolling updates)

A publisher builds a **bundle** (about 5 MB, a tar of the `ITEMS`) from a git ref with a **serial** (1, 2, 3...). A **channel** (`stable` or `nightly`) has a **manifest** naming the bundle by SHA-256, **signed** by the NoctraOS update key (public key: `configs/update/update-signers`; the private key `~/secrets/noctraos-update-signing` is used only by `iso/publish-update.sh` on the release workstation). The machine reads manifests from every mirror, keeps the highest serial that verifies, applies it if newer and its **staged rollout** turn has come, swaps it in as the new root-owned snapshot (keeping the previous one), runs module 07 plus **migrations**, smoke-tests, and **rolls back by itself on failure**. A check is a plain GET of two static files; nothing is sent.

- Client: `bin/noc-selfupdate` (installed to `/usr/local/libexec/noctraos`): `status`, `apply`, `rollback`, `set-channel`, `migrate --scope system|user`, `check`, `notify`.
- Channel: `noc channel` shows, `noc channel nightly` switches; stored in `/etc/noctraos/update.json` and never overwritten by an install.
- Go back: `noc channel rollback` (or the Updates page) restores the previous NoctraOS layer. It undoes the code, not data; files changed for a new feature stay changed.
- Machines installed from 0.3.2 or earlier need the one-line installer once to get the updater.
- Manifests expire after 30 days. A weekly user timer (`iso/setup-update-renewal.sh status`) re-signs both channels; never switch the release workstation off for a month without renewing by hand.

## Migrations (`migrations/`)

Run once to bring an already-installed system in line; a fresh install does not need them.

- `system/NNNN_name.sh`: once, as root, in order, after the snapshot is in place.
- `user/NNNN_name.sh`: once per account, as that account, after an update and again at every login (catch-up).
- Rules: idempotent (a failed one is retried); additive first (rollback does not undo migrations); never overwrite the user's choices; no network, prompts or long builds; warn rather than die for desktop settings; four-digit numbers never reused or reordered.
- An update refreshes by itself: module 07 (`noc`, `noc-gpu`, `noc-upstream`, root helper, Control Panel, updater), every already-installed `/usr/local/bin/noctraos-*` program, launchers and icons. It does **not** re-run modules 06, 08, 09; add a system migration that re-runs the module (`SUDO_USER="$NOCTRAOS_USER" bash "$NOCTRAOS_SNAPSHOT/install.sh" --only 09_super_search.sh`) if your change touches what they install.

The item list must stay equal in three places (a test pins it): `install/07_persistence.sh`, `BUNDLE_ITEMS` in `bin/noc-selfupdate`, `ITEMS` in `scripts/make-update.py`. Bundles hold plain files only (no symlinks). A published bundle `updates/bundles/noctraos-N.tar.gz` is never replaced; publish the next serial.

## Upstream apps (`bin/noc-upstream`)

The only place that resolves "latest" (GitHub `releases/latest`, npm `latest`; never a prerelease or branch tip). Lookups are cached 6 hours (`~/.cache/noctraos/upstream.json`); a failed lookup keeps the old answer marked old; no answer is "unknown", never "up to date". History in `~/.local/state/noctraos/apps.json`.

| App | Updated by |
|---|---|
| Hermes | `noctraos-hermes update` (user): sets the old runtime aside, installs the release tag fresh, rebuilds the desktop app, restores on failure; `~/.hermes` is never touched; refuses while running or under 4 GB free |
| Ollama | `install/03b_ollama_update.sh` via the privileged helper; the person's autostart choice is put back |
| AppManager | `install/04d_appmanager.sh` via the privileged helper |
| Codex, Claude Code, OpenCode, Grok, Gemini CLI, Qwen Code | `npm install -g <pkg>@<exact version>`, only when already installed |

Do **not** use `hermes update --branch <tag>` (treats the tag as a branch, fails) or `hermes update --channel stable` (not published, 404). Never pin Hermes to a release older than the installer expects.

## Publishing (maintainers)

Updates ship through the pipeline: an `update-YYYY.MM.DD` tag (protected like `v*`) runs `update-nightly`; manual `update-stable-10/50/100` jobs stage it (`iso/ci-publish-update.sh`; only commits in GitHub `main`, never a lowered rollout). Optional daily nightly publisher: `iso/setup-nightly-update.sh`. Manual: `iso/publish-update.sh`. Read back and verify both stores after publishing.
