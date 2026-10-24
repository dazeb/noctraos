"""Desktop-owned controls and the browser-history opt-in query payload."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'search'))
SPEC = importlib.util.spec_from_file_location('search_preferences_main', ROOT / 'search/main.py')
SEARCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SEARCH)


class DesktopAndHistoryTests(unittest.TestCase):
    def test_desktop_detection_uses_session_not_flavour(self):
        for desktop, expected in [('KDE', True), ('plasma', True), ('ubuntu:KDE', True),
                                  ('GNOME', False), ('not-kde', False), ('', False)]:
            with self.subTest(desktop=desktop), patch.dict(os.environ, {
                    'XDG_CURRENT_DESKTOP': desktop, 'NOCTRAOS_FLAVOUR': 'zorin'}):
                self.assertEqual(SEARCH.desktop_is_plasma(), expected)

    def test_query_offers_history_only_when_unanswered_and_history_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / 'History'
            history.write_bytes(b'fixture browser history')
            for setup, available, expected in [('unset', True, True), ('unset', False, False),
                                                ('dismissed', True, False), ('configured', True, False)]:
                with self.subTest(setup=setup, available=available):
                    class Settings:
                        def get_string(self, key):
                            return setup

                    config = {'files': False, 'clipboard': False, 'history': False, 'max-results': 12}
                    output = io.StringIO()
                    patterns = [str(history)] if available else []
                    with patch.object(SEARCH, 'get_settings', return_value=Settings()), \
                            patch.object(SEARCH, 'options', return_value=config), \
                            patch.object(SEARCH, 'cache_dir', return_value=Path(tmp)), \
                            patch.object(SEARCH.browsers, '_patterns', return_value=patterns), \
                            patch.object(SEARCH.browsers, 'refresh_history', side_effect=AssertionError('not opted in')), \
                            patch.object(SEARCH.browsers, 'search_history', side_effect=AssertionError('not opted in')), \
                            patch.object(SEARCH.browsers, 'default_browser', side_effect=AssertionError('no subprocess needed')), \
                            patch.object(sys, 'argv', ['noctraos-search', '--query', 'example']), \
                            contextlib.redirect_stdout(output):
                        SEARCH.main()
                    self.assertEqual(json.loads(output.getvalue()), {
                        'results': [], 'notice': '', 'history_setup_needed': expected})
                    self.assertEqual(list(Path(tmp).iterdir()), [history])


GTK_DRIVER = r'''
import json, sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gio, GLib, Gtk
import main, preferences

settings = Gio.Settings.new(main.SCHEMA)
settings.set_boolean('apps', False)
settings.set_strv('toggle-search', ['not-a-valid-shortcut'])
settings.set_strv('roots', [sys.argv[2]])
commands, errors = [], []

def walk(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from walk(child)

def inspect():
    try:
        window = next(w for w in Gtk.Window.list_toplevels() if w.get_title() == 'Search settings')
        widgets = list(walk(window))
        switches = {w.get_accessible().get_name(): w for w in widgets if isinstance(w, Gtk.Switch)}
        buttons = {w.get_label(): w for w in widgets if isinstance(w, Gtk.Button)}
        shortcuts = [w for w in widgets if isinstance(w, Gtk.Button) and
                     w.get_accessible().get_name() == 'Change keyboard shortcut']
        if main.desktop_is_plasma():
            assert 'Applications and system settings' not in switches
            assert shortcuts == []
            buttons['Application search settings…'].clicked()
            buttons['Keyboard shortcuts…'].clicked()
            switches['Files and folders'].set_active(False)
            switches['Web search'].set_active(False)
            buttons['Save settings'].clicked()
            assert settings.get_boolean('files') is False
            assert settings.get_boolean('web') is False
            assert settings.get_boolean('apps') is False
            assert settings.get_strv('toggle-search') == ['not-a-valid-shortcut']
            assert settings.get_boolean('history') is False
            assert settings.get_string('history-setup') == 'unset'
            assert commands == [['systemsettings', 'kcm_plasmasearch'], ['systemsettings', 'kcm_keys']]
            labels = [w.get_text() for w in widgets if isinstance(w, Gtk.Label)]
            assert 'Settings saved. The file index is rebuilding in the background.' in labels
            print(json.dumps({'saved': True, 'native_settings': commands, 'history': False}))
        else:
            assert switches['Applications and system settings'].get_active() is False
            assert len(shortcuts) == 1
            assert 'Application search settings…' not in buttons
            print(json.dumps({'apps_control': True, 'shortcut_control': True}))
        window.destroy()
    except Exception as error:
        errors.append(str(error))
        for window in Gtk.Window.list_toplevels():
            window.destroy()
    return False

GLib.timeout_add(150, inspect)
with patch.object(main, 'request_index'), patch.object(preferences.subprocess, 'Popen',
        side_effect=lambda argv, **kwargs: commands.append(argv)):
    preferences.show_settings(settings)
assert not errors, errors
'''


@unittest.skipUnless(shutil.which('xvfb-run') and shutil.which('glib-compile-schemas') and
                     shutil.which('dbus-run-session'), 'needs GTK smoke-test tools')
class PreferencesSmokeTests(unittest.TestCase):
    def test_plasma_saves_without_gnome_schema_and_gnome_keeps_its_controls(self):
        python = '/usr/bin/python3'
        env = {k: v for k, v in os.environ.items() if k not in ('LD_LIBRARY_PATH', 'LD_PRELOAD')}
        probe = subprocess.run([python, '-c', 'import gi; gi.require_version("Gtk", "3.0")'],
                               env=env, capture_output=True)
        if probe.returncode:
            self.skipTest('system Python GTK bindings unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            schema = ROOT / 'configs/gsettings/org.gnome.shell.extensions.noctraos-search.gschema.xml'
            shutil.copy(schema, tmp)
            subprocess.run(['glib-compile-schemas', tmp], check=True)
            driver = Path(tmp) / 'smoke.py'
            driver.write_text(GTK_DRIVER)
            for desktop, expected in [('KDE', {'saved': True, 'native_settings': [
                    ['systemsettings', 'kcm_plasmasearch'], ['systemsettings', 'kcm_keys']], 'history': False}),
                    ('GNOME', {'apps_control': True, 'shortcut_control': True})]:
                with self.subTest(desktop=desktop):
                    result = subprocess.run(['dbus-run-session', '--', 'xvfb-run', '-a', python,
                                             str(driver), str(ROOT / 'search'), tmp],
                                            env={**env, 'XDG_CURRENT_DESKTOP': desktop,
                                                 'GSETTINGS_BACKEND': 'memory', 'GSETTINGS_SCHEMA_DIR': tmp},
                                            capture_output=True, text=True, timeout=20)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    # Daemons in the session can print to the driver's stdout; the result is its last line.
                    self.assertEqual(json.loads(result.stdout.strip().splitlines()[-1]), expected)


if __name__ == '__main__':
    unittest.main()