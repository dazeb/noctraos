"""The Kubuntu remaster (iso/flavours/kubuntu.sh, flavour: kubuntu). The functions run on a small tree made of real files
copied from the kubuntu-26.04.1 ISO (tests/fixtures/kubuntu-26.04.1); nothing here unpacks an ISO. A real build was run
separately (see the pull request)."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "iso/flavours/kubuntu.sh"
FIXTURE = ROOT / "tests/fixtures/kubuntu-26.04.1"


def sh(body, cwd=None):
    return subprocess.run(["bash", "-c", f'set -Eeuo pipefail; source "{SCRIPT}"; {body}'], capture_output=True, text=True, cwd=cwd)


class Tree:
    """A copy of the fixture as an ISO tree (iso/) and a system root (root/)."""

    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "root"
        self.iso = self.tmp / "iso"
        shutil.copytree(FIXTURE, self.root)
        (self.root / "boot").rename(self.tmp / "boot")
        shutil.rmtree(self.root / ".disk")
        self.iso.mkdir()
        shutil.move(str(self.tmp / "boot"), str(self.iso / "boot"))
        (self.iso / ".disk").mkdir()
        shutil.copy(FIXTURE / ".disk/info", self.iso / ".disk/info")
        (self.root / "usr/lib/os-release").parent.mkdir(parents=True, exist_ok=True)
        (self.root / "etc/os-release").symlink_to("../usr/lib/os-release")
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.tmp, ignore_errors=True)


class RebrandTests(unittest.TestCase):
    def test_names_change_and_identity_stays(self):
        with Tree() as t:
            r = sh(f'kubuntu_rebrand "{t.root}" 0.5.0')
            self.assertEqual(r.returncode, 0, r.stderr)
            text = (t.root / "etc/os-release").read_text()
            self.assertIn('PRETTY_NAME="NoctraOS 0.5.0"', text)
            self.assertIn('NAME="NoctraOS"', text)
            self.assertIn("LOGO=noctraos-logo", text)
            # what apt, Calamares and the provisioner's OS check key on is untouched
            for line in ("ID=ubuntu", "ID_LIKE=debian", 'VERSION_ID="26.04"', "UBUNTU_CODENAME=resolute"):
                self.assertIn(line, text)
            self.assertIn('DISTRIB_DESCRIPTION="NoctraOS 0.5.0"', (t.root / "etc/lsb-release").read_text())
            self.assertIn("DISTRIB_ID=Ubuntu", (t.root / "etc/lsb-release").read_text())
            self.assertTrue((t.root / "usr/share/pixmaps/noctraos-logo.svg").is_file())
            self.assertNotIn("Ubuntu", (t.root / "etc/issue").read_text())

    def test_a_base_that_changed_shape_fails_the_build(self):
        with Tree() as t:
            (t.root / "usr/lib/os-release").write_text('ID=ubuntu\n')
            r = sh(f'kubuntu_rebrand "{t.root}" 0.5.0')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("nothing to change", r.stderr)


class CalamaresTests(unittest.TestCase):
    def test_noctraos_branding_is_selected(self):
        with Tree() as t:
            r = sh(f'kubuntu_calamares "{t.root}" 0.5.0')
            self.assertEqual(r.returncode, 0, r.stderr)
            desc = (t.root / "etc/calamares/branding/noctraos/branding.desc").read_text()
            self.assertIn("componentName: noctraos", desc)
            self.assertNotIn("Kubuntu", desc)
            self.assertRegex(desc, r"productName:\s+NoctraOS")
            self.assertRegex(desc, r"shortVersionedName:\s+NoctraOS 0\.5\.0")
            self.assertIn("slideshow:               \"show.qml\"", desc)
            self.assertTrue((t.root / "etc/calamares/branding/noctraos/show.qml").is_file())
            self.assertIn("branding: noctraos", (t.root / "etc/calamares/settings.conf").read_text())
            # Kubuntu's own branding is left in place
            self.assertTrue((t.root / "etc/calamares/branding/kubuntu/branding.desc").is_file())

    def test_our_pictures_and_slideshow_replace_kubuntus(self):
        with Tree() as t:
            r = sh(f'kubuntu_calamares "{t.root}" 0.5.0')
            self.assertEqual(r.returncode, 0, r.stderr)
            dst = t.root / "etc/calamares/branding/noctraos"
            art = ROOT / "assets/boot/calamares"
            for name in ("logo.png", "icon.png", "welcome.png"):
                self.assertEqual((dst / name).read_bytes(), (art / name).read_bytes(), name)
            self.assertEqual((dst / "welcome-oem.png").read_bytes(), (art / "welcome.png").read_bytes())
            slides = sorted(p.name for p in art.glob("slide-*.png"))
            self.assertGreaterEqual(len(slides), 3)
            show = (dst / "show.qml").read_text()
            self.assertEqual(re.findall(r'source: "(slide-\d+\.png)"', show), slides)
            for name in slides:
                self.assertTrue((dst / name).is_file(), name)
            self.assertNotIn("Kubuntu", show)
            self.assertEqual(show.count("{"), show.count("}"))
            # every picture branding.desc names is one we ship
            desc = (dst / "branding.desc").read_text()
            for name in re.findall(r':\s+"?([\w-]+\.png)"?', desc):
                self.assertTrue((dst / name).is_file(), name)
            self.assertRegex(desc, r"(?m)^\s*version:\s+0\.5\.0$")

    def test_the_plasma_look_is_baked_into_the_squashfs(self):
        text = SCRIPT.read_text()
        self.assertIn('configs/plasma/install-look.sh" "$1"', text)
        main = text[text.index("kubuntu_main()"):]
        self.assertIn('kubuntu_look "$sq_root"', main)


class GrubTests(unittest.TestCase):
    def test_entries_are_renamed_and_the_theme_is_hooked_in(self):
        with Tree() as t:
            r = sh(f'kubuntu_theme_grub "{t.iso}"')
            self.assertEqual(r.returncode, 0, r.stderr)
            cfg = (t.iso / "boot/grub/grub.cfg").read_text()
            self.assertIn('menuentry "Try or Install NoctraOS"', cfg)   # the release build check greps for this
            self.assertNotIn("Kubuntu", cfg)
            self.assertNotIn("Kubuntu", (t.iso / "boot/grub/loopback.cfg").read_text())
            self.assertIn("set theme=/boot/grub/themes/noctraos/theme.txt", cfg)
            self.assertLess(cfg.index("insmod gfxterm"), cfg.index("set theme="))
            self.assertTrue((t.iso / "boot/grub/themes/noctraos/theme.txt").is_file())
            for font in re.findall(r"loadfont (/boot/grub/themes/noctraos/\S+)", cfg):
                self.assertTrue((t.iso / font.lstrip("/")).is_file(), font)

    def test_layout_check_accepts_the_real_layout_and_refuses_a_zorin_one(self):
        with Tree() as t:
            for rel in ("casper/filesystem.squashfs", "casper/initrd", "casper/vmlinuz", "md5sum.txt"):
                (t.iso / rel).parent.mkdir(parents=True, exist_ok=True)
                (t.iso / rel).write_text("x")
            (t.iso / "boot/grub/x86_64-efi").mkdir(parents=True)
            (t.iso / "boot/grub/i386-pc").mkdir(parents=True)
            self.assertEqual(sh(f'kubuntu_check_layout "{t.iso}"').returncode, 0)
            (t.iso / ".disk/info").write_text("Zorin-OS 18.1 Core 64bit\n")
            r = sh(f'kubuntu_check_layout "{t.iso}"')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("does not say Kubuntu", r.stderr)


class FirstBootTests(unittest.TestCase):
    def test_flavour_file_runner_and_live_guard(self):
        with Tree() as t:
            r = sh(f'kubuntu_firstboot "{t.root}" mybranch')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((t.root / "etc/noctraos/flavour").read_text(), "kubuntu\n")
            runner = t.root / "usr/local/sbin/noctraos-firstboot"
            self.assertIn('REPO_BRANCH="mybranch"', runner.read_text())
            self.assertNotIn("__NOCTRAOS_BRANCH__", runner.read_text())
            self.assertTrue(runner.stat().st_mode & 0o111)
            desktop = (t.root / "etc/skel/.config/autostart/noctraos-setup.desktop").read_text()
            self.assertIn("boot=casper", desktop)       # never provisions inside the live session
            self.assertNotIn("GNOME", desktop)

    def test_the_runner_is_the_zorin_runner_word_for_word(self):
        build = (ROOT / "iso/build-noctraos-iso.sh").read_text()
        start_marker = "cat > \"$SQ_ROOT/usr/local/sbin/noctraos-firstboot\" <<'EOF'\n"
        start = build.index(start_marker) + len(start_marker)
        body = build[start:build.index("\nEOF\n", start) + 1]
        self.assertEqual((ROOT / "iso/firstboot-runner.sh").read_text(), body)


class RefusalTests(unittest.TestCase):
    def test_an_unattended_build_is_not_applied(self):
        r = subprocess.run(["bash", str(SCRIPT), "/nonexistent.iso"], capture_output=True, text=True,
                           env={"PATH": "/usr/bin:/bin", "NOCTRAOS_UNATTENDED": "1"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("NOT APPLIED", r.stderr)

    def test_build_local_refuses_kubuntu_appliance_and_unknown_flavours(self):
        with tempfile.TemporaryDirectory() as tmp:
            for flavour, target, code, text in (("kubuntu", "appliance", 2, "NOT APPLIED"), ("kubuntu", "both", 2, "NOT APPLIED"),
                                                ("fedora", "release", 1, "unknown flavour")):
                r = subprocess.run(["bash", str(ROOT / "iso/build-local.sh"), tmp, target], capture_output=True, text=True,
                                   env={"PATH": "/usr/bin:/bin", "NOCTRAOS_FLAVOUR": flavour})
                self.assertEqual(r.returncode, code, (flavour, target, r.stderr))
                self.assertIn(text, r.stderr)

    def test_sourcing_defines_functions_and_runs_nothing(self):
        r = sh("declare -F kubuntu_main kubuntu_rebrand >/dev/null")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_zorin_or_gnome_code_here(self):
        text = SCRIPT.read_text()
        for word in ("gdm", "gnome-shell", "ubiquity", "isolinux", "gsettings"):
            self.assertNotIn(word, re.sub(r"(?m)^\s*#.*$", "", text), word)


if __name__ == "__main__":
    unittest.main()
