"""Plasma desktop code (flavour kubuntu): the palette-derived KDE files, the Dolphin actions, the module guards.

Nothing here needs KDE: the files are parsed, the action runner is driven with stand-in scripts, and each module is run on a
machine without plasmashell to prove it says NOT APPLIED instead of reporting success."""
import configparser
import json
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


LNF = ROOT / "assets/plasma/look-and-feel/dev.noctraos.desktop"
MARKER = "# Written by NoctraOS (configs/plasma/install-look.sh)."


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


class LookTests(unittest.TestCase):
    """The system-wide look (configs/plasma/install-look.sh), installed into a scratch root as the ISO build does."""

    def install(self, root):
        result = subprocess.run(["bash", str(ROOT / "configs/plasma/install-look.sh"), str(root)],
                                capture_output=True, text=True, env={**os.environ, "XDG_CONFIG_HOME": str(root / "xdg")})
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def scratch_root(self, tmp, breeze=True):
        root = Path(tmp) / "root"
        if breeze:
            (root / "usr/share/sddm/themes/breeze").mkdir(parents=True)
            (root / "usr/share/sddm/themes/breeze/metadata.desktop").write_text("[SddmGreeterTheme]\n")
        (root / "usr/share/applications").mkdir(parents=True)
        (root / "usr/share/applications/code.desktop").write_text("[Desktop Entry]\n")
        return root

    def test_everything_lands_and_a_second_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.scratch_root(tmp)
            self.install(root)
            first = snapshot(root)
            out = self.install(root)
            self.assertEqual(snapshot(root), first)
            self.assertNotIn("kept (not ours)", out)
            share = root / "usr/local/share"
            lnf = share / "plasma/look-and-feel/dev.noctraos.desktop"
            for rel in ("metadata.json", "contents/defaults", "contents/splash/Splash.qml",
                        "contents/splash/images/lockup.png", "contents/previews/preview.png"):
                self.assertTrue((lnf / rel).is_file(), rel)
            layout = (lnf / "contents/layouts/org.kde.plasma.desktop-layout.js").read_text()
            self.assertIn("applications:code.desktop", layout)
            self.assertIn('writeConfig("icon", "noctraos-logo")', layout)
            wallpapers = sorted(p.name for p in (share / "wallpapers").iterdir())
            self.assertEqual(len(wallpapers), len(list((ROOT / "assets/wallpapers").glob("*.jpg"))))
            for name in wallpapers:
                meta = json.loads((share / "wallpapers" / name / "metadata.json").read_text())
                self.assertEqual(meta["KPlugin"]["Id"], name)
                self.assertTrue((share / "wallpapers" / name / "contents/images/3840x2160.jpg").is_file())
            self.assertTrue((share / "color-schemes/NoctraOSDark.colors").is_file())
            self.assertTrue((share / "icons/hicolor/scalable/apps/noctraos-logo.svg").is_file())
            sddm = parse(root / "usr/share/sddm/themes/breeze/theme.conf.user")
            for key in ("background", "logo"):
                self.assertTrue((root / sddm["General"][key].lstrip("/")).is_file(), key)
            self.assertEqual(parse(root / "etc/sddm.conf.d/30-noctraos.conf")["Theme"]["Current"], "breeze")
            self.assertLess("30-noctraos.conf", "kde_settings.conf")      # System Settings' own choice sorts later and wins
            splash = parse(root / "etc/xdg/ksplashrc")["KSplash"]
            self.assertEqual((splash["Engine"], splash["Theme"]), ("KSplashQML", "dev.noctraos.desktop"))
            lock = (root / "etc/xdg/kscreenlockerrc").read_text()
            self.assertIn("Image=file:///usr/local/share/noctraos/plasma/login/background.jpg", lock)
            about = parse(root / "etc/skel/.config/kcm-about-distrorc")["General"]
            self.assertEqual(about["Name"], "NoctraOS")
            self.assertEqual(about["Version"], (ROOT / "VERSION").read_text().strip())
            self.assertTrue((root / about["LogoPath"].lstrip("/")).is_file())

    def test_a_file_someone_else_wrote_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.scratch_root(tmp)
            own = root / "usr/share/sddm/themes/breeze/theme.conf.user"
            own.write_text("[General]\nbackground=/home/me/cat.jpg\n")
            (root / "etc/xdg").mkdir(parents=True)
            (root / "etc/xdg/ksplashrc").write_text("[KSplash]\nTheme=Mine\n")
            out = self.install(root)
            self.assertEqual(own.read_text(), "[General]\nbackground=/home/me/cat.jpg\n")
            self.assertEqual((root / "etc/xdg/ksplashrc").read_text(), "[KSplash]\nTheme=Mine\n")
            self.assertIn("kept (not ours): /usr/share/sddm/themes/breeze/theme.conf.user", out)
            self.assertIn("kept (not ours): /etc/xdg/ksplashrc", out)

    def test_without_sddm_breeze_the_login_screen_is_not_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.scratch_root(tmp, breeze=False)
            out = self.install(root)
            self.assertIn("NOT APPLIED: login screen", out)
            self.assertFalse((root / "etc/sddm.conf.d").exists())

    def test_global_theme_package_is_consistent(self):
        meta = json.loads((LNF / "metadata.json").read_text())
        self.assertEqual(meta["KPackageStructure"], "Plasma/LookAndFeel")
        self.assertEqual(meta["KPlugin"]["Id"], LNF.name)
        defaults = (LNF / "contents/defaults").read_text()
        self.assertIn("ColorScheme=NoctraOSDark", defaults)
        self.assertIn(f"Theme={LNF.name}", defaults)
        # the wallpaper the theme names is one of the packages install-look.sh builds
        wallpaper = re.search(r"(?m)^\[Wallpaper\]\nImage=(\S+)", defaults).group(1)
        titles = {"NoctraOS-" + "".join(w.capitalize() for w in p.stem.removeprefix("noctraos-").removesuffix("-2160p").split("-"))
                  for p in (ROOT / "assets/wallpapers").glob("*.jpg")}
        self.assertIn(wallpaper, titles)
        splash = (LNF / "contents/splash/Splash.qml").read_text()
        for image in re.findall(r'source: "([^"]+)"', splash):
            self.assertTrue((LNF / "contents/splash" / image).is_file(), image)
        self.assertIn("property int stage", splash)                     # ksplashqml drives the splash through it

    def test_rendered_artwork_is_committed_at_the_sizes_plasma_and_calamares_use(self):
        sizes = {
            "assets/boot/calamares/icon.png": (512, 512),
            "assets/boot/calamares/welcome.png": (800, 300),
            "assets/plasma/look-and-feel/dev.noctraos.desktop/contents/previews/preview.png": (640, 360),
        }
        for rel, size in sizes.items():
            data = (ROOT / rel).read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n", rel)
            self.assertEqual((int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")), size, rel)
        for slide in sorted((ROOT / "assets/boot/calamares").glob("slide-*.png")):
            data = slide.read_bytes()
            width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
            self.assertAlmostEqual(width / height, 16 / 9, places=2, msg=slide.name)


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
            # The legacy-named search schema stores shared backend settings, not GNOME desktop settings.
            shared_schema = 'configs/gsettings/org.gnome.shell.extensions.noctraos-search.gschema.xml'
            code = re.sub(r"(?m)^\s*#.*$", "", text).replace(shared_schema, 'shared-search-schema')
            code = code.replace('/usr/share/glib-2.0/schemas/org.gnome.shell.extensions.noctraos-search.gschema.xml',
                                'installed-shared-search-schema')
            self.assertNotRegex(code, r"(?i)zorin|gnome|gsettings", path.name)

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
