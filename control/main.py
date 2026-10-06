#!/usr/bin/python3
# System Python on purpose: it has PyGObject; a mise-managed python3 (first on PATH in a
# session) does not. bin/noctraos-control execs /usr/bin/python3 on this file.
"""noctraos-control — the NoctraOS Control Panel (design: docs/control-panel-plan.md).

A sidebar of pages in one GTK window. Every number comes from `noc ... --json`; the panel never
reimplements what the CLI does, so the two cannot drift. Slow calls run on a thread and the UI
only ever shows a spinner, never blocks.
"""
import os
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gi  # noqa: E402

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

import panel  # noqa: E402

APP_ID = 'local.noctraos.Control'
LINKS = [('Website', 'https://noctraos.dev'), ('Source code', 'https://github.com/dazeb/noctraos'),
         ('Contact', 'mailto:admin@noctraos.dev')]

# Same palette as the Welcome and Appearance windows (configs/theme/palette.json), 2 px corners.
CSS = b"""
window, .content { background: #121212; color: #bebebe; }
.sidebar { background: #0d0d0d; border-right: 1px solid #333333; }
.sidebar row { padding: 10px 18px; color: #bebebe; border-left: 3px solid transparent;
               font-family: 'JetBrainsMono Nerd Font', monospace; }
.sidebar row:hover { background: #1e1e1e; }
.sidebar row:selected { background: #1e1e1e; color: #eaeaea; border-left-color: #e68e0d; }
.brand { font-size: 15px; font-weight: bold; color: #eaeaea; }
.title { font-size: 24px; font-weight: bold; color: #eaeaea; }
.lede { font-size: 14px; color: #8a8a8d; }
.card { background: #1e1e1e; border: 1px solid #333333; border-left: 3px solid #333333;
        border-radius: 2px; padding: 14px 16px; }
.card.ok { border-left-color: #ffc107; }
.card.warn { border-left-color: #e68e0d; }
.card.clickable:hover { background: #2a2a2a; }
.card-title { color: #8a8a8d; font-size: 12px; font-family: 'JetBrainsMono Nerd Font', monospace; }
.card-value { color: #eaeaea; font-size: 17px; font-weight: bold; }
.card-detail { color: #8a8a8d; font-size: 13px; }
.muted { color: #8a8a8d; }
button { background-image: none; background: #1e1e1e; color: #bebebe; border: 1px solid #333333;
         border-radius: 2px; padding: 6px 16px; box-shadow: none; text-shadow: none; }
button:hover { background: #2a2a2a; }
button.link { background: none; border: none; color: #e68e0d; padding: 4px 8px; }
"""


def label(text, *classes, xalign=0.0, wrap=True, selectable=False, chars=-1):
    item = Gtk.Label(label=text, xalign=xalign, wrap=wrap, selectable=selectable, max_width_chars=chars)
    for name in classes:
        item.get_style_context().add_class(name)
    return item


def background(work, done):
    """Run work() on a thread, then done(result) on the GTK main loop."""
    def target():
        result = work()
        GLib.idle_add(lambda: done(result) and False)
    threading.Thread(target=target, daemon=True).start()


class CardWidget(Gtk.EventBox):
    def __init__(self, card, on_open):
        super().__init__()
        self.card, self.on_open = card, on_open
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class('card')
        box.get_style_context().add_class(card.level)
        # max_width_chars keeps a long sentence from making every card as wide as the window.
        box.add(label(card.title.upper(), 'card-title'))
        box.add(label(card.value, 'card-value', chars=26))
        if card.detail:
            box.add(label(card.detail, 'card-detail', chars=30))
        self.add(box)
        if card.page and on_open:
            box.get_style_context().add_class('clickable')
            self.connect('button-release-event', lambda *_: self.on_open(card.page))
            self.connect('realize', lambda w: w.get_window().set_cursor(
                Gdk.Cursor.new_from_name(w.get_display(), 'pointer')))


class OverviewPage(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=24)
        self.window = window
        head = Gtk.Box(spacing=12)
        head.pack_start(label('Overview', 'title'), True, True, 0)
        self.spinner = Gtk.Spinner()
        head.pack_end(self.spinner, False, False, 0)
        refresh = Gtk.Button(label='Refresh')
        refresh.connect('clicked', lambda *_: self.refresh())
        head.pack_end(refresh, False, False, 0)
        self.pack_start(head, False, False, 0)
        self.pack_start(label('The state of this workstation, checked just now.', 'lede'), False, False, 0)
        self.holder = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.pack_start(self.holder, True, True, 0)
        self.status = None
        self.refresh()

    def refresh(self):
        self.spinner.start()
        self._show(Gtk.Label(label='Checking…', xalign=0, margin_top=8))
        background(lambda: panel.noc_json('status'), self._loaded)

    def _loaded(self, status):
        self.spinner.stop()
        self.status = status
        if status is None:
            self._show(label('Could not read the system state. Is `noc` installed? '
                             'Run the installer again, then press Refresh.', 'muted'))
            return
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, row_spacing=12,
                           column_spacing=12, min_children_per_line=2, max_children_per_line=3, valign=Gtk.Align.START)
        for card in panel.cards(status):
            flow.add(CardWidget(card, self.window.open_page))
        self._show(flow)

    def _show(self, widget):
        child = self.holder.get_child()
        if child:
            self.holder.remove(child if child.get_parent() is self.holder else child.get_parent())
        self.holder.add(widget)
        self.holder.show_all()


class AboutPage(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=24, valign=Gtk.Align.START)
        self.window = window
        row = Gtk.Box(spacing=16)
        row.pack_start(Gtk.Image.new_from_icon_name('noctraos-logo', Gtk.IconSize.DIALOG), False, False, 0)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        col.add(label('NoctraOS', 'title'))
        self.version = label('', 'lede')
        col.add(self.version)
        row.pack_start(col, False, False, 0)
        self.pack_start(row, False, False, 0)
        self.pack_start(label('An AI development workstation OS: local AI models and AI coding '
                              'assistants ready when you are.', 'lede'), False, False, 0)
        self.pack_start(label('Built on Zorin OS, which is built on Ubuntu.', 'muted'), False, False, 0)
        self.pack_start(label('Licence: not chosen yet; all rights reserved until then.', 'muted'), False, False, 0)
        links = Gtk.Box(spacing=4, margin_top=6)
        for name, uri in LINKS:
            button = Gtk.Button(label=name)
            button.get_style_context().add_class('link')
            button.connect('clicked', lambda _b, uri=uri: Gtk.show_uri_on_window(window, uri, Gdk.CURRENT_TIME))
            links.pack_start(button, False, False, 0)
        self.pack_start(links, False, False, 0)
        copy = Gtk.Button(label='Copy diagnostics', halign=Gtk.Align.START, margin_top=6)
        copy.set_tooltip_text('Version, hardware and update state as text for a bug report. No files or prompts.')
        copy.connect('clicked', self._copy)
        self.pack_start(copy, False, False, 0)
        self.note = label('', 'muted')
        self.pack_start(self.note, False, False, 0)
        background(lambda: panel.noc_json('status'), self._loaded)

    def _loaded(self, status):
        self.status = status
        self.version.set_text(f'Version {status["version"]}' if status else 'Version unknown')

    def _copy(self, *_):
        text = panel.diagnostics_text(getattr(self, 'status', None) or {}, os.uname().release)
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)
        self.note.set_text('Copied. Paste it into your bug report.')


PAGES = [('overview', 'Overview', OverviewPage), ('about', 'About', AboutPage)]


class ControlPanel(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='NoctraOS Control Panel')
        self.set_default_size(920, 620)
        self.set_icon_name('noctraos-control')
        root = Gtk.Box()
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.set_size_request(200, -1)
        side.get_style_context().add_class('sidebar')
        side.pack_start(label('NoctraOS', 'brand', xalign=0), False, False, 0)
        side.get_children()[0].set_margin_start(18)
        side.get_children()[0].set_margin_top(18)
        side.get_children()[0].set_margin_bottom(12)
        self.list = Gtk.ListBox()
        self.list.get_style_context().add_class('sidebar')
        side.pack_start(self.list, True, True, 0)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True)
        self.stack.get_style_context().add_class('content')
        self.ids = []
        for page_id, title, cls in PAGES:
            self.stack.add_named(cls(self), page_id)
            row = Gtk.ListBoxRow()
            row.add(label(title, xalign=0, wrap=False))
            self.list.add(row)
            self.ids.append(page_id)
        self.list.connect('row-selected', self._selected)
        root.pack_start(side, False, False, 0)
        root.pack_start(self.stack, True, True, 0)
        self.add(root)
        self.list.select_row(self.list.get_row_at_index(0))

    def _selected(self, _list, row):
        if row:
            self.stack.set_visible_child_name(self.ids[row.get_index()])

    def open_page(self, page_id):
        """A card asked for a page; ignore ones that are not built yet."""
        if page_id in self.ids:
            self.list.select_row(self.list.get_row_at_index(self.ids.index(page_id)))


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        window = self.props.active_window or ControlPanel(self)
        window.show_all()
        window.present()


if __name__ == '__main__':
    sys.exit(App().run(sys.argv))
