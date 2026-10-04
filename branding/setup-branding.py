#!/usr/bin/python3
"""Once per account: enable Noctra's start icon and apply the desktop layout
(top bar kept, taskbar shrunk to a centred dock). Later user choices are kept."""
import json
from pathlib import Path
from gi.repository import Gio


LAYOUT_MARKER = Path.home() / '.config/noctraos/desktop-layout-v1'
# Dock elements only; the clock, tray and system menu stay in the stock top bar.
DOCK_ELEMENTS = [
    {'element': 'leftBox', 'visible': True, 'position': 'stackedTL'},
    {'element': 'showAppsButton', 'visible': False, 'position': 'stackedTL'},
    {'element': 'taskbar', 'visible': True, 'position': 'stackedTL'},
    {'element': 'centerBox', 'visible': False, 'position': 'stackedBR'},
    {'element': 'activitiesButton', 'visible': False, 'position': 'stackedBR'},
    {'element': 'rightBox', 'visible': False, 'position': 'stackedBR'},
    {'element': 'systemMenu', 'visible': False, 'position': 'stackedBR'},
    {'element': 'dateMenu', 'visible': False, 'position': 'stackedBR'},
    {'element': 'desktopButton', 'visible': False, 'position': 'stackedBR'},
]


def apply_layout(taskbar):
    """Keys are per monitor; "0" covers the primary one (the taskbar falls back to the index)."""
    values = {
        'panel-lengths': json.dumps({'0': -1}),           # -1: dock mode, hugs its icons
        'panel-anchors': json.dumps({'0': 'MIDDLE'}),
        'panel-sizes': json.dumps({'0': 40}),
        'panel-element-positions': json.dumps({'0': DOCK_ELEMENTS}),
    }
    taskbar.set_boolean('stockgs-keep-top-panel', True)
    taskbar.set_int('panel-margin', 6)
    for key, value in values.items():
        taskbar.set_string(key, value)


def setup():
    config = Path.home() / '.config/noctraos'
    branding_marker = config / 'branding-provisioned'
    if not branding_marker.exists():
        uuid = 'noctraos-branding@noctraos.local'
        shell = Gio.Settings.new('org.gnome.shell')
        enabled = shell.get_strv('enabled-extensions')
        if uuid not in enabled and not shell.set_strv('enabled-extensions', enabled + [uuid]):
            raise RuntimeError('Extension settings are locked')
        Gio.Settings.sync()
        config.mkdir(parents=True, exist_ok=True)
        branding_marker.touch()
    if LAYOUT_MARKER.exists():
        return
    schema = Gio.SettingsSchemaSource.get_default().lookup('org.gnome.shell.extensions.zorin-taskbar', True)
    if schema and schema.has_key('stockgs-keep-top-panel'):
        taskbar = Gio.Settings.new_full(schema, None, None)
        if not taskbar.is_writable('panel-lengths'):
            raise RuntimeError('Taskbar settings are locked')
        apply_layout(taskbar)
        # Zorin's supported scale is 5 px per step; 0 uses the rounder stock theme.
        if taskbar.get_int('global-border-radius') == 0:
            taskbar.set_int('global-border-radius', 1)
        Gio.Settings.sync()
    config.mkdir(parents=True, exist_ok=True)
    LAYOUT_MARKER.touch()


if __name__ == '__main__':
    setup()
