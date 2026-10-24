#!/usr/bin/python3
"""KRunner bridge for the NoctraOS search (flavour kubuntu, docs/flavours.md phase 5).

GNOME gets Super+Space from a Shell extension. On KDE Plasma the same shortcut opens KRunner, and this
file makes KRunner answer with the SAME results: it implements the KRunner DBus runner interface
(org.kde.krunner1, a "DBus runner": see configs/plasma/krunner/noctraos-search.desktop) and gets its
results from the shared search helper (`noctraos-search --query`), so the index, the clipboard history,
the browser history and every setting are the ones the GNOME flavour uses too.

  noctraos-search-plasma              serve the runner on the session bus (KRunner starts it on demand)
  noctraos-search-plasma --setup      once per account: Super+Space opens KRunner (keeps the old shortcut)
  noctraos-search-plasma --status     what is installed, as text or --json (noc doctor)

The KRunner interface (read from KDE's sources, 2026-10-14):
  Match(query) -> a(sssida{sv})   id, text, iconName, categoryRelevance (KRunner::QueryMatch), relevance
                                  0..1, properties {subtext, category, multiline, urls}
  Run(matchId, actionId)          actionId is empty for the default action (open, or copy for clipboard)
  Actions() -> a(sss)             none: the default action does the right thing, as in the GNOME overlay
  Teardown(), SetActivationToken()  accepted and ignored
The shortcut goes through KGlobalAccel itself (setShortcutKeys), discovering KRunner's component and
action at runtime, so no kglobalshortcutsrc spelling is guessed at. One dependency, PyGObject, which the
Plasma desktop module installs.
"""
import argparse
import base64
import collections
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SEARCH_CLI = os.environ.get('NOCTRAOS_SEARCH_CLI', '/usr/local/bin/noctraos-search')
BUS_NAME = 'org.kde.noctraos.search'
OBJECT_PATH = '/runner'
KRUNNER_IFACE = 'org.kde.krunner1'
QUERY_TIMEOUT = 4                    # seconds; the helper is local, and a stuck one must not wedge KRunner
CLIPBOARD_KEEP = 500                 # clipboard payloads remembered between Match and Run (bounded)

# KRunner::QueryMatch::CategoryRelevance (krunner/src/querymatch.h): groups results by source.
RELEVANCE_LOW, RELEVANCE_MODERATE, RELEVANCE_HIGH = 30, 50, 70
CATEGORY = {'file': 'Files and folders', 'history': 'Browser history', 'clipboard': 'Clipboard', 'web': 'Web'}
# KDE icon names; the search core hands out GNOME symbolic names, so each kind is mapped here.
ICON = {'file': 'text-x-generic', 'history': 'internet-web-browser', 'clipboard': 'edit-paste', 'web': 'internet-web-browser'}
FOLDER_ICON = 'folder'
# The same three engines as ENGINES in extensions/noctraos-search@noctraos.local/extension.js; tests/test_plasma_search.py
# keeps the two maps equal, so both flavours offer the same web search.
WEB_ENGINES = {'DuckDuckGo': 'https://duckduckgo.com/?q=',
               'Google': 'https://www.google.com/search?q=',
               'Bing': 'https://www.bing.com/search?q='}

# Clipboard text is the one payload that can be huge, so the match id carries a short digest and the text
# waits here (bounded) until Run. Everything else is small enough to travel inside the id.
_payloads = collections.OrderedDict()


def _remember(text):
    digest = hashlib.sha256(text.encode('utf-8', 'replace')).hexdigest()[:16]
    _payloads[digest] = text
    _payloads.move_to_end(digest)
    while len(_payloads) > CLIPBOARD_KEEP:
        _payloads.popitem(last=False)
    return digest


def match_id(kind, payload):
    """A self-contained id for a result: <kind>:<base64 payload> (the clipboard uses a digest)."""
    if kind == 'clipboard':
        return f'clipboard:{_remember(payload)}'
    encoded = base64.urlsafe_b64encode(payload.encode('utf-8', 'replace')).decode('ascii')
    return f'{kind}:{encoded}'


def decode_match_id(value):
    """(kind, payload) from a match id, or (None, None) for an id we did not make."""
    kind, _, encoded = (value or '').partition(':')
    if kind not in ('file', 'history', 'web', 'clipboard', 'settings') or not encoded:
        return None, None
    if kind == 'clipboard':
        return kind, _payloads.get(encoded)
    try:
        return kind, base64.urlsafe_b64decode(encoded.encode('ascii')).decode('utf-8', 'replace')
    except (ValueError, UnicodeError):
        return None, None



def matches_for(results, query, web_provider='DuckDuckGo', web=True):
    """KRunner matches for the search helper's results, in the same order the overlay shows them."""
    term = (query or '').strip().casefold()
    matches = []
    for result in results:
        kind = result.get('kind')
        if kind == 'file':
            payload = result.get('path', '')
            icon = FOLDER_ICON if result.get('icon') == 'folder-symbolic' else ICON['file']
        elif kind == 'history':
            payload, icon = result.get('uri', ''), ICON['history']
        elif kind == 'clipboard':
            payload, icon = result.get('text', ''), ICON['clipboard']
        else:
            continue
        if not payload:
            continue
        title = ' '.join(str(result.get('title', '')).split())
        # An exact title match floats above the rest; clipboard entries stay below the files, as in the overlay.
        relevance = RELEVANCE_HIGH if term and title.casefold() == term else (
            RELEVANCE_MODERATE if kind == 'file' else RELEVANCE_LOW)
        matches.append({'id': match_id(kind, payload), 'text': title or payload,
                        'icon': icon, 'relevance': relevance,
                        'properties': {'subtext': ' '.join(str(result.get('detail', '')).split()),
                                       'category': CATEGORY[kind]}})
    if web and query.strip():
        provider = web_provider if web_provider in WEB_ENGINES else 'DuckDuckGo'
        from urllib.parse import quote
        url = WEB_ENGINES[provider] + quote(query.strip(), safe='')
        matches.append({'id': match_id('web', url), 'text': f'Search {provider} for “{query.strip()}”',
                        'icon': ICON['web'], 'relevance': RELEVANCE_LOW,
                        'properties': {'subtext': 'Web · Opens in your browser', 'category': CATEGORY['web']}})
    return matches


def settings_matches(query, notice='', history_setup=False):
    matches = []
    if notice or query.strip().casefold() in ('search settings', 'noctraos search settings'):
        matches.append({'id': match_id('settings', 'search'), 'text': 'NoctraOS Search settings',
                        'icon': 'configure', 'relevance': RELEVANCE_HIGH,
                        'properties': {'subtext': notice or 'Sources, indexed folders and browser history',
                                       'category': 'Settings'}})
    if history_setup:
        matches.append({'id': match_id('settings', 'history'),
                        'text': 'Set up browser-history search', 'icon': 'internet-web-browser',
                        'relevance': RELEVANCE_MODERATE,
                        'properties': {'subtext': 'Search your visited pages locally · opt-in',
                                       'category': 'Settings'}})
    return matches


def run_search(query):
    """The shared helper's answer: the same code path, index and settings as the GNOME overlay."""
    # No setup offer while the helper is broken: the GNOME overlay asks only after `--status`
    # answered, so an unavailable search shows its notice (and the settings action) alone.
    unavailable = ([], 'Local search is unavailable. Check Search settings.', False)
    try:
        process = subprocess.run([SEARCH_CLI, '--query', query], capture_output=True, text=True,
                                 timeout=QUERY_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return unavailable
    if process.returncode != 0:
        return unavailable
    try:
        payload = json.loads(process.stdout)
    except ValueError:
        return unavailable
    return payload.get('results', []), payload.get('notice', ''), bool(payload.get('history_setup_needed'))


def web_settings():
    """(web-provider, web) from the search settings — the GSettings schema both flavours install."""
    schema_id = 'org.gnome.shell.extensions.noctraos-search'
    try:
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio
        # Gio.Settings.new aborts the process when the schema is missing (not a Python exception), so ask first.
        if Gio.SettingsSchemaSource.get_default().lookup(schema_id, True) is None:
            return 'DuckDuckGo', True
        settings = Gio.Settings.new(schema_id)
        return settings.get_string('web-provider'), settings.get_boolean('web')
    except Exception:  # noqa: BLE001 — optional GI/schema support must not abort search
        return 'DuckDuckGo', True


def _open(payload, activation_token=''):
    opener = shutil.which('xdg-open')
    if not opener:
        return False
    environment = dict(os.environ)
    if activation_token:
        environment['XDG_ACTIVATION_TOKEN'] = activation_token
    subprocess.Popen([opener, payload], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True, env=environment)
    return True


def _copy(text):
    """Copy to the clipboard with whatever the session offers (Klipper is always there on Plasma)."""
    for argv in (['wl-copy'], ['xclip', '-selection', 'clipboard'], ['copyq', 'copy', '-']):
        if not shutil.which(argv[0]):
            continue
        environment = {**os.environ, 'QT_QPA_PLATFORM': 'xcb'} if argv[0] == 'copyq' else None
        try:
            subprocess.run(argv, input=text, text=True, timeout=5, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment)
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    for qdbus in ('qdbus6', 'qdbus-qt6'):
        if not shutil.which(qdbus):
            continue
        try:
            subprocess.run([qdbus, 'org.kde.klipper', '/klipper',
                            'org.kde.klipper.klipper.setClipboardContents', text],
                           timeout=5, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


def activate(kind, payload, action_id='', activation_token=''):
    """Run a match: the default action opens it, except a clipboard entry, which is copied."""
    if kind == 'clipboard':
        return _copy(payload)
    if kind == 'settings':
        flag = '--setup-history' if payload == 'history' else '--settings'
        environment = dict(os.environ)
        if activation_token:
            environment['XDG_ACTIVATION_TOKEN'] = activation_token
        subprocess.Popen([SEARCH_CLI, flag], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True, env=environment)
        return True
    if kind == 'file' and action_id == 'reveal':
        folder = str(Path(payload).parent)
        for manager in ('dolphin', 'xdg-open'):
            if shutil.which(manager):
                subprocess.Popen([manager, folder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
                return True
        return False
    if kind in ('history', 'web', 'file'):
        return _open(payload, activation_token)
    return False


# ---------------------------------------------------------------- the KRunner DBus service

INTROSPECTION = """<node>
  <interface name="org.kde.krunner1">
    <method name="Teardown"/>
    <method name="Actions">
      <arg name="matches" type="a(sss)" direction="out"/>
    </method>
    <method name="Run">
      <arg name="matchId" type="s" direction="in"/>
      <arg name="actionId" type="s" direction="in"/>
    </method>
    <method name="Match">
      <arg name="query" type="s" direction="in"/>
      <arg name="matches" type="a(sssida{sv})" direction="out"/>
    </method>
    <method name="SetActivationToken">
      <arg name="token" type="s" direction="in"/>
    </method>
  </interface>
</node>"""


def _gi():
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio, GLib
    return Gio, GLib


class RunnerService:
    """Answers KRunner's Match/Run calls with the NoctraOS search results."""

    def __init__(self, connection, Gio, GLib):
        self._Gio, self._GLib = Gio, GLib
        self._activation_token = ''
        node = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION)
        self._interface = node.interfaces[0]
        import warnings
        with warnings.catch_warnings():      # register_object is deprecated but is the only API PyGObject has here
            warnings.simplefilter('ignore', DeprecationWarning)
            connection.register_object(OBJECT_PATH, self._interface, self._on_call, None, None)

    def _on_call(self, connection, sender, path, interface, method, parameters, invocation):
        try:
            if method == 'Match':
                query = parameters.unpack()[0]
                results, notice, history_setup = run_search(query)
                provider, web = web_settings()
                body = [(match['id'], match['text'], match['icon'], int(match['relevance']),
                         float(match['relevance']) / 100.0,
                         {key: self._GLib.Variant('s', value) for key, value in match['properties'].items()})
                        for match in matches_for(results, query, provider, web)
                        + settings_matches(query, notice, history_setup)]
                invocation.return_value(self._GLib.Variant('(a(sssida{sv}))', (body,)))
            elif method == 'Run':
                identifier, action_id = parameters.unpack()
                kind, payload = decode_match_id(identifier)
                token, self._activation_token = self._activation_token, ''
                if payload:
                    activate(kind, payload, action_id, token)
                invocation.return_value(None)
            elif method == 'Actions':
                invocation.return_value(self._GLib.Variant('(a(sss))', ([],)))
            elif method == 'SetActivationToken':
                self._activation_token = parameters.unpack()[0]
                invocation.return_value(None)
            else:                                   # Teardown, SetActivationToken: accepted, nothing to do
                invocation.return_value(None)
        except Exception as error:  # noqa: BLE001 — every D-Bus call must receive a reply
            invocation.return_dbus_error(KRUNNER_IFACE + '.Error', str(error))


def serve():
    Gio, GLib = _gi()
    loop = GLib.MainLoop()
    state = {'service': None}

    def acquired(connection, _name):
        state['service'] = RunnerService(connection, Gio, GLib)

    def lost(_connection, _name):
        loop.quit()

    Gio.bus_own_name(Gio.BusType.SESSION, BUS_NAME, Gio.BusNameOwnerFlags.NONE, acquired, None, lost)
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    if state['service'] is None:
        print(f'noctraos-search-plasma: could not own {BUS_NAME} on the session bus', file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------- Super+Space (KGlobalAccel)

# KGlobalAccel's D-Bus destination is org.kde.kglobalaccel (lowercase); the interface it exports is org.kde.KGlobalAccel.
KGL_SERVICE = 'org.kde.kglobalaccel'
KGL_IFACE = 'org.kde.KGlobalAccel'
KGL_PATH = '/kglobalaccel'
COMPONENT_IFACE = 'org.kde.kglobalaccel.Component'
# Qt::MetaModifier | Qt::Key_Space, as QKeyCombination::toCombined() (what kglobalaccel marshals).
META_SPACE = 0x10000000 | 0x20
ALT_SPACE = 0x08000000 | 0x20
ALT_F2 = 0x08000000 | 0x01000031          # Qt::Key_F2 = 0x01000031


def find_krunner_action(connection, Gio, GLib):
    """(component, action, keys, defaults) for KRunner's launch shortcut, or None.

    Discovered rather than hardcoded: KRunner's component and action names are kglobalaccel's business,
    and this finds them whether it calls them 'krunner'/'Run Command' or something else.
    The struct is KGlobalShortcutInfo (kglobalshortcutinfo_dbus.cpp): actionUnique, actionFriendly,
    componentUnique, componentFriendly, contextUnique, contextFriendly, keys, defaultKeys — where each
    key list is one combined int per shortcut (QKeyCombination::toCombined()).
    """
    paths = connection.call_sync(KGL_SERVICE, KGL_PATH, KGL_IFACE, 'allComponents', None, None,
                                 Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
    best = None
    for path in paths:
        if 'krunner' not in path.casefold():
            continue
        try:
            infos = connection.call_sync(KGL_SERVICE, path, COMPONENT_IFACE, 'allShortcutInfos', None, None,
                                         Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
        except GLib.Error:
            continue
        for action, action_name, component, component_name, _ctx, _ctx_name, keys, defaults in infos:
            if 'krunner' not in f'{component} {component_name} {action} {action_name}'.casefold() \
                    and action != 'Run Command':
                continue
            score = 3 if action in ('Run Command', '_launch') else (2 if ALT_SPACE in defaults or ALT_F2 in defaults else 1)
            if best is None or score > best[0]:
                best = (score, component, action, list(keys), list(defaults))
    return None if best is None else best[1:]


def set_super_space(connection, Gio, GLib):
    """Add Meta+Space to KRunner's shortcut, keeping the ones it already has. Returns (ok, message)."""
    found = find_krunner_action(connection, Gio, GLib)
    if found is None:
        return False, 'KRunner has no global shortcut to change (is KRunner installed?)'
    component, action, keys, _defaults = found
    current = keys                                 # an empty list can be an explicit disabled shortcut
    if META_SPACE in current:
        return True, 'Super+Space already opens KRunner'
    # Qt reads four chords even for a single-key shortcut. Pad them: older KF6
    # deserializers abort KWin if the array ends early.
    existing = connection.call_sync(KGL_SERVICE, KGL_PATH, KGL_IFACE, 'shortcutKeys',
                                    GLib.Variant('(as)', ([component, action, '', ''],)), None,
                                    Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
    sequences = []
    for sequence in existing:
        chords = list(sequence[0])
        if len(chords) > 4:
            return False, 'KRunner returned an unsupported shortcut sequence'
        sequences.append((chords + [0] * (4 - len(chords)),))
    sequences.append(([META_SPACE, 0, 0, 0],))
    connection.call_sync(KGL_SERVICE, KGL_PATH, KGL_IFACE, 'setForeignShortcutKeys',
                         GLib.Variant('(asa(ai))', ([component, action, '', ''], sequences)), None,
                         Gio.DBusCallFlags.NONE, 5000, None)
    updated = find_krunner_action(connection, Gio, GLib)
    if updated is None or META_SPACE not in updated[2]:
        return False, 'Super+Space could not be assigned; check System Settings > Shortcuts for a conflict'
    return True, f'Super+Space now opens KRunner ({component}/{action})'


def status(json_mode=False):
    """What is installed, for the installer and `noc doctor`."""
    installed = {'runner': Path('/usr/local/bin/noctraos-search-plasma').is_file(),
                 'metadata': Path('/usr/share/krunner/dbusplugins/noctraos-search.desktop').is_file(),
                 'service': Path('/usr/share/dbus-1/services/org.kde.noctraos.search.service').is_file(),
                 'search': Path(SEARCH_CLI).is_file()}
    shortcut = None
    try:
        Gio, GLib = _gi()
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        found = find_krunner_action(connection, Gio, GLib)
        if found is not None:
            active = found[2]
            shortcut = META_SPACE in active
    except Exception:  # noqa: BLE001 — a missing or unavailable session bus is an unknown status
        shortcut = None
    report = {**installed, 'shortcut': shortcut, 'installed': all(installed.values())}
    if json_mode:
        print(json.dumps(report))
    else:
        for name in ('runner', 'metadata', 'service', 'search'):
            print(f'{"OK" if installed[name] else "MISSING"}  {name}')
        print({True: 'OK  Super+Space opens KRunner', False: 'MISSING  Super+Space',
               None: '..  Super+Space (no Plasma session to ask)'}[shortcut])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='NoctraOS search for KRunner (flavour kubuntu)')
    parser.add_argument('--setup', action='store_true', help='add Super+Space to KRunner (once per account)')
    parser.add_argument('--status', action='store_true', help='what is installed')
    parser.add_argument('--json', action='store_true', help='with --status: JSON')
    args = parser.parse_args(argv)
    if args.status:
        return 0 if status(args.json)['installed'] else 1
    if args.setup:
        try:
            Gio, GLib = _gi()
            connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            ok, message = set_super_space(connection, Gio, GLib)
        except Exception as error:  # noqa: BLE001 — report GI and D-Bus setup errors without a traceback
            print(f'Noctra Search: {error}', file=sys.stderr)
            return 1
        print(f'Noctra Search: {message}')
        return 0 if ok else 1
    return serve()


if __name__ == '__main__':
    sys.exit(main())
