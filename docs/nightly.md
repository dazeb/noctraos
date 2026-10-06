# The `nightly` branch and the nightly download

`nightly` is the staging branch. New work lands here first and is tried in a VM; if it holds up,
it is promoted to `main`. There is no nightly website: the site deploys from `main` only.

```
feature branch  ->  PR into nightly  ->  nightly VM image  ->  works?  ->  PR nightly into main
```

## The nightly download

A ready-made VM disk built from `nightly`: `https://files.dazeb.dev/nightly/noctraos-nightly.qcow2`
(with `SHA256SUMS` and `BUILD-INFO.txt`, which names the branch and commit it was built from).

It is a finished image, not an installer, on purpose. The ISO provisions itself on first boot (25
to 40 minutes of downloads and an Electron build) and that step can fail on someone's network. The
nightly build does that provisioning once, here, and only writes the image if it finished and
`noc doctor` is clean. Whoever tests it boots a system that already works.

Login is `noctraos` / `noctraos` with autologin and passwordless sudo. It is a trial appliance for
testing: never production, never real credentials.

### Building it

```bash
git push origin nightly                       # the build clones nightly from GitHub
iso/build-nightly.sh /run/media/dazeb/2tb/noctraos-build            # build only
iso/build-nightly.sh /run/media/dazeb/2tb/noctraos-build --upload   # build and publish
```

About 45 to 60 minutes, almost all provisioning. It builds an appliance ISO with the `nightly`
branch baked in (`NOCTRAOS_BRANCH`, so first boot fetches `nightly`, not `main`), installs it
unattended into a throwaway local KVM VM (`/mnt/nvme1/noctraos-nightly-vm`, ssh port 2223, so it
can run beside the 2222 test VM), waits for provisioning, checks `noc doctor`, runs the sysprep and
exports the qcow2 to `<build-dir>/out/nightly/`. Upload is only done with `--upload`, and
overwrites the same three names each time. Uploading is public: build first, look, then upload.

## Rules

- Branch features off `nightly`, open the PR against `nightly`.
- Promote with a PR `nightly` -> `main` once the nightly image has been tried. Never push to
  `main` from `nightly` directly.
- After a promotion `nightly` equals `main`. If a hotfix goes straight to `main`, merge `main` back
  into `nightly` the same day.
- Docs-only changes may skip staging and go to `main`.

## Quick checks without an image

On a test VM (never on the dev workstation; see `AGENTS.md`):

```bash
NOCTRAOS_BRANCH=nightly bash boot.sh
```

Static checks, the same as CI (`git push gitlab nightly` runs the GitLab pipeline):

```bash
bash -n boot.sh install.sh install/*.sh bin/noc bin/noc-gpu bin/noc-privileged bin/noctraos-control \
  bin/noctraos-agent bin/noctraos-hermes bin/noctraos-search configs/nautilus-scripts/*
python3 -m unittest discover -s tests
python3 scripts/render-theme.py --check
```

## What nightly does not touch

Installed systems and release ISOs follow `main`. Staged changes reach them only after promotion.
