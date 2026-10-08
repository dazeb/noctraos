# Migrations

Scripts that bring an **already installed** system in line with a new release. A fresh install does not need them
(the install modules do the work); an update does, because modules are not re-run for every change.

- `system/NNNN_name.sh` run once as root by `noc-selfupdate`, in order, after the new snapshot is in place.
- `user/NNNN_name.sh` run once per account, as that account, after an update and again at every login
  (an account that was not logged in during the update catches up).

Rules (the updater and `docs/updates.md` rely on them):

1. **Idempotent.** A migration that failed is retried at the next update, and one that half-ran must be safe to run again.
   Check before you change (`command -v`, file exists, `gsettings get`), exactly like an install module.
2. **Additive first.** The previous version can be restored (`noc-selfupdate rollback`) but migrations are not undone.
   Add the new thing, ship the code that uses it, and remove the old thing in a later update.
3. **Never overwrite the user's choices.** Seed a setting only when it is missing; keep what they changed.
4. **No network, no prompts, no long builds.** If it needs a download, make it a step the person can see in `noc update`.
5. **Warn, do not die, for desktop settings** (rule 3 in AGENTS.md); a migration may exit non-zero only when the
   system would be left worse than before.
6. Name files `NNNN_short-name.sh` (four digits, lowercase). Numbers are never reused or reordered once released.

Environment: `NOCTRAOS_SNAPSHOT` (the root-owned snapshot), `NOCTRAOS_MIGRATION_SCOPE`, and for system migrations
`NOCTRAOS_USER` (the desktop user who asked). User migrations run with that user's `HOME` and session bus.
