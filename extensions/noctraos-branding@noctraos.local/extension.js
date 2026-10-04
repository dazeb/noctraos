import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const MENU_UUID = 'zorin-menu@zorinos.com';
const ICON = '/usr/local/share/icons/hicolor/scalable/apps/noctraos-start.svg';

export default class NoctraStart extends Extension {
    enable() {
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
