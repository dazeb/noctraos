"""iso/renew-update-channels.sh with stub publish-update.sh, curl and notify-send: it renews every channel, checks the PUBLIC
manifest really got a fresh expiry, keeps going when one channel fails, and says so loudly. No network, no key, no bucket."""
import datetime
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "iso/renew-update-channels.sh"
SETUP = ROOT / "iso/setup-update-renewal.sh"

PUBLISH = '''#!/usr/bin/env bash
echo "$*" >> "$STUB_LOG"
[ "$2" != "${FAIL_CHANNEL:-}" ]
'''
CURL = '''#!/usr/bin/env bash
for a; do u="$a"; done
ch="${u%/manifest.json}"; ch="${ch##*/}"
days="${DAYS_LEFT:-30}"; [ "$ch" != "${SOON_CHANNEL:-}" ] || days="${SOON_DAYS:-3}"
printf '{"channel":"%s","serial":2,"expires":"%s"}\\n' "$ch" "$(date -u -d "+$days days" +%Y-%m-%dT%H:%M:%SZ)"
'''
NOTIFY = '#!/usr/bin/env bash\necho "$*" >> "$NOTIFY_LOG"\n'


class RenewTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        iso = self.tmp / "iso"
        iso.mkdir()
        shutil.copy(SCRIPT, iso / "renew-update-channels.sh")
        for name, body in (("publish-update.sh", PUBLISH),):
            (iso / name).write_text(body)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        for name, body in (("curl", CURL), ("notify-send", NOTIFY)):
            (bin_dir / name).write_text(body)
            (bin_dir / name).chmod(0o755)
        self.script = iso / "renew-update-channels.sh"
        self.env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "STUB_LOG": str(self.tmp / "publish.log"),
                    "NOTIFY_LOG": str(self.tmp / "notify.log")}

    def run_renew(self, **env):
        return subprocess.run(["bash", str(self.script)], capture_output=True, text=True, env={**self.env, **env})

    def lines(self, name):
        p = self.tmp / name
        return p.read_text().splitlines() if p.exists() else []

    def test_every_channel_is_renewed_and_checked(self):
        r = self.run_renew()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.lines("publish.log"), ["renew nightly", "renew stable"])
        self.assertIn("all channels renewed", r.stdout)
        self.assertEqual(self.lines("notify.log"), [])

    def test_one_failing_channel_does_not_stop_the_other_and_is_reported(self):
        r = self.run_renew(FAIL_CHANNEL="nightly")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.lines("publish.log"), ["renew nightly", "renew stable"])       # stable was still tried
        self.assertIn("nightly: the renewal itself failed", r.stdout)
        self.assertEqual(len(self.lines("notify.log")), 1)
        self.assertIn("nightly", self.lines("notify.log")[0])
        self.assertIn("critical", self.lines("notify.log")[0])

    def test_a_public_manifest_that_did_not_get_a_fresh_expiry_is_a_failure(self):
        """The renewal ran but the host still serves an old manifest (a cache, a failed upload): do not call that renewed."""
        r = self.run_renew(SOON_CHANNEL="stable", SOON_DAYS="3")
        self.assertEqual(r.returncode, 1)
        self.assertIn("stable: the public manifest expires in", r.stdout)
        self.assertIn("nightly: the public manifest now expires in", r.stdout)

    def test_the_threshold_is_adjustable(self):
        self.assertEqual(self.run_renew(DAYS_LEFT="20").returncode, 1)
        self.assertEqual(self.run_renew(DAYS_LEFT="20", RENEW_MIN_DAYS="15").returncode, 0)

    def test_an_unreachable_public_host_is_a_failure_not_a_pass(self):
        broken = self.tmp / "bin/curl"
        broken.write_text("#!/usr/bin/env bash\nexit 7\n")
        r = self.run_renew()
        self.assertEqual(r.returncode, 1)
        self.assertIn("expires in -1 days", r.stdout)

    def test_it_still_fails_loudly_without_a_desktop_to_notify(self):
        (self.tmp / "bin/notify-send").unlink()
        r = self.run_renew(FAIL_CHANNEL="stable", PATH=f"{self.tmp}/bin:/usr/bin:/bin")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAILED", r.stdout)

    def test_channels_can_be_chosen(self):
        self.run_renew(RENEW_CHANNELS="stable")
        self.assertEqual(self.lines("publish.log"), ["renew stable"])


class SetupTests(unittest.TestCase):
    def test_install_writes_units_that_survive_a_missing_checkout(self):
        """The generated job must not depend on any development checkout: it uses its own clone and resets it to origin/main."""
        text = SETUP.read_text()
        self.assertIn('reset -q --hard origin/main', text)
        self.assertIn("Persistent=true", text)
        self.assertIn("OnCalendar=Mon", text)
        self.assertNotIn(".claude/worktrees", text)

    def test_usage_is_printed_for_nonsense(self):
        r = subprocess.run(["bash", str(SETUP), "nonsense"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage", r.stderr)


if __name__ == "__main__":
    unittest.main()
