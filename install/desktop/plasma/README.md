# KDE Plasma desktop code (flavour: kubuntu)

Code that only runs on the Plasma desktop: the Plasma panels and layout, KRunner and the
Super+Space binding, Kickoff, the Breeze theme, and Plasma settings written with kwriteconfig6.

Rules:
- Every module here declares `# desktops: plasma` on line 2 and prints `NOT APPLIED` when it
  cannot apply on the running desktop.
- Nothing here names Zorin or GNOME.
- Changes here need the code owner's review (`.github/CODEOWNERS`).

Status: empty. The Plasma port is planned and has no modules yet.
