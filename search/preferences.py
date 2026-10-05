"""Native GTK settings, launched outside the GNOME Shell process."""
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gio, Gtk

import browsers


def expanded_roots(settings):
    """The saved folders as absolute paths (the default is '~', the home folder)."""
    return [str(Path(root).expanduser()) for root in settings.get_strv('roots')]


def choose_history(settings, parent=None):
    """Ask which browser(s) to search. Closing the dialog changes nothing."""
    from main import request_index
    found = browsers.detected()
    dialog = Gtk.Dialog(title='Search your browser history?', transient_for=parent, modal=True)
    dialog.set_default_size(460, -1)
    area = dialog.get_content_area()
    area.set_spacing(12)
    area.set_border_width(20)

    def label(text):
        item = Gtk.Label(label=text, xalign=0, wrap=True)
        area.pack_start(item, False, False, 0)

    label('Find pages you have visited from Super+Space. Titles and addresses are read from your '
          'browser on this computer and searched locally. Nothing is uploaded, and you can change '
          'this later in Search settings.')
    boxes = {}
    if found:
        label('Which browser do you use?')
        chosen = set(settings.get_strv('history-browsers'))
        if not chosen:
            default = browsers.default_browser()
            chosen = {default} if default in {b['id'] for b in found} else {b['id'] for b in found}
        for browser in found:
            check = Gtk.CheckButton(label=browser['name'], active=browser['id'] in chosen)
            area.pack_start(check, False, False, 0)
            boxes[browser['id']] = check
        yes = dialog.add_button('Search my history', Gtk.ResponseType.OK)
        yes.get_style_context().add_class('suggested-action')
        dialog.add_button('No thanks', Gtk.ResponseType.REJECT)

        def update(*_):
            yes.set_sensitive(any(box.get_active() for box in boxes.values()))
        for box in boxes.values():
            box.connect('toggled', update)
        update()
    else:
        label('No browser history found yet. Use a browser for a while, then set this up again.')
        dialog.add_button('Close', Gtk.ResponseType.CLOSE)
    dialog.show_all()
    response = dialog.run()
    dialog.destroy()
    if response == Gtk.ResponseType.OK:
        settings.set_strv('history-browsers', [b for b, box in boxes.items() if box.get_active()])
        settings.set_boolean('history', True)
        settings.set_string('history-setup', 'configured')
    elif response == Gtk.ResponseType.REJECT:
        settings.set_boolean('history', False)
        settings.set_string('history-setup', 'dismissed')
    else:
        return
    Gio.Settings.sync()
    request_index()


def show_history_setup(settings):
    Gtk.init([])
    choose_history(settings)


def show_settings(settings):
    from main import request_index
    app = Gtk.Application(application_id='local.noctraos.SearchSettings')

    def activate(application):
        if application.get_active_window():
            application.get_active_window().present()
            return
        window = Gtk.ApplicationWindow(application=application, title='Search settings')
        window.set_default_size(560, 620)
        window.set_position(Gtk.WindowPosition.CENTER)
        header = Gtk.HeaderBar(title='Search settings', show_close_button=True)
        window.set_titlebar(header)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        window.add(scroller)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=24)
        scroller.add(box)

        def label(text):
            item = Gtk.Label(label=text, xalign=0, wrap=True)
            box.pack_start(item, False, False, 0)
            return item

        label('Find apps, files, clipboard history, and the web from one place.')
        toggles = {}
        for key, title in [('apps', 'Applications and system settings'),
                           ('files', 'Files and folders'), ('clipboard', 'Clipboard and CopyQ text history'),
                           ('web', 'Web search'), ('history', 'Browser history'), ('hidden', 'Include hidden files and folders'),
                           ('contents', 'Search inside small text files (up to 128 KiB)')]:
            row = Gtk.Box(spacing=12)
            row.pack_start(Gtk.Label(label=title, xalign=0), True, True, 0)
            switch = Gtk.Switch(active=settings.get_boolean(key), valign=Gtk.Align.CENTER)
            switch.get_accessible().set_name(title)
            row.pack_end(switch, False, False, 0)
            box.pack_start(row, False, False, 0)
            toggles[key] = switch
        choose = Gtk.Button(label='Choose browsers…', halign=Gtk.Align.START)
        choose.connect('clicked', lambda _button: (choose_history(settings, window),
                                                   toggles['history'].set_active(settings.get_boolean('history'))))
        box.pack_start(choose, False, False, 0)
        label('Search folders — one absolute path per line. Your home folder by default; use / for the whole accessible system (system files then appear in results).')
        roots = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        roots.get_accessible().set_name('Search folders')
        roots.set_size_request(-1, 80)
        roots.get_buffer().set_text('\n'.join(expanded_roots(settings)))
        box.pack_start(roots, False, False, 0)
        add_folder = Gtk.Button(label='Add folder…', halign=Gtk.Align.START)
        box.pack_start(add_folder, False, False, 0)

        def choose_folder(_button):
            dialog = Gtk.FileChooserDialog(title='Choose a search folder', transient_for=window,
                                           action=Gtk.FileChooserAction.SELECT_FOLDER)
            dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Add folder', Gtk.ResponseType.OK)
            if dialog.run() == Gtk.ResponseType.OK:
                buffer = roots.get_buffer()
                text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
                path = dialog.get_filename()
                if path not in text.splitlines():
                    buffer.set_text(text.rstrip() + '\n' + path)
            dialog.destroy()
        add_folder.connect('clicked', choose_folder)
        label('Protected files and virtual filesystems are excluded. Directory symlinks are not followed. '
              'Names update every 15 minutes; Rebuild index refreshes them now. '
              'Content search indexes UTF-8 text, including personal text in selected folders.')
        label('Web provider — queries are sent only when you select a web result.')
        provider = Gtk.ComboBoxText()
        provider.get_accessible().set_name('Web provider')
        engines = ['DuckDuckGo', 'Google', 'Bing']
        for engine in engines:
            provider.append_text(engine)
        current = settings.get_string('web-provider')
        provider.set_active(engines.index(current) if current in engines else 0)
        box.pack_start(provider, False, False, 0)
        label('Keyboard shortcut — click to record a new key combination.')
        shortcut_value = (settings.get_strv('toggle-search') or ['<Super>space'])[0]
        shortcut = Gtk.Button(label=Gtk.accelerator_get_label(*Gtk.accelerator_parse(shortcut_value)))
        shortcut.get_accessible().set_name('Change keyboard shortcut')
        box.pack_start(shortcut, False, False, 0)

        def record_shortcut(_button):
            dialog = Gtk.Dialog(title='Change keyboard shortcut', transient_for=window, modal=True)
            dialog.get_content_area().add(Gtk.Label(label='Press a shortcut with Super, Ctrl, or Alt. Escape cancels.',
                                                   margin=24))

            def capture(_dialog, event):
                nonlocal shortcut_value
                if event.keyval == Gdk.KEY_Escape:
                    dialog.response(Gtk.ResponseType.CANCEL)
                    return True
                key = Gdk.keyval_to_lower(event.keyval)
                modifiers = event.state & Gtk.accelerator_get_default_mod_mask()
                if modifiers and Gtk.accelerator_valid(key, modifiers):
                    shortcut_value = Gtk.accelerator_name(key, modifiers)
                    shortcut.set_label(Gtk.accelerator_get_label(key, modifiers))
                    dialog.response(Gtk.ResponseType.OK)
                return True
            dialog.connect('key-press-event', capture)
            dialog.show_all()
            dialog.run()
            dialog.destroy()
        shortcut.connect('clicked', record_shortcut)
        label('Maximum results per source')
        count = Gtk.SpinButton.new_with_range(5, 30, 1)
        count.get_accessible().set_name('Maximum results per source')
        count.set_value(settings.get_int('max-results'))
        box.pack_start(count, False, False, 0)
        notice = label('Clipboard results copy text back; paste with Ctrl+V. No clipboard text is indexed on disk.')
        actions = Gtk.Box(spacing=10)
        rebuild = Gtk.Button(label='Rebuild index')
        save = Gtk.Button(label='Save settings')
        save.get_style_context().add_class('suggested-action')
        actions.pack_start(rebuild, False, False, 0)
        actions.pack_end(save, False, False, 0)
        box.pack_start(actions, False, False, 0)

        def apply(_button, reindex=False):
            buffer = roots.get_buffer()
            paths = [str(Path(p.strip()).expanduser()) for p in
                     buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False).splitlines()
                     if p.strip()]
            if not paths or any(not Path(p).is_absolute() or not Path(p).is_dir() for p in paths):
                notice.set_text('Choose existing absolute folder paths before saving.')
                return
            key, modifiers = Gtk.accelerator_parse(shortcut_value)
            if not key or not modifiers or not Gtk.accelerator_valid(key, modifiers):
                notice.set_text('Choose a shortcut with Super, Ctrl, or Alt and a valid key.')
                return
            accelerator = Gtk.accelerator_name(key, modifiers)
            wm = Gio.Settings.new('org.gnome.desktop.wm.keybindings')
            conflicts = []
            for name in wm.list_keys():
                value = wm.get_value(name)
                if value.get_type_string() == 'as':
                    for binding in value.unpack():
                        if Gtk.accelerator_parse(binding) == (key, modifiers):
                            conflicts.append(name)
            if conflicts:
                notice.set_text('That shortcut is used by ' + ', '.join(name.replace('-', ' ') for name in conflicts) + '. Choose another.')
                return
            changed = any(settings.get_boolean(k) != toggles[k].get_active()
                          for k in ('files', 'hidden', 'contents', 'history')) or paths != expanded_roots(settings)
            settings.delay()
            for name, toggle in toggles.items():
                settings.set_boolean(name, toggle.get_active())
            settings.set_strv('roots', paths)
            if toggles['history'].get_active():
                if not settings.get_strv('history-browsers'):
                    settings.set_strv('history-browsers', [b['id'] for b in browsers.detected()])
                settings.set_string('history-setup', 'configured')
            settings.set_strv('toggle-search', [accelerator])
            settings.set_string('web-provider', provider.get_active_text())
            settings.set_int('max-results', count.get_value_as_int())
            settings.apply()
            Gio.Settings.sync()
            if changed or reindex:
                request_index()
            notice.set_text('Settings saved. ' + ('The file index is rebuilding in the background.'
                                                if changed or reindex else 'Your shortcut is ready.'))

        save.connect('clicked', apply)
        rebuild.connect('clicked', lambda button: apply(button, True))
        window.show_all()
    app.connect('activate', activate)
    app.run([])
