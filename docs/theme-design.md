# NoctraOS-Dark: Omarchy design reference

The main design follows [Omarchy's Matte Black palette](https://github.com/basecamp/omarchy/blob/8b4eae66da2938ba9559f103b18dbf85cdf28a70/themes/matte-black/colors.toml)
and coordinated theme model, adapted to Zorin OS 18.1 and GNOME. This is the
starting reference, not a replacement compositor or a copy of Omarchy branding.

## Design decisions

| Element | Decision |
| --- | --- |
| Canvas | `#121212` charcoal |
| Panels | `#0d0d0d`; raised controls `#1e1e1e` |
| Selection | `#2a2a2a` with readable foreground text |
| Borders | `#333333`, 1 px; amber only for focus/active controls |
| Text | `#bebebe`; secondary text `#8a8a8d` |
| Accent | `#e68e0d` amber; dark text on solid accent buttons |
| Typography | JetBrainsMono Nerd Font in the shell, terminal, and editor; GTK retains application fonts |
| Geometry | 0 px corners everywhere (sharp); menu rows retain mouse-friendly padding |
| Identity | Existing AI menu sections, white glyphs, and polygon wallpapers |

The desktop uses Omarchy's palette roles. Terminal ANSI colors remain distinct
from application status semantics: Matte Black uses amber/yellow for several
ANSI roles, so a terminal color named `green` is not a success indicator.

## Implemented first pass

- Shell: taskbar, menus, search, quick settings, sliders, notifications,
  dialogs, overview, and scrollbars.
- GTK: headers, buttons, inputs, menus, popovers, selections, checks, switches,
  progress indicators, and scrollbars.
- Apps: Microsoft VS Code defaults, GNOME Terminal, Herdr, and btop.
- Persistence: VS Code settings, Continue configuration, app themes, and the
  renamed Nautilus action are provided for new accounts.

`configs/theme/palette.json` is the source for colors, terminal ANSI values,
the monospace font, and corner radius. CSS templates live next to it. Run:

```sh
python3 scripts/render-theme.py
python3 scripts/render-theme.py --check
python3 -m unittest discover -s tests -v
```

The generated files are committed so installation needs no design tools or
network theme downloads. `scripts/build-desktop-theme.py` combines these
overrides with the installed Zorin base and changes only differing files.
The original system themes are never patched in place.

## Settings and migration

The GUI module installs VS Code first, then removes installed apt packages
`codium`, `chatbox`, `xyz.chatboxapp.app`, and `foot` without purging settings or
running autoremove. The retired VSCodium menu action is removed from the current
user and `/etc/skel`. GNOME Terminal remains the workstation terminal.

Existing VS Code settings are kept verbatim, including JSONC comments and
custom colors. They are not silently replaced with theme defaults. VSCodium
settings remain on disk for manual import into VS Code. Existing Herdr settings
are updated only if they exactly match the previous installer default.

## Remaining surfaces and limits

Libadwaita, Qt, Flatpak, Snap, and apps with internal themes may not adopt GTK
overrides. This pass does not force `GTK_THEME`, write global user GTK CSS,
change GDM, or modify Zorin extensions. It also does not install Foot, Hyprland,
SDDM, Quickshell, or Omarchy's theme switcher.

The first pass includes selectors from the installed Zorin menu and taskbar.
Next passes should review their remaining states, add app-specific Qt/Flatpak
integration where supported, and review
wallpapers against the calmer desktop. Shell/menu changes need a new session.

Before a release, verify the installer twice on a test VM (`iso/local-vm.sh`, or VM 114),
reboot and inspect the session, then rebuild and boot-test the ISO from the published
repository (see the [release runbook](release-runbook.md)).

## Validation — 2026-09-30 (historical)

The first-pass check, kept for the record; the later coverage table below is the current state.

- Bash syntax, Docker ShellCheck at warning severity, JSON/TOML parsing, palette
  output consistency, and four theme-composition regression tests passed.
- Two full installer passes completed on VM 114. VS Code 1.139.1 and the five
  configured extensions installed; VSCodium and Chatbox were removed. Foot was
  already absent. The new desktop ID is pinned and the Nautilus action is renamed.
- All 433 checked base-theme, custom-theme, and user configuration files retained
  their contents and timestamps on the second full pass. The final CSS refinement
  also produced no changes on its second theme-module pass.
- GTK 3 and GTK 4 reported no CSS parsing diagnostics. After reboot, GNOME Shell
  loaded NoctraOS-Dark without theme-parser errors; the menu and terminal were
  inspected. `noc doctor` was green.
- The reference VM was restored after testing. (This pass has since been published and
  is part of the current ISO build.)

![NoctraOS menu and terminal with the Omarchy-inspired theme](screenshots/noctraos-matte-black.png)


## Coverage, 2026-10-04

Checked on VM 114 by screenshot unless noted. The shell and GTK stylesheets are
recoloured from the installed Zorin themes to this palette at build time
(`configs/theme/shell-remap.json`, `gtk-remap.json`), corners are 0 px, and the icon
theme is Zorin's own `ZorinGrey-Dark`.

| Surface | State |
|---|---|
| Top bar, quick settings, calendar and notifications | Done |
| Dock, Start panel, Super+Space overlay | Done |
| Overview background | Done (dark with a dot grid); the workspace preview still has rounded corners drawn by the shell |
| Files, Settings, Text Editor, GTK dialogs | Done: neutral dark, sharp, quiet amber selection marker |
| GNOME Terminal, btop, Herdr | Done (palette) |
| VS Code | Dark and neutral; link, badge and progress colours now in the generated defaults, but existing accounts keep their old settings |
| Wallpapers | The purple neon set stays. Added `ember-night` (near-black facets, low amber sun) to the generator and the rotation (`noc bg`); better ones still welcome |
| Desktop folder icon | Done: a small derived icon theme, `NoctraOS` (inherits `ZorinGrey-Dark`), replaces the cyan PNG from Zorin's base set with a grey SVG; more overrides can be added under `assets/icons/noctraos-theme/` |
| **Dock app icons** | Brand icons (VS Code blue, Brave/Chromium) stay as the apps ship them |
| **Lock screen** | Gap, and not fixable from our extensions or user theme: GNOME 46 draws it with the *stock* shell theme because extensions and the user-theme are off in the lock session. It shows the blurred desktop wallpaper (the `screensaver picture-uri` setting is not used). Styling it means replacing the system shell theme resource (which also themes the GDM greeter) — doable but if the resource is broken the session will not start, so it needs a snapshot and a deliberate step |
| **Login screen (GDM)** | Gap: unthemed, and the greeter is broken on Zorin 18.1 (autologin is used) |
| Boot splash (Plymouth) | Done in the repo: dark `two-step` theme with the N mark, `noctraos` wordmark and a blinking cursor (`assets/boot/plymouth/noctraos`). Baked into the ISO's live initrd, the squashfs and, via module 10, any other install. Rendered and checked here with the x11 renderer and on a booted ISO under QEMU; not yet seen on real hardware or the installed system after a reboot |
| GRUB menu (UEFI ISO and installed system) | Done in the repo: flat dark menu, JetBrains Mono, square frame, amber selection bar, text countdown (`assets/boot/grub/noctraos`). Checked on a booted ISO under QEMU/OVMF at 800x600 only; other resolutions and a real installed GRUB are unchecked |
| ISO BIOS boot menu (isolinux) | Done in the repo: same palette, header lockup, amber selection. Checked under QEMU/SeaBIOS |
| Installer and live session | Done in the repo and seen under QEMU: the live session defaults to `ZorinGrey-Dark` and the ember-night wallpaper (a gschema override that repeats Zorin's `:zorin` groups), the first page reads "Try / Install NoctraOS" (the build now rewrites `.disk/info` correctly) with new pictures, and the slideshow is one dark Super+Space slide. **Still Zorin's:** the live session's top bar (light grey, it comes from the Zorin Taskbar, not the theme) and the translated installer strings. The later installer pages were not looked at |
| Flatpak and Electron apps (Mission Center, Obsidian, Chromium, Hermes Desktop) | Follow their own styling; Mission Center looked neutral dark, others unchecked |
| NoctraOS Welcome and Appearance windows | Done: GTK 3 windows with their own palette CSS (charcoal, amber keycap and focus). They use a 2 px radius rather than 0, which should be brought in line with the shell |
| Radio buttons and avatars | Left circular on purpose (affordance) |
| Cursor | Stock Adwaita |
| Super+Space overlay | Reference surface for the theme. Uses a 2 px radius and a soft shadow, where the Start panel and shell use 0 px |
