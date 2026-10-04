#!/usr/bin/python3
"""Enable Noctra's start icon once per account; retain later user choices."""
from pathlib import Path
from gi.repository import Gio


def setup():
    marker = Path.home() / '.config/noctraos/branding-provisioned'
    if marker.exists():
        return
    uuid = 'noctraos-branding@noctraos.local'
    shell = Gio.Settings.new('org.gnome.shell')
    enabled = shell.get_strv('enabled-extensions')
    if uuid not in enabled and not shell.set_strv('enabled-extensions', enabled + [uuid]):
        raise RuntimeError('Extension settings are locked')
    source = Gio.SettingsSchemaSource.get_default()
    schema = source.lookup('org.gnome.shell.extensions.zorin-taskbar', True)
    if schema and schema.has_key('global-border-radius'):
        taskbar = Gio.Settings.new_full(schema, None, None)
        # Zorin's supported scale is 5 px per step; 0 uses the rounder stock theme.
        if taskbar.get_int('global-border-radius') == 0 and taskbar.is_writable('global-border-radius'):
            if not taskbar.set_int('global-border-radius', 1):
                raise RuntimeError('Taskbar corner setting could not be saved')
    Gio.Settings.sync()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()


if __name__ == '__main__':
    setup()
