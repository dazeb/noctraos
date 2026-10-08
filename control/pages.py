"""GTK pages of the Control Panel. All logic that can be tested without GTK lives in panel.py."""
import os
import subprocess
import threading

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

import panel  # noqa: E402

LINKS = [('Website', 'https://noctraos.dev'), ('Source code', 'https://github.com/dazeb/noctraos'),
         ('Contact', 'mailto:admin@noctraos.dev')]


LOGO_FILES = ['/usr/local/share/icons/hicolor/scalable/apps/noctraos-logo.svg',
              '/usr/share/icons/hicolor/scalable/apps/noctraos-logo.svg',
              os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'icons', 'noctraos-logo.svg')]


def logo_image(size):
    """The NoctraOS mark, `size` px tall at most. The icon theme first (it follows the screen scale); when the
    theme does not have it (a checkout, a machine without the icon installed) the SVG file itself, so the panel
    never shows a blank or a broken-image placeholder where the logo belongs."""
    if Gtk.IconTheme.get_default().has_icon('noctraos-logo'):
        image = Gtk.Image.new_from_icon_name('noctraos-logo', Gtk.IconSize.DIALOG)
        image.set_pixel_size(size)
        return image
    for path in LOGO_FILES:
        if os.path.isfile(path):
            try:
                return Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size))
            except GLib.Error:
                continue
    return Gtk.Image()


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


class RunLog(Gtk.Box):
    """A progress bar, a status line and an expandable log for a long job (updates, GPU setup)."""
    LINES = 2000

    def __init__(self, reminder='Keep the computer on until this finishes.'):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, no_show_all=True)
        self.label = label('', 'card-detail')
        self.bar = Gtk.ProgressBar()
        self.add(self.label)
        self.add(self.bar)
        self.add(label(reminder, 'muted'))
        expander = Gtk.Expander(label='Show details')
        view = Gtk.ScrolledWindow(min_content_height=150, hscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        self.view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
        view.add(self.view)
        expander.add(view)
        self.add(expander)

    def begin(self, text='Starting…'):
        self.view.get_buffer().set_text('')
        self.set_status(text, 0)
        self.set_no_show_all(False)
        self.show_all()
        self.set_no_show_all(True)

    def set_status(self, text, fraction=None):
        """fraction None pulses the bar (work of unknown length)."""
        self.label.set_text(text)
        if fraction is None:
            self.bar.pulse()
        else:
            self.bar.set_fraction(fraction)

    def append(self, line):
        buffer = self.view.get_buffer()
        buffer.insert(buffer.get_end_iter(), line + '\n')
        if buffer.get_line_count() > self.LINES:
            buffer.delete(buffer.get_start_iter(), buffer.get_iter_at_line(buffer.get_line_count() - self.LINES))
        self.view.scroll_to_mark(buffer.get_insert(), 0, False, 0, 0)


class Page(Gtk.Box):
    """A sidebar page. on_show() is called each time it becomes the visible one."""

    def __init__(self, window, spacing=14):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=spacing, margin=24)
        self.window = window

    def on_show(self):
        pass

    def reload(self):
        """Ctrl+R / F5: check this page again."""
        for name in ('refresh', 'run_check'):
            action = getattr(self, name, None)
            if action:
                action()
                return

    def make_note(self):
        """A one-line status label that takes no room while it is empty."""
        note = label('', 'muted')
        note.set_no_show_all(True)
        self.pack_start(note, False, False, 0)
        return note

    @staticmethod
    def reveal(box):
        """Show a no_show_all container and its children (show_all() skips such a widget)."""
        box.set_no_show_all(False)
        box.show_all()
        box.set_no_show_all(True)

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
            self.set_tooltip_text(f'Open {page_title(card.page)}')
            box.get_style_context().add_class('clickable')
            self.connect('button-release-event', lambda *_: on_open(card.page))
            self.connect('realize', lambda w: w.get_window().set_cursor(
                Gdk.Cursor.new_from_name(w.get_display(), 'pointer')))


class OverviewPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.spinner = Gtk.Spinner()
        self.pack_start(header('Overview', self.spinner, button('Refresh', on_click=lambda *_: self.refresh(), tooltip='Check again (Ctrl+R)'),
                               button('Run health check', on_click=lambda *_: window.open_page('health', True), tooltip='Open Health and check everything now')),
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
        self.recheck = button('Re-check', on_click=lambda *_: self.run_check(), tooltip='Run the checks again (Ctrl+R)')
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
        mark = label('●', 'mark', f'status-{row["status"]}', wrap=False)
        mark.set_tooltip_text({'ok': 'OK', 'warn': 'Could be better', 'fail': 'Needs attention'}.get(row['status'], 'Information'))
        box.pack_start(mark, False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        argv = panel.fix_command(row.get('fix'))
        text.add(label(row['label'], 'row-title'))
        detail = panel.clean_detail(row.get('detail'), bool(argv))
        if detail:
            text.add(label(detail, 'card-detail', chars=70))
        box.pack_start(text, True, True, 0)
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


# ---- Updates ---------------------------------------------------------------------------------

class UpdatesPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.running = False
        self.checks = {}
        self.spinner = Gtk.Spinner()
        self.pack_start(header('Updates', self.spinner, button('Refresh', on_click=lambda *_: self.refresh(), tooltip='Check again (Ctrl+R)')),
                        False, False, 0)
        self.pack_start(label('Choose what to update. Nothing changes until you press Update.', 'lede'),
                        False, False, 0)
        self.offline = self.make_note()
        self.holder = self.scroller()
        self.update_button = button('Update selected', 'suggested', on_click=lambda *_: self.start())
        self.update_button.set_halign(Gtk.Align.START)
        self.pack_start(self.update_button, False, False, 0)
        self.note = self.make_note()
        self.run = RunLog()
        self.pack_start(self.run, False, False, 0)

    def on_show(self):
        if not self.running:
            self.refresh()

    def refresh(self):
        if self.running:
            return
        self.spinner.start()
        self.update_button.set_sensitive(False)
        background(lambda: panel.noc_json('updates', timeout=120), self._loaded)

    def _loaded(self, updates):
        self.spinner.stop()
        if updates is None:
            self.say(self.offline, 'Could not check for updates. Is `noc` installed?')
            self.swap(self.holder, label('', 'muted'))
            return
        self.say(self.offline, panel.offline_message(updates))
        online = not panel.offline_message(updates)
        self.checks = {}
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_end=8)
        for row in panel.update_rows(updates):
            line = Gtk.Box(spacing=12, margin_top=6)
            check = Gtk.CheckButton()
            check.set_active(row['checked'] and online)
            check.set_sensitive(row['available'] and online)
            check.connect('toggled', lambda *_: self._sync())
            self.checks[row['id']] = check
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            text.add(label(row['title'], 'row-title'))
            text.add(label(row['detail'], 'card-detail', chars=70))
            line.pack_start(check, False, False, 0)
            line.pack_start(text, True, True, 0)
            body.add(line)
        if updates.get('reboot_required'):
            body.add(label('A restart is needed to finish an earlier update.', 'section'))
        self.swap(self.holder, body)
        self._sync()

    def _sync(self):
        """The button is live only when something is ticked (and the network is there)."""
        self.update_button.set_sensitive(
            not self.running and any(c.get_active() and c.get_sensitive() for c in self.checks.values()))

    # -- running ---------------------------------------------------------------------------
    def start(self):
        selected = [step for step, check in self.checks.items() if check.get_active()]
        if not selected or self.running:
            return
        self.running = True
        self.update_button.set_sensitive(False)
        for check in self.checks.values():
            check.set_sensitive(False)
        self.say(self.note, '')
        self.run.begin()
        progress = panel.UpdateProgress(selected)

        def work():
            code_message = ''
            for _ids, argv in panel.plan_chunks(selected):
                for event in panel.run_events(argv):
                    if event['event'] == 'exit':
                        code_message = code_message or panel.exit_message(event['code'])
                        continue
                    line = progress.feed(event)
                    GLib.idle_add(self._tick, progress, line)
                if code_message:
                    break
            return progress, code_message

        background(work, self._finished)

    def _tick(self, progress, line):
        self.run.set_status(progress.text, progress.display_fraction)
        if line:
            self.run.append(line)
        return False

    def _finished(self, result):
        progress, problem = result
        self.running = False
        self.run.hide()
        if problem:
            message = problem
        elif progress.failed:
            names = ', '.join(panel.STEP_TITLES.get(i, i) for i in progress.failed)
            message = f'Finished, but these did not complete: {names}. Open Show details next time for the reason.'
        else:
            message = 'Everything you picked is up to date.'
        if progress.reboot_required:
            message += ' Restart the computer to finish.'
        self.say(self.note, message)
        self.refresh()


# ---- AI models -------------------------------------------------------------------------------

class ModelsPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.spinner = Gtk.Spinner()
        self.pack_start(header('AI models', self.spinner, button('Refresh', on_click=lambda *_: self.refresh(), tooltip='Check again (Ctrl+R)')),
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
        text.add(label(item['size'] + (f'  ·  {item["can"]}' if item['can'] else ''), 'card-detail'))
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
        self.reveal(self.progress_box)
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


# ---- Hardware --------------------------------------------------------------------------------

class HardwarePage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.running = False
        self.detect = None
        self.free_bytes = None
        self.spinner = Gtk.Spinner()
        self.pack_start(header('Hardware', self.spinner, button('Refresh', on_click=lambda *_: self.refresh(), tooltip='Check again (Ctrl+R)')),
                        False, False, 0)
        self.headline = label('', 'lede')
        self.pack_start(self.headline, False, False, 0)
        self.holder = self.scroller()
        self.setup = button('Set up GPU for local AI…', 'suggested', on_click=lambda *_: self._confirm())
        self.setup.set_halign(Gtk.Align.START)
        self.setup.set_no_show_all(True)
        self.pack_start(self.setup, False, False, 0)
        self.note = self.make_note()
        self.run = RunLog()
        self.pack_start(self.run, False, False, 0)

    def on_show(self):
        if not self.running:
            self.refresh()

    def refresh(self):
        if self.running:
            return
        self.spinner.start()

        def work():
            return panel.gpu_json('detect', '--json'), panel.gpu_json('status', '--json'), panel.noc_json('status')
        background(work, self._loaded)

    def _loaded(self, result):
        self.spinner.stop()
        detect, gstatus, status = result
        self.detect = detect
        self.free_bytes = ((status or {}).get('disk') or {}).get('root_free_bytes')
        state = panel.hardware_state(detect, gstatus)
        self.headline.set_text(state['headline'])
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_end=8)
        body.add(label('Graphics', 'section'))
        for gpu in state['gpus']:
            body.add(label(gpu['name'], 'row-title'))
            body.add(label(gpu['verdict'], 'card-detail', chars=80))
        if not state['gpus']:
            body.add(label('No NVIDIA or AMD GPU was found.', 'muted'))
        if state['rows']:
            body.add(label('Status', 'section'))
            for row in state['rows']:
                line = Gtk.Box(spacing=10)
                mark = {'ok': 'ok', 'fail': 'fail'}.get(row['status'], 'info')
                line.pack_start(label('●', 'mark', f'status-{mark}', wrap=False), False, False, 0)
                line.pack_start(label(row['text'], 'card-detail', chars=80), True, True, 0)
                body.add(line)
        body.add(label('Memory and disk', 'section'))
        if status:
            body.add(label(f'{status.get("ram_gb")} GB of RAM', 'card-detail'))
            disk = status.get('disk') or {}
            if disk:
                body.add(label(f'{panel.fmt_bytes(disk["root_free_bytes"])} free of '
                               f'{panel.fmt_bytes(disk["root_total_bytes"])} on the system disk', 'card-detail'))
        self.swap(self.holder, body)
        self.setup.set_visible(state['can_install'])

    # -- install: always an explicit summary and a yes -------------------------------------
    def _confirm(self):
        if self.running or self.detect is None:
            return
        blocker = panel.install_blocker(self.detect, self.free_bytes)
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.NONE, text='Set up your GPU for local AI?')
        dialog.format_secondary_text('\n'.join(panel.install_summary(self.detect)) + (f'\n\n{blocker}' if blocker else ''))
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        if not blocker:
            dialog.add_button('Install', Gtk.ResponseType.OK)
        answer = dialog.run()
        dialog.destroy()
        if answer == Gtk.ResponseType.OK:
            self._install()

    def _install(self):
        argv = panel.gpu_install_argv(self.detect)
        if not argv:
            return
        self.running = True
        self.setup.set_sensitive(False)
        self.say(self.note, '')
        self.run.begin('Setting up the GPU…')

        def work():
            problem = ''
            for event in panel.run_events(argv):
                if event['event'] == 'exit':
                    return event['code'], panel.exit_message(event['code'])
                GLib.idle_add(self._tick, event.get('line') or '')
            return 1, problem

        background(work, self._finished)

    def _tick(self, line):
        if line:
            self.run.append(line)
        self.run.set_status('Setting up the GPU…', None)
        return False

    def _finished(self, result):
        code, problem = result
        self.running = False
        self.run.hide()
        self.setup.set_sensitive(True)
        if code == 0:
            self.say(self.note, 'Done. Check the status above; a restart may be needed to finish.')
        else:
            self.say(self.note, problem or 'The setup did not finish. Open Show details next time for the reason.')
        self.refresh()


# ---- Privacy ---------------------------------------------------------------------------------

class PrivacyPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.mode = None
        self.syncing = False
        self.spinner = Gtk.Spinner()
        self.pack_start(header('Privacy', self.spinner, button('Refresh', on_click=lambda *_: self.refresh(), tooltip='Check again (Ctrl+R)')),
                        False, False, 0)
        self.pack_start(label('Where what you type can go, and the settings that decide it.', 'lede'),
                        False, False, 0)
        scroller = self.scroller()
        self.note = self.make_note()
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_end=8)
        body.add(label('Hermes', 'section'))
        self.hermes_head = label('', 'row-title')
        self.hermes_text = label('', 'card-detail', chars=80)
        body.add(self.hermes_head)
        body.add(self.hermes_text)
        self.local = Gtk.RadioButton.new_with_label_from_widget(None, 'Local only: nothing leaves this computer')
        self.cloud = Gtk.RadioButton.new_with_label_from_widget(self.local, 'Nous free tier (cloud): what you type leaves this computer')
        for radio, target in ((self.local, 'local'), (self.cloud, 'cloud')):
            radio.connect('toggled', lambda r, target=target: self._toggled(r, target))
            body.add(radio)
        body.add(label('A change applies the next time Hermes starts: close it and open it again.', 'muted'))
        body.add(label('Search', 'section'))
        body.add(label('Super+Space searches apps, files in your home folder, clipboard history, the web and '
                       'browser history. Each of those can be switched off, and the folders chosen.',
                       'card-detail', chars=80))
        body.add(self._launch_button('Search settings…', panel.SEARCH_SETTINGS))
        body.add(label('Weather', 'section'))
        body.add(label('Off until you pick a city. Only the city name you type is sent, to Open-Meteo, '
                       'to look up the weather.', 'card-detail', chars=80))
        body.add(self._launch_button('Weather settings…', panel.WEATHER_SETUP))
        scroller.add(body)
        self.sync_controls(None)

    def _launch_button(self, text, argv):
        item = button(text, on_click=lambda *_: self._launch(argv))
        item.set_halign(Gtk.Align.START)
        return item

    def _launch(self, argv):
        try:
            subprocess.Popen(argv, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self.say(self.note, 'That settings window could not be opened.')

    def on_show(self):
        self.say(self.note, '')
        self.refresh()

    def refresh(self):
        self.spinner.start()
        background(panel.hermes_mode, self._loaded)

    def _loaded(self, mode):
        self.spinner.stop()
        self.sync_controls(mode)

    def sync_controls(self, mode):
        self.mode = mode
        info = panel.hermes_privacy(mode)
        self.hermes_head.set_text(info['headline'])
        self.hermes_text.set_text(info['text'])
        self.syncing = True
        self.local.set_active(mode == 'local')
        self.cloud.set_active(mode == 'cloud')
        self.syncing = False
        for radio in (self.local, self.cloud):
            radio.set_sensitive(info['can_switch'])

    def _toggled(self, radio, target):
        if self.syncing or not radio.get_active():
            return
        argv = panel.switch_command(target, self.mode)
        if not argv:
            return
        if target == 'cloud' and not self._confirm_cloud():
            self.sync_controls(self.mode)
            return
        self.say(self.note, 'Switching…')

        def done(result):
            ok, message = result
            self.say(self.note, 'Done. It applies the next time Hermes starts.' if ok else f'Could not switch: {message}')
            self.refresh()
        background(lambda: panel.run_ok(argv), done)

    def _confirm_cloud(self):
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.NONE, text='Send what you type to Hermes to the cloud?')
        dialog.format_secondary_text("The Nous free tier is Nous Research's cloud service. What you type to "
                                     'Hermes will leave this computer. You can switch back any time.')
        dialog.add_buttons('Keep it local', Gtk.ResponseType.CANCEL, 'Use the cloud', Gtk.ResponseType.OK)
        answer = dialog.run()
        dialog.destroy()
        return answer == Gtk.ResponseType.OK


# ---- About -----------------------------------------------------------------------------------

class AboutPage(Page):
    def __init__(self, window):
        super().__init__(window, spacing=12)
        self.set_valign(Gtk.Align.START)
        self.status = None
        row = Gtk.Box(spacing=16)
        row.pack_start(logo_image(96), False, False, 0)
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


def page_title(page_id):
    """The sidebar name of a page ("AI models", not "Ai Models")."""
    return next((title for pid, title, _ in PAGES if pid == page_id), page_id)


PAGES = [('overview', 'Overview', OverviewPage), ('updates', 'Updates', UpdatesPage),
         ('models', 'AI models', ModelsPage), ('hardware', 'Hardware', HardwarePage),
         ('health', 'Health', HealthPage), ('privacy', 'Privacy', PrivacyPage), ('about', 'About', AboutPage)]
