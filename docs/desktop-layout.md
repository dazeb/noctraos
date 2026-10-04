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

## How we read it

- The top bar carries status only: network, volume/power and the clock on the
  right; notifications in the centre (the area where GNOME shows notification
  banners). Moving these off the bottom bar leaves the dock for launching.
- The dock keeps the Windows habit (Start on the left of the icons, running
  apps as icons) while centring it, as Windows 11 does.
- The Start menu is for **browsing and launching**; Super+Space is for
  **searching**. They must not duplicate each other. The AI-first menu (Agents,
  Local LLM, models) is the Start menu's job.

## Today versus the mockup

| Element | Today (VM 114) | Mockup |
|---|---|---|
| Bar at the top | none (Zorin Taskbar replaces the stock top panel) | thin full-width bar with notifications, network, clock |
| Bottom bar | full-width, 48 px, square corners; icons left-aligned; tray and clock at the right | floating, centred, rounded; Start plus app icons only |
| Tray, network, volume, power, clock | bottom right | top right |
| Start button | Noctra "N" (extension) | rounded "Start" button inside the dock |
| Start menu | stock Zorin Menu, compact styling | large rounded popup redesigned around AI apps |
| Corner radius | 2 px everywhere (matches the Super+Space overlay) | clearly rounded dock, button and popup |
| Wallpaper | purple/magenta neon scenes | plain dark |

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

1. **Rounded or sharp?** The mockup is rounded; the Super+Space overlay and the
   whole palette work so far use 2 px corners. Pick one radius and apply it
   everywhere, including the overlay.
2. **What goes in the centre of the top bar?** The notification area only, or
   the clock too (GNOME's default), or a Super+Space hint?
3. **Does the dock need running-app indicators, window previews, a Show Desktop
   button?** (Today it has all three.)
4. **Where do the tray indicators (CopyQ, Connect, etc.) live** — top bar?
5. **Should the Start menu also list recent files and Super+Space results,** or
   stay a pure launcher?
6. **Plain dark wallpaper** replacing the neon set: confirm, and whether the
   user can still pick their own.
