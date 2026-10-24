# KDE Plasma desktop code (flavour: kubuntu)

Code that only runs on the Plasma desktop: the Plasma panels and layout, KRunner and the
Super+Space binding, Kickoff, the Breeze theme, and Plasma settings written with kwriteconfig6.

Rules:
- Every module here declares `# desktops: plasma` on line 2 and prints `NOT APPLIED` when it
  cannot apply on the running desktop.
- Do not apply GNOME desktop settings here. The legacy-named
  `org.gnome.shell.extensions.noctraos-search` GSettings schema is a narrow
  exception: it stores shared search sources, index roots and web-provider
  preferences, not desktop settings. Browser history stays opt-in.
- Changes here need the code owner's review (`.github/CODEOWNERS`).

Status as of 2026-10-14: modules 01_desktop_packages, 04_desktop_apps, 05_mouse_ergonomics, 06_desktop_theme, 07_nautilus_skel (it keeps
the name module 07 calls; it seeds the Dolphin actions) and 08_shell_theme are written and unit-tested
(tests/test_plasma_desktop.py). Broad interactive theme acceptance is still untested. 08 runs `configs/plasma/install-look.sh /`: the Global Theme
`dev.noctraos.desktop` (splash, previews, panel layout), wallpaper packages, the SDDM login screen (Breeze with our
background and logo), the lock-screen picture, the splash default and "About this System"; the kubuntu ISO build runs the
same script on the squashfs. Module 09 now installs the shared search backend, index timer, search settings schema,
KRunner D-Bus runner and once-per-account Meta+Space shortcut through `configs/plasma/apply-search.sh`.
Stock KRunner handles application results; the shared backend handles files, CopyQ, opt-in browser history and web search.
The local Kubuntu VM test on 2026-10-14 covered key activation, fixture results, Enter opening Kate,
shortcut persistence after reboot and an idempotent setup rerun. This does not establish broad theme acceptance,
interactive Calamares installation or real-hardware coverage. The AI-first Kickoff Start categories are not implemented.
Published 0.5.0 Kubuntu images still lack the new search. System migration `0002_install_plasma_search.sh` and user
migration `0003_setup_plasma_search.sh` are delivered by Kubuntu update 1, on the nightly channel since 2026-10-24 (not yet on stable).
The artwork is rendered by scripts/render-kubuntu-branding.py into
assets/plasma and assets/boot/calamares. The colour scheme and Konsole files in configs/plasma are rendered from configs/theme/palette.json
by scripts/render-theme.py.
