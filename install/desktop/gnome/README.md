# GNOME desktop code (flavour: zorin)

Code that only runs on the GNOME desktop: the GNOME Shell extensions, gsettings and dconf
settings, the Nautilus scripts, the GNOME theme, and the Super+Space and Start-button install.

Rules:
- Every module here declares `# desktops: gnome` on line 2 and calls `desktop_is_gnome`. When it
  is skipped it prints `NOT APPLIED`, never a success line.
- Nothing here names Kubuntu, Plasma, KDE or KWin.
- Changes here need the code owner's review (`.github/CODEOWNERS`).

Status: empty. Modules 05, 06, 08 and 09 still live in `install/` and will move here in a
separate change.
