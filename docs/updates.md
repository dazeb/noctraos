# Rolling updates for installed systems

How a NoctraOS machine that is already installed gets new features without a new ISO. Built 2026-10-08.
The tools are `bin/noc-selfupdate` (the machine), `scripts/make-update.py` and `iso/publish-update.sh` (the publisher).

## What is and is not covered

| Layer | How it updates | Where |
|---|---|---|
| Ubuntu/Zorin base, system packages | apt | `noc update` step `apt` |
| Flatpak apps | Flatpak | step `flatpak` |
| **The NoctraOS layer**: install modules, theme, GNOME Shell extensions, search, Control Panel, `noc`, `noc-gpu` | **signed rolling update** (this document) | step `noctraos` |
| Programming languages, AI models | mise, Ollama | steps `mise`, `models` |
| Upgrading the base itself (Zorin 18 to the next release) | not here; a separate, rarer feature | |

The ISO is for new machines. An update is a small signed bundle (about 5 MB) of the same files the ISO's first boot would
install, plus migrations for things that changed on a machine that already has the old version.

## Apps that come straight from their publishers (Hermes, Ollama, coding agents)

Some apps are not in apt or Flatpak: they are installed from the publisher's own release channel. NoctraOS follows the
**newest published release** of each (GitHub's "latest release", never a prerelease or the development branch; the npm
`latest` tag for the coding agents), records the installed version, and shows both in the Control Panel.
`bin/noc-upstream` is the one place that knows how; `noc apps [--json] [--refresh]` prints it.

| App | Newest release comes from | Installed version read from | Updated by |
|---|---|---|---|
| Hermes | GitHub Releases of `NousResearch/hermes-agent` | `hermes --version` | `noctraos-hermes update` (user) |
| Ollama | GitHub Releases of `ollama/ollama` | `ollama --version` | `install/03b_ollama_update.sh` through the privileged helper (root; the Apps page asks first, it restarts the service and keeps whether it starts with the computer: the vendor installer turns that on, the module puts the person's choice back) |
| AppManager | GitHub Releases of `kem-a/AppManager` | `/opt/appmanager/VERSION` | `install/04d_appmanager.sh` through the privileged helper (root) |
| Codex, Claude Code, OpenCode, Grok, Gemini CLI, Qwen Code | npm registry `latest` | the global `node_modules` | `npm install -g <package>@<exact version>` (user); only when already installed |

* **Lookups are cheap and polite:** one request per app, cached for 6 hours (`~/.cache/noctraos/upstream.json`); GitHub's API
  first, and when it rate-limits (60 an hour per address) the `/releases/latest` redirect, which names the same tag. A failed
  lookup keeps the old answer and marks it as old; with no answer at all an app is "unknown", never "up to date".
* **Version history:** `~/.local/state/noctraos/apps.json` remembers each app's installed version and when it changed (including
  changes made by hand), so the panel can say "changed 2 days ago".
* **Ordering is by release, not by tag:** Hermes names its releases `v2026.9.24` (a date) while the version is `0.21.5`; the
  version is read from the release name. A build ahead of the newest release (0.21.5+9141) is not "behind" it.
* **Hermes is moved to a release, not to `main`.** Hermes' own `hermes update` can only follow a branch (`main` is days ahead of
  the last release), its release channels (`--channel stable`) are not published yet (HTTP 404, checked 2026-10-08) and the
  official installer's re-run path fetches branches only. So a fresh install runs the installer pinned to the release tag
  (`--branch v0.21.6`, which works), and `noctraos-hermes update` sets the old runtime directory aside, installs the release
  tag fresh, rebuilds the desktop app, and **puts the old directory back if anything fails**. Everything a person made
  (`config.yaml`, memories, sessions, `SOUL.md`) lives in `~/.hermes` outside that directory and is never touched. It refuses while Hermes
  is running and when under 4 GB is free. If Nous publishes the `stable` channel, switch `cmd_update` to
  `hermes update --channel stable`.
* **Where it shows:** Overview has an **Apps** card; the **Apps** page lists every tracked app with installed and newest version,
  when it last changed, and an Update button (a confirmation for Ollama); the **Updates** page has a "Hermes and coding agents"
  step; `noc update` runs it as step `apps`.

## The model in one paragraph

A publisher builds a **bundle** from a git ref and gives it a **serial** (1, 2, 3, ...). A **channel** (`stable` or
`nightly`) has a small **manifest** that names the bundle by SHA-256 and is **signed** with the NoctraOS update key. A
machine reads the manifest from every mirror, keeps the highest serial that verifies, and applies it only if it is
newer than what is installed and this machine's turn in the **staged rollout** has come. It downloads the bundle,
checks the hash, swaps it in as the new root-owned snapshot (keeping the previous one), runs the install refresh and
the **migrations**, smoke-tests, and puts the old version back by itself if that fails. Nothing is sent anywhere: a
check is a plain GET of two static files.

## Why it is safe

| Risk | What stops it |
|---|---|
| A hacked or wrong mirror serves bad code | Code runs only if the manifest signature verifies with `/usr/local/share/noctraos/update-signers` (ed25519, `ssh-keygen -Y`) and the bundle matches the signed SHA-256. Mirrors are untrusted transports; https is required. |
| Replaying an old (vulnerable) update | The serial must be higher than the installed one. |
| A mirror frozen on an old manifest | All mirrors are read, the highest verified serial wins, and a manifest expires (30 days by default): an expired one is never applied and the Updates page says so. `iso/publish-update.sh renew <channel>` re-signs it. |
| A malicious or broken bundle layout | Only plain files and directories under the allowed top-level names are unpacked (no symlinks, no `..`, no absolute paths, size and count caps). The bundle's own metadata must agree with the signed manifest. |
| A bad update reaches everyone at once | **Staged rollout**: `rollout.percent` in the signed manifest. A machine's place is `sha256(serial + machine-id) % 100`, different for every serial, never sent anywhere. Publish 10, watch, widen to 50, then 100. Setting it back to 0 stops further machines (those already updated stay updated: ship a fix as the next serial). |
| An update that does not work | After the swap the root-owned `install/07_persistence.sh` runs from the new snapshot and `noc status` must work. If either fails, the previous snapshot is restored, the refresh re-runs for it, and that serial is **held** (not offered again; the next serial is). |
| Two updates at once, or a crash half-way | A file lock, and an interrupted swap is repaired at the next start (`repo.prev` is moved back). |
| Root running something the user supplied | `noc-privileged` only runs fixed verbs: `update apt,flatpak,noctraos`, `update-channel stable|nightly`, `update-rollback`. The updater takes no path, URL or command from the caller; the mirror list and key are root-owned files. |
| Not enough disk | The updater refuses below about 600 MB free. |

What it does not do: it cannot undo migrations (see below), and it does not snapshot the whole filesystem as
Omarchy does with Snapper (Zorin installs on ext4). `rollback` restores the NoctraOS layer's code only.

## The pipeline: from a merged change to people's machines

```
PR merged to GitHub main
   |  (a) tag update-YYYY.MM.DD  ->  GitLab update-nightly          or   (b) the daily timer (rolling nightly)
   v
nightly channel  (testers who chose it in the Updates page get it; rollout 100%)
   |  press update-stable-10 in the pipeline, wait, then -50, then -100        (manual jobs)
   v
stable channel  (everyone else, in stages: 10%, 50%, 100%)
```

**(a) A tagged update.** Tag a commit that is already in GitHub `main` and push the tag to GitLab:

```bash
git fetch origin && git tag -a update-2026.10.09 -m "Control Panel icon in the dock

Relogin: no" origin/main
git push gitlab origin/main:refs/heads/main update-2026.10.09     # GitLab must have the commit
```

The tag **message** is the "what's new" line the Updates page shows (first line); `Relogin: yes` and `Reboot: yes` lines in the body
set the flags that tell the person to sign out or restart. `update-*` tags are protected like `v*` (only maintainers can push
them: `iso/setup-release-runner.sh` makes them so), because the job that runs has the signing key. The pipeline
(`.gitlab-ci.yml`, runs on the `noctraos-release` runner) is:

| job | what it does | who gets it |
|---|---|---|
| `shell`, `version`, `tests` | the usual checks, including a bundle of this very repository applied by the real client | nobody |
| `update-nightly` | `iso/ci-publish-update.sh nightly`: refuses a commit that is not in GitHub `main`, then `publish-update.sh nightly` (both stores, read back and verified) | nightly testers |
| `update-stable-10` (manual) | `promote 10`: this update, from nightly to stable, 10% of machines | 10% of stable |
| `update-stable-50`, `update-stable-100` (manual) | `widen 50` / `widen 100`: the same update, more machines | 50%, then everyone |

The manual jobs are safe to press in any order or twice: each refuses anything but **this pipeline's** update (a newer nightly or
stable stays alone) and never lowers a rollout. A release tag `vX.Y.Z` runs the same jobs after `release-site`, so a release is
also an update (its notes are `NoctraOS X.Y.Z`).

**(b) Rolling nightly.** `iso/setup-nightly-update.sh install` (once, on the release workstation) starts a daily user timer running
`iso/nightly-update.sh`: it fetches GitHub `main`, does nothing when no file an update carries changed since the nightly now served
(a website or docs commit spends no serial), runs the unit tests and the theme check, and publishes `main` to **nightly only**, notes
`Nightly 2026-10-09 abc1234: <subject>`. Failed checks send a desktop notification and publish nothing. It never touches stable.
Installing the timer is a decision, not a default: nothing runs it until you do.

**Safety that does not depend on remembering:** `publish-update.sh` takes a lock (two publishes cannot pick the same serial),
never overwrites a bundle, and verifies through the public hostnames; the CI front only ships code that is in `main`; promotion is
manual and staged; `iso/renew-update-channels.sh` keeps the manifests alive.

**On the machine.** The Updates page lists the NoctraOS step like any other, shows which update is installed and which channel
it follows, lets a tester switch to **Nightly** (a confirmation: it can break things) or back to **Stable**, and offers **Go back to the
previous update** when there is one. Terminal: `noc channel [stable|nightly|rollback]`, `noc update --only noctraos`.

## Channels and promotion

* `nightly`: every bundle the publisher cares to push from `main`. For testers and for CI.
* `stable`: the default. A nightly **promoted** after it has soaked: same bundle, same serial, new signature.

```bash
iso/publish-update.sh nightly --ref origin/main --notes "Faster Start panel"   # build + publish the next serial
iso/publish-update.sh stable --rollout 10                                      # promote the newest nightly to 10%
iso/publish-update.sh stable --from stable --rollout 50                        # widen
iso/publish-update.sh stable --from stable --rollout 100
iso/publish-update.sh renew stable                                             # at least every 2 weeks
```

Serials are one counter across channels, so promotion is just the same number appearing in `stable`. A machine that
switches from `nightly` to `stable` gets nothing until `stable` catches up (never backwards).
Add `--relogin` when the update changes GNOME Shell extensions (the shell scans for them once at login) and
`--reboot` for anything that needs a restart; the Updates page tells the person.

Both stores (R2 behind `dl.noctraos.dev`, and the Hetzner bucket) get the same files: all bundles first, manifests
last, and each store is read back through its **public** hostname with the same key clients use. Layout:

```
updates/bundles/noctraos-N.tar.gz            immutable, never overwritten (a different one with the same N stops the publish)
updates/<channel>/manifest.json + .sig       the only mutable files
```

The default mirror list is in the code (`DEFAULT_MIRRORS` in `bin/noc-selfupdate`), so an update can change it. A
machine's `/etc/noctraos/update.json` holds only the person's choice (`channel`); `"mirrors"` there overrides the list.

## What a machine does (`noc update`, the Control Panel's Updates page)

`noc update` runs `apt`, `flatpak`, then `noctraos`, then the user's `mise` and `models`. Packages go first so a new
NoctraOS version can rely on them. In the Control Panel the three root steps share one password prompt.

`noc-selfupdate apply`: lock, recover from an interrupted swap, fetch and verify, decide (current / held / staged /
expired / available), download and check the bundle, unpack, **swap** (`repo` becomes `repo.new`, then `repo.prev` is the
old one), run `install.sh --only 07_persistence.sh` from the new snapshot (installs `noc`, `noc-privileged`, the
Control Panel, the updater itself, `/etc/skel`), smoke-test, write `/var/lib/noctraos/update-state.json`, run system
migrations, then the asking user's migrations. A daily user timer (`noctraos-update-check`) tells the person once per
new update; `touch ~/.config/noctraos/no-update-check` turns it off. A login autostart runs per-account migrations for
accounts that were not logged in during the update.

Useful commands: `noc-selfupdate check [--json]`, `status [--json]`, `set-channel nightly` (root; the panel will use
`noc-privileged update-channel`), `rollback` (root), logs in `/var/log/noctraos/update-*.log`.

## Migrations

`migrations/system/NNNN_name.sh` (root, once) and `migrations/user/NNNN_name.sh` (each account, once). A machine may be
several updates behind, so it runs **every** migration it has not run, in order, and the rules in
`migrations/README.md` make that safe: idempotent, additive first (expand, ship the code, contract in a later update),
never override a person's choice. A failed migration is recorded, retried at the next run, and shown in `noc doctor`
(row `noctraos-update`); it does not roll the update back, because half a migration is not undone by old code.

What an update refreshes without a migration: module 07's files (`noc`, `noc-gpu`, `noc-upstream`, the root helper, the Control
Panel, the updater), every installed `/usr/local/bin/noctraos-*` program, and the NoctraOS **launchers and icons**
(`install_launchers` in `install/lib.sh`: copies only what differs, touches no setting). Files that modules 06, 08 and 09 install
(extensions, the search app, themes, schemas) are **not** refreshed, because those modules also apply desktop settings; a change to
them ships with a migration that re-runs the module (see `migrations/README.md`). Pinning something to the dock is a per-account
setting, so it is a user migration (`migrations/user/0001_pin_control_panel.sh`).

Do not put work in a migration that an install module already does for fresh installs without also making the module
the source of truth: fresh machines run modules, updated machines run modules (07) plus migrations.

## Getting the updater onto machines that predate it

Fresh installs from an ISO built after this lands get it from module 07 at first boot. A machine installed from 0.3.2 or
earlier has no updater: run the one-line installer once (README), which is idempotent and installs it. After that,
`noc update` and the Control Panel do the rest. `noc update` on such a machine says so instead of failing silently.

## The signing key

Private key: `~/secrets/noctraos-update-signing` on the release workstation (mode 600, never in the repo, never in CI
variables). Public key: `configs/update/update-signers`, installed by module 07 and baked into every machine, so
**losing or replacing the key needs a new ISO/updater delivered by another route** (the first update after a key change
can still be signed by the old key and carry the new `update-signers`; do that in a deliberate two-step). Back the key
up offline. `iso/publish-update.sh` is the only thing that uses it, and only on the release workstation.

## Keeping the manifests alive

A manifest expires after 30 days and a client refuses an expired one, so a missed renewal turns "up to date" into "cannot check"
for everyone. `iso/renew-update-channels.sh` re-signs every channel (same bundle, serial and rollout; fresh signature and expiry),
checks that the PUBLIC manifest really expires at least 25 days out, and shows a desktop notification if anything fails.
`iso/setup-update-renewal.sh install` runs it weekly (Mondays 04:30, `Persistent=true` so a missed run happens at the next boot) from a
systemd **user** timer on the release workstation, the only machine with the signing key. The job uses its own clone of GitHub `main`
(`~/.local/share/noctraos-renew/repo`, reset before every run), never a development checkout. `status` shows the timer and the real
expiry of each public manifest; `run` renews now.

## Limits and next steps

* **Published so far (2026-10-08):** update 1 (a baseline: the same files as 0.4.0) and update 2 (the 403 fix) on `nightly`; update 2 on `stable` at 100%. Every host must answer a missing manifest as "nothing published": S3-style storage says 403, which the client treats like 404 for the manifest. The 0.4.0 images contain the client from before that fix and receive it as update 2.
* **Needs doing once by a person:** run `iso/setup-release-runner.sh install` again (it now also protects `update-*` tags; it is idempotent) and, if you want a rolling nightly, `iso/setup-nightly-update.sh install`. Neither has been run from this repository's CI.
* An update-level boot test: boot the previous release's qcow2, apply the update from a local mirror, run `noc doctor`. The unit tests cover the logic with real signing and apply a bundle of this very repository (`tests/test_update_pipeline.py`); they do not boot a desktop.
* A `.deb` in a signed apt repository (the bucket can host one) would let apt and Software Updater carry the NoctraOS layer; the manifest/bundle format stays useful for the nightly channel.
