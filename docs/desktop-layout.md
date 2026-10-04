# Desktop layout (target)

Owner's mockup: [`mockups/desktop-layout.webp`](mockups/desktop-layout.webp).
It is a wireframe ("very basic, but you get the idea"), so this document records
how we read it, what differs from the image today, and what is still open.

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
  artifact. One radius (2 px today) across the whole system.
- **Top bar, left:** Show Desktop.
- **Top bar, centre:** the **clock**. Notifications open from it (GNOME's
  date/notification menu), which also covers the mockup's "notification" label.
- **Top bar, right:** running-app indicators and the tray icons (network,
  volume, power, CopyQ and other indicators).
- **Bottom dock:** floating and centred: Start button, then application icons.
- **Start menu:** shows **recent files** as well as apps, and is closer to
  macOS (a launcher grid with a Recents area, not a Windows-style tree) than to
  Windows. Redesigned around AI applications: Agents and Local LLM come first.
  Browsing and launching only; Super+Space remains the search surface.
- **Wallpaper:** the current set stays; better ones are welcome at any time
  (the generator is `assets/wallpapers/generate-wallpapers.py`).

## Today versus the mockup

| Element | Today (VM 114) | Mockup |
|---|---|---|
| Bar at the top | none (Zorin Taskbar replaces the stock top panel) | thin full-width bar with notifications, network, clock |
| Bottom bar | full-width, 48 px, square corners; icons left-aligned; tray and clock at the right | floating, centred, rounded; Start plus app icons only |
| Clock | bottom right | top centre |
| Tray, network, volume, power, running-app indicators | bottom right | top right |
| Show Desktop | bottom right edge | top left |
| Start button | Noctra "N" (extension) | rounded "Start" button inside the dock |
| Start menu | stock Zorin Menu, compact styling | large rounded popup redesigned around AI apps |
| Corner radius | 2 px everywhere (matches the Super+Space overlay) | **decided: sharp, 2 px** (mockup shows rounded) |
| Wallpaper | purple/magenta neon scenes | **decided: keep current**, add better ones over time |

## Feasibility on GNOME (read from the live settings, not yet tried)

- A centred, partial-width dock looks supported: the Zorin Taskbar (a Dash to
  Panel fork) exposes `panel-lengths`, `panel-anchors`, `panel-sizes`,
  `panel-position` and `global-border-radius`. Whether it can look like the
  floating, rounded dock in the mockup needs a try.
- A **second bar at the top is the hard part.** The taskbar replaces the stock
  top panel rather than sitting beside it. Options to investigate: re-enable the
  stock panel and hide the taskbar's tray and clock; or write a small top-bar
  extension of our own. Neither is verified.
- The Start menu redesign is real work: restyling the Zorin Menu is not
  enough for a new layout, so this likely means our own menu extension (the
  search overlay is already one).

## Open questions

1. **"Running-app indicators" in the top bar:** an icon strip of open apps
   (with window previews on hover?) or just a mark for which apps are open?
   And does the dock then show only pinned launchers, or also a dot under
   running ones?
2. **Start menu, macOS-like:** a full-screen/centred grid like Launchpad, or a
   panel anchored above the dock? How many recent files, and which types
   (documents only, or everything)?
3. **Where does the AI emphasis sit in the Start menu:** a pinned Agents row
   on top, a local-model status tile, or both?
4. **Top bar technique** (still to prove on the VM): restore GNOME's stock
   panel beside the taskbar, or build our own top-bar extension that takes the
   tray, clock and Show Desktop out of the taskbar.
