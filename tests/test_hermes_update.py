"""noctraos-hermes install/update with a stub installer: a fresh install pins to the newest release tag; an update sets
the old code aside, installs the new release and removes the old copy, or puts the old copy back when anything fails.
Nothing real is downloaded or touched."""
import fcntl
import os
from pathlib import Path
import pty
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HERMES = ROOT / "bin/noctraos-hermes"

INSTALLER = r'''#!/usr/bin/env bash
# stub of hermes-agent.nousresearch.com/install.sh: records its arguments, then "installs" the release it was given
echo "$*" >> "$INSTALL_LOG"
[ -z "${INSTALL_FAIL:-}" ] || { echo "stub installer: failing on purpose" >&2; exit 1; }
tag=""; while [ $# -gt 0 ]; do [ "$1" = "--branch" ] && tag="$2"; shift; done
[ -z "${INSTALL_FAIL_ON_TAG:-}" ] || [ -z "$tag" ] || { echo "stub installer: this release does not install" >&2; exit 1; }
[ -n "$tag" ] || tag="main-tip"

d="$HERMES_HOME/hermes-agent"
mkdir -p "$d/apps/desktop/release/linux-unpacked"
echo "${tag#v}" > "$d/VERSION"
touch "$d/.hermes-bootstrap-complete"
printf '#!/bin/sh\n' > "$d/apps/desktop/release/linux-unpacked/hermes"; chmod +x "$d/apps/desktop/release/linux-unpacked/hermes"
'''
HERMES_STUB = r'''#!/usr/bin/env bash
case "$1" in
  --version) [ -f "$HERMES_HOME/hermes-agent/VERSION" ] || exit 1
             echo "Hermes Agent v$(cat "$HERMES_HOME/hermes-agent/VERSION") (2026.9.24) · upstream abc" ;;
  desktop) [ -z "${LOCK_PROBE:-}" ] || { flock -n "$LOCK_PROBE" true && echo free || echo held; } > "$LOCK_PROBE.result"
           mkdir -p "$HERMES_HOME/hermes-agent/apps/desktop/release/linux-unpacked"
           printf '#!/bin/sh\n' > "$HERMES_HOME/hermes-agent/apps/desktop/release/linux-unpacked/hermes"
           chmod +x "$HERMES_HOME/hermes-agent/apps/desktop/release/linux-unpacked/hermes" ;;
  *) exit 0 ;;
esac
'''
UPSTREAM_STUB = r'''#!/usr/bin/env bash
[ -z "${NO_RELEASE:-}" ] || exit 1
[ "$1 $2" = "latest hermes" ] || exit 2
if [ "${3:-}" = "--tag" ]; then echo "v${NEWEST:-0.21.7}"; else echo "${NEWEST:-0.21.7}"; fi
'''
CURL_STUB = r'''#!/usr/bin/env bash
# the installer URL serves the stub installer; every other URL (Ollama, Nous) is "unreachable"
for a in "$@"; do case "$a" in *install.sh) cat "$STUB_INSTALLER"; exit 0 ;; esac; done
exit 7
'''


class HermesBox(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        self.home = self.tmp / "home"
        self.hh = self.home / ".hermes"
        self.bin = self.tmp / "bin"
        for d in (self.home / ".local/bin", self.hh, self.bin):
            d.mkdir(parents=True)
        self.script(self.home / ".local/bin/hermes", HERMES_STUB)
        self.script(self.bin / "noc-upstream", UPSTREAM_STUB)
        self.script(self.bin / "curl", CURL_STUB)
        self.script(self.tmp / "installer.sh", INSTALLER)
        self.log = self.tmp / "install.log"
        self.env = {**os.environ, "HOME": str(self.home), "HERMES_HOME": str(self.hh),
                    "PATH": f"{self.bin}:{self.home}/.local/bin:{os.environ['PATH']}",
                    "NOC_UPSTREAM": str(self.bin / "noc-upstream"), "STUB_INSTALLER": str(self.tmp / "installer.sh"),
                    "INSTALL_LOG": str(self.log), "NOCTRAOS_HERMES_INSTALLER_URL": "https://example.invalid/install.sh",
                    "XDG_CONFIG_HOME": str(self.home / ".config"), "XDG_RUNTIME_DIR": str(self.tmp / "run"),
                    "NOCTRAOS_HERMES_INSTALL_MIN_FREE_KB": "1",      # the box running the tests may be short of room
                    "NOC_AGENT_SKILLS": str(self.bin / "no-such-skill-installer")}
        (self.tmp / "run").mkdir()

    @staticmethod
    def script(path, body):
        path.write_text(body)
        path.chmod(0o755)

    def install_version(self, version):
        d = self.hh / "hermes-agent"
        (d / "apps/desktop/release/linux-unpacked").mkdir(parents=True)
        (d / "VERSION").write_text(version + "\n")
        (d / ".hermes-bootstrap-complete").touch()
        app = d / "apps/desktop/release/linux-unpacked/hermes"
        app.write_text("#!/bin/sh\n")
        app.chmod(0o755)
        (self.hh / "memories").mkdir(exist_ok=True)
        (self.hh / "memories/SENTINEL").write_text("keep\n")
        (self.hh / "SOUL.md").write_text("my soul\n")

    def hermes(self, *args, **env):
        return subprocess.run(["bash", str(HERMES), *args], capture_output=True, text=True, env={**self.env, **env})

    def installs(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def version(self):
        return (self.hh / "hermes-agent/VERSION").read_text().strip()


class InstallTests(HermesBox):
    def test_a_fresh_install_is_pinned_to_the_newest_release_tag(self):
        r = self.hermes("install")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.installs(), ["--skip-setup --branch v0.21.7"])
        self.assertEqual(self.version(), "0.21.7")
        self.assertIn("release v0.21.7", r.stdout)

    def test_without_release_information_the_installers_default_is_used_and_said_so(self):
        r = self.hermes("install", NO_RELEASE="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.installs(), ["--skip-setup"])
        self.assertIn("could not read the latest Hermes release", r.stdout)

    def test_a_release_the_installer_cannot_install_falls_back_to_its_default_branch(self):
        r = self.hermes("install", INSTALL_FAIL_ON_TAG="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.installs(), ["--skip-setup --branch v0.21.7", "--skip-setup"])
        self.assertIn("did not install with the current installer", r.stdout)
        self.assertTrue((self.hh / "hermes-agent/.hermes-bootstrap-complete").exists())

    def test_an_installed_runtime_is_left_alone_by_install(self):
        self.install_version("0.21.5")
        self.hermes("install")
        self.assertEqual(self.installs(), [])
        self.assertEqual(self.version(), "0.21.5")


class OptionalInstallTests(HermesBox):
    """Hermes is not part of the install: nothing sets it up until the person asks, and asking is safe to do twice."""

    def test_it_reports_no_mode_until_it_is_installed(self):
        self.assertEqual(self.hermes("mode").stdout.strip(), "none")
        self.assertIn("runtime: missing", self.hermes("status").stdout)
        self.install_version("0.21.5")
        self.assertEqual(self.hermes("mode").stdout.strip(), "cloud")

    def test_local_and_cloud_need_hermes_to_be_set_up_first(self):
        for word in ("local", "cloud"):
            r = self.hermes(word, "--no-launch") if word == "local" else self.hermes(word)
            self.assertEqual(r.returncode, 1, word)
            self.assertIn("not set up yet", r.stdout)
            self.assertIn("noc hermes setup", r.stdout)

    def test_a_fresh_install_links_the_noctraos_skill_into_hermes(self):
        called = self.tmp / "skills-called"
        self.script(self.bin / "skills", f'#!/bin/sh\necho "$@" >> "{called}"\n')
        r = self.hermes("install", NOC_AGENT_SKILLS=str(self.bin / "skills"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(called.read_text().split(), ["install"])

    def test_a_skill_link_that_fails_does_not_fail_the_install(self):
        self.script(self.bin / "skills", "#!/bin/sh\nexit 1\n")
        r = self.hermes("install", NOC_AGENT_SKILLS=str(self.bin / "skills"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("could not link the NoctraOS agent skill", r.stdout)

    def test_not_enough_room_stops_before_anything_is_downloaded(self):
        r = self.hermes("install", NOCTRAOS_HERMES_INSTALL_MIN_FREE_KB="999999999999")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not enough free disk space", r.stdout)
        self.assertEqual(self.installs(), [])

    def test_two_installs_never_run_at_once(self):
        lock = self.tmp / "run" / f"noctraos-hermes-{os.getuid()}.lock"
        with open(lock, "w") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)             # another window is in the middle of the setup
            r = self.hermes("install")
        self.assertEqual(r.returncode, 75)
        self.assertIn("already being set up", r.stdout)
        self.assertEqual(self.installs(), [])
        self.assertEqual(self.hermes("install").returncode, 0)           # once it has finished, the next one runs

    def launch_in_a_terminal(self, answer):
        """`noctraos-hermes` as the Start menu runs it inside a terminal window: stdout is a terminal, stdin takes the answer."""
        master, slave = pty.openpty()
        try:
            r = subprocess.run(["bash", str(HERMES), "launch"], input=answer, stdout=slave, stderr=subprocess.STDOUT,
                               text=True, env=self.env, timeout=60)
            os.close(slave)
            slave = None
            out = b""
            while True:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
        finally:
            if slave is not None:
                os.close(slave)
            os.close(master)
        return r.returncode, out.decode()

    def test_opening_hermes_before_it_is_set_up_asks_first_and_downloads_nothing_on_no(self):
        for answer in ("n\n", "\n", "x\n"):
            with self.subTest(answer=answer):
                code, out = self.launch_in_a_terminal(answer)
                self.assertEqual(code, 0, out)
                for want in ("not set up on this computer yet", "about 5 GB", "leaves this computer", "Nothing was installed"):
                    self.assertIn(want, out)
                self.assertEqual(self.installs(), [])

    def test_opening_hermes_before_it_is_set_up_installs_it_after_a_yes(self):
        code, out = self.launch_in_a_terminal("y\n")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.installs(), ["--skip-setup --branch v0.21.7"])

    def test_the_setup_lock_is_released_before_hermes_starts(self):
        probe = self.tmp / "run" / f"noctraos-hermes-{os.getuid()}.lock"        # what the app asks: is the setup lock free?
        self.env["LOCK_PROBE"] = str(probe)
        code, out = self.launch_in_a_terminal("y\n")
        self.assertEqual(code, 0, out)
        self.assertEqual(Path(str(probe) + ".result").read_text().strip(), "free",
                         "Hermes inherited the lock, so a later Set up would be refused for as long as it runs")

    def test_the_disk_is_checked_when_only_the_app_is_missing(self):
        self.install_version("0.21.5")                                           # an interrupted setup: runtime in, app never built
        (self.hh / "hermes-agent/apps/desktop/release/linux-unpacked/hermes").unlink()
        r = self.hermes("install", NOCTRAOS_HERMES_INSTALL_MIN_FREE_KB="999999999999")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("not enough free disk space", r.stdout)

    def test_opening_hermes_from_the_menu_runs_in_a_terminal_window(self):
        window = self.tmp / "window-args"
        self.script(self.bin / "gnome-terminal", f'#!/bin/sh\necho "$@" > "{window}"\n')
        r = self.hermes("launch")                                          # stdout is a pipe here, as for a desktop entry
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Setting up Hermes", window.read_text())
        self.assertEqual(self.installs(), [])


class UpdateTests(HermesBox):
    def test_an_older_install_moves_to_the_newest_release_and_keeps_the_persons_data(self):
        self.install_version("0.21.5")
        r = self.hermes("update")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.installs(), ["--skip-setup --branch v0.21.7"])
        self.assertEqual(self.version(), "0.21.7")
        self.assertFalse((self.hh / "hermes-agent.previous").exists(), "the old copy is removed after a good update")
        self.assertEqual((self.hh / "memories/SENTINEL").read_text(), "keep\n")
        self.assertEqual((self.hh / "SOUL.md").read_text(), "my soul\n")
        self.assertIn("Hermes is now 0.21.7", r.stdout)

    def test_already_on_the_newest_release_does_nothing(self):
        self.install_version("0.21.7")
        r = self.hermes("update")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.installs(), [])
        self.assertIn("already the newest release", r.stdout)

    def test_a_build_ahead_of_the_release_is_not_downgraded(self):
        self.install_version("0.21.9")
        self.hermes("update")
        self.assertEqual(self.installs(), [])
        self.assertEqual(self.version(), "0.21.9")

    def test_a_failed_install_puts_the_old_hermes_back(self):
        self.install_version("0.21.5")
        r = self.hermes("update", INSTALL_FAIL="1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("putting the previous Hermes back", r.stdout)
        self.assertEqual(self.version(), "0.21.5")
        self.assertTrue((self.hh / "hermes-agent/.hermes-bootstrap-complete").exists())
        self.assertFalse((self.hh / "hermes-agent.previous").exists())
        self.assertEqual((self.hh / "memories/SENTINEL").read_text(), "keep\n")
        r = subprocess.run([str(self.home / ".local/bin/hermes"), "--version"], capture_output=True, text=True, env=self.env)
        self.assertIn("v0.21.5", r.stdout)                  # and it still runs

    def test_an_update_never_falls_back_to_the_development_branch(self):
        self.install_version("0.21.5")
        r = self.hermes("update", INSTALL_FAIL_ON_TAG="1")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.installs(), ["--skip-setup --branch v0.21.7"])     # tried the release once, nothing else
        self.assertEqual(self.version(), "0.21.5")                               # and kept what the person had
        self.assertIn("putting the previous Hermes back", r.stdout)

    def test_no_release_information_changes_nothing(self):
        self.install_version("0.21.5")
        r = self.hermes("update", NO_RELEASE="1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Nothing was changed", r.stdout)
        self.assertEqual(self.installs(), [])
        self.assertEqual(self.version(), "0.21.5")

    def test_a_running_hermes_is_never_replaced(self):
        self.install_version("0.21.5")
        runtime = self.hh / "hermes-agent"
        busy = subprocess.Popen(["bash", "-c", f'exec -a "{runtime}/venv/bin/python" sleep 60'])
        self.addCleanup(busy.wait)
        self.addCleanup(busy.kill)   # cleanups run last-in first-out: kill, then wait
        r = self.hermes("update")
        self.assertEqual(r.returncode, 75)
        self.assertIn("Hermes is running", r.stdout)
        self.assertEqual(self.installs(), [])
        self.assertEqual(self.version(), "0.21.5")

    def test_not_enough_disk_space_changes_nothing(self):
        self.install_version("0.21.5")
        r = self.hermes("update", NOCTRAOS_HERMES_MIN_FREE_KB="999999999999")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not enough free disk space", r.stdout)
        self.assertEqual(self.installs(), [])

    def test_update_on_a_machine_without_hermes_installs_it(self):
        r = self.hermes("update")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.installs(), ["--skip-setup --branch v0.21.7"])


if __name__ == "__main__":
    unittest.main()
