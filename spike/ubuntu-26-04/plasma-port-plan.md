# NoctraOS Plasma 6 port plan (Ubuntu 26.04 + kubuntu-desktop)

Status: plan only. Nothing was run on a Plasma session. This machine is Ubuntu 26.04 resolute with GNOME,
no KDE packages installed, so `kwriteconfig6`, `lookandfeeltool` and `plasma-apply-*` are not present
(`which` returned nothing). Every statement about KDE tool behaviour, config keys and file names below is
UNVERIFIED until run in a Kubuntu test VM (`iso/local-vm.sh`). Repo facts are cited as file:line.

## 0. Verified package facts (apt-cache policy / show, this machine)

| Package | Candidate | Note |
|---|---|---|
| kubuntu-desktop | 1.496 | meta; Depends include plasma-desktop, plasma-workspace, kwin-wayland, sddm, plasma-session-wayland, systemsettings, kubuntu-settings-desktop, breeze, plymouth-theme-breeze, xdg-desktop-portal-gtk, xdg-desktop-portal-kde |
| plasma-desktop / plasma-workspace | 4:6.6.6-0ubuntu0.1 | archive has 6.6.6 (the task said 6.6.4; 6.6.4 is the older pocket) |
| kwin-wayland / kwin-x11 | 6.6.6 / 6.6.4 | Wayland is the default session |
| breeze, kde-style-breeze, breeze-cursor-theme | 6.6.5 | |
| plasma-desktoptheme | 6.6.6 | Plasma (shell) themes incl. Breeze |
| kf6-breeze-icon-theme | 6.24.0 | `breeze-icon-theme` 5.116 is a transitional dummy |
| breeze-gtk-theme, kde-config-gtk-style | 6.6.4 | GTK apps follow the Plasma colour scheme |
| libkf6config-bin | 6.24.0 | plasma-workspace Depends on it, so it provides `kwriteconfig6`/`kreadconfig6` (UNVERIFIED which file, no apt-file) |
| kglobalacceld | 6.6.5 | global shortcut daemon; plasma-workspace Depends on it |
| dolphin / kio-extras | 25.12.3 | file manager and service-menu host |
| plymouth-theme-breeze | 6.6.4 | our own Plymouth theme (module 10) is independent |
| plasma-workspace-wallpapers, plasma-systemmonitor, plasma-nm | 6.6.x | |

`lookandfeeltool`, `plasma-apply-colorscheme`, `plasma-apply-wallpaperimage`, `plasma-apply-cursortheme`,
`plasma-apply-desktoptheme` are expected in plasma-workspace (UNVERIFIED; confirm with `dpkg -L` in the VM).
`plasma-lookandfeel-fallback`, `krunner`, `qdbus6` do not exist as package names: KRunner ships inside
plasma-workspace/libkf6runner6, and the D-Bus CLI is `qdbus-qt6` (a plasma-workspace Depends).

## 1. Inventory of GNOME-specific calls

Path column is schema/key. "Plasma" is the equivalent; `kwriteconfig6 --file F --group G --key K V`.

### install/05_mouse_ergonomics.sh (27 lines)
| Line | Call | What it does for the user | Plasma 6 equivalent |
|---|---|---|---|
| 6 | `~/.local/share/nautilus/scripts` | right-click Scripts menu in Files | Dolphin service menus in `~/.local/share/kio/servicemenus/*.desktop` (see section 6) |
| 15-19 | install `configs/nautilus-scripts/*` | three actions: Open in VS Code, Ask AI to Explain, Open Terminal Here | one `.desktop` service menu each, `Exec=` calls a wrapper that reads `%F` argv |
| 23 | `nautilus -q` | make Nautilus rescan scripts | `kbuildsycoca6` is not needed for kio servicemenus (Dolphin reads the dir on open; UNVERIFIED), so drop the call |

### install/06_desktop_theme.sh (134 lines)
| Line | gsettings path | What it does | Plasma 6 equivalent |
|---|---|---|---|
| 7 | `gs()` helper | wraps `as_user gsettings set` | new `kw()` helper: `as_user kwriteconfig6 ...`; warn-not-die (rule 3, AGENTS.md) |
| 10 | `org.gnome.desktop.wm.preferences button-layout ':minimize,maximize,close'` | buttons right | kwinrc? No: `~/.config/breezerc`/`kwinrc` group `org.kde.kdecoration2`, keys `ButtonsOnLeft=` (empty) and `ButtonsOnRight=IAX` (I minimise, A maximise, X close); apply with `qdbus-qt6 org.kde.KWin /KWin reconfigure`. Plasma already defaults to right-hand buttons, with a different set. UNVERIFIED |
| 13 | `org.gnome.desktop.interface color-scheme 'prefer-dark'` | dark mode | colour scheme `BreezeDark` via `plasma-apply-colorscheme BreezeDark` (section 5) |
| 24-27, 39 | `org.gnome.shell favorite-apps` (list built at :23-38 incl. `zorin-menu.desktop`, `org.gnome.Nautilus.desktop`, `org.gnome.Terminal.desktop`) | pinned dock apps | task-manager pinned launchers, `plasma-org.kde.plasma.desktop-appletsrc`, applet `org.kde.plasma.icontasks` key `launchers=applications:org.kde.dolphin.desktop,...` (needs the panel script, section 2). Candidate ids change: `org.kde.dolphin`, `org.kde.konsole`, `org.kde.plasma-systemmonitor` (replaces Mission Center only if we drop the Flatpak, see 04_workstation_apps) |
| 86-100 | `org.gnome.desktop.app-folders` folder-children, `.folder:/org/gnome/Desktop/folders/noctraos-agents.folder/` name+categories | "Agents" folder in the app grid | no equivalent. Plasma menus read the same `/etc/xdg/menus/*.menu` file, see next row; the app-folder branch is skipped (guarded by `list-schemas`, :87, already a no-op when absent) |
| 74-83 | install `configs/xdg/gnome-applications.menu` over `/etc/xdg/menus/gnome-applications.menu` | AI-first application menu tree | Plasma reads `applications.menu` (Kubuntu: `/etc/xdg/menus/plasma-applications.menu` via `XDG_MENU_PREFIX=plasma-`; UNVERIFIED). Ship `configs/xdg/plasma-applications.menu` with the same Agents/Local LLM tree; keep `applications-merged/noctraos-agents.menu` (:49-53 area, works for any prefix) |
| 115-117 | `org.gnome.desktop.background picture-uri`, `picture-uri-dark`, `picture-options 'zoom'` | wallpaper | `plasma-apply-wallpaperimage /usr/local/share/backgrounds/noctraos/...jpg` (needs a running plasmashell and D-Bus; fall back to the layout script section 2 writing `Image=` in the containment) |
| 118 | `org.gnome.desktop.screensaver picture-uri` | lock-screen picture | `kscreenlockerrc`, group `Greeter][Wallpaper][org.kde.image][General`, key `Image` (nested group; UNVERIFIED exact name) |
| 122-125 | `org.gnome.desktop.interface accent-color 'orange'` | accent | `kdeglobals` `[General] AccentColor=255,140,0` plus `plasma-apply-colorscheme --accent-color` (UNVERIFIED flag name; both exist in Plasma 6.3+ per upstream docs) |
| 128-131 | `org.gnome.shell.extensions.ding show-home / show-trash` | desktop icons | Plasma desktop folder view shows files only; home/trash come from `~/Desktop` links. Optional: do nothing |

### install/08_shell_theme.sh (142 lines)
| Line | Path | What it does | Plasma 6 equivalent |
|---|---|---|---|
| 7-10 | base `/usr/share/themes/ZorinBlue-Dark`, `ZorinPurple-Dark`, name `NoctraOS-Dark` | derived GTK + shell theme | Zorin themes do not exist on a stock base. GTK part: derive from `/usr/share/themes/Breeze-Dark` (breeze-gtk-theme) via `scripts/build-desktop-theme.py`; shell part is dropped (no `gnome-shell.css`) |
| 13-18 | `theme_set` = compare `gsettings get`, then set | idempotent guard | `theme_set` becomes `kreadconfig6` compare then `kwriteconfig6` (same pattern, section 5) |
| 46 | `org.gnome.desktop.interface gtk-theme` | GTK theme | `~/.config/gtk-3.0/settings.ini` and gtk-4.0 `gtk-theme-name`, written by `kde-config-gtk-style` / `kdeglobals`; or `[General] ColorScheme`, see section 5 |
| 58 | `org.gnome.desktop.interface icon-theme 'NoctraOS'` | icon theme | `kdeglobals` `[Icons] Theme=NoctraOS` (derived from `breeze-dark`, not `ZorinGrey-Dark`, :50-57) |
| 63-72 | `gnome-shell.css`, `org.gnome.shell.extensions.user-theme name` | Shell theme | Plasma theme: `kdeglobals`? No, `plasmarc` `[Theme] name=` (UNVERIFIED); our own theme would be a `~/.local/share/plasma/desktoptheme/<name>/` SVG package. Recommend using Breeze Dark and skipping |
| 100-110 | `org.gnome.Terminal.ProfilesList`, `Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:id/` | terminal palette | Konsole: `~/.local/share/konsole/NoctraOS.colorscheme` + profile `NoctraOS.profile`, `konsolerc` `[Desktop Entry] DefaultProfile=NoctraOS.profile`. Palette comes from `configs/theme/palette.json` |
| 81-96 | white menu icons in `/usr/local/share/icons/hicolor` | menu icon overrides | still valid (hicolor is shared), but Breeze icon theme does not inherit stock names the same way. UNVERIFIED |

### install/09_super_search.sh (79 lines)
| Line | Call | Plasma equivalent |
|---|---|---|
| 12, 33-36 | install three extensions into `/usr/share/gnome-shell/extensions` | drop on Plasma (section 3, 4) |
| 48-56 | glib schemas `org.gnome.shell.extensions.noctraos-search/-start` + `glib-compile-schemas` | search settings move to a plain JSON/INI file under `~/.config/noctraos/` (search/main.py:16-17 uses `Gio.Settings.new(SCHEMA)`; `search/preferences.py` and `bin/noctraos-welcome:30,335` use the same schema). Keep the schemas installed: GSettings works under Plasma (dconf backend) with no change; only the shell extension disappears |
| 53 | `90_noctraos-updates.gschema.override` (`com.ubuntu.update-manager first-run`) | not needed on Kubuntu (Discover/Muon, not update-manager). Skip |
| 61-65 | `systemctl --global enable noctraos-search-index.timer` | unchanged, systemd user unit works on Plasma |
| 67-70 | autostart desktops in `/etc/xdg/autostart` | unchanged (XDG autostart works). `noctraos-branding.desktop` is replaced by the Plasma layout script |
| 74-77 | `noctraos-search --setup`; `setup-branding.py` | see sections 2, 3 |

### branding/setup-branding.py (71 lines)
| Line | Call | Plasma equivalent |
|---|---|---|
| 41-52 | `org.gnome.shell enabled-extensions` add branding+start uuids | none. Replaced by Plasma layout script (section 2) |
| 56-62 | `org.gnome.shell.extensions.zorin-taskbar` schema | none. The dock is a Plasma panel (section 2) |
| 27-31 | `panel-lengths -1`, `panel-anchors MIDDLE`, `panel-sizes 40`, `panel-element-positions` (:7-17), `panel-margin 6`, `global-border-radius` | Plasma panel: `location=bottom`, `alignment=center`, `lengthMode=fit`, `thickness=40`, `floating=1` (floating = margin) |

### search/main.py, search/preferences.py, bin/noctraos-welcome, bin/noc, bin/noctraos-appearance
| File:line | Call | Plasma equivalent |
|---|---|---|
| search/main.py:34-58 (`setup_user`) | enables extension via `org.gnome.shell enabled-extensions`; moves `<Super>space` off `org.gnome.desktop.wm.keybindings switch-input-source(-backward)` | replace with `kglobalshortcutsrc` binding (section 3). Plasma has no `<Super>space` clash by default (input source switching is `Meta+Space` only if `kxkbrc` layout toggling is configured; UNVERIFIED) |
| search/preferences.py:207-211 | scans `org.gnome.desktop.wm.keybindings` for conflicts | scan `kglobalshortcutsrc` groups (all `Key=` values, first comma field) |
| bin/noctraos-welcome:121-130 | `gnome-extensions info <uuid>` to see if the search extension loaded | `kreadconfig6 --file kglobalshortcutsrc --group noctraos-search.desktop --key _launch` is non-empty; or ask `qdbus-qt6 org.kde.kglobalaccel /component/...` (UNVERIFIED) |
| bin/noc:24-34, 59-60 | `with_bus gsettings get/set org.gnome.desktop.background picture-uri[-dark]` (`noc bg`) | `plasma-apply-wallpaperimage`; read-back via `plasma-org.kde.plasma.desktop-appletsrc` `Image=` |
| bin/noc:509 | doctor row checks `/usr/share/gnome-shell/extensions/noctraos-search@noctraos.local` | doctor row on Plasma checks the `.desktop` shortcut file instead |
| bin/noctraos-appearance:22-23, 36, 44-45, 87-88, 139-141 | `org.gnome.desktop.background picture-uri[-dark]`; `org.gnome.desktop.interface font-name`, `document-font-name`, `monospace-font-name` | wallpaper as above; fonts in `kdeglobals` `[General]`: `font`, `menuFont`, `fixed`, `smallestReadableFont`, `toolBarFont` (value `Family,10,-1,5,400,0,0,0,0,0,0,0,0,0,0,1`). Documents font has no Plasma key: drop that row. Python GTK3 window itself is fine on Plasma |

## 2. Dock and top bar

GNOME design today: Zorin Taskbar as a centred floating dock, 40 px, margin 6, `panel-lengths -1` (branding/setup-branding.py:25-31)
with only `showAppsButton` hidden and `taskbar` visible (:7-17); the stock top bar is kept
(`stockgs-keep-top-panel`, :32) and flattened with a Show Desktop button and a tinted CopyQ tray icon
(extensions/noctraos-branding@noctraos.local/extension.js:41-56, 13-17, 103-112).

Plasma equivalent: two panels.
1. Top panel, full width, thickness 28-30, top: `org.kde.plasma.kickoff` omitted (our Start lives in the dock), widgets `org.kde.plasma.pager`? No. Use: `org.kde.plasma.appmenu` (global menu, optional), spacer, `org.kde.plasma.digitalclock`, `org.kde.plasma.systemtray`, `org.kde.plasma.showdesktop`.
2. Dock panel: `location = "bottom"`, `alignment = "center"`, `lengthMode = "fit"`, `thickness = 40`, `floating = true`, widgets `org.kde.plasma.kickoff` (or the Noctra start button, section 4) then `org.kde.plasma.icontasks` with `launchers` = the favourites from 06:39.

Doable with supported config: both panels and all widgets above are stock. The supported way is a **Plasma layout script**
(JavaScript run by plasmashell): `plasmashell --replace` is not needed; use
`qdbus-qt6 org.kde.plasmashell /PlasmaShell evaluateScript "$(cat noctra-layout.js)"` once per account (marker
`~/.config/noctraos/desktop-layout-v1`, same idempotence convention as branding/setup-branding.py:24,63-69). The API is
`panels()`, `new Panel`, `panel.addWidget("org.kde.plasma.icontasks")`, `widget.currentConfigGroup = ["General"]`,
`widget.writeConfig("launchers", [...])` (UNVERIFIED against 6.6). A first-boot alternative is a look-and-feel package whose
`contents/layouts/` holds the layout (`lookandfeeltool -a org.noctraos.desktop`), which is the right fit for the ISO's skel.
Needs a Plasma plasmoid: only the CopyQ tray tint (Breeze system tray tints symbolic icons already; CopyQ's own icon is not
monochrome, so keep our white icon override, assets/icons/overrides/copyq.svg), and any non-stock Show Desktop styling. Neither blocks.

## 3. Super+Space search

Today: extension registers `Main.wm.addKeybinding('toggle-search', ...)` (extensions/noctraos-search@noctraos.local/extension.js:25,
default `<Super>space`, configs/gsettings/org.gnome.shell.extensions.noctraos-search.gschema.xml:4), draws an overlay in the shell
(St widgets, extension.js:77-132), and the Python backend `noctraos-search --query` does ranking (search/main.py:66). The CLI
already has `--settings`, `--query`, `--index` (:66-72), so the engine is portable.

Plasma options:
- A. **KRunner (recommended for v1).** Bind `Meta+Space` to KRunner. Kubuntu default is `Alt+Space`/`Alt+F2`.
  `kwriteconfig6 --file kglobalshortcutsrc --group org.kde.krunner.desktop --key _launch "Meta+Space,Alt+Space\tAlt+F2,Activate KRunner"`
  (format `current,default,description`; UNVERIFIED, test in VM). A **runner plugin** (D-Bus runner, ~60 lines Python, file
  `~/.local/share/krunner/dbusplugins/noctraos.desktop` with `X-Plasma-API=DBus` and `X-Plasma-DBusRunner-Service`) calls
  `noctraos-search --query` and returns matches (files, CopyQ, history, web). This reuses the whole backend; UI is KRunner's.
- B. Rebuild the overlay as a GTK3 window (search/ app) launched by a global shortcut: register a `.desktop` with
  `X-KDE-Shortcuts=Meta+Space` ... (UNVERIFIED), or write
  `[noctraos-search.desktop] _launch=Meta+Space,none,Noctra Search` into `kglobalshortcutsrc`. Works but a GTK window cannot
  stay as an overlay without layer-shell styling and focus stealing under KWin, so it is medium effort.
- The GNOME extension is not loaded on Plasma. Keep it in the repo for the Zorin/GNOME build; gate module 09's extension
  installs on `XDG_CURRENT_DESKTOP`.
- Input-source clash (search/main.py:43-55): drop on Plasma, instead set `kxkbrc` `[Layout] ... ` only if the user has two layouts (skip; UNVERIFIED).
- Persistent apply: kglobalaccel reads the file at login; to apply live use `qdbus-qt6 org.kde.kglobalaccel /kglobalaccel` ... or
  `kquitapp6 kglobalacceld; kglobalacceld &` (UNVERIFIED). First-run setup runs before the session, so no live apply needed.

## 4. Start button / Start panel

Today: extensions/noctraos-start@noctraos.local/extension.js (591 lines) hooks Zorin Menu's private API
(`MENU_UUID = 'zorin-menu@zorinos.com'` :10, `menuButtons[i]._menu.toggle` :78-87) and draws a Start panel with pinned apps
(schema `pinned-apps`, configs/gsettings/...start.gschema.xml:6), weather (`noctraos-weather`), New-users strip, Agents.
It also calls `Main.overview.showApps()` (:554). None of the shell API exists on Plasma.

Options:
1. **Kickoff (stock), recommended.** Place `org.kde.plasma.kickoff` on the dock, set icon to our `noctraos-start` SVG
   (`widget.writeConfig("icon", "noctraos-start")`), pinned favourites via `favoritesPortedToKAstats`/`Favorites` (Plasma 6
   stores them in `plasma-org.kde.plasma.desktop-appletsrc` and `kactivitymanagerdrc`; UNVERIFIED). The AI-first menu tree
   from section 1 (`plasma-applications.menu`) already puts Agents and Local LLM on top. Cost: small to medium. Loses weather
   and the New-users strip; put the strip into the Welcome app and a Dolphin/desktop link.
2. Rebuild as a QML plasmoid (`org.noctraos.start`). High effort, needs QML/Kirigami, version-pinned to Plasma 6.x API.
3. Start panel as a GTK3 window opened by a plasmoid button (`org.kde.plasma.quicklaunch` pointing at `noctraos-start`).
   Medium; has the overlay/focus caveats of 3.B.

Recommendation: **1 for the spike and v1**, 3 only if the weather/New-users strip is a product requirement; defer 2.

## 5. Theme

Installed-package names (verified, section 0): `breeze` (meta), `kde-style-breeze`, `plasma-desktoptheme` (Plasma theme),
`breeze-cursor-theme`, `kf6-breeze-icon-theme`, `breeze-gtk-theme`, `kde-config-gtk-style`, `plymouth-theme-breeze`.
Look-and-feel package ids (UNVERIFIED, from `lookandfeeltool --list` in the VM): `org.kde.breezedark.desktop`,
`org.kde.breeze.desktop`, plus Kubuntu's own (`org.kubuntu.*`; check `apt-cache show kubuntu-settings-desktop`).
Colour scheme ids: `BreezeDark`, `BreezeLight` (files in `/usr/share/color-schemes/`; UNVERIFIED).

Idempotent apply (all run as the target user, with `QT_QPA_PLATFORM` unset; warn-not-die):
```
cur=$(as_user kreadconfig6 --file kdeglobals --group General --key ColorScheme)
[ "$cur" = NoctraOSDark ] || as_user plasma-apply-colorscheme NoctraOSDark || warn ...
cur=$(as_user kreadconfig6 --file kdeglobals --group Icons --key Theme)
[ "$cur" = NoctraOS ] || as_user kwriteconfig6 --file kdeglobals --group Icons --key Theme NoctraOS
```
Plan: ship a custom colour scheme `/usr/local/share/color-schemes/NoctraOSDark.colors` (generated from
`configs/theme/palette.json` by `scripts/render-theme.py`, extending its `--check`), accent orange; and an icon theme
`NoctraOS` that `Inherits=breeze-dark` (replace the Zorin base used at install/08_shell_theme.sh:50-58). `theme_set`
(08:14-20) becomes a `kreadconfig6`-guarded `kwriteconfig6`. Apply via `lookandfeeltool -a org.kde.breezedark.desktop` only
at first login (it resets panels/colours/cursor, so it must run before the layout script, never on reruns; guard with a marker).
`kwriteconfig6` changes only the file; a running session needs `plasma-apply-colorscheme` or a D-Bus `notifyChange`.
GTK apps: install `kde-config-gtk-style` so Breeze/colour-scheme sync applies; our derived GTK CSS
(scripts/build-desktop-theme.py with Breeze-Dark base) is optional.

## 6. Mouse ergonomics (module 05)

Nautilus scripts (configs/nautilus-scripts/*, three files; selection via `NAUTILUS_SCRIPT_SELECTED_FILE_PATHS`, e.g.
`Open in VS Code`:3-9) become Dolphin service menus. Files: `~/.local/share/kio/servicemenus/noctraos-<action>.desktop`
(system-wide `/usr/share/kio/servicemenus/` also works), with
```
[Desktop Entry]
Type=Service
MimeType=all/all;inode/directory;
Actions=openCode
X-KDE-Submenu=NoctraOS
[Desktop Action openCode]
Name=Open in VS Code
Exec=/usr/local/bin/noctraos-open-code %F
```
(`X-KDE-Priority`, `Icon=` optional; UNVERIFIED on Dolphin 25.12, where servicemenus must be executable `chmod +x`).
Script change: replace the env-var loop with `args=("$@")`; keep the "no selection -> current dir" fallback via `%d`/`$PWD`.
Install into `/usr/local/bin` so the same wrapper serves both file managers; keep Nautilus install on GNOME builds.
Underscore-mnemonic pitfall (module 05:9-10) does not apply (no GTK menu labels), but keep plain spaces.
Remove `nautilus -q` (:23). `kio-extras` is already pulled by kubuntu-desktop.

## 7. Risks and what cannot be ported

| Item | Size | Notes |
|---|---|---|
| Rewriting modules 06, 08, 09 behind a `DESKTOP=gnome|kde` switch (lib.sh helper, `XDG_CURRENT_DESKTOP`) | medium | scripts are ~350 lines; most calls guarded already |
| Plasma panel layout script (dock + top bar) | medium | API undocumented in places; evaluateScript needs running plasmashell; first-boot ordering |
| Super+Space KRunner runner plugin | medium | D-Bus runner API is stable; shortcut write is small |
| Start panel (weather, strip, Edit pins) | high if rebuilt, small if Kickoff | recommend Kickoff |
| GNOME extensions (3 JS files, 1,213 lines) | cannot port | GNOME-only API (St, Meta, Main); keep for GNOME build, rebuild equivalent per section 3/4 |
| Derived NoctraOS-Dark GTK/Shell theme from Zorin base | medium | base theme absent; shell CSS dropped; GTK theme re-derived from Breeze |
| Terminal palette (gnome-terminal dconf) | small | Konsole colorscheme file |
| Agents folder in app grid | cannot port | menu tree covers it |
| `noc bg`, `noc doctor` extension row, appearance, welcome probe | small each | swap gsettings for KDE calls (section 1) |
| Control Panel (control/main.py:22, pages.py:10) | small | GTK3 imports only, no gsettings (`grep` found none); runs under Plasma with `python3-gi gir1.2-gtk-3.0` (module 09:27-33); needs `gnome-themes`? UNVERIFIED for dark styling, and GTK3 under KDE uses `kde-config-gtk-style` |
| GDM greeter bug / autologin (AGENTS.md pitfalls) | n/a | Kubuntu uses SDDM; needs `/etc/sddm.conf.d/autologin.conf` for unattended builds; ISO build scripts (casper, ubiquity -> Calamares?) may differ. UNVERIFIED: Kubuntu 26.04 installer; this is the largest unknown for ISO builds (iso/*.sh assume Zorin's ubiquity) |
| Keyring (scripts/seed-password-store.py) | small | KWallet instead of GNOME keyring; Hermes/Chromium still use Secret Service; kwallet-pam vs unencrypted keyring needs rethinking |
| Plymouth/GRUB themes (module 10) | small | independent of DE |
| Zorin-specific modules 04c retiring `zorin-*` apps | small | most do nothing on stock Ubuntu; add Kubuntu junk list |
| Wayland vs X11 session, XWayland CopyQ (AGENTS.md CopyQ pitfall) | small | `QT_QPA_PLATFORM=xcb` rule still holds; Klipper (KDE clipboard) conflicts with CopyQ, retire or disable Klipper autostart |
| Flatpak/AppImage policy | small | Discover handles Flatpak; add `plasma-discover-backend-flatpak` (name UNVERIFIED) |

## 8. Ordered task list

| # | Task | Lane |
|---|---|---|
| 1 | In a Kubuntu VM (`iso/local-vm.sh`): install `kubuntu-desktop`, record `dpkg -L` of plasma-workspace/libkf6config-bin for the tool names, `lookandfeeltool --list`, `kreadconfig6` of the keys above, and mark each UNVERIFIED line in this plan as verified or wrong | medium |
| 2 | Add `DESKTOP` detection and `kw()`/`kcfg_set()` helpers to `install/lib.sh`; gate modules 05/06/08/09 on it (no behaviour change on GNOME) | medium |
| 3 | Module 06 KDE branch: wallpaper, dark scheme, accent, buttons, favourites, XDG menu file, skip app-folders/DING | medium |
| 4 | Colour scheme + icon theme generation (`NoctraOS` icons from `breeze-dark`; `NoctraOSDark.colors` from palette.json), extend `render-theme.py --check` and tests/test_desktop_theme | medium |
| 5 | Plasma layout script (dock + top bar) and once-per-account marker, run from autostart | high |
| 6 | KRunner D-Bus runner plugin wrapping `noctraos-search --query` + `kglobalshortcutsrc` binding for `Meta+Space`; settings file instead of GSettings on KDE | high |
| 7 | Start button via Kickoff: icon, favourites; decision record on weather/New-users strip | medium |
| 8 | Dolphin service menus + `noctraos-open-code`/`-ask-ai`/`-terminal` wrappers (argv based) and module 05 branch | small |
| 9 | Konsole colour scheme and profile from palette.json | small |
| 10 | Port `noc bg`, doctor row, welcome probe, `noctraos-appearance` (drop documents font) to KDE calls | medium |
| 11 | Retire Klipper, disable KDE-only duplicates; SDDM autologin config; KWallet policy for the Secret Service pitfall | high |
| 12 | Unattended/ISO build on Kubuntu (installer, casper, preseed, branding scripts iso/*.sh) | escalate |
| 13 | Idempotency and second-run test in the VM, plus unit tests for new helpers (`python3 -m unittest discover -s tests`, `bash -n`, shellcheck via docker) | medium |
| 14 | Docs: objectives/AGENTS.md/README note that the product has a KDE variant | small |
