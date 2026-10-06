import Clutter from 'gi://Clutter';
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
// Tray icons that are not symbolic are tinted to the panel's foreground colour. CopyQ draws its own
// two-tone green icon from built-in resources: no theme icon, setting or custom-icons entry replaces
// it (the AppIndicator custom icon is drawn on top of the original, which still shows through).
// Matched by the indicator id the app reports.
const MONO_TRAY_IDS = ['CopyQ_copyq'];
const TINT_EFFECT = 'noctra-mono';

export default class NoctraStart extends Extension {
    enable() {
        this._enableTopBar();
        this._enableTray();
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

    // The tint is read from the theme (the colour of the status icons beside it), so it follows a theme change. New tray items
    // (an app starting or restarting) are picked up when they are added to the panel.
    _enableTray() {
        this._themeContext = St.ThemeContext.get_for_stage(global.stage);
        this._themeId = this._themeContext.connect('changed', () => this._queueTint());
        this._trayId = Main.panel._rightBox.connect('child-added', () => this._queueTint());
        this._queueTint();
    }

    _queueTint() {
        if (this._tintIdle)
            return;
        // Let the theme node settle after a stylesheet reload, and the indicator finish initialising.
        this._tintIdle = GLib.timeout_add(GLib.PRIORITY_DEFAULT_IDLE, 300, () => {
            this._tintIdle = 0;
            this._tintTray();
            return GLib.SOURCE_REMOVE;
        });
    }

    // Guarded: these are the AppIndicator extension's private fields; if they change, icons stay as they are.
    _trayIcons() {
        return Object.values(Main.panel.statusArea)
            .filter(item => MONO_TRAY_IDS.includes(item?._indicator?.id) && item._icon)
            .map(item => item._icon);
    }

    _firstStatusIcon(actor) {
        for (const child of actor?.get_children() ?? []) {
            if (child instanceof St.Icon && child.has_style_class_name('system-status-icon'))
                return child;
            const found = this._firstStatusIcon(child);
            if (found)
                return found;
        }
        return null;
    }

    _tintTray() {
        // The colour of the neighbouring symbolic icons: read from one of those icons, so it is whatever
        // the theme really draws them in (not the #panel container, which a theme may style differently).
        let color;
        try {
            const button = Main.panel.statusArea.quickSettings ?? Main.panel.statusArea.aggregateMenu;
            const reference = this._firstStatusIcon(button) ?? button ?? Main.panel;
            color = reference.get_theme_node().get_foreground_color();
        } catch (error) {
            return;
        }
        for (const icon of this._trayIcons()) {
            let effect = icon.get_effect(TINT_EFFECT);
            if (!effect) {
                effect = new Clutter.ColorizeEffect();
                icon.add_effect_with_name(TINT_EFFECT, effect);
            }
            effect.set_tint(color);
        }
    }

    _disableTray() {
        if (this._tintIdle)
            GLib.source_remove(this._tintIdle);
        this._tintIdle = 0;
        this._themeContext?.disconnect(this._themeId);
        Main.panel._rightBox.disconnect(this._trayId);
        for (const icon of this._trayIcons()) {
            const effect = icon.get_effect(TINT_EFFECT);
            if (effect)
                icon.remove_effect(effect);
        }
        this._themeContext = null;
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
        this._disableTray();
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
