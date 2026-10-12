"""Plasma desktop code (flavour kubuntu): the palette-derived KDE files, the Dolphin actions, the module guards.

Nothing here needs KDE: the files are parsed, the action runner is driven with stand-in scripts, and each module is run on a
machine without plasmashell to prove it says NOT APPLIED instead of reporting success."""
import configparser
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLASMA = ROOT / "install/desktop/plasma"
MODULES = sorted(PLASMA.glob("[0-9]*.sh"))


def parse(path):
    parser = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    parser.optionxform = str
    parser.read_string(path.read_text())
    return parser


class PlasmaFilesTests(unittest.TestCase):
    def test_colour_scheme_carries_the_palette(self):
        scheme = parse(ROOT / "configs/plasma/NoctraOSDark.colors")
        for section in ("Button", "Complementary", "Header", "Selection", "Tooltip", "View", "Window"):
            self.assertIn(f"Colors:{section}", scheme)
        self.assertEqual(scheme["Colors:View"]["BackgroundNormal"], "18,18,18")       # background #121212
        self.assertEqual(scheme["Colors:View"]["DecorationFocus"], "230,142,13")      # accent #e68e0d
        self.assertEqual(scheme["Colors:Selection"]["BackgroundNormal"], "230,142,13")
        self.assertEqual(scheme["General"]["ColorScheme"], "NoctraOSDark")

    def test_konsole_scheme_has_sixteen_colours_and_the_profile_points_at_it(self):
        konsole = parse(ROOT / "configs/plasma/konsole/NoctraOS.colorscheme")
        for index in range(8):
            self.assertIn(f"Color{index}", konsole)
            self.assertIn(f"Color{index}Intense", konsole)
        self.assertEqual(konsole["Background"]["Color"], "18,18,18")
        profile = parse(ROOT / "configs/plasma/konsole/NoctraOS.profile")
        self.assertEqual(profile["Appearance"]["ColorScheme"], "NoctraOS")
        self.assertTrue(profile["Appearance"]["Font"].startswith("JetBrainsMono Nerd Font,"))

    def test_service_menu_actions_exist_and_call_the_runner(self):
        menu = parse(ROOT / "configs/plasma/servicemenus/noctraos-actions.desktop")
        actions = menu["Desktop Entry"]["Actions"].rstrip(";").split(";")
        self.assertEqual(len(actions), 3)
        runner = (ROOT / "bin/noctraos-fileaction").read_text()
        for action in actions:
            section = menu[f"Desktop Action {action}"]
            match = re.fullmatch(r"noctraos-fileaction (\S+) %F", section["Exec"])
            self.assertIsNotNone(match, section["Exec"])
            self.assertIn(match.group(1) + ")", runner)

    def test_layout_script_pins_launchers_that_exist_in_the_repo(self):
        script = (ROOT / "configs/plasma/panel-layout.js").read_text()
        for name in re.findall(r"applications:(noctraos-[\w-]+\.desktop)", script):
            self.assertTrue((ROOT / "configs/applications" / name).exists(), name)


class LayoutScriptTests(unittest.TestCase):
    def printed(self, *launchers):
        with tempfile.TemporaryDirectory() as tmp:
            for name in launchers:
                (Path(tmp) / name).write_text("[Desktop Entry]\n")
            env = {**os.environ, "NOCTRAOS_APP_DIRS": tmp, "NOCTRAOS_PLASMA_DIR": str(ROOT / "configs/plasma"),
                   "XDG_CONFIG_HOME": tmp}
            result = subprocess.run([str(ROOT / "configs/plasma/apply-layout.sh"), "--print-script"],
                                    capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_the_vscode_pin_follows_the_launcher_the_machine_has(self):
        self.assertIn("applications:com.microsoft.VSCode.desktop", self.printed("com.microsoft.VSCode.desktop"))
        self.assertIn("applications:code.desktop", self.printed("code.desktop"))
        self.assertIn("applications:code.desktop", self.printed())          # none yet: the older name
        self.assertNotIn("@VSCODE_LAUNCHER@", self.printed("com.microsoft.VSCode.desktop"))

    def test_the_session_run_also_activates_the_colour_scheme(self):
        self.assertIn("plasma-apply-colorscheme NoctraOSDark", (ROOT / "configs/plasma/apply-layout.sh").read_text())


class PackageInstallTests(unittest.TestCase):
    def test_package_installs_keep_the_existing_conffiles(self):
        # a half-configured package with a changed conffile (gnome-menus on a machine that once ran the GNOME flavour)
        # must not stop apt at dpkg's prompt, which has no stdin here
        for name in ("01_desktop_packages.sh", "04_desktop_apps.sh"):
            self.assertIn("--force-confold", (PLASMA / name).read_text(), name)


class FileActionTests(unittest.TestCase):
    def run_action(self, *args):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp)
            for name in ("Open in VS Code", "Ask AI to Explain"):
                path = scripts / name
                path.write_text('#!/bin/sh\nprintf "%s|%s" "$NAUTILUS_SCRIPT_SELECTED_FILE_PATHS" '
                                '"$NAUTILUS_SCRIPT_CURRENT_DIR"\n')
                path.chmod(0o755)
            env = {**os.environ, "NOCTRAOS_FILE_ACTIONS": str(scripts), "HOME": "/home/test"}
            return subprocess.run([str(ROOT / "bin/noctraos-fileaction"), *args], capture_output=True, text=True, env=env)

    def test_selection_becomes_the_nautilus_environment(self):
        result = self.run_action("open-in-vscode", "/work/a b.txt", "file:///work/c.txt")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "/work/a b.txt\n/work/c.txt\n|/work")

    def test_a_folder_is_its_own_current_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_action("ask-ai", folder)
        self.assertTrue(result.stdout.endswith("|" + folder), result.stdout)

    def test_an_unknown_action_is_refused(self):
        result = self.run_action("rm-everything", "/")
        self.assertEqual(result.returncode, 2)


class ModuleGuardTests(unittest.TestCase):
    def test_every_module_declares_plasma_and_guards_itself(self):
        self.assertTrue(MODULES)
        for path in MODULES:
            text = path.read_text()
            self.assertEqual(text.splitlines()[1], "# desktops: plasma", path.name)
            self.assertIn("desktop_is_plasma", text, path.name)
            self.assertIn("NOT APPLIED", text, path.name)
            self.assertNotRegex(re.sub(r"(?m)^\s*#.*$", "", text), r"(?i)zorin|gnome|gsettings", path.name)

    def test_off_plasma_every_module_says_not_applied_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            for tool in ("sudo", "apt-get"):          # would be called by a module that wrongly went on
                (bin_dir / tool).write_text('#!/bin/sh\necho "$0 $*" >> "$STUB_LOG"\n')
                (bin_dir / tool).chmod(0o755)
            log = Path(tmp) / "stub.log"
            env = {**os.environ, "REPO_ROOT": str(ROOT), "TARGET_USER": "nobody", "TARGET_HOME": tmp,
                   "TARGET_UID": "65534", "XDG_CURRENT_DESKTOP": "GNOME", "STUB_LOG": str(log),
                   "PATH": f"{bin_dir}:/usr/bin:/bin"}
            for path in MODULES:
                result = subprocess.run(["bash", str(path)], capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 0, f"{path.name}: {result.stderr}")
                self.assertIn("NOT APPLIED", result.stdout + result.stderr, path.name)
            self.assertFalse(log.exists(), log.read_text() if log.exists() else "")


if __name__ == "__main__":
    unittest.main()
