# KDE Plasma desktop code (flavour: kubuntu)

Code that only runs on the Plasma desktop: the Plasma panels and layout, KRunner and the
Super+Space binding, Kickoff, the Breeze theme, and Plasma settings written with kwriteconfig6.

Rules:
- Every module here declares `# desktops: plasma` on line 2 and prints `NOT APPLIED` when it
  cannot apply on the running desktop.
- Nothing here names Zorin or GNOME.
- Changes here need the code owner's review (`.github/CODEOWNERS`).

Status: modules 01_desktop_packages, 04_desktop_apps, 05_mouse_ergonomics, 06_desktop_theme and 07_nautilus_skel (it keeps
the name module 07 calls; it seeds the Dolphin actions) are written and unit-tested (tests/test_plasma_desktop.py), not yet
run in a Plasma session. 08 (SDDM theme) and 09 (Super+Space, phase 5) have no Plasma counterpart, so `install.sh` prints
`NOT APPLIED` for them. The colour scheme and Konsole files in configs/plasma are rendered from configs/theme/palette.json
by scripts/render-theme.py.
