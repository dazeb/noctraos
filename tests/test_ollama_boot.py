"""install/lib.sh keeps the person's choice about Ollama starting with the computer: the vendor installer turns the service
on at boot, a first install ends with it off, and a later run puts back what the person had."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "install/lib.sh"
OPTIONAL = ROOT / "install/optional/local_llm.sh"


class BootChoiceTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "sudo").write_text('#!/bin/sh\nexec "$@"\n')
        (self.bin / "sudo").chmod(0o755)

    def stand_in(self, unit=True, enabled=False, ollama=True):
        """systemctl with one unit (or none) whose boot setting is a file; an ollama binary or none. Returns the log path."""
        (self.tmp / "boot").write_text("enabled\n" if enabled else "disabled\n")
        (self.tmp / "log").unlink(missing_ok=True)
        for name, body in {
            "systemctl": '#!/bin/sh\ncase "$1" in cat) [ "$UNIT" = 1 ] ;; is-enabled) [ "$(cat "$BOOT")" = enabled ] ;; '
                         'enable) echo enabled > "$BOOT"; echo enable >> "$LOG" ;; disable) echo disabled > "$BOOT"; echo disable >> "$LOG" ;; esac\n',
            "ollama": "#!/bin/sh\ntrue\n",
        }.items():
            path = self.bin / name
            if name == "ollama" and not ollama:
                path.unlink(missing_ok=True)
                continue
            path.write_text(body)
            path.chmod(0o755)
        self.env = {"PATH": f"{self.bin}:/usr/bin:/bin", "REPO_ROOT": str(ROOT), "TARGET_USER": "t", "TARGET_UID": "1000",
                    "TARGET_HOME": str(self.tmp), "UNIT": "1" if unit else "0", "BOOT": str(self.tmp / "boot"),
                    "LOG": str(self.tmp / "log")}
        return self.tmp / "log"

    def bash(self, expr):
        return subprocess.run(["bash", "-c", f'source "{LIB}"; {expr}'], capture_output=True, text=True, env=self.env)

    def test_the_choice_is_on_only_for_an_installed_service_that_starts_with_the_computer(self):
        cases = [(dict(enabled=True), "on"), (dict(enabled=False), "off"),
                 (dict(unit=False, enabled=True), "off"),             # no service unit: nothing to keep
                 (dict(ollama=False, enabled=True), "off")]           # not installed yet: a first install
        for setup, want in cases:
            with self.subTest(**setup):
                self.stand_in(**setup)
                self.assertEqual(self.bash("ollama_boot_choice").stdout.strip(), want)

    def test_restoring_puts_back_what_the_person_had_and_changes_nothing_else(self):
        for before, after, call in (("off", True, "disable"), ("on", False, "enable")):
            with self.subTest(before=before):
                log = self.stand_in(enabled=after)                    # the vendor installer left it the other way
                self.assertEqual(self.bash(f"ollama_boot_restore {before}").returncode, 0)
                self.assertEqual(log.read_text().split(), [call])
        for state in ("on", "off"):
            with self.subTest(already=state):
                log = self.stand_in(enabled=state == "on")
                self.assertEqual(self.bash(f"ollama_boot_restore {state}").returncode, 0)
                self.assertFalse(log.exists())


class OptionalModuleTests(unittest.TestCase):
    """The optional local AI step must not decide this for the person."""

    def test_it_does_not_enable_the_service_on_its_own(self):
        text = OPTIONAL.read_text()
        self.assertNotRegex(text, r"systemctl\s+enable")
        self.assertLess(text.index("ollama_boot_choice"), text.index("ollama.com/install.sh"), "remember the choice before the vendor installer")
        self.assertLess(text.index("ollama.com/install.sh"), text.index("ollama_boot_restore"), "put it back after")

    def test_it_still_starts_the_service_now_so_a_model_can_be_pulled(self):
        self.assertRegex(OPTIONAL.read_text(), r"systemctl start ollama")


if __name__ == "__main__":
    unittest.main()
