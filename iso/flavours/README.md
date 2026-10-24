# Base ISO scripts, one per flavour

One file per flavour, named by its id: `zorin.sh` and `kubuntu.sh`. Each defines its base ISO,
its installer, its boot chain and its rebrand steps. Build steps shared by every flavour stay in
`iso/`.

Rules:
- Only `zorin` and `kubuntu` are valid file names. `tests/test_flavour_layout.py` enforces this.
- A flavour's helper files go in a folder named by its id (`kubuntu/autoinstall.sh`), never beside the flavour scripts.
- Never add a flavour `if` inside `iso/build-noctraos-iso.sh`. Shared helpers only.
- Changes here need the code owner's review (`.github/CODEOWNERS`).

Status: `kubuntu.sh` is the Kubuntu 26.04.1 remaster. The release ISO installs with Calamares. Calamares has no
unattended mode, so the appliance ISO (`NOCTRAOS_UNATTENDED=1`, the source of the VM disks) boots into
`kubuntu/autoinstall.sh` instead, which repeats Calamares' steps. It is a script you run (`sudo iso/flavours/kubuntu.sh <base.iso> [out.iso]`,
or `NOCTRAOS_FLAVOUR=kubuntu iso/build-local.sh <dir>`) and, when sourced, only defines functions (`tests/test_kubuntu_iso.py`).
The first-boot runner text is shared (`iso/firstboot-runner.sh`; a test pins it to the Zorin script's copy). The Zorin remaster is
still `iso/build-noctraos-iso.sh` and moves here in a separate change.

As of 2026-10-14, published 0.5.0 Kubuntu artifacts remain a preview without the
new Super+Space search. The working Kubuntu remaster now includes the KRunner
search files and Meta+Space setup. The working port was tested in a local Kubuntu
VM for key activation, fixture results, Enter opening Kate, shortcut persistence
after reboot and an idempotent setup rerun. That test does not verify a rebuilt
release ISO, interactive Calamares installation, broad theme acceptance or real
hardware. The AI-first Kickoff Start categories are not implemented. See
[flavour status](../../docs/flavours.md) before describing an image as ready.
