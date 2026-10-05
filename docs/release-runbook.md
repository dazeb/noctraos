# Release runbook: NoctraOS 0.3.0

Written 2026-10-05 as a handoff. Read `AGENTS.md` first (rules, pitfalls). This file is the
ordered list of what is left to ship 0.3.0 and exactly how. Everything below was done by hand
once; the scripts named here exist so you do not have to repeat the discovery.

## Where things stand

Done and on `main`: the Hermes Desktop module (`install/11_hermes.sh`, runs last), the onboarding
prompt, the release/unattended split in the ISO build (a release ISO has no seed and no
unattended boot entry), the `VERSION` file (0.3.0) and ISO labelling, `iso/vm-sysprep.sh`.

In PR #17 (`audit/apps`; merged by the time you read this, check `git log origin/main`): the
app policy (`install/04c_app_policy.sh`), the NoctraOS welcome (`bin/noctraos-welcome`) replacing
Zorin's tour, `bin/noctraos-appearance`, `noctraos-hermes local|ready`, the preflight relaxation.

**Stale, do not use:** every ISO currently in `/run/media/dazeb/2tb/noctraos-build/out/` and on the
Proxmox node was built from `main` BEFORE #17 and has none of the above. Rebuild.

**Not published yet, nothing tagged:** no `v0.3.0` tag, no GitHub release, the website still says
"Not yet published".

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
  background" status line, and the Windows+Space screen says it works after setup and a new
  sign-in (the search extension is not loaded in that session). Both Hermes buttons stay disabled
  until module 11 finishes. Skipping/finishing must NOT write `~/.config/noctraos/welcome-done`
  when the shortcut could not be tried.
- After provisioning, log out and in: the welcome returns once, the shortcut works.
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
`site/` directory deploys with `wrangler.jsonc`; check how before merging a change to it.

## Cleanup

- Local: `iso/local-vm.sh stop`, delete `$VM_DIR/disk.qcow2` when done;
  `/run/media/dazeb/2tb/noctraos-build/work.img` (40 GB sparse) can be deleted any time.
- Proxmox node: VM 115 `noctraos-release-test` (stopped, mine) and the files in
  `/local-zfs/noctraos-isos/template/iso/` are all stale; `qm destroy 115 --purge` and delete them
  when the user agrees. Do not touch VMs 107, 108, 113, 114 (rule 9 in AGENTS.md).

## Known open items (not blockers unless you decide so)

- Welcome: prefilled search examples (needs a D-Bus `Open(query)` on the search extension) and
  the provisioner log panel are not built; `docs/onboarding.md` says so.
- The Software Updater pops "Updated software has been issued since Zorin OS 18 was released"
  (717 MB) on first login, in Zorin wording. Not addressed.
- `noctraos-appearance` fonts: the interface font setting (`Cantarell 11`) is not what the theme
  actually renders (Inter), so changing it may not visibly change the shell. Verify before promising.
- Vim cannot be removed (Zorin's `zorin-os-minimal` depends on it); its launcher is hidden.
