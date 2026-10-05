# Desktop layout

Owner's mockup: [`mockups/desktop-layout.webp`](mockups/desktop-layout.webp).
It is a wireframe ("very basic, but you get the idea"), so this document records
how we read it, what was built, and what is still open. The top bar, floating
dock and Start panel are all built; the comparison table below says where the
result still differs from the mockup.

![Desktop layout mockup](mockups/desktop-layout.webp)

## What the mockup shows

1. **Top bar**, full width, thin. Labelled *Top notification bar* (centre) and
   *Network – Time* (right).
2. **Floating bottom dock**, centred, rounded, not edge to edge. Contains a
   **Start** button at its left end, then the **application icons**.
3. **Start menu popup**, a large rounded panel opening above the dock,
   *"redesigned for AI applications"*.
4. Plain near-black background, light outlines. Nothing else on screen.

## Decisions (owner, 2026-10-04)

These override the mockup where they differ.

- **Sharp corners everywhere**, very opinionated: dock, Start button, Start
  menu, top bar, overlay, dialogs. The mockup's rounding is a wireframe
  artifact. 0 px across the shell, dock, menus and Start panel (`palette.json`
  radius 0); the Super+Space overlay and our own GTK windows (Welcome, Appearance)
  still use 2 px, which should be brought in line.
- **Top bar, left:** Show Desktop.
- **Top bar, centre:** the **clock**. Notifications open from it (GNOME's
  date/notification menu), which also covers the mockup's "notification" label.
- **Top bar, right:** running-app indicators and the tray icons (network,
  volume, power, CopyQ and other indicators).
  *Styling (done):* the whole shell theme is recoloured from the Zorin blue to the
  NoctraOS palette at build time (`configs/theme/shell-remap.json`, property-aware:
  text becomes foreground, fills become amber), corners are 0 px everywhere
  (`palette.json` radius 0), and the quick-settings and calendar/notification menus
  match the top bar.
- **Bottom dock:** floating and centred: Start button, then application icons.
- **Start menu:** shows **recent files** as well as apps, and is closer to
  macOS (a launcher grid with a Recents area, not a Windows-style tree) than to
  Windows. Redesigned around AI applications: Agents and Local LLM come first.
  Browsing and launching only; Super+Space remains the search surface.
- **Wallpaper:** the current set stays; better ones are welcome at any time
  (the generator is `assets/wallpapers/generate-wallpapers.py`).

## Today versus the mockup

| Element | Today | Mockup |
|---|---|---|
| Bar at the top | thin (28 px) flat panel: the stock GNOME panel kept via the Zorin Taskbar's `stockgs-keep-top-panel` | thin full-width bar with notifications, network, clock |
| Bottom bar | floating, centred dock hugging its icons (40 px); Start button plus app icons | floating, centred, rounded; Start plus app icons only |
| Clock | top centre, opens notifications and the calendar | top centre |
| Tray, network, volume, power, running-app indicators | top right | top right |
| Show Desktop | top left (`noctraos-branding`) | top left |
| Start button | Noctra logo (the website mark; extension), in the dock | rounded "Start" button inside the dock |
| Start menu | the Noctra Start panel (`noctraos-start`): header, Agents row, recent files, All apps | large rounded popup redesigned around AI apps |
| Corner radius | 0 px (shell, dock, Start panel); 2 px in the search overlay and our GTK windows | **decided: sharp** (mockup shows rounded) |
| Wallpaper | six polygonal 4K scenes, including near-black `ember-night` | **decided: keep current**, add better ones over time |

## Spike result: top bar + floating dock (works, 2026-10-04)

Proved on VM 114 with settings plus a few lines in the branding extension. No
patching of Zorin code.

- **Top bar = the stock GNOME panel, kept.** The Zorin Taskbar has a
  `stockgs-keep-top-panel` setting. With it on, the stock panel stays at the top
  and keeps what it already does well: the **clock in the centre** with the
  notification/calendar menu, the **tray strip** (zorin-appindicator, so CopyQ
  and other indicators land top right) and the network/volume/power menu.
- **Dock = the taskbar, shrunk.** `panel-lengths` of -1 ("dock mode") makes it
  hug its icons; `panel-anchors` MIDDLE centres it; `panel-sizes` 40, `panel-margin`
  6, and the taskbar elements trimmed to the Start button plus app icons
  (`panel-element-positions`).
- **Show Desktop, top left:** a small button added to the panel's left box by
  `noctraos-branding`, replacing Activities. Verified with a virtual mouse: the
  first click minimizes the open window, the second restores it.
- **Flat top bar:** 28 px, no hover effects, an open menu marked in amber, 0
  radius (extension stylesheet).
- **Applied once per account** by `branding/setup-branding.py` (marker
  `~/.config/noctraos/desktop-layout-v1`), so later user changes are kept.
  Verified from the repo scripts: install run, layout applied, session restart,
  screenshot.
- **Known limits:** the settings are keyed to monitor "0" (the primary), so a
  second monitor keeps the stock full-width taskbar; no multi-monitor test yet.
  Show Desktop remembers the windows it minimized for the current workspace only.

## Start menu spec (owner, 2026-10-04)

**v1 is built** (`extensions/noctraos-start@noctraos.local`): a 560 px panel above the
dock with a header bar (title and a **settings gear on the right** that opens
Settings), the **pinned Agents row** (Hermes, Claude Code, Codex, OpenCode, Grok,
Gemini CLI, Qwen Code), **recent files** (8, from the desktop's recent list; scratch and
hidden paths skipped; each opens in its default app), and a footer with *All apps*
and a Super+Space hint. Sharp, monospace, palette from `palette.json`. The Start
button opens it; Esc, a click outside, or the button again close it.
Verified on VM 114 with a virtual mouse and keyboard: open, close three ways,
gear to Settings, a recent file opening.
Since then: the header shows the **user's name** and an opt-in **weather** readout
(Open-Meteo, keyless; `+ weather` opens a small dialog to pick a city and units,
which can also remove it), a dismissible **"New users start here"** strip opens a
local help page (`help/index.html`, installed to `/usr/local/share/noctraos/help/`).
Settings live in `org.gnome.shell.extensions.noctraos-start` (`show-name`,
`show-start-here`, `weather*`). Verified on VM 114: live weather (13°C, Leeds),
the dialog, the strip, and the help page (rendered headlessly). The page opens in the default browser; the locked-keyring prompt that Chromium
used to show on first start is now fixed for the browsers we install (see
AGENTS.md); a browser the user installs themselves (Brave, Chrome) can still prompt.
Not yet built: an apps list and a settings page for customisation (today it is
the in-panel controls and GSettings). Untested: launching an agent from the row and
*All apps*. The panel replaces the Zorin Menu popup by overriding its
`_menu.toggle`/`open`, a private API, so a Zorin Menu update could break it (the
stock menu then simply keeps working). The pinned row is Hermes first, then Claude
Code, Codex, OpenCode, Grok, Gemini CLI and Qwen Code (seven agents).

### Full spec

- A **panel above the dock** (not full screen). Compact, edgy, sharp corners,
  **terminal (monospace) font**.
- **Top right of the panel: the user's name and the weather**, so it feels
  welcoming.
- A **"New users start here"** section that opens a help page showing how to use
  the OS.
- A **pinned Agents row** (Hermes, Codex, Claude Code, OpenCode, Grok, Gemini CLI,
  Qwen Code), then the apps, then **recent files** (macOS-like, not a Windows tree).
- **Customisable:** users can add or remove widgets such as weather and time.
- Browsing and launching only; Super+Space stays the search.

Notes for when we build it: the weather needs a data source and a location. A
keyless service (such as Open-Meteo) works, but location should be a user choice
(typed city or an opt-in lookup), not silent. The help page can be a local HTML
or app page reachable from the onboarding flow as well.

## Open questions

Settled by the v1 build: the panel is 560 px wide, and it shows 8 recent files of any
type (scratch and hidden paths skipped). Still open:

1. **Apps in the panel:** a grid or a list under the Agents row, or leave apps to
   *All apps*?
2. **Dock behaviour:** running apps show as icons in the dock with a dot today;
   keep that, or move all running state to the top bar?
3. **Customisation UI:** a settings page, a right-click on the panel, or both?
   Today it is the in-panel controls and GSettings.
4. **Help page:** `help/index.html` is a short reference opened from the Start panel
   and is not the same thing as the Welcome's "where things are" screen. Keep two
   or merge them?
5. **Second monitor:** the dock settings are keyed to the primary monitor; the
   layout has not been tested with more than one.
