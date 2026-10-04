import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const MENU_UUID = 'zorin-menu@zorinos.com';
const AGENTS = ['noctraos-hermes', 'noctraos-claude', 'noctraos-codex', 'noctraos-opencode',
    'noctraos-grok', 'noctraos-gemini', 'noctraos-qwen'];
const RECENT_LIMIT = 8;
const WIDTH = 560;
const HELP_URI = 'file:///usr/local/share/noctraos/help/index.html';
// Open-Meteo / WMO weather codes to symbolic icons.
const WEATHER_ICONS = [[[0], 'weather-clear-symbolic'], [[1, 2], 'weather-few-clouds-symbolic'],
    [[3], 'weather-overcast-symbolic'], [[45, 48], 'weather-fog-symbolic'],
    [[51, 53, 55, 56, 57], 'weather-showers-scattered-symbolic'],
    [[61, 63, 65, 66, 67, 80, 81, 82], 'weather-showers-symbolic'],
    [[71, 73, 75, 77, 85, 86], 'weather-snow-symbolic'], [[95, 96, 99], 'weather-storm-symbolic']];

export default class NoctraStart extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._patched = new Map();
        this._root = null;
        this._panel = null;
        this._hook();
        this._extensionId = Main.extensionManager.connect('extension-state-changed', () => this._schedule());
        this._monitorId = Main.layoutManager.connect('monitors-changed', () => this._schedule());
        this._schedule();
    }

    disable() {
        this._close();
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
        Main.extensionManager.disconnect(this._extensionId);
        Main.layoutManager.disconnect(this._monitorId);
        for (const menu of this._patched.keys()) {
            delete menu.toggle;
            delete menu.open;
        }
        this._patched.clear();
        this._settings = null;
    }

    // Retry for a few seconds: the Zorin Menu builds its buttons after the shell starts.
    _schedule() {
        if (this._timer)
            GLib.source_remove(this._timer);
        let attempts = 0;
        this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
            this._hook();
            if (++attempts < 12)
                return GLib.SOURCE_CONTINUE;
            this._timer = 0;
            return GLib.SOURCE_REMOVE;
        });
    }

    // Route the Start button to our panel by replacing its popup menu's open/toggle.
    // Guarded: if the Zorin Menu changes shape, its own menu simply keeps working.
    _hook() {
        const menu = Main.extensionManager.lookup(MENU_UUID)?.stateObj;
        for (const button of menu?.menuButtons ?? []) {
            const popup = button._menu;
            if (!popup || this._patched.has(popup))
                continue;
            this._patched.set(popup, button);
            popup.toggle = () => this._toggle(button);
            popup.open = () => this._open(button);
        }
    }

    _toggle(button) {
        if (this._root)
            this._close();
        else
            this._open(button);
    }

    _open(button) {
        if (this._root)
            return;
        if (Main.overview.visible)
            Main.overview.hide();
        // A transparent full-screen root takes the modal grab, so a click anywhere
        // outside the panel lands on the root itself and closes the menu.
        const root = new St.Widget({reactive: true, layout_manager: new Clutter.FixedLayout()});
        root.add_constraint(new Clutter.BindConstraint({
            source: global.stage, coordinate: Clutter.BindCoordinate.ALL}));
        const panel = new St.BoxLayout({style_class: 'noctra-start', vertical: true, reactive: true});
        panel.set_width(WIDTH);
        try {
            panel.add_child(this._header());
            const startHere = this._startHere();
            if (startHere)
                panel.add_child(startHere);
            panel.add_child(this._section('AGENTS'));
            panel.add_child(this._agents());
            panel.add_child(this._section('RECENT'));
            panel.add_child(this._recent());
            panel.add_child(this._footer());
        } catch (error) {
            logError(error, 'Noctra Start could not build its panel');
            panel.destroy();
            root.destroy();
            return;
        }
        root.add_child(panel);
        root.connect('button-press-event', (_actor, event) => {
            // Decide by position: the event source is not reliable for clicks on the root.
            const [x, y] = event.get_coords();
            const box = panel.get_transformed_extents();
            if (x >= box.get_x() && x <= box.get_x() + box.get_width() &&
                y >= box.get_y() && y <= box.get_y() + box.get_height())
                return Clutter.EVENT_PROPAGATE;
            this._close();
            return Clutter.EVENT_STOP;
        });
        root.connect('key-press-event', (_actor, event) => {
            if (event.get_key_symbol() === Clutter.KEY_Escape) {
                this._close();
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        Main.layoutManager.uiGroup.add_child(root);
        this._root = root;
        this._panel = panel;

        // Centered on the monitor, sitting just above the dock.
        const monitor = Main.layoutManager.primaryMonitor;
        const [, height] = panel.get_preferred_height(WIDTH);
        const [, top] = button?.get_transformed_position() ?? [0, monitor.y + monitor.height - 60];
        panel.set_position(Math.round(monitor.x + (monitor.width - WIDTH) / 2),
            Math.max(monitor.y + 40, Math.round(top - height - 8)));
        this._grab = Main.pushModal(root, {actionMode: Shell.ActionMode.POPUP});
        if (!this._grab) {
            this._close();
            return;
        }
        panel.grab_key_focus();
    }

    _close() {
        if (this._grab) {
            Main.popModal(this._grab);
            this._grab = null;
        }
        this._root?.destroy();
        this._root = null;
        this._panel = null;
    }

    _header() {
        const bar = new St.BoxLayout({style_class: 'noctra-start-header'});
        bar.add_child(new St.Label({text: 'NOCTRAOS', style_class: 'noctra-start-title',
            x_expand: true, y_align: Clutter.ActorAlign.CENTER}));
        if (this._settings.get_boolean('show-name')) {
            bar.add_child(new St.Label({text: this._userName(), style_class: 'noctra-start-user',
                y_align: Clutter.ActorAlign.CENTER}));
        }
        bar.add_child(this._weather());
        const settings = new St.Button({style_class: 'noctra-start-icon-button', reactive: true,
            can_focus: true, accessible_name: 'Settings',
            child: new St.Icon({icon_name: 'emblem-system-symbolic', icon_size: 16})});
        settings.connect('clicked', () => this._launchApp('org.gnome.Settings.desktop'));
        bar.add_child(settings);
        return bar;
    }

    _userName() {
        const real = GLib.get_real_name();
        return real && real !== 'Unknown' ? real : GLib.get_user_name();
    }

    // Opt-in: until a city is chosen this is just a small "+ weather" link.
    _weather() {
        const button = new St.Button({style_class: 'noctra-start-weather', reactive: true,
            can_focus: true, accessible_name: 'Weather'});
        const row = new St.BoxLayout();
        const icon = new St.Icon({icon_name: 'weather-clear-symbolic', icon_size: 14,
            style_class: 'noctra-start-weather-icon'});
        const label = new St.Label({y_align: Clutter.ActorAlign.CENTER});
        row.add_child(icon);
        row.add_child(label);
        button.set_child(row);
        button.connect('clicked', () => {
            this._close();
            this._spawn(['noctraos-weather', '--setup']);
        });
        if (!this._settings.get_boolean('weather')) {
            icon.hide();
            label.set_text('+ weather');
            return button;
        }
        label.set_text('…');
        try {
            const process = Gio.Subprocess.new(['noctraos-weather', '--fetch'],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
            process.communicate_utf8_async(null, null, (source, result) => {
                try {
                    const [, stdout] = source.communicate_utf8_finish(result);
                    const weather = JSON.parse(stdout);
                    if (button.get_stage() === null)
                        return; // the panel was closed meanwhile
                    if (!weather.ok) {
                        icon.hide();
                        label.set_text('weather n/a');
                        return;
                    }
                    const match = WEATHER_ICONS.find(([codes]) => codes.includes(weather.code));
                    icon.set_icon_name(!weather.day && weather.code === 0 ? 'weather-clear-night-symbolic' :
                        (match ? match[1] : 'weather-overcast-symbolic'));
                    label.set_text(`${weather.temp}°${weather.unit}`);
                } catch (error) {
                    if (button.get_stage() !== null)
                        label.set_text('weather n/a');
                }
            });
        } catch (error) {
            label.set_text('weather n/a');
        }
        return button;
    }

    // Pointer for people new to the OS. Dismissible; the choice is kept.
    _startHere() {
        if (!this._settings.get_boolean('show-start-here'))
            return null;
        const row = new St.BoxLayout({style_class: 'noctra-start-here', x_expand: true});
        const open = new St.Button({style_class: 'noctra-start-here-open', reactive: true, can_focus: true,
            x_expand: true, x_align: Clutter.ActorAlign.FILL, accessible_name: 'New users start here'});
        const content = new St.BoxLayout({x_expand: true});
        content.add_child(new St.Label({text: 'NEW USERS START HERE', x_expand: true,
            y_align: Clutter.ActorAlign.CENTER}));
        content.add_child(new St.Icon({icon_name: 'go-next-symbolic', icon_size: 14}));
        open.set_child(content);
        open.connect('clicked', () => this._openUri(HELP_URI));
        const hide = new St.Button({style_class: 'noctra-start-icon-button', reactive: true, can_focus: true,
            accessible_name: 'Hide this',
            child: new St.Icon({icon_name: 'window-close-symbolic', icon_size: 12})});
        hide.connect('clicked', () => {
            this._settings.set_boolean('show-start-here', false);
            row.destroy();
        });
        row.add_child(open);
        row.add_child(hide);
        return row;
    }

    _section(text) {
        return new St.Label({text, style_class: 'noctra-start-section'});
    }

    _agents() {
        const row = new St.BoxLayout({style_class: 'noctra-start-agents', x_expand: true});
        const appSystem = Shell.AppSystem.get_default();
        for (const id of AGENTS) {
            const app = appSystem.lookup_app(`${id}.desktop`);
            if (!app)
                continue;
            const button = new St.Button({style_class: 'noctra-start-agent', reactive: true,
                can_focus: true, x_expand: true, accessible_name: app.get_name()});
            const box = new St.BoxLayout({vertical: true, x_align: Clutter.ActorAlign.CENTER});
            box.add_child(app.create_icon_texture(24));
            box.add_child(new St.Label({text: app.get_name(), style_class: 'noctra-start-agent-label',
                x_align: Clutter.ActorAlign.CENTER}));
            button.set_child(box);
            button.connect('clicked', () => this._launchApp(`${id}.desktop`));
            row.add_child(button);
        }
        return row;
    }

    _recentFiles() {
        const bookmarks = new GLib.BookmarkFile();
        try {
            bookmarks.load_from_file(GLib.build_filenamev([GLib.get_user_data_dir(), 'recently-used.xbel']));
        } catch (error) {
            return [];
        }
        const items = [];
        for (const uri of bookmarks.get_uris()) {
            if (!uri.startsWith('file://'))
                continue;
            const file = Gio.File.new_for_uri(uri);
            const path = file.get_path() ?? '';
            // Scratch and hidden locations are noise, not "recent files".
            if (path.startsWith('/tmp/') || path.includes('/.') || !file.query_exists(null))
                continue;
            let modified = 0;
            let mime = 'application/octet-stream';
            try {
                modified = bookmarks.get_modified(uri);
                mime = bookmarks.get_mime_type(uri) || mime;
            } catch (error) {
                // Keep defaults for entries without that metadata.
            }
            items.push({uri, file, modified, mime});
        }
        items.sort((a, b) => b.modified - a.modified);
        return items.slice(0, RECENT_LIMIT);
    }

    _recent() {
        const list = new St.BoxLayout({vertical: true, style_class: 'noctra-start-recent'});
        const items = this._recentFiles();
        if (!items.length) {
            list.add_child(new St.Label({text: 'Nothing here yet. Files you open show up here.',
                style_class: 'noctra-start-empty'}));
            return list;
        }
        const home = GLib.get_home_dir();
        for (const item of items) {
            const button = new St.Button({style_class: 'noctra-start-file', reactive: true,
                can_focus: true, x_expand: true, x_align: Clutter.ActorAlign.FILL,
                accessible_name: item.file.get_basename()});
            const row = new St.BoxLayout({style_class: 'noctra-start-file-row', x_expand: true});
            row.add_child(new St.Icon({gicon: Gio.content_type_get_icon(item.mime), icon_size: 16}));
            row.add_child(new St.Label({text: item.file.get_basename(), style_class: 'noctra-start-file-name',
                x_expand: true, y_align: Clutter.ActorAlign.CENTER}));
            const folder = (item.file.get_parent()?.get_path() ?? '').replace(home, '~');
            row.add_child(new St.Label({text: folder, style_class: 'noctra-start-file-detail',
                y_align: Clutter.ActorAlign.CENTER}));
            button.set_child(row);
            button.connect('clicked', () => this._openUri(item.uri));
            list.add_child(button);
        }
        return list;
    }

    _footer() {
        const bar = new St.BoxLayout({style_class: 'noctra-start-footer'});
        const all = new St.Button({label: 'All apps', style_class: 'noctra-start-text-button',
            reactive: true, can_focus: true});
        all.connect('clicked', () => {
            this._close();
            Main.overview.showApps();
        });
        bar.add_child(all);
        bar.add_child(new St.Label({text: 'Super+Space  search everything', style_class: 'noctra-start-hint',
            x_expand: true, x_align: Clutter.ActorAlign.END, y_align: Clutter.ActorAlign.CENTER}));
        return bar;
    }

    _spawn(argv) {
        try {
            Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE);
        } catch (error) {
            Main.notify('Noctra Start', `Could not run ${argv[0]}.`);
        }
    }

    _launchApp(id) {
        const app = Shell.AppSystem.get_default().lookup_app(id);
        this._close();
        if (app)
            app.activate();
    }

    _openUri(uri) {
        this._close();
        try {
            Gio.AppInfo.launch_default_for_uri(uri, global.create_app_launch_context(0, -1));
        } catch (error) {
            Main.notify('Noctra Start', 'Could not open this. Is a web browser set up?');
        }
    }
}
