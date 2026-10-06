#!/usr/bin/python3
# System Python on purpose: it has PyGObject; a mise-managed python3 (first on PATH in a
# session) does not. bin/noctraos-control execs /usr/bin/python3 on this file.
"""noctraos-control — the NoctraOS Control Panel (design: docs/control-panel-plan.md).

A sidebar of pages in one GTK window. Every number comes from `noc ... --json`; the panel never
reimplements what the CLI does, so the two cannot drift. Slow calls run on a thread and the UI
only ever shows a spinner, never blocks.

  noctraos-control                 open the panel
  noctraos-control --page models   open it on a page (overview, models, health, about)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gi  # noqa: E402

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

import pages  # noqa: E402
from pages import label  # noqa: E402

APP_ID = 'local.noctraos.Control'

# Same palette as the Welcome and Appearance windows (configs/theme/palette.json), 2 px corners.
CSS = b"""
window, .content { background: #121212; color: #bebebe; }
.sidebar { background: #0d0d0d; border-right: 1px solid #333333; }
.sidebar row { padding: 10px 18px; color: #bebebe; border-left: 3px solid transparent;
               font-family: 'JetBrainsMono Nerd Font', monospace; }
.sidebar row:hover { background: #1e1e1e; }
.sidebar row:selected { background: #1e1e1e; color: #eaeaea; border-left-color: #e68e0d; }
.sidebar row:selected label { color: #eaeaea; }
.brand { font-size: 15px; font-weight: bold; color: #eaeaea; }
.title { font-size: 24px; font-weight: bold; color: #eaeaea; }
.section { font-size: 13px; font-weight: bold; color: #e68e0d; margin-top: 10px;
           font-family: 'JetBrainsMono Nerd Font', monospace; }
.lede { font-size: 14px; color: #8a8a8d; }
.card { background: #1e1e1e; border: 1px solid #333333; border-left: 3px solid #333333;
        border-radius: 2px; padding: 14px 16px; }
.card.ok { border-left-color: #ffc107; }
.card.warn { border-left-color: #e68e0d; }
.card.clickable:hover { background: #2a2a2a; }
.card-title { color: #8a8a8d; font-size: 12px; font-family: 'JetBrainsMono Nerd Font', monospace; }
.card-value { color: #eaeaea; font-size: 17px; font-weight: bold; }
.card-detail { color: #8a8a8d; font-size: 13px; }
.row-title { color: #eaeaea; font-weight: bold; }
.rows, .rows row { background: transparent; border-bottom: 1px solid #333333; }
.mark { font-size: 16px; }
.status-ok { color: #ffc107; }
.status-warn { color: #e68e0d; }
.status-fail { color: #d35f5f; }
.status-info { color: #8a8a8d; }
.muted { color: #8a8a8d; }
entry { background: #0d0d0d; color: #eaeaea; border: 1px solid #333333; border-radius: 2px; box-shadow: none; }
progressbar trough { background: #0d0d0d; border: 1px solid #333333; border-radius: 2px; min-height: 8px; }
progressbar progress { background: #e68e0d; border-radius: 2px; min-height: 8px; }
button { background-image: none; background: #1e1e1e; color: #bebebe; border: 1px solid #333333;
         border-radius: 2px; padding: 6px 16px; box-shadow: none; text-shadow: none; }
button:hover { background: #2a2a2a; }
button:disabled { color: #555555; }
button.link { background: none; border: none; color: #e68e0d; padding: 4px 8px; }
"""


class ControlPanel(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='NoctraOS Control Panel')
        self.set_default_size(920, 620)
        self.set_icon_name('noctraos-control')
        root = Gtk.Box()
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.set_size_request(200, -1)
        side.get_style_context().add_class('sidebar')
        brand = label('NoctraOS', 'brand', xalign=0)
        brand.set_margin_start(18)
        brand.set_margin_top(18)
        brand.set_margin_bottom(12)
        side.pack_start(brand, False, False, 0)
        self.list = Gtk.ListBox()
        self.list.get_style_context().add_class('sidebar')
        side.pack_start(self.list, True, True, 0)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True)
        self.stack.get_style_context().add_class('content')
        self.ids, self.pages = [], {}
        for page_id, title, cls in pages.PAGES:
            page = cls(self)
            self.pages[page_id] = page
            self.stack.add_named(page, page_id)
            row = Gtk.ListBoxRow()
            row.add(label(title, xalign=0, wrap=False))
            self.list.add(row)
            self.ids.append(page_id)
        self.list.connect('row-selected', self._selected)
        root.pack_start(side, False, False, 0)
        root.pack_start(self.stack, True, True, 0)
        self.add(root)
        self.open_page('overview')

    def _selected(self, _list, row):
        if row:
            page_id = self.ids[row.get_index()]
            self.stack.set_visible_child_name(page_id)
            self.pages[page_id].on_show()

    def open_page(self, page_id, recheck=False):
        """Switch to a page; ignore ids that are not built (a card may point at a later phase)."""
        if page_id not in self.ids:
            return
        self.list.select_row(self.list.get_row_at_index(self.ids.index(page_id)))
        if recheck and hasattr(self.pages[page_id], 'run_check'):
            self.pages[page_id].run_check()


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.add_main_option('page', 0, GLib.OptionFlags.NONE, GLib.OptionArg.STRING, 'Open on this page', 'PAGE')

    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_command_line(self, command_line):
        options = command_line.get_options_dict().end().unpack()
        window = self.props.active_window or ControlPanel(self)
        window.show_all()
        window.present()
        if options.get('page'):
            window.open_page(options['page'])
        return 0


if __name__ == '__main__':
    sys.exit(App().run(sys.argv))
