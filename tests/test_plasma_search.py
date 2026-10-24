"""Super+Space on the kubuntu flavour: the KRunner bridge (search/krunner.py), its metadata and the module.

The mapping and the match-id codec are pure Python and tested directly. The D-Bus service and the
KGlobalAccel shortcut are tested for real on a private session bus (dbus-run-session) with a stub search
helper and a stand-in kglobalaccel, so the protocol and the key encoding are exercised, not assumed.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "search"))
import krunner

MODULE = ROOT / "install/desktop/plasma/09_super_search.sh"
METADATA = ROOT / "configs/plasma/krunner/noctraos-search.desktop"
ACTIVATION = ROOT / "configs/plasma/krunner/org.kde.noctraos.search.service"
SETUP = ROOT / "configs/plasma/apply-search.sh"
AUTOSTART = ROOT / "configs/autostart/noctraos-plasma-search.desktop"
EXTENSION = ROOT / "extensions/noctraos-search@noctraos.local/extension.js"

FILES = [
    {"kind": "file", "title": "alpha.txt", "detail": "/home/x/alpha.txt", "path": "/home/x/alpha.txt",
     "icon": "text-x-generic-symbolic"},
    {"kind": "file", "title": "notes", "detail": "/home/x/notes", "path": "/home/x/notes", "icon": "folder-symbolic"},
    {"kind": "history", "title": "Alpha docs", "detail": "https://example.org/a · Firefox",
     "uri": "https://example.org/a", "icon": "web-browser-symbolic"},
    {"kind": "clipboard", "title": "alpha clip", "detail": "Clipboard · Enter to copy", "text": "alpha clip",
     "icon": "edit-paste-symbolic"},
]


def sh(body):
    """Run a function of iso/flavours/kubuntu.sh (sourcing it only defines functions)."""
    return subprocess.run(["bash", "-c", f'set -Eeuo pipefail; source "{ROOT}/iso/flavours/kubuntu.sh"; {body}'],
                          capture_output=True, text=True, cwd=str(ROOT), check=False)


class MappingTests(unittest.TestCase):
    """The search helper's results become KRunner matches, with the same meaning as the GNOME overlay."""

    def matches(self, **kwargs):
        return krunner.matches_for(FILES, "alpha", web=False, **kwargs)

    def test_notices_and_settings_queries_offer_a_working_settings_action(self):
        for query, notice in [('alpha', 'Local search is unavailable.'), ('search settings', '')]:
            matches = krunner.settings_matches(query, notice)
            self.assertEqual(len(matches), 1)
            kind, payload = krunner.decode_match_id(matches[0]['id'])
            self.assertEqual((kind, payload), ('settings', 'search'))
            with mock.patch.object(krunner.subprocess, 'Popen') as launch:
                self.assertTrue(krunner.activate(kind, payload, activation_token='plasma-token'))
            self.assertEqual(launch.call_args.args[0], [krunner.SEARCH_CLI, '--settings'])
            self.assertEqual(launch.call_args.kwargs['env']['XDG_ACTIVATION_TOKEN'], 'plasma-token')

    def test_the_history_setup_offer_is_a_match_only_when_the_helper_asks_for_it(self):
        # The GNOME overlay shows its banner only when `--status` says the question is unanswered and a
        # browser history exists; KRunner has no banner, so the same offer is a match beside the results.
        for asked, expected in [(True, 1), (False, 0)]:
            with self.subTest(asked=asked):
                matches = krunner.settings_matches('alpha', '', asked)
                self.assertEqual(len(matches), expected)
                if asked:
                    kind, payload = krunner.decode_match_id(matches[0]['id'])
                    self.assertEqual((kind, payload), ('settings', 'history'))
                    with mock.patch.object(krunner.subprocess, 'Popen') as launch:
                        self.assertTrue(krunner.activate(kind, payload, activation_token='plasma-token'))
                    self.assertEqual(launch.call_args.args[0], [krunner.SEARCH_CLI, '--setup-history'])

    def test_an_unavailable_helper_offers_no_history_setup(self):
        # A broken helper cannot answer the question, so the notice travels alone (like the GNOME overlay).
        for stdout, code in [('', 1), ('not json', 0)]:
            with self.subTest(stdout=stdout), mock.patch.object(krunner.subprocess, 'run',
                    return_value=mock.Mock(returncode=code, stdout=stdout)):
                results, notice, history_setup = krunner.run_search('alpha')
                self.assertEqual((results, history_setup), ([], False))
                self.assertIn('unavailable', notice)
                self.assertEqual(len(krunner.settings_matches('alpha', notice, history_setup)), 1)

    def test_web_activation_passes_the_wayland_token_to_the_opener(self):
        with mock.patch.object(krunner.shutil, 'which', return_value='/usr/bin/xdg-open'), \
                mock.patch.object(krunner.subprocess, 'Popen') as launch:
            krunner.activate('web', 'https://example.org/', activation_token='plasma-token')
        self.assertEqual(launch.call_args.kwargs['env']['XDG_ACTIVATION_TOKEN'], 'plasma-token')

    def test_shortcut_setup_keeps_disabled_defaults_disabled_and_checks_acceptance(self):
        connection, Gio, GLib = mock.Mock(), mock.Mock(), mock.Mock()
        GLib.Variant.side_effect = lambda signature, values: (signature, values)
        connection.call_sync.return_value.unpack.return_value = [[]]
        found = ('org.kde.krunner.desktop', '_launch', [], [krunner.ALT_SPACE])
        updated = ('org.kde.krunner.desktop', '_launch', [krunner.META_SPACE], [krunner.ALT_SPACE])
        with mock.patch.object(krunner, 'find_krunner_action', side_effect=[found, updated]):
            self.assertTrue(krunner.set_super_space(connection, Gio, GLib)[0])
        self.assertEqual(connection.call_sync.call_args.args[4],
                         ('(asa(ai))', (['org.kde.krunner.desktop', '_launch', '', ''],
                                        [([krunner.META_SPACE, 0, 0, 0],)])))
        with mock.patch.object(krunner, 'find_krunner_action', side_effect=[found, found]):
            self.assertFalse(krunner.set_super_space(connection, Gio, GLib)[0])

    def test_discovery_does_not_ask_other_components_for_shortcut_info(self):
        connection, Gio, GLib = mock.Mock(), mock.Mock(), mock.Mock()
        infos = [('RunClipboard', 'Clipboard', 'org.kde.krunner.desktop', 'KRunner', '', '', [], []),
                 ('_launch', 'KRunner', 'org.kde.krunner.desktop', 'KRunner', '', '', [], [krunner.ALT_SPACE])]
        connection.call_sync.side_effect = [mock.Mock(unpack=lambda: [['/component/kwin', '/component/org_kde_krunner_desktop']]),
                                            mock.Mock(unpack=lambda: [infos])]
        self.assertEqual(krunner.find_krunner_action(connection, Gio, GLib)[1], '_launch')
        self.assertEqual(connection.call_sync.call_count, 2)

    def test_setup_preserves_all_chords_in_existing_shortcuts(self):
        connection, Gio, GLib = mock.Mock(), mock.Mock(), mock.Mock()
        GLib.Variant.side_effect = lambda signature, values: (signature, values)
        sequence = [0x04000000 | ord('K'), 0x04000000 | ord('R'), 0, 0]
        connection.call_sync.return_value.unpack.return_value = [[(sequence,)]]
        before = ('krunner', 'Run Command', [sequence[0]], [])
        after = ('krunner', 'Run Command', [sequence[0], krunner.META_SPACE], [])
        with mock.patch.object(krunner, 'find_krunner_action', side_effect=[before, after]):
            self.assertTrue(krunner.set_super_space(connection, Gio, GLib)[0])
        self.assertEqual(connection.call_sync.call_args.args[4][1][1],
                         [(sequence,), ([krunner.META_SPACE, 0, 0, 0],)])

    def test_every_result_becomes_a_match_with_its_own_category_and_icon(self):
        matches = self.matches()
        self.assertEqual(len(matches), 4)
        self.assertEqual({m["properties"]["category"] for m in matches},
                         {"Files and folders", "Browser history", "Clipboard"})
        by_text = {m["text"]: m for m in matches}
        self.assertEqual(by_text["alpha.txt"]["icon"], "text-x-generic")
        self.assertEqual(by_text["notes"]["icon"], "folder")
        self.assertEqual(by_text["Alpha docs"]["icon"], "internet-web-browser")
        self.assertEqual(by_text["alpha clip"]["icon"], "edit-paste")

    def test_a_folder_gets_the_folder_icon_and_an_exact_title_match_floats_up(self):
        matches = krunner.matches_for([FILES[1]], "notes", web=False)
        self.assertEqual(matches[0]["icon"], "folder")
        self.assertEqual(matches[0]["relevance"], krunner.RELEVANCE_HIGH)

    def test_files_outrank_the_clipboard(self):
        by_kind = {krunner.decode_match_id(m["id"])[0]: m["relevance"] for m in self.matches()}
        self.assertEqual(by_kind["file"], krunner.RELEVANCE_MODERATE)
        self.assertEqual(by_kind["clipboard"], krunner.RELEVANCE_LOW)

    def test_the_web_offer_comes_last_and_uses_the_configured_engine(self):
        matches = krunner.matches_for(FILES, "alpha beta", web_provider="Google")
        self.assertEqual(matches[-1]["properties"]["category"], "Web")
        self.assertIn("Google", matches[-1]["text"])
        kind, url = krunner.decode_match_id(matches[-1]["id"])
        self.assertEqual((kind, url), ("web", "https://www.google.com/search?q=alpha%20beta"))

    def test_an_unknown_provider_falls_back_and_an_empty_query_offers_no_web_search(self):
        self.assertIn("DuckDuckGo", krunner.matches_for([], "x", web_provider="Nope")[0]["text"])
        self.assertEqual(krunner.matches_for([], "   "), [])

    def test_a_result_without_a_payload_is_dropped(self):
        self.assertEqual(krunner.matches_for([{"kind": "file", "title": "x"}], "x", web=False), [])
        self.assertEqual(krunner.matches_for([{"kind": "other", "title": "x", "path": "/x"}], "x", web=False), [])

    def test_match_ids_round_trip_and_foreign_ids_are_refused(self):
        for kind, payload in (("file", "/home/x/a b.txt"), ("history", "https://example.org/q?x=1"),
                              ("web", "https://d/?q=1")):
            self.assertEqual(krunner.decode_match_id(krunner.match_id(kind, payload)), (kind, payload))
        self.assertEqual(krunner.decode_match_id(krunner.match_id("clipboard", "hello world")),
                         ("clipboard", "hello world"))
        for bad in ("", "nonsense", "other:zzz", "file:"):
            self.assertEqual(krunner.decode_match_id(bad), (None, None))

    def test_the_web_engines_match_the_gnome_extension(self):
        """The two flavours must offer the same web search; the map lives in both languages (like the VM guest packages)."""
        javascript = EXTENSION.read_text()
        start = javascript.index("const ENGINES")
        engines = dict(re.findall(r"(\w+):\s*'([^']+)'", javascript[start:javascript.index("};", start)]))
        self.assertEqual(engines, krunner.WEB_ENGINES)


class MetadataTests(unittest.TestCase):
    def test_krunner_metadata_declares_a_dbus_runner_for_our_service(self):
        text = METADATA.read_text()
        self.assertIn("X-Plasma-API=DBus", text)
        self.assertIn("X-Plasma-DBusRunner-Service=org.kde.noctraos.search", text)
        self.assertIn("X-Plasma-DBusRunner-Path=/runner", text)
        self.assertIn("X-KDE-PluginInfo-EnabledByDefault=true", text)
        self.assertIn("Type=Service", text)

    def test_the_activation_file_starts_the_runner_script(self):
        text = ACTIVATION.read_text()
        self.assertIn(f"Name={krunner.BUS_NAME}", text)
        self.assertIn("Exec=/usr/local/bin/noctraos-search-plasma", text)

    def test_the_runner_wrapper_uses_the_system_python(self):
        wrapper = (ROOT / "bin/noctraos-search-plasma").read_text()
        self.assertIn("/usr/bin/python3", wrapper)          # a mise python has no gi (AGENTS.md)
        self.assertIn("krunner.py", wrapper)

    def test_the_session_setup_is_once_per_account_and_only_on_kde(self):
        self.assertIn("plasma-search-v1", SETUP.read_text())
        self.assertIn("--setup", SETUP.read_text())
        self.assertIn("OnlyShowIn=KDE;", AUTOSTART.read_text())
        self.assertIn("apply-search.sh", AUTOSTART.read_text())


class ModuleGuardTests(unittest.TestCase):
    """Off Plasma the module must say NOT APPLIED and touch nothing (docs/flavours.md rule 6)."""

    def run_module(self, desktop):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            log = Path(tmp) / "stub.log"
            for tool in ("sudo", "apt-get", "install"):
                (bin_dir / tool).write_text('#!/bin/sh\necho "$0 $*" >> "$STUB_LOG"\n')
                (bin_dir / tool).chmod(0o755)
            env = {**os.environ, "REPO_ROOT": str(ROOT), "TARGET_USER": "nobody", "TARGET_HOME": tmp,
                   "TARGET_UID": "65534", "XDG_CURRENT_DESKTOP": desktop, "STUB_LOG": str(log),
                   "PATH": f"{bin_dir}:/usr/bin:/bin"}
            result = subprocess.run(["bash", str(MODULE)], capture_output=True, text=True, env=env, check=False)
            return result, log

    def test_off_plasma_it_says_not_applied_and_changes_nothing(self):
        result, log = self.run_module("GNOME")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NOT APPLIED", result.stdout + result.stderr)
        self.assertFalse(log.exists(), log.read_text() if log.exists() else "")

    def test_the_module_declares_its_desktop_and_installs_the_krunner_pieces(self):
        text = MODULE.read_text()
        self.assertEqual(text.splitlines()[1], "# desktops: plasma")
        for needle in ("/usr/share/krunner/dbusplugins/noctraos-search.desktop",
                       "/usr/share/dbus-1/services/org.kde.noctraos.search.service",
                       "/usr/local/bin/noctraos-search-plasma",
                       "/usr/local/share/noctraos-search/",
                       "/etc/xdg/autostart/noctraos-plasma-search.desktop"):
            self.assertIn(needle, text)


@unittest.skipUnless(shutil.which("glib-compile-schemas"), "needs glib-compile-schemas")
class BakeTests(unittest.TestCase):
    """iso/flavours/kubuntu.sh bakes the same files the module installs, so the first session has them."""

    def test_bakes_the_runner_metadata_and_the_shared_search_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            result = sh(f'kubuntu_search "{root}" "{ROOT}"')
            self.assertEqual(result.returncode, 0, result.stderr)
            for path in ("usr/local/bin/noctraos-search", "usr/local/bin/noctraos-search-plasma",
                         "usr/local/share/noctraos-search/krunner.py",
                         "usr/share/krunner/dbusplugins/noctraos-search.desktop",
                         "usr/share/dbus-1/services/org.kde.noctraos.search.service",
                         "usr/local/share/noctraos/plasma/apply-search.sh",
                         "etc/xdg/autostart/noctraos-plasma-search.desktop",
                         "usr/share/glib-2.0/schemas/gschemas.compiled"):
                self.assertTrue((root / path).is_file(), path)
            compiled = (root / "usr/share/glib-2.0/schemas/gschemas.compiled").read_bytes()
            self.assertIn(b"org.gnome.shell.extensions.noctraos-search", compiled)

    def test_every_file_the_module_installs_is_baked(self):
        module = MODULE.read_text()
        bake = (ROOT / "iso/flavours/kubuntu.sh").read_text()
        bake = bake[bake.index("kubuntu_search()"):bake.index("# First-boot provisioning")]
        for name in ("noctraos-search-plasma", "search/*.py", "noctraos-search.desktop",
                     "org.kde.noctraos.search.service", "noctraos-search-settings.desktop", "apply-search.sh", "noctraos-plasma-search.desktop"):
            self.assertIn(name, module, name)
            self.assertIn(name, bake, f"{name} is installed by the module but not baked into the ISO")


def python_with_gi():
    """A Python that can import gi (PyGObject): the system one, or whatever is running the tests."""
    for candidate in ("/usr/bin/python3", sys.executable):
        if candidate and Path(candidate).exists() and \
                subprocess.run([candidate, "-c", "import gi"], capture_output=True, check=False).returncode == 0:
            return candidate
    return None


# The KRunner client: calls the runner over the bus and prints what came back as JSON.
CLIENT = """
import json, sys
import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib
connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)

def call(method, args=None):
    return connection.call_sync(sys.argv[1], "/runner", "org.kde.krunner1", method, args, None,
                                Gio.DBusCallFlags.NONE, 20000, None)

matches = call("Match", GLib.Variant("(s)", ("alpha",))).unpack()[0]
print(json.dumps([{"id": m[0], "text": m[1], "icon": m[2], "relevance": m[3], "relevance_value": m[4],
                   "subtext": m[5]["subtext"], "category": m[5]["category"]} for m in matches]))
print(json.dumps(call("Actions").unpack()[0]))
print(json.dumps(call("Run", GLib.Variant("(ss)", (matches[0][0], ""))).unpack()))
print(json.dumps(call("Run", GLib.Variant("(ss)", ("nonsense", ""))).unpack()))
print(json.dumps(call("Teardown").unpack()))
"""


# A stand-in kglobalaccel: answers the two discovery calls, records setShortcutKeys and keeps the new
# shortcut, so a second setup run can be shown to be a no-op.
FAKE_KGLOBALACCEL = """
import json, os, warnings
import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

LOG = os.environ["FAKE_KGL_LOG"]
XML = '''<node>
 <interface name="org.kde.KGlobalAccel">
  <method name="allComponents"><arg type="ao" direction="out"/></method>
  <method name="shortcutKeys">
   <arg name="actionId" type="as" direction="in"/>
   <arg type="a(ai)" direction="out"/>
  </method>
  <method name="setForeignShortcutKeys">
   <arg name="actionId" type="as" direction="in"/>
   <arg name="keys" type="a(ai)" direction="in"/>
  </method>
 </interface>
 <interface name="org.kde.kglobalaccel.Component">
  <method name="allShortcutInfos"><arg type="a(ssssssaiai)" direction="out"/></method>
 </interface>
</node>'''

# KGlobalShortcutInfo: actionUnique, actionFriendly, componentUnique, componentFriendly, contextUnique,
# contextFriendly, keys, defaultKeys (one combined int per shortcut).
state = {"keys": [0x08000000 | 0x20], "defaults": [0x08000000 | 0x20, 0x08000000 | 0x01000031]}


def chords(sequence):
    # The combined ints of one shortcut: setShortcutKeys sends (ai) per QKeySequence.
    while isinstance(sequence, (list, tuple)) and len(sequence) == 1 and isinstance(sequence[0], (list, tuple)):
        sequence = sequence[0]
    return list(sequence) if isinstance(sequence, (list, tuple)) else [sequence]


def log(entry):
    with open(LOG, "a") as handle:
        handle.write(json.dumps(entry) + chr(10))


def on_call(connection, sender, path, interface, method, parameters, invocation):
    if method == "allComponents":
        invocation.return_value(GLib.Variant("(ao)", (["/component/krunner"],)))
    elif method == "allShortcutInfos":
        infos = [("Run Command", "Run Command", "krunner", "KRunner", "default", "Default",
                  state["keys"], state["defaults"])]
        invocation.return_value(GLib.Variant("(a(ssssssaiai))", (infos,)))
    elif method == "shortcutKeys":
        invocation.return_value(GLib.Variant("(a(ai))", ([([key, 0, 0, 0],) for key in state["keys"]],)))
    elif method == "setForeignShortcutKeys":
        action_id, keys = parameters.unpack()
        state["keys"] = [chords(sequence)[0] for sequence in keys]
        log({"method": method, "actionId": action_id, "keys": [chords(sequence) for sequence in keys]})
        invocation.return_value(None)
    else:
        invocation.return_value(None)


node = Gio.DBusNodeInfo.new_for_xml(XML)
interfaces = {i.name: i for i in node.interfaces}
loop = GLib.MainLoop()


def acquired(connection, name):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        connection.register_object("/kglobalaccel", interfaces["org.kde.KGlobalAccel"], on_call, None, None)
        connection.register_object("/component/krunner", interfaces["org.kde.kglobalaccel.Component"],
                                   on_call, None, None)


Gio.bus_own_name(Gio.BusType.SESSION, "org.kde.kglobalaccel", Gio.BusNameOwnerFlags.NONE, acquired, None,
                 lambda connection, name: loop.quit())
loop.run()
"""


@unittest.skipUnless(shutil.which("dbus-run-session") and shutil.which("gdbus") and python_with_gi(),
                     "needs dbus-run-session, gdbus and a python with gi")
class LiveBusTests(unittest.TestCase):
    """The real thing on a private session bus: the KRunner protocol and the KGlobalAccel shortcut."""

    def run_on_a_bus(self, script, timeout=90):
        return subprocess.run(["dbus-run-session", "--", "bash", "-c", script],
                              capture_output=True, text=True, timeout=timeout, check=False)

    def test_match_actions_run_and_teardown_answer_over_the_bus(self):
        python = python_with_gi()
        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp) / "stub-search"
            stub.write_text("#!/bin/sh\nprintf '%s' '" + json.dumps({"results": FILES, "notice": ""}) + "'\n")
            stub.chmod(0o755)
            client = Path(tmp) / "client.py"
            client.write_text(CLIENT)
            script = (
                'export NOCTRAOS_SEARCH_CLI="' + str(stub) + '"\n'
                '"' + python + '" "' + str(ROOT / "search/krunner.py") + '" & runner=$!\n'
                'for _ in $(seq 1 50); do\n'
                '  gdbus call --session --dest ' + krunner.BUS_NAME + ' --object-path /runner'
                ' --method org.kde.krunner1.Actions >/dev/null 2>&1 && break\n'
                '  sleep 0.2\n'
                'done\n'
                '"' + python + '" "' + str(client) + '" ' + krunner.BUS_NAME + '\n'
                'kill $runner 2>/dev/null\n'
            )
            result = self.run_on_a_bus(script)
            lines = result.stdout.strip().splitlines()
            self.assertEqual(len(lines), 5, result.stdout + result.stderr)
            matches, actions, run_ok, run_bad, teardown = (json.loads(line) for line in lines)
            self.assertEqual((actions, run_ok, run_bad, teardown), ([], [], [], []))
            self.assertEqual([m["text"] for m in matches],
                             ["alpha.txt", "notes", "Alpha docs", "alpha clip",
                              "Search DuckDuckGo for “alpha”"])
            self.assertEqual(matches[0]["relevance"], krunner.RELEVANCE_MODERATE)
            self.assertEqual(matches[0]["relevance_value"], 0.5)
            self.assertEqual(matches[0]["subtext"], "/home/x/alpha.txt")
            self.assertEqual(matches[0]["icon"], "text-x-generic")
            self.assertEqual(matches[1]["icon"], "folder")
            self.assertEqual(matches[3]["category"], "Clipboard")
            self.assertEqual(krunner.decode_match_id(matches[3]["id"])[0], "clipboard")

    def test_setup_adds_super_space_and_keeps_the_shortcut_krunner_had(self):
        python = python_with_gi()
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "kglobalaccel.py"
            fake.write_text(FAKE_KGLOBALACCEL)
            log = Path(tmp) / "kgl.log"
            script = (
                'export FAKE_KGL_LOG="' + str(log) + '"\n'
                '"' + python + '" "' + str(fake) + '" & daemon=$!\n'
                'for _ in $(seq 1 50); do\n'
                '  gdbus call --session --dest org.kde.kglobalaccel --object-path /kglobalaccel'
                ' --method org.kde.KGlobalAccel.allComponents >/dev/null 2>&1 && break\n'
                '  sleep 0.2\n'
                'done\n'
                '"' + python + '" "' + str(ROOT / "search/krunner.py") + '" --setup; echo "setup=$?"\n'
                '"' + python + '" "' + str(ROOT / "search/krunner.py") + '" --setup; echo "again=$?"\n'
                '"' + python + '" "' + str(ROOT / "search/krunner.py") + '" --status --json; echo "status=$?"\n'
                'kill $daemon 2>/dev/null\n'
            )
            result = self.run_on_a_bus(script)
            self.assertIn("setup=0", result.stdout, result.stdout + result.stderr)
            self.assertIn("again=0", result.stdout)
            self.assertIn('"shortcut": true', result.stdout)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(len(calls), 1, calls)                    # the second run changed nothing
            self.assertEqual(calls[0]["actionId"], ["krunner", "Run Command", "", ""])
            self.assertEqual(calls[0]["keys"], [[0x08000000 | 0x20, 0, 0, 0], [0x10000000 | 0x20, 0, 0, 0]])

    def test_setup_says_so_when_there_is_no_kglobalaccel(self):
        python = python_with_gi()
        result = self.run_on_a_bus('"' + python + '" "' + str(ROOT / "search/krunner.py") + '" --setup; echo "setup=$?"')
        self.assertIn("setup=1", result.stdout)
        self.assertIn("org.kde.kglobalaccel", result.stderr)


if __name__ == "__main__":
    unittest.main()
