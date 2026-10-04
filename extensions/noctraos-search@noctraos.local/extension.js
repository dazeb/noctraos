import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as ModalDialog from 'resource:///org/gnome/shell/ui/modalDialog.js';

const ENGINES = {
    DuckDuckGo: 'https://duckduckgo.com/?q=',
    Google: 'https://www.google.com/search?q=',
    Bing: 'https://www.bing.com/search?q=',
};

export default class SearchExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._serial = 0;
        this._selectionTouched = false;
        this._timeout = 0;
        this._process = null;
        this._dialog = null;
        Main.wm.addKeybinding('toggle-search', this._settings, Meta.KeyBindingFlags.NONE,
            Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW | Shell.ActionMode.POPUP,
            () => this._toggle());
        this._changed = this._settings.connect('changed', () => {
            if (this._dialog)
                this._schedule();
        });
    }

    disable() {
        Main.wm.removeKeybinding('toggle-search');
        this._close();
        this._settings.disconnect(this._changed);
        this._settings = null;
    }

    _cancel() {
        this._serial++;
        if (this._timeout)
            GLib.source_remove(this._timeout);
        this._timeout = 0;
        this._cancellable?.cancel();
        this._cancellable = null;
        this._process?.force_exit();
        this._process = null;
    }

    _close() {
        this._cancel();
        const dialog = this._dialog;
        this._dialog = null;
        if (dialog) {
            dialog.close();
            dialog.destroy();
        }
        this._items = [];
        this._entry = null;
    }

    _toggle() {
        if (this._dialog) {
            this._close();
            return;
        }
        if (Main.overview.visible)
            Main.overview.hide();
        const dialog = new ModalDialog.ModalDialog({
            styleClass: 'noctra-search-dialog', destroyOnClose: false,
            actionMode: Shell.ActionMode.POPUP, shouldFadeIn: false, shouldFadeOut: false,
        });
        this._dialog = dialog;
        const monitor = Main.layoutManager.currentMonitor;
        const width = Math.min(720, monitor.width - 48);
        dialog.contentLayout.set_style(`width: ${width - 40}px; max-width: ${width - 40}px; margin: 0;`);
        const header = new St.BoxLayout({style_class: 'noctra-search-header'});
        header.add_child(new St.Icon({icon_name: 'system-search-symbolic', icon_size: 24}));
        this._entry = new St.Entry({hint_text: 'Search your system…',
            reactive: true, can_focus: true, x_expand: true, style_class: 'noctra-search-entry'});
        this._entry.clutter_text.set_single_line_mode(true);
        header.add_child(this._entry);
        const cog = new St.Button({style_class: 'noctra-search-cog', reactive: true, can_focus: true,
            accessible_name: 'Search settings', child: new St.Icon({
                icon_name: 'emblem-system-symbolic', icon_size: 20})});
        cog.connect('clicked', () => {
            this._close();
            this._spawn(['noctraos-search', '--settings']);
        });
        header.add_child(cog);
        dialog.contentLayout.add_child(header);
        const scroll = new St.ScrollView({style_class: 'noctra-search-scroll',
            overlay_scrollbars: true, x_expand: true});
        scroll.set_policy(St.PolicyType.NEVER, St.PolicyType.AUTOMATIC);
        scroll.set_style(`max-height: ${Math.min(420, monitor.height - 260)}px;`);
        this._list = new St.BoxLayout({vertical: true, style_class: 'noctra-search-list'});
        scroll.set_child(this._list);
        this._scroll = scroll;
        dialog.contentLayout.add_child(scroll);
        this._notice = new St.Label({style_class: 'noctra-search-notice',
            text: '↑↓ Choose · Enter Open/copy · Esc Close'});
        this._notice.clutter_text.set_line_wrap(true);
        dialog.contentLayout.add_child(this._notice);
        this._entry.clutter_text.connect('text-changed', () => this._schedule());
        this._entry.clutter_text.connect('activate', () => {
            const item = this._items[this._selected];
            if (item)
                this._activate(item);
        });
        // Handle keyboard navigation on the dialog so Tab-focused rows work too.
        dialog.connect('key-press-event', (_actor, event) => this._key(event));
        dialog.connect('destroy', () => {
            if (this._dialog === dialog) {
                this._cancel();
                this._dialog = null;
                this._entry = null;
            }
        });
        dialog.setInitialKeyFocus(this._entry.clutter_text);
        if (!dialog.open(global.get_current_time())) {
            this._close();
            return;
        }
        this._render([], '↑↓ Choose · Enter Open/copy · Esc Close');
    }

    _key(event) {
        const key = event.get_key_symbol();
        if (key === Clutter.KEY_Escape ||
            (key === Clutter.KEY_space && (event.get_state() & Clutter.ModifierType.MOD4_MASK))) {
            this._close();
        } else if (key === Clutter.KEY_Down || key === Clutter.KEY_Up) {
            this._selectionTouched = true;
            if (this._items.length)
                this._select((this._selected + (key === Clutter.KEY_Down ? 1 : -1) +
                    this._items.length) % this._items.length);
        } else if (key === Clutter.KEY_Return || key === Clutter.KEY_KP_Enter) {
            // Leave Enter on the cog/button to native focus activation.
            if (global.stage.key_focus !== this._entry?.clutter_text)
                return Clutter.EVENT_PROPAGATE;
            const item = this._items[this._selected];
            if (item)
                this._activate(item);
        } else {
            return Clutter.EVENT_PROPAGATE;
        }
        return Clutter.EVENT_STOP;
    }

    _schedule() {
        this._cancel();
        this._selectionTouched = false;
        const query = this._entry.get_text().trim().slice(0, 512);
        this._base = this._localResults(query);
        this._render(this._base, query ? 'Searching…' : 'Type to search · Esc to close');
        if (!query)
            return;
        const serial = this._serial;
        this._timeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 120, () => {
            this._timeout = 0;
            this._query(query, serial);
            return GLib.SOURCE_REMOVE;
        });
    }

    _localResults(query) {
        if (!query)
            return [];
        const results = [];
        if (this._settings.get_boolean('apps')) {
            const words = query.toLocaleLowerCase().split(/\s+/);
            const appSystem = Shell.AppSystem.get_default();
            for (const info of appSystem.get_installed()) {
                const app = appSystem.lookup_app(info.get_id());
                if (!app)
                    continue;
                if (!info?.should_show())
                    continue;
                const haystack = `${app.get_name()} ${info.get_description() ?? ''} ${info.get_keywords()?.join(' ') ?? ''}`.toLocaleLowerCase();
                if (words.every(word => haystack.includes(word)))
                    results.push({kind: 'app', title: app.get_name(),
                        detail: info.get_description() || 'Application', app});
            }
            const term = query.toLocaleLowerCase();
            const rank = item => item.title.toLocaleLowerCase() === term ? 0 :
                (item.title.toLocaleLowerCase().includes(term) ? 1 : 2);
            results.sort((a, b) => rank(a) - rank(b) || a.title.localeCompare(b.title));
            results.splice(this._settings.get_int('max-results'));
        }
        if (this._settings.get_boolean('web')) {
            const provider = this._settings.get_string('web-provider');
            results.push({kind: 'web', title: `Search ${provider} for “${query}”`,
                detail: 'Web · Opens in your browser', icon: 'web-browser-symbolic',
                uri: (ENGINES[provider] ?? ENGINES.DuckDuckGo) + encodeURIComponent(query)});
        }
        return results;
    }

    _query(query, serial) {
        try {
            const cancellable = new Gio.Cancellable();
            this._cancellable = cancellable;
            const process = Gio.Subprocess.new(['noctraos-search', '--query', query],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
            this._process = process;
            process.communicate_utf8_async(null, cancellable, (source, result) => {
                try {
                    const [, stdout] = source.communicate_utf8_finish(result);
                    if (serial !== this._serial || !this._dialog)
                        return;
                    if (!source.get_successful())
                        throw new Error('Search helper failed');
                    const payload = JSON.parse(stdout);
                    const apps = this._base.filter(item => item.kind === 'app');
                    const web = this._base.filter(item => item.kind === 'web');
                    const items = [...apps, ...payload.results, ...web];
                    const notice = payload.notice || (items.length ?
                        '↑↓ Choose · Enter Open/copy · Esc Close' :
                        'No results. Try another search or change your sources in settings.');
                    this._render(items, notice);
                    this._currentClipboard(query, serial, items, notice);
                } catch (error) {
                    if (serial === this._serial && this._dialog)
                        this._render(this._base, 'Local search is unavailable. Check Search settings.');
                } finally {
                    if (this._process === source)
                        this._process = null;
                }
            });
        } catch (error) {
            this._render(this._base, 'Local search is unavailable. Check Search settings.');
        }
    }

    _currentClipboard(query, serial, items, notice) {
        if (!this._settings.get_boolean('clipboard'))
            return;
        St.Clipboard.get_default().get_text(St.ClipboardType.CLIPBOARD, (_clipboard, text) => {
            if (serial !== this._serial || !this._dialog || !text ||
                !text.toLocaleLowerCase().includes(query.toLocaleLowerCase()) ||
                items.some(item => item.kind === 'clipboard' && item.text === text))
                return;
            const current = {kind: 'clipboard', title: text.replace(/\s+/g, ' ').slice(0, 160),
                detail: 'Current clipboard · Enter to copy', text, icon: 'edit-paste-symbolic'};
            const local = items.filter(item => item.kind !== 'clipboard' && item.kind !== 'web');
            const history = items.filter(item => item.kind === 'clipboard');
            history.unshift(current);
            history.splice(this._settings.get_int('max-results'));
            this._render([...local, ...history, ...items.filter(item => item.kind === 'web')], notice);
        });
    }

    _identity(item) {
        return item ? `${item.kind}:${item.path ?? item.text ?? item.uri ?? item.app?.get_id()}` : '';
    }

    _render(items, notice) {
        const selected = this._selectionTouched ? this._identity(this._items[this._selected]) : '';
        this._items = items;
        this._list.destroy_all_children();
        this._rows = [];
        let previousKind = '';
        const headings = {app: 'Applications', file: 'Files and folders', clipboard: 'Clipboard', web: 'Web'};
        for (const [index, item] of items.entries()) {
            if (item.kind !== previousKind) {
                this._list.add_child(new St.Label({text: headings[item.kind],
                    style_class: 'noctra-search-heading'}));
                previousKind = item.kind;
            }
            const button = new St.Button({style_class: 'noctra-search-result', reactive: true, track_hover: true, can_focus: true,
                x_expand: true, accessible_name: `${item.title}, ${item.detail}`});
            const row = new St.BoxLayout({style_class: 'noctra-search-row', x_expand: true});
            row.add_child(item.app ? item.app.create_icon_texture(28) :
                new St.Icon({icon_name: item.icon, icon_size: 28}));
            const text = new St.BoxLayout({vertical: true, x_expand: true});
            text.add_child(new St.Label({text: item.title, style_class: 'noctra-search-title', x_expand: true}));
            text.add_child(new St.Label({text: item.detail.replace(/\s+/g, ' '),
                style_class: 'noctra-search-detail', x_expand: true}));
            row.add_child(text);
            button.set_child(row);
            button.connect('clicked', () => this._activate(item));
            button.connect('notify::hover', () => {
                if (button.hover) {
                    this._selectionTouched = true;
                    this._select(index);
                }
            });
            this._list.add_child(button);
            this._rows.push(button);
        }
        this._notice.set_text(notice);
        this._selected = -1;
        if (items.length) {
            const index = items.findIndex(item => this._identity(item) === selected);
            this._select(index < 0 ? 0 : index);
        }
    }

    _select(index) {
        this._rows[this._selected]?.remove_style_pseudo_class('selected');
        this._selected = index;
        const row = this._rows[index];
        row.add_style_pseudo_class('selected');
        // Keep keyboard selection in view without moving focus out of the entry.
        const adjustment = this._scroll.vadjustment;
        const box = row.get_allocation_box();
        if (box.y1 < adjustment.value)
            adjustment.value = box.y1;
        else if (box.y2 > adjustment.value + adjustment.page_size)
            adjustment.value = box.y2 - adjustment.page_size;
    }

    _spawn(argv) {
        try {
            Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE);
        } catch (error) {
            Main.notify('Noctra Search', 'Unable to open Search settings. Run the provisioner again.');
        }
    }

    _activate(item) {
        try {
            if (item.kind === 'clipboard') {
                St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, item.text);
            } else if (item.kind === 'app') {
                item.app.activate();
            } else {
                const uri = item.kind === 'file' ? Gio.File.new_for_path(item.path).get_uri() : item.uri;
                Gio.AppInfo.launch_default_for_uri(uri, global.create_app_launch_context(0, -1));
            }
            this._close();
            if (item.kind === 'clipboard')
                Main.notify('Noctra Search', 'Copied to clipboard. Paste with Ctrl+V.');
        } catch (error) {
            this._notice.set_text('Could not open this result. It may have moved or has no associated app.');
        }
    }
}
