# GNOME desktop code (flavour: zorin)

Code that only runs on the GNOME desktop: the GNOME Shell extensions, gsettings and dconf
settings, the Nautilus scripts, the GNOME theme, and the Super+Space and Start-button install.

Rules:
- Every module here declares `# desktops: gnome` on line 2 and calls `desktop_is_gnome`. When it
  is skipped it prints `NOT APPLIED`, never a success line.
- Nothing here names Kubuntu, Plasma, KDE or KWin.
- Changes here need the code owner's review (`.github/CODEOWNERS`).

Status: modules 01_desktop_packages, 04_desktop_apps, 05, 06, 07_nautilus_skel, 08 and 09 live here.
`install.sh` runs them through `run_desktop_module`; `install.sh --only 09_super_search.sh` still works by bare name.
