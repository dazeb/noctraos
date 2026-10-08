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

## Limits and next steps

* Not wired into the tag pipeline yet: pushing `vX.Y.Z` still publishes ISOs only. A natural next job is `publish-update.sh nightly --ref vX.Y.Z` plus a first `stable --rollout 10`.
* A nightly timer on the release runner (build the newest `main` if it changed and its tests pass) would make nightly truly rolling.
* An update-level boot test: boot the previous release's qcow2, apply the update from a local mirror, run `noc doctor`. The unit tests cover the logic with real signing; they do not boot a desktop.
* A `.deb` in a signed apt repository (the bucket can host one) would let apt and Software Updater carry the NoctraOS layer; the manifest/bundle format stays useful for the nightly channel.
