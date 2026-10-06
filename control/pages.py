"""GTK pages of the Control Panel. All logic that can be tested without GTK lives in panel.py."""
import os
import subprocess
import threading

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

import panel  # noqa: E402

LINKS = [('Website', 'https://noctraos.dev'), ('Source code', 'https://github.com/dazeb/noctraos'),
         ('Contact', 'mailto:admin@noctraos.dev')]


def label(text, *classes, xalign=0.0, wrap=True, selectable=False, chars=-1):
    item = Gtk.Label(label=text, xalign=xalign, wrap=wrap, selectable=selectable, max_width_chars=chars)
    for name in classes:
        item.get_style_context().add_class(name)
    return item


def button(text, *classes, on_click=None, tooltip=None):
    item = Gtk.Button(label=text)
    for name in classes:
        item.get_style_context().add_class(name)
    if on_click:
        item.connect('clicked', on_click)
    if tooltip:
        item.set_tooltip_text(tooltip)
    return item


def background(work, done):
    """Run work() on a thread, then done(result) on the GTK main loop."""
    def target():
        result = work()
        GLib.idle_add(lambda: done(result) and False)
    threading.Thread(target=target, daemon=True).start()


def clear(container):
    for child in container.get_children():
        container.remove(child)


def header(title, *right):
    """Title on the left, widgets packed to the right (first given ends up rightmost)."""
    box = Gtk.Box(spacing=10)
    box.pack_start(label(title, 'title'), True, True, 0)
    for widget in right:
        box.pack_end(widget, False, False, 0)
    return box


def copy_to_clipboard(text):
    Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)


class Page(Gtk.Box):
    """A sidebar page. on_show() is called each time it becomes the visible one."""

    def __init__(self, window, spacing=14):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=spacing, margin=24)
        self.window = window

    def on_show(self):
        pass

    def make_note(self):
        """A one-line status label that takes no room while it is empty."""
        note = label('', 'muted')
        note.set_no_show_all(True)
        self.pack_start(note, False, False, 0)
        return note

    @staticmethod
    def say(note, text):
        note.set_text(text)
        note.set_visible(bool(text))

    def scroller(self):
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.pack_start(scroller, True, True, 0)
        return scroller

    @staticmethod
    def swap(scroller, widget):
        child = scroller.get_child()
        if child:
            scroller.remove(child if child.get_parent() is scroller else child.get_parent())
        scroller.add(widget)
        scroller.show_all()


# ---- Overview --------------------------------------------------------------------------------

class CardWidget(Gtk.EventBox):
    def __init__(self, card, on_open):
        super().__init__()
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
            self.connect('button-release-event', lambda *_: on_open(card.page))
            self.connect('realize', lambda w: w.get_window().set_cursor(
                Gdk.Cursor.new_from_name(w.get_display(), 'pointer')))


class OverviewPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.spinner = Gtk.Spinner()
        self.pack_start(header('Overview', self.spinner, button('Refresh', on_click=lambda *_: self.refresh()),
                               button('Run health check', on_click=lambda *_: window.open_page('health', True))),
                        False, False, 0)
        self.pack_start(label('The state of this workstation.', 'lede'), False, False, 0)
        self.holder = self.scroller()
        self.refresh()

    def refresh(self):
        self.spinner.start()
        self.swap(self.holder, Gtk.Label(label='Checking…', xalign=0, margin_top=8))
        background(lambda: panel.noc_json('status'), self._loaded)

    def _loaded(self, status):
        self.spinner.stop()
        if status is None:
            self.swap(self.holder, label('Could not read the system state. Is `noc` installed? '
                                         'Run the installer again, then press Refresh.', 'muted'))
            return
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, row_spacing=12,
                           column_spacing=12, min_children_per_line=2, max_children_per_line=3,
                           valign=Gtk.Align.START)
        for card in panel.cards(status):
            flow.add(CardWidget(card, self.window.open_page))
        self.swap(self.holder, flow)


# ---- Health ----------------------------------------------------------------------------------

class HealthPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.rows = None
        self.checked = False
        self.spinner = Gtk.Spinner()
        self.recheck = button('Re-check', on_click=lambda *_: self.run_check())
        self.copy = button('Copy report', on_click=self._copy,
                           tooltip='The whole check as text for a bug report. No files or prompts.')
        self.pack_start(header('Health', self.spinner, self.recheck, self.copy), False, False, 0)
        self.headline = label('', 'lede')
        self.pack_start(self.headline, False, False, 0)
        self.note = self.make_note()
        self.holder = self.scroller()

    def on_show(self):
        if not self.checked:
            self.run_check()

    def run_check(self):
        self.checked = True
        self.spinner.start()
        self.recheck.set_sensitive(False)
        self.headline.set_text('Checking… this takes a few seconds.')
        background(lambda: panel.noc_json('doctor', '--json'), self._loaded)

    def _loaded(self, rows):
        self.spinner.stop()
        self.recheck.set_sensitive(True)
        self.rows = rows
        if rows is None:
            self.headline.set_text('The health check could not run.')
            self.swap(self.holder, label('`noc doctor` did not answer. Run the installer again, then press Re-check.',
                                         'muted'))
            return
        text, _level = panel.health_headline(rows)
        self.headline.set_text(text)
        listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listing.get_style_context().add_class('rows')
        for row in panel.sort_rows(rows):
            listing.add(self._row(row))
        self.swap(self.holder, listing)

    def _row(self, row):
        box = Gtk.Box(spacing=12, margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
        box.pack_start(label('●', 'mark', f'status-{row["status"]}', wrap=False), False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text.add(label(row['label'], 'row-title'))
        if row.get('detail'):
            text.add(label(row['detail'], 'card-detail', chars=70))
        box.pack_start(text, True, True, 0)
        argv = panel.fix_command(row.get('fix'))
        if argv:
            box.pack_end(button('Fix', on_click=lambda b, argv=argv: self._fix(b, argv),
                                tooltip=f'Runs: {" ".join(argv)}'), False, False, 0)
        return box

    def _fix(self, widget, argv):
        widget.set_sensitive(False)
        widget.set_label('Working…')
        self.say(self.note, 'Fixing… this can take a while. You can keep using the panel.')

        def work():
            try:
                return subprocess.run(argv, capture_output=True, text=True, timeout=3600).returncode == 0
            except (OSError, subprocess.SubprocessError):
                return False

        def done(ok):
            self.say(self.note, 'Fixed.' if ok else 'The fix did not finish. Run the check again for details.')
            self.run_check()
        background(work, done)

    def _copy(self, *_):
        if self.rows is None:
            self.say(self.note, 'Nothing to copy yet.')
            return
        copy_to_clipboard(panel.report_text(self.rows, os.uname().release))
        self.say(self.note, 'Copied. Paste it into your bug report.')


# ---- AI models -------------------------------------------------------------------------------

class ModelsPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.spinner = Gtk.Spinner()
        self.pack_start(header('AI models', self.spinner, button('Refresh', on_click=lambda *_: self.refresh())),
                        False, False, 0)
        self.sub = label('Models run on this computer through Ollama.', 'lede')
        self.pack_start(self.sub, False, False, 0)
        self.note = self.make_note()
        self.progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, no_show_all=True)
        self.progress_label = label('', 'card-detail')
        self.bar = Gtk.ProgressBar()
        self.cancel = button('Cancel', on_click=lambda *_: self._cancel())
        self.progress_box.add(self.progress_label)
        row = Gtk.Box(spacing=10)
        row.pack_start(self.bar, True, True, 0)
        row.pack_start(self.cancel, False, False, 0)
        self.progress_box.add(row)
        self.pack_start(self.progress_box, False, False, 0)
        self.holder = self.scroller()
        self.pulling = None   # name being downloaded, None when idle
        self.stop = False
        self.loaded = False
        self.buttons = []

    def on_show(self):
        if not self.loaded:
            self.refresh()

    def refresh(self):
        self.loaded = True
        self.spinner.start()

        def work():
            listing = panel.noc_json('models', 'list', '--json')
            return listing, panel.noc_json('models', 'presets', '--json')
        background(work, self._loaded)

    def _loaded(self, result):
        self.spinner.stop()
        listing, presets = result
        self.buttons = []
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_end=8)
        if listing is None or not listing.get('ollama'):
            body.add(label('Ollama is not running yet. It starts by itself after the first boot; '
                           'press Refresh in a minute.', 'muted'))
            self.swap(self.holder, body)
            return
        installed = panel.installed_rows(listing)
        body.add(label('Installed', 'section'))
        if not installed:
            body.add(label('No models yet. Pick one below.', 'muted'))
        for item in installed:
            body.add(self._installed_row(item))
        suggestions = panel.suggestion_rows(presets, [i['name'] for i in installed])
        if suggestions:
            hardware = f'{presets["ram_gb"]} GB RAM' + (f', {presets["vram_gb"]} GB video memory' if presets['vram_gb'] else '')
            body.add(label(f'Suggested for this computer ({hardware})', 'section'))
            for item in suggestions:
                body.add(self._suggestion_row(item))
        body.add(label('Another model', 'section'))
        body.add(self._custom_row())
        self.swap(self.holder, body)
        self._set_busy(self.pulling is not None)

    def _installed_row(self, item):
        box = Gtk.Box(spacing=10, margin_top=4)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        text.add(label(item['name'] + ('   default' if item['default'] else ''), 'row-title'))
        text.add(label(item['size'], 'card-detail'))
        box.pack_start(text, True, True, 0)
        remove = button('Remove', on_click=lambda *_: self._remove(item))
        box.pack_end(remove, False, False, 0)
        if not item['default']:
            make = button('Make default', on_click=lambda *_: self._make_default(item['name']),
                          tooltip='Used by Hermes, the Welcome app and "Ask AI to Explain".')
            box.pack_end(make, False, False, 0)
        return box

    def _suggestion_row(self, item):
        box = Gtk.Box(spacing=10, margin_top=4)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        text.add(label(item['name'] + ('   recommended' if item['recommended'] else ''), 'row-title'))
        text.add(label(f'{item["note"]}. {item["fit"]}.', 'card-detail', chars=60))
        box.pack_start(text, True, True, 0)
        download = button('Download', on_click=lambda *_: self.pull(item['name']))
        self.buttons.append(download)
        box.pack_end(download, False, False, 0)
        return box

    def _custom_row(self):
        box = Gtk.Box(spacing=10, margin_top=4)
        entry = Gtk.Entry(placeholder_text='for example llama3.2:3b', hexpand=True)
        download = button('Download', on_click=lambda *_: self._pull_custom(entry))
        entry.connect('activate', lambda *_: self._pull_custom(entry))
        self.buttons.append(download)
        box.pack_start(entry, True, True, 0)
        box.pack_start(download, False, False, 0)
        return box

    def _pull_custom(self, entry):
        name = entry.get_text().strip()
        if not panel.valid_model_name(name):
            self.say(self.note, 'That is not a model name. Use letters, digits and . _ : / - only.')
            return
        self.pull(name)

    # -- actions ---------------------------------------------------------------------------
    def _make_default(self, name):
        self.say(self.note, f'Setting {name} as the default…')

        def done(result):
            ok, message = result
            self.say(self.note, f'{name} is now the default.' if ok else f'Could not set the default: {message}')
            self.refresh()
        background(lambda: panel.noc_run('models', 'default', name), done)

    def _remove(self, item):
        extra = ('\n\nThis is the default model. Hermes, the Welcome app and "Ask AI to Explain" '
                 'will not work until you pick another.' if item['default'] else '')
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.NONE, text=f'Remove {item["name"]}?')
        dialog.format_secondary_text(f'It frees {item["size"]}. You can download it again later.{extra}')
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Remove', Gtk.ResponseType.OK)
        answer = dialog.run()
        dialog.destroy()
        if answer != Gtk.ResponseType.OK:
            return
        self.say(self.note, f'Removing {item["name"]}…')

        def done(result):
            ok, message = result
            self.say(self.note, f'Removed {item["name"]}.' if ok else f'Could not remove it: {message}')
            self.refresh()
        background(lambda: panel.noc_run('models', 'rm', item['name']), done)

    def pull(self, name):
        if self.pulling:
            return
        self.pulling, self.stop = name, False
        self.say(self.note, '')
        self.progress_box.show_all()
        self.progress_label.set_text(f'Starting {name}…')
        self.bar.set_fraction(0)
        self._set_busy(True)
        tracker = panel.PullTracker()

        def work():
            try:
                for event in panel.iter_pull(name, cancelled=lambda: self.stop):
                    fraction, text = tracker.feed(event)
                    GLib.idle_add(self._progress, name, fraction, text)
                    if event.get('error'):
                        return False, event['error']
                return (not self.stop), ('Cancelled.' if self.stop else '')
            except OSError as error:
                return False, f'Could not reach Ollama ({error})'

        def done(result):
            ok, message = result
            self.pulling = None
            self.progress_box.hide()
            self.say(self.note, f'{name} is ready.' if ok else (message or f'{name} did not finish.'))
            self._set_busy(False)
            self.refresh()
        background(work, done)

    def _progress(self, name, fraction, text):
        if self.pulling == name:
            self.progress_label.set_text(f'{name}: {text}')
            if fraction is None:
                self.bar.pulse()
            else:
                self.bar.set_fraction(fraction)
        return False

    def _cancel(self):
        self.stop = True
        self.progress_label.set_text('Cancelling…')

    def _set_busy(self, busy):
        for item in self.buttons:
            item.set_sensitive(not busy)


# ---- About -----------------------------------------------------------------------------------

class AboutPage(Page):
    def __init__(self, window):
        super().__init__(window, spacing=12)
        self.set_valign(Gtk.Align.START)
        self.status = None
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
            links.pack_start(button(name, 'link', on_click=lambda _b, uri=uri: Gtk.show_uri_on_window(
                window, uri, Gdk.CURRENT_TIME)), False, False, 0)
        self.pack_start(links, False, False, 0)
        copy = button('Copy diagnostics', on_click=self._copy,
                      tooltip='Version, hardware and update state as text for a bug report. No files or prompts.')
        copy.set_halign(Gtk.Align.START)
        copy.set_margin_top(6)
        self.pack_start(copy, False, False, 0)
        self.note = label('', 'muted')
        self.pack_start(self.note, False, False, 0)
        background(lambda: panel.noc_json('status'), self._loaded)

    def _loaded(self, status):
        self.status = status
        self.version.set_text(f'Version {status["version"]}' if status else 'Version unknown')

    def _copy(self, *_):
        copy_to_clipboard(panel.diagnostics_text(self.status or {}, os.uname().release))
        self.note.set_text('Copied. Paste it into your bug report.')


PAGES = [('overview', 'Overview', OverviewPage), ('models', 'AI models', ModelsPage),
         ('health', 'Health', HealthPage), ('about', 'About', AboutPage)]
