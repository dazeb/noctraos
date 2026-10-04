# First-run onboarding (draft)

Status: **design draft, nothing built yet.** Goals come from
[objectives.md](objectives.md): put **Super+Space** front and center for people
moving from Windows, without a terminal, without a lecture.

## Why this matters now

On the ISO's first boot the user currently sees the provisioner running in a
terminal (Ollama, the model pull, a Python build — tens of minutes) and is told
nothing about the product. That dead time is the best onboarding slot we will
ever get: **the welcome app runs while provisioning runs**, so waiting becomes
learning.

## Principles

1. **One hero, then stop.** Super+Space gets the first real screen. Everything
   else is a short reference, not a tour.
2. **Make them do it.** The Super+Space step does not advance until the user
   has actually opened the overlay. Reading about a shortcut does not build
   the habit; pressing it does.
3. **Always skippable, always reopenable** — from the start menu ("Welcome to
   NoctraOS"), and by typing "welcome" in Super+Space.
4. **Under two minutes**, five screens or fewer, no account, no telemetry.
5. **One keybind.** NoctraOS is mouse-first. Super+Space is the only shortcut
   we teach; everything else is reachable with the mouse (and through Super+Space).
6. **Windows vocabulary.** Say "Windows key" (it is the Super key), "Task
   Manager" (Mission Center), "Start button" (the N).

## Flow

| # | Screen | Purpose | Advances when |
|---|--------|---------|---------------|
| 1 | **Welcome** — one line on what NoctraOS is, a *Start* button, a *Skip* link | Set expectations | Click |
| 2 | **Press Windows + Space** — large keycap graphic, short copy: "Search everything from one place." | Teach the hero feature by doing it | The user opens the overlay once (see *Detecting the keypress*) |
| 3 | **What can it find?** — four tappable examples that open the overlay with a query filled in: an app ("files"), a file by name, something from clipboard history, a web search. Browser history is not an example here: it is offered later (below) | Show the range; each is one click | Click *Next* (no forced interaction) |
| 4 | **Where things are** — a compact, mouse-only map of familiar things: Start button (N, bottom-left), Task Manager → Mission Center, File Explorer → Files, screenshots, system tray. **No shortcut list** | Reassure; nothing to relearn | Click *Next* |
| 5 | **Your AI is local** — status of the local model (installed / downloading, with progress), the Agents menu, how to open it | Introduce the AI half without blocking on the download | Click *Done*; if provisioning is still running, show "Finishing setup in the background" |

After *Done*: no nagging. One non-modal hint — the start menu's search box
reads "Search, or press Windows + Space".

### Screen 2 detail: detecting the keypress

The overlay is a Shell modal, so the welcome app cannot see the keystroke.
Add a boolean key `first-used` to the search schema
(`org.gnome.shell.extensions.noctraos-search`); the extension sets it on first
open, and the welcome app watches it with `Gio.Settings` and advances. No new
IPC.

### Screen 3 detail: prefilled queries

Needs a way to open the overlay with text already in it. Proposed: a D-Bus
method `Open(query)` on the search extension (or a hidden GSettings string the
extension watches). To be chosen during implementation; D-Bus is cleaner.

File search is only as good as the index. Screen 3 must handle the first-boot
case where the index is still building: show "Still indexing your files — try
this one in a minute" and keep the app and web examples enabled.

## After onboarding: finishing search setup

Browser history cannot be set up during onboarding because a new user has no
browser history yet. The overlay itself carries the offer (built): when a
supported browser has history and the question is unanswered, a small "Finish
setup" notice appears under the search box with **Set up** / **Not now**. See
[objectives.md](objectives.md#browser-history-is-opt-in-and-set-up-after-first-use).
Onboarding screen 2/3 should not mention it, and must not depend on it.

## Implementation sketch

- A small GTK app, `noctraos-welcome`, in the same stack as the existing
  Search settings window (system Python + PyGObject), so no new runtime.
  `gnome-tour` was considered; it is static slides and cannot do the
  "try it now" step in screen 2.
- Launched once per account from `/etc/xdg/autostart` with a marker file in
  `~/.config/noctraos/`, the same pattern as the search and branding setup.
- A start-menu entry, `noctraos-welcome.desktop`, for reopening.
- On the ISO, replace the raw provisioning terminal with a progress panel in
  this window (tail of the provisioner log, collapsed by default, with
  "Show details" for anyone who wants it). Failures must surface clearly
  with a retry button; the current terminal behaviour is the fallback.
- The theme is inherited: dark, amber focus, small radii, monospace for
  keycaps. Design it to match the Super+Space overlay.

## Open questions

1. **Forced vs optional step 2.** Gating "Next" on actually pressing the keys is
   the point, but it must never trap someone whose keyboard layout or hardware
   (some laptops, VMs, remote sessions) swallows the shortcut. Keep a visible
   "It's not working" escape that explains the shortcut and the settings.
2. **Shortcut parity** — resolved: we do not promise any. See the audit below.
3. **Languages.** Copy is English only for now.
4. **Provisioning offline.** The "full ISO" goal means the model and runtimes
   should eventually be baked in, which would shorten or remove the waiting
   period this design uses. The welcome flow still stands without it.

## Shortcut audit (VM 114, 2026-10-04)

Checked from the live GSettings configuration (not by pressing every key).
Per the "one keybind" principle none of these is taught or added; this just
records what a switcher who tries a habit will find.

| Windows habit | On NoctraOS today |
|---|---|
| Windows key alone | Opens the Shell overview (the Zorin Menu hotkey is off) |
| Alt+Tab | Works (also Super+Tab) |
| Windows+L lock | Works |
| Windows+Arrows | Maximize / restore / tile left and right work |
| Windows+1..9 | Launches or focuses taskbar apps (Zorin taskbar) |
| Print | Screenshot UI (Flameshot is also installed) |
| Windows+Space | **NoctraOS search** (input-source switch moved to Shift+Super+Space) |
| Windows+V | Notification tray (GNOME default), **not** clipboard history |
| Windows+E (Files) | Not bound |
| Windows+D (show desktop) | Not bound (Windows+H minimizes the window) |
| Ctrl+Shift+Esc (Task Manager) | Not bound; Mission Center is a taskbar app |
| Windows+Shift+S (region screenshot) | Not bound; Print opens the screenshot UI |
| Windows+R (Run) | Not bound; Super+Space does it |

The unbound ones all have a mouse route, and the ones worth a keyboard route
(apps, files, clipboard) already go through Super+Space.

## Clipboard history

Clipboard history is reached through Super+Space, not a second shortcut (no
Windows+V rebinding). The open question is the backend, not the door.

**Should we build our own permanent clipboard, like KDE's Klipper?** We would
be building a daemon that watches the clipboard, stores text and images,
persists history safely (including passwords and secrets handling), and
survives Wayland's restrictions — a lot of surface area for a feature that
mature software already covers. Recommended order:

1. **Keep CopyQ** for now: it is installed, persistent, and Super+Space already
   searches it. Its weakness on GNOME is Wayland: GNOME does not let a
   background app watch the clipboard the way a KDE service can, so CopyQ's
   capture may be incomplete for native Wayland apps. **This is unverified on
   our image**: my attempts to test it on VM 114 were inconclusive for both
   CopyQ and GPaste (the probe copy never reached either), so treat it as a
   hypothesis, not a finding.
2. **Test properly** by copying from real apps (Firefox/Chromium, Files, GNOME
   Text Editor, VS Code, terminal) and checking what history captures.
3. If CopyQ fails that test, move to **GPaste**: it is the GNOME-native
   equivalent of Klipper (a daemon plus a Shell extension, persistent history,
   a CLI/D-Bus API we can bridge to Super+Space), packaged for GNOME Shell 46 in
   the Ubuntu archive (`gnome-shell-extension-gpaste`). That is a swap of the
   backend behind `search/core.py`, not a new clipboard manager.
4. Only build our own if both fail a concrete requirement, and then as a Shell
   extension (it runs inside the compositor, so it sees every copy), not a
   standalone daemon.
