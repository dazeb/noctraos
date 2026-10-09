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

    def terminal_button(self, key):
        """A small "Terminal" button: hovering shows the commands for this action in a terminal, clicking copies them. The
        commands stay out of sight for anyone who never looks (mouse first, terminal a close second: docs/objectives.md)."""
        def copy(*_):
            copy_to_clipboard(panel.terminal_commands(key))
            note = getattr(self, 'note', None)
            if note:
                self.say(note, 'Copied. Paste it into a terminal.')
        return button('Terminal', 'terminal', on_click=copy, tooltip=panel.terminal_tip(key))

    @staticmethod
    def tucked(widget):
        """A widget that starts hidden and is shown or hidden with set_visible() (window.show_all() leaves it alone)."""
        widget.show_all()
        widget.set_no_show_all(True)
        widget.hide()
        return widget

    def skip_chore(self, chore, skip=True):
        """Record that the person will do `chore` themselves (or take that back), then check the page again."""
        argv = panel.skip_command(chore, skip)
        if not argv:
            return

        def done(result):
            ok, message = result
            if not ok:
                self.say(self.note, f'Could not save that choice: {message}')
            elif skip:
                self.say(self.note, f'Okay, {panel.SKIPPABLE[chore]} is yours. The terminal commands are shown below.')
            else:
                self.say(self.note, 'Back on. You can set it up here whenever you like.')
            self.refresh()
        background(lambda: panel.run_ok(argv), done)

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
    MARKS = {'done': ('✓', 'status-ok'), 'todo': ('●', 'status-warn'), 'skipped': ('–', 'status-info'), 'waiting': ('…', 'status-info')}

    def __init__(self, window):
        super().__init__(window)
        self.spinner = Gtk.Spinner()
        self.pack_start(header('Overview', self.spinner, button('Refresh', on_click=lambda *_: self.refresh(), tooltip='Check again (Ctrl+R)'),
                               button('Run health check', on_click=lambda *_: window.open_page('health', True), tooltip='Open Health and check everything now')),
                        False, False, 0)
        self.pack_start(label('The state of this workstation, and what is left to set up.', 'lede'), False, False, 0)
        self.holder = self.scroller()
        self.refresh()

    def on_show(self):
        # Coming back from Accounts or Hardware: the checklist should already show what was just done.
        if getattr(self, 'loaded', False):
            self.refresh()

    def refresh(self):
        self.spinner.start()
        self.swap(self.holder, Gtk.Label(label='Checking…', xalign=0, margin_top=8))
        background(lambda: (panel.noc_json('status'), panel.setup_extras()), self._loaded)

    def _loaded(self, result):
        status, extras = result
        self.spinner.stop()
        self.loaded = True
        if status is None:
            self.swap(self.holder, label('Could not read the system state. Is `noc` installed? '
                                         'Run the installer again, then press Refresh.', 'muted'))
            return
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_end=8)
        body.add(self._setup_section(panel.setup_steps(status, extras)))
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, row_spacing=12,
                           column_spacing=12, min_children_per_line=2, max_children_per_line=3,
                           valign=Gtk.Align.START)
        for card in panel.cards(status):
            flow.add(CardWidget(card, self.window.open_page))
        body.add(flow)
        self.swap(self.holder, body)

    def _setup_section(self, steps):
        """Every first-run step with its state. Finished steps are only counted; what is left (and what was skipped, so the
        way back stays in sight) gets a row with a button that does it."""
        headline, level = panel.setup_summary(steps)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.get_style_context().add_class('card')
        box.get_style_context().add_class(level)
        box.add(label('SETUP', 'card-title'))
        box.add(label(headline, 'card-value'))
        shown = [s for s in steps if s.state != 'done']
        done = len(steps) - len(shown)
        if done and shown:
            box.add(label(f'{done} of {len(steps)} steps done.', 'card-detail'))
        for step in shown:
            box.add(self._step_row(step))
        return box

    def _step_row(self, step):
        row = Gtk.Box(spacing=12, margin_top=6)
        mark, css = self.MARKS[step.state]
        row.pack_start(label(mark, 'mark', css, xalign=0.5, wrap=False), False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text.add(label(step.title + ('  (optional)' if step.optional else ''), 'row-title', xalign=0, wrap=False))
        text.add(label(step.text, 'card-detail', chars=70))
        row.pack_start(text, True, True, 0)
        if step.state != 'waiting' or step.page:
            classes = ['suggested'] if step.state == 'todo' and not step.optional else []
            action = button(step.button, *classes, on_click=lambda *_: self._do(step))
            action.set_valign(Gtk.Align.CENTER)       # a tall row must not stretch its button
            row.pack_end(action, False, False, 0)
        return row

    def _do(self, step):
        if step.launch:
            try:
                subprocess.Popen(list(step.launch), start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass
        elif step.page:
            self.window.open_page(step.page)


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
        self.pack_start(header('Health', self.spinner, self.recheck, self.copy, self.terminal_button('health')), False, False, 0)
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
        self.pack_start(header('Updates', self.spinner, button('Refresh', on_click=lambda *_: self.refresh(), tooltip='Check again (Ctrl+R)'),
                               self.terminal_button('updates')), False, False, 0)
        self.pack_start(label('Choose what to update. Nothing changes until you press Update.', 'lede'),
                        False, False, 0)
        self.offline = self.make_note()
        self.holder = self.scroller()
        self.layer = self._layer_box()
        self.pack_start(self.layer, False, False, 0)
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
        background(panel.layer_status, self._layer_loaded)

    # -- the NoctraOS layer: channel and going back ------------------------------------------
    def _layer_box(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add(label('NoctraOS updates', 'section'))
        self.layer_head = label('', 'row-title')
        self.layer_problem = label('', 'status-warn', chars=80)
        box.add(self.layer_head)
        box.add(self.layer_problem)
        self.syncing = False
        self.channel_radios = {}
        group = None
        for channel, (title, text) in panel.CHANNELS.items():
            radio = Gtk.RadioButton.new_with_label_from_widget(group, f'{title}: {text}')
            group = group or radio
            radio.connect('toggled', lambda r, channel=channel: self._channel_toggled(r, channel))
            self.channel_radios[channel] = radio
            box.add(radio)
        self.layer_state = None
        self.rollback = button('Go back to the previous update', on_click=lambda *_: self._rollback(),
                               tooltip='Puts the previous version of the NoctraOS features back. Your files and settings stay.')
        self.rollback.set_halign(Gtk.Align.START)
        box.add(self.rollback)
        return self.tucked(box)

    def _layer_loaded(self, status):
        self.layer_state = status
        summary = panel.layer_summary(status)
        self.layer_head.set_text(summary['headline'])
        self.layer_problem.set_text(summary['problem'])
        self.layer_problem.set_visible(bool(summary['problem']))
        self.syncing = True
        for channel, radio in self.channel_radios.items():
            radio.set_active(channel == summary['channel'])
            radio.set_visible(summary['channel'] is not None)
            radio.set_sensitive(not self.running)
        self.syncing = False
        self.rollback.set_visible(summary['can_rollback'])
        self.layer.set_visible(True)

    def _channel_toggled(self, radio, channel):
        current = (self.layer_state or {}).get('channel')
        argv = panel.channel_command(channel, current)
        if self.syncing or not radio.get_active() or not argv:
            return
        if channel == 'nightly' and not self._confirm(
                'Follow the nightly channel?', 'Nightly updates arrive before they are fully tested and can break things. '
                'You can switch back to stable any time, but updates never go backwards, so stable will not '
                'change anything until it catches up.', 'Use nightly'):
            self._layer_loaded(self.layer_state)
            return
        self._run_layer(argv, 'Switching…', 'Done. You are on the ' + channel + ' channel.')

    def _rollback(self):
        argv = panel.rollback_command(self.layer_state)
        if argv and self._confirm('Go back to the previous update?', 'The previous version of the NoctraOS features is put back. '
                                  'Your files and settings are not touched, and steps that already ran are not undone. '
                                  'That update is not offered again; the next one is.',
                                  'Go back'):
            self._run_layer(argv, 'Going back…', 'Done. The previous update is back.')

    def _run_layer(self, argv, working, finished):
        self.say(self.note, working)

        def done(result):
            ok, message = result
            self.say(self.note, finished if ok else f'That did not work: {message}')
            self.refresh()
        background(lambda: panel.run_ok(argv, timeout=600), done)

    def _confirm(self, title, text, action):
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.NONE, text=title)
        dialog.format_secondary_text(text)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, action, Gtk.ResponseType.OK)
        answer = dialog.run()
        dialog.destroy()
        return answer == Gtk.ResponseType.OK

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


# ---- Accounts --------------------------------------------------------------------------------

class AccountsPage(Page):
    """The two things that stop a newcomer's first git commit and push, done without a terminal: the name and e-mail
    Git signs work with, and signing in to GitHub (the browser device flow: a short code, approved on github.com)."""

    def __init__(self, window):
        super().__init__(window)
        self.loaded = False
        self.signing = False
        self.cancelled = False
        self.proc = None
        self.state = None
        self.spinner = Gtk.Spinner()
        self.pack_start(header('Accounts', self.spinner,
                               button('Refresh', on_click=lambda *_: self.refresh(), tooltip='Check again (Ctrl+R)')),
                        False, False, 0)
        self.headline = label('', 'lede')
        self.pack_start(self.headline, False, False, 0)
        self.note = self.make_note()

        # -- Git: who the work is signed as
        self.pack_start(label('Your name for Git', 'section'), False, False, 6)
        self.pack_start(label('Git stamps every change you save with a name and an e-mail address. Without them it '
                              'refuses to save anything. It is only a label: nothing is sent anywhere by entering it.',
                              'card-detail', chars=80), False, False, 0)
        self.git_form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        grid = Gtk.Grid(column_spacing=12, row_spacing=8)
        self.name = Gtk.Entry(placeholder_text='Your name', hexpand=True, width_chars=34)
        self.email = Gtk.Entry(placeholder_text='you@example.com', hexpand=True, width_chars=34)
        for row, (text, entry) in enumerate((('Name', self.name), ('E-mail', self.email))):
            grid.attach(label(text, 'muted', xalign=0, wrap=False), 0, row, 1, 1)
            grid.attach(entry, 1, row, 1, 1)
            entry.connect('activate', lambda *_: self.save())
        self.git_form.add(grid)
        self.save_button = button('Save', 'suggested', on_click=lambda *_: self.save())
        self.skip_git = button("No, I'll set up Git myself", 'link', on_click=lambda *_: self.skip_chore('git'),
                               tooltip='Nothing is saved. The terminal commands are shown here instead.')
        self.terminal_git = self.terminal_button('git')
        git_buttons = Gtk.Box(spacing=10)
        for item in (self.save_button, self.skip_git, self.terminal_git):
            git_buttons.pack_start(item, False, False, 0)
        git_buttons.set_halign(Gtk.Align.START)
        self.git_form.add(git_buttons)
        self.pack_start(self.git_form, False, False, 0)
        self.git_note = label('', 'card-detail', chars=80)
        self.pack_start(self.git_note, False, False, 0)
        self.git_skipped = self.tucked(self._skipped_box('git'))
        self.pack_start(self.git_skipped, False, False, 0)

        # -- GitHub: signing in
        self.pack_start(label('GitHub', 'section'), False, False, 10)
        self.pack_start(label('GitHub is where projects live online. Sign in once and your AI tools can save and share '
                              'your work. You approve it in your browser; no password is typed here.', 'card-detail',
                              chars=80), False, False, 0)
        self.github_status = label('', 'row-title')
        self.pack_start(self.github_status, False, False, 0)
        buttons = Gtk.Box(spacing=10)
        self.signin = button('Sign in to GitHub', 'suggested', on_click=lambda *_: self.sign_in())
        self.signout = button('Sign out', on_click=lambda *_: self.sign_out())
        self.use_github = button('Use my GitHub name and e-mail', on_click=lambda *_: self.use_github_details(),
                                 tooltip='Fills in and saves the name and e-mail from your GitHub account.')
        self.skip_github = button("No, I'll set up GitHub myself", 'link', on_click=lambda *_: self.skip_chore('github'),
                                  tooltip='You stay signed out. The terminal commands are shown here instead.')
        self.terminal_github = self.terminal_button('github')
        for b in (self.signin, self.use_github, self.signout, self.skip_github, self.terminal_github):
            buttons.pack_start(b, False, False, 0)
        self.pack_start(buttons, False, False, 0)
        self.private = Gtk.CheckButton(label='Keep my e-mail private (recommended)', active=True)
        self.private.set_tooltip_text("Uses GitHub's private address, which works even when your e-mail is hidden on GitHub.")
        self.pack_start(self.private, False, False, 0)
        self.github_skipped = self.tucked(self._skipped_box('github'))
        self.pack_start(self.github_skipped, False, False, 0)

        # -- the one-time code, shown while the person approves in the browser
        self.code_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, no_show_all=True)
        self.code_box.get_style_context().add_class('card')
        self.code_box.add(label('1. Copy this code', 'row-title'))
        self.code = Gtk.Label(selectable=True, xalign=0.0)
        self.code_box.add(self.code)
        row = Gtk.Box(spacing=10)
        self.copy_code = button('Copy code', on_click=lambda *_: self._copy())
        self.open_github = button('Open GitHub', 'suggested', on_click=lambda *_: self._open())
        row.pack_start(self.copy_code, False, False, 0)
        row.pack_start(self.open_github, False, False, 0)
        self.code_box.add(row)
        self.code_box.add(label('2. On the GitHub page, paste the code and press Authorize. This window finishes by itself.',
                                'card-detail', chars=70))
        self.cancel = button('Cancel', on_click=lambda *_: self._cancel())
        self.cancel.set_halign(Gtk.Align.START)
        self.code_box.add(self.cancel)
        self.pack_start(self.code_box, False, False, 6)
        self.code_text = self.code_url = ''

    def on_show(self):
        if not self.loaded:
            self.refresh()

    def refresh(self):
        if self.signing:
            return
        self.loaded = True
        self.spinner.start()
        background(lambda: (panel.noc_json('accounts', 'status', '--json', timeout=60),
                            panel.noc_json('skip', 'list', '--json')), self._loaded)

    def _skipped_box(self, chore):
        """What replaces a chore the person skipped: the commands for doing it themselves, and a way back."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.add(label(panel.skipped_text(chore), 'card-detail', chars=80, selectable=True))
        again = button('Set it up here after all', on_click=lambda *_: self.skip_chore(chore, False))
        again.set_halign(Gtk.Align.START)
        box.add(again)
        return box

    def _loaded(self, result):
        self.spinner.stop()
        data, skipped = result
        state = panel.accounts_state(data, skipped)
        self.state = state
        if state is None:
            self.headline.set_text('The accounts helper did not answer. Update the NoctraOS features (Updates page) first.')
            return
        if state['done']:
            headline = 'Everything is set up.'
        elif state['todo']:
            headline = ('Two quick things' if len(state['todo']) == 2 else 'One quick thing') + \
                ' to do once, so your AI tools can save and share your work.'
        else:
            headline = 'Nothing left for you here. You chose to do the rest yourself.'
        self.headline.set_text(headline)
        if not self.name.get_text().strip():
            self.name.set_text(state['name'])
        if not self.email.get_text().strip():
            self.email.set_text(state['email'])
        self.git_note.set_text(('✓ ' + state['git_text'] + (f' <{state["email"]}>.' if state['email'] else '.'))
                               if state['git_ready'] else '' if state['git_skipped'] else 'Not set yet.')
        self.github_status.set_text(('✓ ' + state['github_text'] + '.') if state['signed_in'] else state['github_text'] + '.')
        busy = self.signing
        # A chore the person chose to do themselves shows its terminal commands instead of the form or the button.
        self.git_form.set_visible(not state['git_skipped'])
        self.skip_git.set_visible(not state['git_ready'])
        self.terminal_git.set_visible(not state['git_ready'])
        self.git_skipped.set_visible(state['git_skipped'])
        self.github_status.set_visible(not state['github_skipped'])
        self.github_skipped.set_visible(state['github_skipped'])
        self.signin.set_visible(not state['signed_in'] and state['gh_installed'] and not state['github_skipped'])
        self.signin.set_sensitive(not busy)
        self.skip_github.set_visible(not state['signed_in'] and not state['github_skipped'])
        self.skip_github.set_sensitive(not busy)
        self.terminal_github.set_visible(not state['signed_in'] and not state['github_skipped'])
        self.signout.set_visible(state['signed_in'])
        self.use_github.set_visible(state['signed_in'])
        self.private.set_visible(state['signed_in'] or self.signing)

    # -- Git identity ----------------------------------------------------------------------
    def save(self, quiet=False):
        name, email = self.name.get_text().strip(), self.email.get_text().strip()
        problem = panel.identity_problem(name, email)
        if problem:
            self.say(self.note, problem)
            return
        self.save_button.set_sensitive(False)

        def done(result):
            ok, message = result
            self.save_button.set_sensitive(True)
            self.say(self.note, (f'Saved. Git will sign your work as {name}.' if ok else f'Could not save: {message}'))
            self.refresh()
        background(lambda: panel.run_ok([panel.NOC, 'accounts', 'git', 'set', '--name', name, '--email', email]), done)

    def use_github_details(self):
        self.say(self.note, 'Reading your GitHub account…')
        self.use_github.set_sensitive(False)
        background(lambda: panel.noc_json('accounts', 'github', 'suggest', '--json', timeout=60), self._suggested)

    def _suggested(self, suggestion):
        self.use_github.set_sensitive(True)
        fill = panel.suggested_identity(suggestion, self.private.get_active())
        if fill is None:
            self.say(self.note, 'Could not read your GitHub account. Check the connection and try again.')
            return
        self.name.set_text(fill[0])
        self.email.set_text(fill[1])
        self.save()

    # -- GitHub sign-in --------------------------------------------------------------------
    def sign_in(self):
        if self.signing:
            return
        self.signing = True
        self.cancelled = False
        self.signin.set_sensitive(False)
        self.say(self.note, 'Starting the sign-in…')

        def work():
            result = {'ok': False, 'message': 'The sign-in did not finish.'}
            try:
                self.proc = subprocess.Popen(panel.ACCOUNTS_LOGIN, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                             text=True, bufsize=1)
            except OSError as error:
                return {'ok': False, 'message': str(error)}
            for line in self.proc.stdout:
                event = panel.parse_event(line)
                if not event:
                    continue
                if event['event'] == 'code':
                    GLib.idle_add(self._show_code, event['code'], event['url'])
                elif event['event'] == 'done':
                    result = event
            self.proc.wait()
            return result
        background(work, self._signed_in)

    def _show_code(self, code, url):
        self.code_text, self.code_url = code, url
        self.code.set_markup(f'<span size="xx-large" weight="bold" font_family="monospace">{GLib.markup_escape_text(code)}</span>')
        self.say(self.note, '')
        self.reveal(self.code_box)
        self._copy()                      # the code is already on the clipboard: they only have to paste it
        self._open()                      # and the page to paste it on is the next thing they need
        return False

    def _copy(self):
        if self.code_text:
            copy_to_clipboard(self.code_text)

    def _open(self):
        if self.code_url:
            Gtk.show_uri_on_window(self.window, self.code_url, Gdk.CURRENT_TIME)

    def _cancel(self):
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    def _signed_in(self, result):
        self.signing = False
        self.proc = None
        self.code_box.set_no_show_all(True)
        self.code_box.hide()
        if result.get('ok'):
            self.say(self.note, f'Signed in to GitHub as {result.get("login") or "your account"}.')
            self.refresh()
            if not (self.state and self.state['git_ready']) and not self.email.get_text().strip():
                self.use_github_details()            # also fills in the Git name and e-mail, in the same click
        else:
            self.say(self.note, 'Sign-in cancelled.' if self.cancelled else
                     f'Could not sign in: {result.get("message") or "the sign-in did not finish"}')
            self.refresh()

    def sign_out(self):
        self.say(self.note, 'Signing out…')
        background(lambda: panel.run_ok([panel.NOC, 'accounts', 'github', 'logout']),
                   lambda result: (self.say(self.note, 'Signed out of GitHub.' if result[0] else f'Could not sign out: {result[1]}'),
                                   self.refresh()))


# ---- Apps ------------------------------------------------------------------------------------

class AppsPage(Page):
    """The apps NoctraOS takes from their publishers (Hermes, Ollama, AppManager, the coding agents): the version
    that is installed, the newest release, and a button to move to it."""

    def __init__(self, window):
        super().__init__(window)
        self.loaded = False
        self.running = False
        self.buttons = []
        self.spinner = Gtk.Spinner()
        self.pack_start(header('Apps', self.spinner,
                               button('Check now', on_click=lambda *_: self.refresh(force=True),
                                      tooltip='Look up the newest releases again (Ctrl+R)'),
                               self.terminal_button('apps')), False, False, 0)
        self.headline = label('', 'lede')
        self.pack_start(self.headline, False, False, 0)
        self.note = self.make_note()
        self.holder = self.scroller()
        self.run = RunLog()
        self.pack_start(self.run, False, False, 0)

    def on_show(self):
        if not self.loaded and not self.running:
            self.refresh()

    def refresh(self, force=False):
        if self.running:
            return
        self.loaded = True
        self.spinner.start()
        self.headline.set_text('Checking the newest releases…' if force else 'Reading the app versions…')
        args = ['apps', '--json'] + (['--refresh'] if force else [])
        background(lambda: panel.noc_json(*args, timeout=150), self._loaded)

    def _loaded(self, data):
        self.spinner.stop()
        self.headline.set_text(panel.apps_headline(data))
        self.buttons = []
        if data is None:
            self.swap(self.holder, label('`noc apps` did not answer. Update the NoctraOS features first (Updates page), '
                                         'then press Check now.', 'muted'))
            return
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_end=8)
        agents_started = False
        for row in panel.apps_rows(data):
            if row['agent'] and not agents_started:
                agents_started = True
                body.add(label('Coding agents', 'section'))
            body.add(self._row(row))
        self.swap(self.holder, body)

    def _row(self, row):
        box = Gtk.Box(spacing=12, margin_top=6)
        mark = label('●', 'mark', f'status-{row["level"]}', wrap=False)
        box.pack_start(mark, False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text.add(label(row['title'] + (f'   {row["about"]}' if row['about'] else ''), 'row-title'))
        text.add(label(row['status'], 'card-detail', chars=70))
        if row['detail']:
            text.add(label(row['detail'], 'muted', chars=70))
        box.pack_start(text, True, True, 0)
        if row['argv']:
            update = button('Update', 'suggested', on_click=lambda *_: self.update(row))
            self.buttons.append(update)
            box.pack_end(update, False, False, 0)
        return box

    def update(self, row):
        if self.running or not row['argv']:
            return
        if row['confirm']:
            dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.QUESTION,
                                       buttons=Gtk.ButtonsType.NONE, text=f'Update {row["title"]}?')
            dialog.format_secondary_text(row['confirm'])
            dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Update', Gtk.ResponseType.OK)
            answer = dialog.run()
            dialog.destroy()
            if answer != Gtk.ResponseType.OK:
                return
        self.running = True
        for b in self.buttons:
            b.set_sensitive(False)
        self.say(self.note, '')
        self.run.begin(f'Updating {row["title"]}…')

        def work():
            code = 1
            for event in panel.run_events(row['argv']):
                if event['event'] == 'exit':
                    code = event['code']
                elif event.get('line'):
                    GLib.idle_add(self._tick, event['line'])
            return code

        background(work, lambda code: self._finished(row, code))

    def _tick(self, line):
        self.run.set_status(line[:120])
        self.run.append(line)
        return False

    def _finished(self, row, code):
        self.running = False
        self.run.hide()
        problem = panel.exit_message(code)
        if problem:
            self.say(self.note, problem)
        elif code == 0:
            self.say(self.note, f'{row["title"]} is up to date.')
        else:
            self.say(self.note, f'{row["title"]} could not be updated. Open Show details next time for the reason.')
        self.refresh(force=True)


# ---- AI models -------------------------------------------------------------------------------

class ModelsPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.spinner = Gtk.Spinner()
        self.pack_start(header('AI models', self.spinner, button('Refresh', on_click=lambda *_: self.refresh(), tooltip='Check again (Ctrl+R)'),
                               self.terminal_button('models')), False, False, 0)
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
        self.pack_start(header('Hardware', self.spinner, button('Refresh', on_click=lambda *_: self.refresh(), tooltip='Check again (Ctrl+R)'),
                               self.terminal_button('gpu')), False, False, 0)
        self.headline = label('', 'lede')
        self.pack_start(self.headline, False, False, 0)
        self.holder = self.scroller()
        self.disk = {}
        self.grow = button('Use all the disk space…', 'suggested', on_click=lambda *_: self._confirm_grow())
        self.grow.set_halign(Gtk.Align.START)
        self.grow.set_no_show_all(True)
        self.pack_start(self.grow, False, False, 0)
        self.setup = button('Set up GPU for local AI…', 'suggested', on_click=lambda *_: self._confirm())
        self.skip = button("No, I'll set up the GPU myself", 'link', on_click=lambda *_: self.skip_chore('gpu'),
                           tooltip='Nothing is installed. The terminal commands are shown here instead.')
        self.unskip = None                  # built with the page body when the GPU was skipped
        row = Gtk.Box(spacing=10)
        for item in (self.setup, self.skip):
            item.set_no_show_all(True)
            row.pack_start(item, False, False, 0)
        row.set_halign(Gtk.Align.START)
        self.pack_start(row, False, False, 0)
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
            return (panel.gpu_json('detect', '--json'), panel.gpu_json('status', '--json'), panel.noc_json('status'),
                    panel.noc_json('skip', 'list', '--json'))
        background(work, self._loaded)

    def _loaded(self, result):
        self.spinner.stop()
        detect, gstatus, status, skipped = result
        self.detect = detect
        self.free_bytes = ((status or {}).get('disk') or {}).get('root_free_bytes')
        state = panel.hardware_state(detect, gstatus, skipped)
        self.disk = (status or {}).get('disk') or {}
        can_grow = panel.disk_can_grow(self.disk)
        self.headline.set_text(panel.disk_headline(self.disk)[0] if can_grow else state['headline'])
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_end=8)
        if can_grow:
            body.add(label('Disk size', 'section'))
            for line in panel.disk_grow_summary(self.disk)[:2]:
                body.add(label(line, 'card-detail', chars=80))
        self.unskip = None
        if state['skipped']:
            body.add(label(panel.skipped_text('gpu'), 'card-detail', selectable=True))
            self.unskip = button('Set it up here after all', on_click=lambda *_: self.skip_chore('gpu', False))
            self.unskip.set_halign(Gtk.Align.START)
            body.add(self.unskip)
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
        self.grow.set_visible(can_grow)
        self.skip.set_visible(state['can_install'])

    # -- use the unused disk space: an explicit summary and a yes, never on its own ---------
    def _confirm_grow(self):
        if self.running or not panel.disk_can_grow(self.disk):
            return
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.NONE, text='Use all of the disk?')
        dialog.format_secondary_text('\n\n'.join(panel.disk_grow_summary(self.disk)))
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        dialog.add_button('Use all the space', Gtk.ResponseType.OK)
        answer = dialog.run()
        dialog.destroy()
        if answer == Gtk.ResponseType.OK:
            self._grow()

    def _grow(self):
        self.running = True
        self.grow.set_sensitive(False)
        self.say(self.note, '')
        self.run.begin('Using the rest of the disk…')

        def work():
            for event in panel.run_events(panel.DISK_GROW):
                if event['event'] == 'exit':
                    return event['code']
                GLib.idle_add(self._tick, event.get('line') or '')
            return 1

        background(work, self._grown)

    def _grown(self, code):
        self.running = False
        self.run.hide()
        self.grow.set_sensitive(True)
        message, restart = panel.disk_grow_result(code)
        self.say(self.note, message)
        if restart:
            self._offer_restart()
        self.refresh()

    def _offer_restart(self):
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.NONE, text='Restart to finish?')
        dialog.format_secondary_text('The new disk size is saved. A restart lets the system use it. Save your work '
                                     'first. Afterwards, open Hardware and use the space once more to finish.')
        dialog.add_button('Later', Gtk.ResponseType.CANCEL)
        dialog.add_button('Restart now', Gtk.ResponseType.OK)
        answer = dialog.run()
        dialog.destroy()
        if answer == Gtk.ResponseType.OK:
            subprocess.Popen(['systemctl', 'reboot'])

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
        self.skip.set_sensitive(False)
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
        self.skip.set_sensitive(True)
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
        self.pack_start(header('Privacy', self.spinner, button('Refresh', on_click=lambda *_: self.refresh(), tooltip='Check again (Ctrl+R)'),
                               self.terminal_button('privacy')), False, False, 0)
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


PAGES = [('overview', 'Overview', OverviewPage), ('accounts', 'Accounts', AccountsPage),
         ('updates', 'Updates', UpdatesPage), ('apps', 'Apps', AppsPage), ('models', 'AI models', ModelsPage), ('hardware', 'Hardware', HardwarePage),
         ('health', 'Health', HealthPage), ('privacy', 'Privacy', PrivacyPage), ('about', 'About', AboutPage)]
