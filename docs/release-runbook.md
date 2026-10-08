# Release runbook: NoctraOS 0.3.0

Written 2026-10-05 as a handoff. Read `AGENTS.md` first (rules, pitfalls). This file is the
ordered list of what is left to ship 0.3.0 and exactly how. Everything below was done by hand
once; the scripts named here exist so you do not have to repeat the discovery.

## Releasing with the GitLab pipeline (the normal way)

A release is one tag. The homelab GitLab builds, tests and publishes everything and updates the site.

```bash
# 1. bump VERSION, bin/noc, bin/noc-gpu (the version job fails if they disagree); optionally write
#    docs/release-notes/vX.Y.Z.md (known issues etc.: it becomes the top of the GitHub release notes)
# 2. merge that to GitHub main  (the build clones main, and refuses a tag that is not main's head)
git fetch origin && git tag vX.Y.Z origin/main
git push gitlab origin/main:refs/heads/main vX.Y.Z    # GitLab must have the commit the tag points at
```

| job | what it does | public? |
|---|---|---|
| `release-build` | release ISO + appliance ISO (`iso/build-local.sh both`), unattended install in a KVM VM, first-boot provisioning, `noc doctor` must be clean, sysprep, qcow2 + vmdk export, torrent, `SHA256SUMS`, then a boot test of the exported disk (ssh, autologin session, new host key). 45 to 90 minutes. | no |
| `release-publish` | uploads to `dl.noctraos.dev/releases/vX.Y.Z/` (SHA256SUMS last), streams every file back through the public hostname and compares SHA-256, creates the GitHub release (links + checksums). Refuses a version already in the bucket. | **yes** |
| `release-site` | PR to GitHub `main` that updates `site/download.html`, `site/index.html`, the sitemap, `proxmox-install.sh`, the social cards and the torrent, merges it (Cloudflare then deploys the site from `main`) and waits until `noctraos.dev/download` shows the version. | yes |

Everything is in `.gitlab-ci.yml`; the work is done by `iso/build-release.sh`, `iso/publish-release.sh` and
`scripts/release-site-pr.sh` (each also runs by hand: `iso/build-release.sh <build-dir>`). Outputs stay on the
runner in `<build-dir>/release/vX.Y.Z/` (default `/run/media/dazeb/2tb/noctraos-release-ci`).

- **A failed job:** fix the cause and use *Retry* on that job; earlier stages are not repeated. `release-publish`
  and `release-site` are safe to retry (they stop if the release is already published or the site already shows it).
  `release-build` throws the previous attempt away.
- **Rehearse changes to the pipeline** without publishing anything:
  `RELEASE_REHEARSAL=1 REHEARSAL_BRANCH=<branch on GitHub> iso/build-release.sh <build-dir>`; it writes
  `release/vX.Y.Z-rehearsal/` and `publish-release.sh` refuses it.
- **Review the site PR before it merges:** run the pipeline with `SITE_MERGE=pr` (a CI variable) and the job
  stops after opening the PR. To gate the public upload as well, add `when: manual` to `release-publish` in
  `.gitlab-ci.yml`.
- **The runner:** `iso/setup-release-runner.sh doctor|install|status|remove`. It is a project runner on the
  workstation (Docker, KVM, the R2 and GitHub credentials, the 2 TB drive are there), a systemd *user* service, tag
  `noctraos-release`, ref-protected, locked to this project; `v*` tags are protected so only maintainers can start a
  release. The checks (`shell`, `version`, `tests`) still run on the TrueNAS Docker runner.
- Needs on the runner: Docker, KVM, qemu + OVMF, google-chrome, `gh` logged in, ssh push to GitHub,
  `~/secrets/cloudflare-r2.env`, and `in/Zorin-OS-18.1-Core-64-bit.iso` in the build dir.

The numbered sections below are the same steps by hand: still the way to recover from a half-finished release.

## Where things stand

Done and on `main`: the Hermes Desktop module (`install/11_hermes.sh`, runs last), the onboarding
prompt, the release/unattended split in the ISO build (a release ISO has no seed and no
unattended boot entry), the `VERSION` file (0.3.0) and ISO labelling, `iso/vm-sysprep.sh`.

Also on `main` since PR #17 (`audit/apps`, merged): the app policy (`install/04c_app_policy.sh`),
AppManager (`04d`), the NoctraOS welcome (`bin/noctraos-welcome`) replacing Zorin's tour,
`bin/noctraos-appearance`, `noctraos-hermes local|ready`, the preflight relaxation, and the local
build and test tooling (`iso/build-local.sh`, `iso/local-vm.sh`). The docs were realigned with all
of this afterwards (README, AGENTS.md, `docs/`).

**Status (2026-10-05):** steps 1 to 4 below are done. The ISOs were rebuilt from `main` after #17,
the release ISO boots to the installer, the appliance ISO installs and provisions unattended, and both
VM disks (QCOW2, VMDK) were exported from that clean run, boot-tested and published with `SHA256SUMS`
at `https://dl.noctraos.dev/releases/v0.3.0/` (also reachable as files.dazeb.dev/releases/v0.3.0/).
The old unattended test ISO was removed from the bucket. ISOs older than #17, wherever they sit, are
stale: do not use them.

**Done:** step 5: `v0.3.0` is tagged on the PR #28 merge commit (d6ef42b) and the GitHub release (links and
checksums only) is published. A full interactive install of the release ISO, the welcome while
provisioning is still running, and real hardware are still untested.

## 1. Rebuild the ISOs (about 5 minutes)

```bash
iso/build-local.sh /run/media/dazeb/2tb/noctraos-build both
```

Builds from a fresh clone of GitHub `main` in a privileged container (ext4 image file on the
2 TB drive; see the header of the script for why). It fails if the release ISO contains a seed or
an unattended boot entry. Outputs in `out/`:

- `noctraos-0.3.0-amd64.iso` + `.sha256`: the release installer. **This is what gets published.**
- `noctraos-0.3.0-appliance-build.iso`: unattended, user `noctraos`/`noctraos`, autologin,
  passwordless sudo. Only a means to build the VM disk. **Never publish it.**

## 2. Test the release ISO from scratch (this is the part nobody has seen)

The welcome app running **while first-boot provisioning runs** (`--provisioning`) has only been
reviewed, never run. Use the appliance ISO for the unattended path:

```bash
export VM_DIR=/mnt/nvme1/noctraos-vm            # ext4, not NTFS
iso/local-vm.sh stop; rm -f $VM_DIR/disk.qcow2 $VM_DIR/vars.fd
VM_DISK_SIZE=64G iso/local-vm.sh start /run/media/dazeb/2tb/noctraos-build/out/noctraos-0.3.0-appliance-build.iso
iso/local-vm.sh shot /tmp/s.png                 # look at it; the installer slideshow, then a reboot
```

The installer takes about 5 minutes and reboots into the installed system, which autologins and
starts provisioning (25 to 40 minutes: Ollama model, Flatpaks, Hermes Electron build). Things to
look at with `shot`/`click`, none verified yet:

- The welcome opens during provisioning, shows the "Setting up your AI workstation in the
  background" status line, and the Windows+Space screen can be tried at once (the ISO bakes the
  Shell extensions in; if it says "after setup and a new sign-in", the bake did not work). Both Hermes buttons stay disabled
  until module 11 finishes. Skipping/finishing must NOT write `~/.config/noctraos/welcome-done`
  when the shortcut could not be tried.
- The first session already has Super+Space and the Start panel (`gnome-extensions info
  noctraos-search@noctraos.local` says ACTIVE before provisioning ends), with no sign-out needed.
- "Meet Hermes (free, uses the Nous cloud)" starts Hermes on the free tier; "Hermes, local only"
  starts it on the local model (this one was verified).
- Provisioning finished: `iso/local-vm.sh ssh 'test -f ~/.local/share/noctraos/.provisioned && noc doctor'`.

The interactive release ISO cannot be installed unattended. Boot it to the installer screen to
confirm it starts ("Try or Install NoctraOS"): `iso/local-vm.sh start <release iso>` on a fresh
disk. A full interactive install by hand is still untested.

## 3. Build the downloadable VM disk

Use the VM from step 2 once provisioning has finished and **before** launching Hermes in it (a
launch mints the Nous free-tier identity; the sysprep removes it anyway, but do not rely on that).

```bash
iso/local-vm.sh scp iso/vm-sysprep.sh
iso/local-vm.sh ssh 'sudo NOCTRAOS_SYSPREP_YES=1 bash /tmp/vm-sysprep.sh noctraos'   # refuses bare metal
iso/local-vm.sh ssh 'sudo poweroff'; sleep 15; iso/local-vm.sh status                  # not running
cd /run/media/dazeb/2tb/noctraos-build/out
qemu-img convert -p -O qcow2 -c $VM_DIR/disk.qcow2 noctraos-0.3.0.qcow2
qemu-img convert -p -O vmdk -o subformat=streamOptimized $VM_DIR/disk.qcow2 noctraos-0.3.0.vmdk
sha256sum noctraos-0.3.0.qcow2 noctraos-0.3.0.vmdk noctraos-0.3.0-amd64.iso > SHA256SUMS
```

The sysprep removes the machine id, SSH host keys (regenerated at first boot), the Hermes identity
and history, the welcome marker, logs and caches, and aborts if anything identifying is left.
**Boot-test the exported qcow2 once** (`VM_DIR=/tmp/x iso/local-vm.sh start` with that disk copied
in as `disk.qcow2`): it must autologin, show the welcome, and have a new SSH host key.
The image logs in as `noctraos`/`noctraos` with autologin and passwordless sudo. That is on
purpose (the GDM greeter is broken on this base, see AGENTS.md) and must be stated on the download
page: it is a trial appliance, change the password.

## 4. Upload to files.dazeb.dev (stable names)

`~/.hermes/skills/media/r2-file-upload/scripts/r2-upload.sh` adds a random suffix, wrong for a
release. Use rclone with the same credentials, never printing them:

```bash
set -a; source ~/secrets/cloudflare-r2.env; set +a
export RCLONE_CONFIG_R2_TYPE=s3 RCLONE_CONFIG_R2_PROVIDER=Cloudflare \
  RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
  RCLONE_CONFIG_R2_ENDPOINT="$R2_ENDPOINT"
for f in noctraos-0.3.0-amd64.iso noctraos-0.3.0.qcow2 noctraos-0.3.0.vmdk SHA256SUMS; do
  rclone copyto "$f" "r2:$R2_BUCKET/releases/v0.3.0/$f" -P
done
# public: https://files.dazeb.dev/releases/v0.3.0/<file>   (world-readable; verify with curl -I)
```

Uploading is public and cannot be recalled once cached, so inspect first (step 1's checks, a boot
test) and confirm with the user if anything changed. GitHub release assets are capped at 2 GiB
and the ISO is 3.7 GiB, so the files live here and the GitHub release links to them.

**Already public and should come down** (ask the user, then `rclone deletefile`):
An earlier test upload at the bucket root,
`unattended-test-noctraos-18-1-amd64-20261004-191534-18f5.iso`. It is the old unattended test build: autologin, passwordless sudo, the throwaway
password `zorin-test-2026`, and an unattended boot entry that wipes the disk.

## 5. Tag, release, website

```bash
git tag -a v0.3.0 -m "NoctraOS 0.3.0" origin/main && git push origin v0.3.0     # tag the commit you built from
gh release create v0.3.0 --title "NoctraOS 0.3.0" --notes-file notes.md          # links + sha256 only, no assets
```

Then a PR updating `site/download.html` (the "Not yet published" row, file sizes, checksums, the
VM disk with its credentials) and `README.md` (download links), merged like the others. The
`site/` directory deploys with `wrangler.jsonc`: Cloudflare builds it automatically whenever
GitHub `main` is updated, so merging the PR publishes the site.

## Cleanup

- Local: `iso/local-vm.sh stop`, delete `$VM_DIR/disk.qcow2` when done;
  `/run/media/dazeb/2tb/noctraos-build/work.img` (40 GB sparse) can be deleted any time.
- Proxmox node: VM 115 `noctraos-release-test` (stopped, mine) and the files in
  `/local-zfs/noctraos-isos/template/iso/` are all stale; `qm destroy 115 --purge` and delete them
  when the user agrees. Do not touch VMs 107, 108, 113, 114 (rule 9 in AGENTS.md).

## Known open items (not blockers unless you decide so)

- Welcome: prefilled search examples (needs a D-Bus `Open(query)` on the search extension) and
  the provisioner log panel are not built; `docs/onboarding.md` says so.
- The Software Updater still pops up on first login (about 700 MB of updates), but no longer in Zorin wording:
  `configs/gsettings/90_noctraos-updates.gschema.override` turns off update-manager's first-run sentence, which
  Zorin's patched package hardcodes as "Zorin OS".
- `noctraos-appearance` fonts: the interface font setting (`Cantarell 11`) is not what the theme
  actually renders (Inter), so changing it may not visibly change the shell. Verify before promising.
- Vim cannot be removed (Zorin's `zorin-os-minimal` depends on it); its launcher is hidden.
