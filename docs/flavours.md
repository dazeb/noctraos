# NoctraOS flavours

Status: agreed direction, 2026-10-10. Read this before changing anything that differs by desktop or
base: `install/05` to `09`, `install/desktop/`, `install/lib.sh` desktop guards, `iso/`, `branding/`,
`extensions/`, the release pipeline, the update channel, or any doc that describes what the user sees.

## What we are doing

NoctraOS is **one product**: the same OS, name, version, feature set and command set, shipped in
**flavours**. A flavour is one supported build: an upstream base, one desktop, and its own ISO pipeline.
The base and the desktop are implementation choices. The product stays the same.

| Flavour id | Base | Desktop | Status |
|---|---|---|---|
| `zorin` | Zorin OS 18.1 (Ubuntu 24.04) | GNOME | shipped (0.3.x, 0.4.0) |
| `kubuntu` | Kubuntu 26.04 (Ubuntu 26.04) | KDE Plasma 6 | in progress; no release |

## Vocabulary (use these words exactly)

- **NoctraOS**: the product. Never "Zorin edition" and never "Kubuntu fork".
- **flavour**: a supported build, named by its id (`zorin`, `kubuntu`). Used for artifacts, the flavour
  file, ISO scripts and release folders.
- **base**: the upstream distribution and its ISO. Zorin and Kubuntu are bases. Ubuntu is their common
  ancestor.
- **desktop**: the session environment (`gnome`, `plasma`). Used for module code and module headers. Each
  flavour has exactly one desktop today. A desktop could later be shared by two flavours.
- **core**: everything in the provisioner that is not desktop-specific.

## What must stay identical across flavours

- The product name, `VERSION` and release numbering.
- The `noc` CLI commands and the `--json` contracts (pinned by `tests/test_noc_cli.py`).
- The Control Panel pages and what they mean. The content can differ by desktop.
- The AI stack: Ollama and its model choices, Hermes and its disclosure rules (the free tier is a cloud
  service), and the agents menu list.
- Super+Space as the one shortcut, with the same results. The UI behind it can differ.
- The app set and the Flatpak-first policy (`install/04c_app_policy.sh`), except the exceptions a flavour
  documents below.
- Palette, wallpapers and visual direction (`configs/theme/palette.json`, `docs/theme-design.md`),
  implemented the way each desktop does it.
- Update rules: signed bundles, staged rollout and migrations.
- Privacy and security statements.

## What may differ (and must be listed in the flavour)

- The base ISO, its installer, and the boot chain (GRUB and Plymouth, or their equivalents).
- The login manager (GDM or SDDM) and its theme.
- The desktop shell and its settings, the panel or dock layout, the start menu, the file manager, and the
  GTK or Qt theme engine.
- How Super+Space is implemented: a GNOME Shell extension, or a KRunner runner bound to a KDE shortcut.
- Packages a base ships or lacks. Each flavour documents these.

## Where code goes

Decide in this order:

1. Does the change alter what a user sees on both flavours? Then it is shared code. Both flavours must be
   tested before the change is called done.
2. Does it touch gsettings, dconf, `gnome-shell`, Nautilus or Zorin names? Then it is GNOME desktop code:
   `install/desktop/gnome/` (planned), or a module with header `# desktops: gnome`.
3. Does it touch `kwriteconfig6`, `plasma*`, KWin, KDE or Dolphin? Then it is Plasma desktop code:
   `install/desktop/plasma/` (planned), or a module with header `# desktops: plasma`.
4. Does it touch the ISO, a base's installer, the boot chain or the release? Then it goes in
   `iso/flavours/<id>.sh` (planned). Never add a flavour `if` inside `iso/build-noctraos-iso.sh`.
5. Does it describe the product in a doc? Shared text says NoctraOS. Base names appear only in the base
   sections.

Module headers: a module that depends on the desktop declares it on its second line:
`# desktops: any`, `# desktops: gnome` or `# desktops: plasma`. On a desktop it does not support, it prints
`NOT APPLIED on this desktop: <what>` and exits 0. It never prints a success line for work it skipped. A lint
check to enforce the header is planned, not written yet.

Desktop detection: `desktop_is_gnome()` in `install/lib.sh` is a guard, not a selector. The flavour is
selected from the flavour file (below), never from `XDG_CURRENT_DESKTOP`, which is unset over SSH.

Flavour file (planned): the ISO writes `/etc/noctraos/flavour` containing `zorin` or `kubuntu`.
`install.sh` reads that file, or `NOCTRAOS_FLAVOUR` when it is set. A machine with no file was installed
before flavours existed, so it is `zorin`.

## Current state of the code (2026-10-10)

Taken from the repo and the VM runs. Not every item has been verified on a VM.

- **Desktop-only today:** `05_mouse_ergonomics`, `06_desktop_theme`, `08_shell_theme`, `09_super_search`,
  `branding/setup-branding.py`, and the three GNOME Shell extensions under `extensions/`.
- **Core modules that still contain GNOME-coupled lines** (split or guard them before a Plasma release):
  `01_system` (2 lines), `04_workstation_apps` (2), `04c_app_policy` (6, including Zorin package removals),
  `07_persistence` (5). `lib.sh` has the one allowed desktop guard.

## Rules for agents

1. Name the flavour in every commit title and PR, for example `[all]`, `[kubuntu]` or `[zorin]`. List the
   flavours a change was tested on, for example `Tested: zorin, kubuntu` or `Tested: zorin only; kubuntu not run`.
2. Never copy a fix from one desktop to another without the port. The other flavour gets its own change and
   its own test.
3. A shared change that touches a desktop module must say what the other flavour does with it.
4. "Works on Plasma" or "works on both" needs evidence for each flavour: a VM run, a log, or the words "not
   verified".
5. Shared modules contain no Zorin or Kubuntu branch. Desktop checks use the guards in `install/lib.sh`, not
   string matching inside a module body.
6. Skipped work is reported as `NOT APPLIED`, never as `OK`, `installed` or `complete`.
7. Keep warn-not-die for desktop settings. Core steps such as apt and Ollama may still die.
8. Each flavour has its own artifact names (`noctraos-<version>-<flavour>-amd64.iso`), its own folder in the
   release bucket and its own update channel. Never publish, overwrite or update one flavour's artifact from
   another flavour's build.
9. An update bundle carries only its flavour's items. A `kubuntu` machine never receives GNOME Shell items.
10. Experiments do not go in product directories. Investigations stay under `spike/`, or on their own branch,
    until a flavour decision is made.
11. Status reports to the user name the flavour and say what was not verified.
12. Product decisions are recorded only in `docs/objectives.md`. Update it when a flavour decision changes, and
    do not restate decisions in other docs.

## Wrong phrasing, and what to write instead

- "NoctraOS Zorin" or "the Zorin version" → "NoctraOS (zorin flavour)".
- "NoctraOS KDE" or "the Kubuntu version" → "NoctraOS (kubuntu flavour)".
- "works on Kubuntu" with no VM run behind it → "installs on Kubuntu; the desktop is not yet ported".

## Status matrix (2026-10-10)

| Component | zorin | kubuntu |
|---|---|---|
| Core provisioner: 00, 01, 02, 04, 04b, 04c, 04d, 07, 10 | shipped | ran on a 26.04.1 VM with return code 0; 01, 04b, 04c and 07 still contain GNOME-coupled lines |
| 03 Ollama, 11 Hermes | shipped | 03 and 11 not run |
| 05 mouse ergonomics | shipped (Nautilus scripts) | ran with return code 0, but it writes Nautilus scripts Dolphin never reads. It needs the `NOT APPLIED` guard |
| 06 desktop theme, 08 shell theme | shipped | report `NOT APPLIED`; the Plasma theme is not started |
| 09 Super+Space and Start | shipped (GNOME Shell extensions) | report `NOT APPLIED`; plan is a KRunner runner and Kickoff |
| Login and boot | shipped | SDDM greeter starts, and login reaches a Plasma session on the VM with virtio-vga-gl; the screen is not verified from the host |
| ISO build | remaster script | no build; the VM was installed by hand |
| Release pipeline and update channel | wired | not wired |
| Control Panel | shipped | runs on GTK3; not verified on Plasma |
