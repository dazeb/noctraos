# The `nightly` branch

`nightly` is the staging branch. Changes land here first, get exercised on a test VM, and are
promoted to `main` only once they hold up. `main` is production: the site deploys from it
(Cloudflare, on every GitHub `main` update), first boot of an installed ISO clones it, and
release ISOs are built from it.

```
feature branch  ->  PR into nightly  ->  test on the VM  ->  PR nightly into main
```

## Rules

- Branch features off `nightly`, open the PR against `nightly`, not `main`.
- Nothing is promoted to `main` until the checks below are green on `nightly`.
- Promote with a PR `nightly` -> `main` (merge commit, so the staging history stays visible).
  Never push to `main` directly from `nightly`.
- After each promotion, `nightly` equals `main`. If a hotfix goes straight to `main`,
  merge `main` back into `nightly` the same day.
- Docs-only changes may skip staging and go to `main`.

## Testing a nightly change

The provisioner's bootstrap takes a branch, so no ISO is needed. On the test VM (never on the
dev workstation; see `AGENTS.md`):

```bash
NOCTRAOS_BRANCH=nightly bash boot.sh
```

or deploy the working tree with the tarball flow in `AGENTS.md` ("deploy a change to the test
VM"). Run the full installer twice: the second pass must be a no-op.

Checks that must pass before promoting (the same ones CI runs):

```bash
bash -n boot.sh install.sh install/*.sh bin/noc bin/noc-gpu bin/noc-menu bin/noctraos-agent \
  bin/noctraos-hermes bin/noctraos-search configs/nautilus-scripts/*
python3 -m unittest discover -s tests
python3 scripts/render-theme.py --check
```

Push to the homelab GitLab as well to run its pipeline: `git push gitlab nightly`.

## What `nightly` does not cover

- **The site** deploys from GitHub `main` only; `nightly` is never published.
- **ISO builds** (`iso/build-local.sh`, `iso/build-noctraos-iso.sh`) clone the default branch
  (`main`). To bake a nightly into a test ISO, set `REPO_URL` to a clone that has `nightly`
  checked out as its HEAD, or add a branch option to the scripts when it is needed.
- **Installed systems** fetch `main` on first boot, so staged changes reach them only after
  promotion.
