import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const MENU_UUID = 'zorin-menu@zorinos.com';
// The Start button shows the Noctra OS logo (same mark as the website). The N
// (noctraos-start.svg) stays on the Welcome app and in the boot art.
const ICON = '/usr/local/share/icons/hicolor/scalable/apps/noctraos-logo.svg';

export default class NoctraStart extends Extension {
    enable() {
        this._enableTopBar();
        this._records = new Map();
        const file = Gio.File.new_for_path(ICON);
        const schema = Gio.SettingsSchemaSource.get_default()?.lookup('org.gnome.shell.extensions.zorin-menu', true);
        if (!file.query_exists(null) || !schema)
            return;
        this._icon = new Gio.FileIcon({file});
        this._settings = new Gio.Settings({schema_id: 'org.gnome.shell.extensions.zorin-menu'});
        this._settingsId = this._settings.connect('changed::logo-icon', () => this._sync());
        this._extensionId = Main.extensionManager.connect('extension-state-changed', () => this._schedule());
        this._monitorId = Main.layoutManager.connect('monitors-changed', () => this._schedule());
        this._sync();
        this._schedule();
    }

    // Top bar (stock GNOME panel, kept by the taskbar): Show Desktop on the
    // left in place of Activities. Clock, tray strip and system menu stay as is.
    _enableTopBar() {
        const activities = Main.panel.statusArea.activities;
        if (activities) {
            this._activities = activities;
            this._activitiesShown = activities.connect('notify::visible', () => {
                if (activities.visible)
                    activities.hide();
            });
            activities.hide();
        }
        this._desktopButton = new St.Button({
            style_class: 'panel-button noctra-showdesktop', reactive: true, can_focus: true,
            track_hover: false, accessible_name: 'Show desktop',
            child: new St.Icon({icon_name: 'user-desktop-symbolic', style_class: 'system-status-icon'}),
        });
        this._desktopButton.connect('clicked', () => this._toggleDesktop());
        Main.panel._leftBox.insert_child_at_index(this._desktopButton, 0);
        this._minimized = [];
    }

    _toggleDesktop() {
        const workspace = global.workspace_manager.get_active_workspace();
        const open = workspace.list_windows().filter(w =>
            w.get_window_type() === Meta.WindowType.NORMAL && !w.is_skip_taskbar() && !w.minimized);
        if (open.length) {
            this._minimized = open;
            open.forEach(w => w.minimize());
        } else {
            this._minimized.forEach(w => { if (w.get_workspace()) w.unminimize(); });
            this._minimized = [];
        }
    }

    _disableTopBar() {
        if (this._activities) {
            this._activities.disconnect(this._activitiesShown);
            this._activities.show();
            this._activities = null;
        }
        this._desktopButton?.destroy();
        this._desktopButton = null;
        this._minimized = [];
    }

    _schedule() {
        if (this._timer)
            GLib.source_remove(this._timer);
        let attempts = 0;
        this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
            this._sync();
            if (++attempts < 12)
                return GLib.SOURCE_CONTINUE;
            this._timer = 0;
            return GLib.SOURCE_REMOVE;
        });
    }

    _sync() {
        // GNOME 46 / Zorin Menu 18: the extension owns one button per panel.
        // Guard its private API so a changed upstream layout leaves the stock icon.
        const menu = Main.extensionManager.lookup(MENU_UUID)?.stateObj;
        for (const button of menu?.menuButtons ?? []) {
            const icon = button._menuButton?._icon;
            if (!icon || this._records.has(icon))
                continue;
            const record = {original: icon.gicon, changing: false};
            this._records.set(icon, record);
            record.changed = icon.connect('notify::gicon', () => {
                if (record.changing)
                    return;
                record.original = icon.gicon;
                this._apply(icon, record);
            });
            record.destroyed = icon.connect('destroy', () => {
                this._records.delete(icon);
                this._schedule();
            });
        }
        for (const [icon, record] of this._records)
            this._apply(icon, record);
    }

    _apply(icon, record) {
        const desired = this._settings.get_boolean('logo-icon') ? this._icon : record.original;
        if (icon.gicon?.equal(desired))
            return;
        record.changing = true;
        icon.set_gicon(desired);
        record.changing = false;
    }

    disable() {
        this._disableTopBar();
        if (!this._settings)
            return;
        if (this._timer)
            GLib.source_remove(this._timer);
        this._timer = 0;
        Main.extensionManager.disconnect(this._extensionId);
        Main.layoutManager.disconnect(this._monitorId);
        this._settings.disconnect(this._settingsId);
        for (const [icon, record] of this._records) {
            icon.disconnect(record.changed);
            icon.disconnect(record.destroyed);
            if (icon.gicon?.equal(this._icon))
                icon.set_gicon(record.original);
        }
        this._records.clear();
        this._settings = null;
        this._icon = null;
    }
}
