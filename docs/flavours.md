# NoctraOS flavours

Status updated 2026-10-14; flavour direction agreed 2026-10-10. Read this before changing anything that differs by desktop or
base: `install/05` to `09`, `install/desktop/`, `install/lib.sh` desktop guards, `iso/`, `branding/`,
`extensions/`, the release pipeline, the update channel, or any doc that describes what the user sees.

## What we are doing

NoctraOS is **one product**: the same name, version and command set, with feature parity as the goal, shipped in
**flavours**. A flavour is one supported build: an upstream base, one desktop, and its own ISO pipeline.
The base and the desktop are implementation choices. The product stays the same.

| Flavour id | Base | Desktop | Status |
|---|---|---|---|
| `zorin` | Zorin OS 18.1 (Ubuntu 24.04) | GNOME | shipped, including 0.5.0; recommended download |
| `kubuntu` | Kubuntu 26.04 (Ubuntu 26.04) | KDE Plasma 6 | preview from 0.5.0 (released beside zorin, labelled preview) |

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
- Flatpak and AppImage prerequisites (`install/01_system.sh`): the same packages on every flavour. That
  means FUSE 2 and FUSE 3 for AppImages, and all four desktop portal backends (GTK, GNOME and KDE, plus the
  portal itself), so no flavour chooses a portal by desktop. Flatpak apps bring their own runtimes, so the
  desktop does not change which apps run; it only changes the file dialogs and theme integration.
  The cost is paid on the GNOME flavour: on Zorin (noble) the KDE portal backend adds 74 packages and about
  95 MiB (`kio`, `kded5`, the KWallet libraries), and nine KDE D-Bus services become activatable, none of them
  running. GNOME still routes to its own backends (`gnome-portals.conf`) and the Secret portal stays pinned to
  gnome-keyring. Measured on a fresh Zorin install, 2026-10-10. If this ever bites (for example a Qt app starting
  `kwalletd5`), the fix is a per-flavour portal list once the flavour file exists.
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
2. Does it touch GNOME desktop gsettings, dconf, `gnome-shell`, Nautilus or Zorin names? Then it is GNOME desktop code:
   `install/desktop/gnome/`, or a module with header `# desktops: gnome`.
3. Does it touch `kwriteconfig6`, `plasma*`, KWin, KDE or Dolphin? Then it is Plasma desktop code:
   `install/desktop/plasma/`, or a module with header `# desktops: plasma`.
4. Does it touch the ISO, a base's installer, the boot chain or the release? Then it goes in
   `iso/flavours/<id>.sh` (planned). Never add a flavour `if` inside `iso/build-noctraos-iso.sh`.
5. Does it describe the product in a doc? Shared text says NoctraOS. Base names appear only in the base
   sections.

The legacy `org.gnome.shell.extensions.noctraos-search` GSettings schema is a
narrow shared exception to rule 2. It stores search sources, index roots and
web-provider preferences for both desktops, not GNOME desktop settings. Keep
browser history opt-in. This exception does not permit GNOME Shell extensions
or other GNOME desktop schemas in a Kubuntu bundle.

Module headers: a module that depends on the desktop declares it on its second line:
`# desktops: any`, `# desktops: gnome` or `# desktops: plasma`. On a desktop it does not support, it prints
`NOT APPLIED on this desktop: <what>` and exits 0. It never prints a success line for work it skipped. A lint
check to enforce the header is planned, not written yet.

Desktop detection: `desktop_is_gnome()` in `install/lib.sh` is a guard, not a selector. The flavour is
selected from the flavour file (below), never from `XDG_CURRENT_DESKTOP`, which is unset over SSH.

Flavour file: `/etc/noctraos/flavour` contains `zorin` or `kubuntu`. The kubuntu ISO script writes it (`kubuntu`); the Zorin remaster does not yet; module 07 writes it once when `install.sh` was given `NOCTRAOS_FLAVOUR` and the file is missing. A machine
with no file was installed before flavours existed, so it is `zorin`, and nothing is written for that default.
`noctraos_flavour` in `install/lib.sh` resolves it (file, else `NOCTRAOS_FLAVOUR`, else `zorin`) and refuses a variable that
contradicts the file or an unknown value; `install.sh` exports the result as `NOCTRAOS_FLAVOUR`. `bin/noc-selfupdate` reads
the same file to pick the machine's update channel (`docs/updates.md`) and passes `NOCTRAOS_FLAVOUR` to migrations; a
migration for one flavour prints `NOT APPLIED on the <flavour> flavour` on the others and exits 0.

## Current state of the code (2026-10-14)

Taken from the repo and the VM runs. Not every item has been verified on a VM.

- **Desktop-only, now in `install/desktop/gnome/`:** `01_desktop_packages`, `04_desktop_apps`, `05_mouse_ergonomics`,
  `06_desktop_theme`, `07_nautilus_skel`, `08_shell_theme`, `09_super_search`. `install.sh` runs them with
  `run_desktop_module`; a flavour without that file prints `NOT APPLIED`. Still at the top level because update bundles
  and the ISO bake list them: `branding/setup-branding.py` and the three GNOME Shell extensions under `extensions/`.
- **Core modules that still contain GNOME/Zorin-coupled lines** (split or guard them before a Plasma release):
  `04_gui_apps` (the gnome-keyring restart) and `04c_app_policy` (Zorin package removals and launcher hides). The ISO
  remaster is still `iso/build-noctraos-iso.sh`, not yet `iso/flavours/zorin.sh`. `lib.sh` has the one allowed desktop guard.

Published 0.5.0 Kubuntu artifacts still lack the new Super+Space search and the
AI-first Start categories. The working code now has Plasma module 09: Meta+Space
opens KRunner, stock KRunner supplies apps, and the shared backend supplies files,
CopyQ, opt-in browser history and web search. On 2026-10-14, the local Kubuntu VM
test covered key activation, fixture results, Enter opening Kate, shortcut
persistence after reboot and an idempotent setup rerun. No new Zorin runtime test
is claimed by this test. The AI-first Kickoff Start categories are not implemented.
Broad theme acceptance and real hardware remain untested.

**Interactive Calamares install (2026-10-24, local KVM, a release ISO built from
main).** English (US), a user, erase disk, Next through to "All done", then SDDM
and a Plasma login all worked. First-boot provisioning did not: the autostart
entry used `Terminal=true`, which Plasma 6 ignores (it starts autostart through
`systemd-xdg-autostart-generator`), so the runner had no TTY and its first `sudo`
could not ask for the password. **The published 0.5.0 Kubuntu release ISOs have
this bug**; an interactive install from them ends at a bare Kubuntu desktop until
`/usr/local/sbin/noctraos-firstboot` is run by hand in Konsole. Fixed on main
(`kubuntu_firstboot` now opens Konsole itself; the Zorin entry is unchanged, GNOME
honours `Terminal=true`). With the fix applied to the installed system, the run
went through to "setup complete" in about 10 minutes: `noc doctor` all OK except
the Flatpak security row (Kubuntu 26.04 ships Flatpak 1.16.6), Meta+Space search
returned application results, and after a reboot the NoctraOS panel layout and
wallpaper were in place (the layout shows from the next login, not the first
session). The fixed ISO has not been rebuilt and installed again, so the fix is
verified on the installed system, not on a fresh image. Other things seen and not
fixed: the live-session welcome and Plymouth still show stock Kubuntu branding,
the root filesystem label is `kubuntu_2604`, the installer's final slide mentions
an Agents Start menu that the Plasma flavour does not have, and the keyboard
defaults to UK until chosen.

System and user search migrations are in the working tree for existing Kubuntu
systems to receive search through an optional signed update. Publication
scripts take an explicit `--flavour` and the CI has per-flavour jobs. On 2026-10-24 Kubuntu update 1 (this search) was published on the **nightly** channel only (`updates/kubuntu/nightly/`, relogin flagged); `stable` has no Kubuntu manifest yet. It was applied through the real updater on a VM booted from the published 0.5.0 Kubuntu image: both migrations ran, Meta+Space was assigned, `noc doctor` showed the search row OK, the KRunner runner answered over D-Bus, and a rerun was a no-op.
Not yet done: promotion to `stable`, and no real-desktop (interactive) check of the update prompt.

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

## Status matrix (2026-10-14)

| Component | zorin | kubuntu |
|---|---|---|
| Core provisioner | shipped | earlier 26.04.1 VM run returned 0; the Oct 14 search test is not a full provisioner rerun |
| Optional local Ollama, 11 Hermes | shipped | no new runtime acceptance claimed by the Oct 14 search test |
| 05 mouse ergonomics | shipped (Nautilus scripts) | written (Dolphin right-click actions through `noctraos-fileaction`); interactive action acceptance not established by the search test |
| 06 desktop theme | shipped | written: colour scheme, Konsole profile, wallpapers, Agents section, panel layout; broad interactive acceptance remains untested |
| 08 shell theme | shipped | written: Global Theme `dev.noctraos.desktop` (splash, previews, layout), wallpaper packages, SDDM login screen, lock-screen picture, About this System, NoctraOS logo on Kickoff (`configs/plasma/install-look.sh`, also baked into the ISO); unit-tested and splash rendered offscreen with Qt 6; broad interactive acceptance remains untested; AI-first Kickoff Start categories are not implemented |
| 09 Super+Space and Start | shipped (GNOME Shell extensions) | working module 09 and KRunner runner; local VM search scope above passed; published 0.5.0 still lacks search; AI-first Kickoff Start categories are not implemented |
| Login and boot | shipped | local Kubuntu VM search shortcut persisted after reboot on Oct 14; broader login and boot visual acceptance not established by that test |
| ISO build | remaster script (`iso/build-noctraos-iso.sh`) | `iso/flavours/kubuntu.sh` builds release and appliance ISOs; appliance uses `kubuntu/autoinstall.sh` (Oct 12 local KVM test installed, rebooted into SDDM autologin and Plasma, and started first-boot provisioning); working remaster includes search files; no rebuilt release-ISO search acceptance claimed; interactive Calamares install run 2026-10-24: installs and boots, first-boot setup bug found and fixed on main, fixed ISO not yet rebuilt |
| Release pipeline and update channel | release pipeline wired; existing legacy update paths retained | 0.5.0 preview published; client reads `kubuntu/<channel>/`; publisher takes `--flavour`, Kubuntu CI jobs exist; update 1 (search, with system and user migrations) is on the `kubuntu/nightly` channel since 2026-10-24 and was applied on a 0.5.0 VM; `kubuntu/stable` has no manifest yet |
| Control Panel | shipped | runs on GTK3; not verified on Plasma |
