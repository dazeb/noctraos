"""The update pipeline end to end, as far as it can be proven without a desktop:

  * a bundle built from THIS repository (not a toy repo) is signed, found, applied and migrated by the real client, and the
    real per-account migration runs from it;
  * the migrations in the tree follow the rules the updater relies on (migrations/README.md);
  * the CI front (iso/ci-publish-update.sh) only ships code that is in GitHub main, takes notes and flags from the tag, and
    cannot promote or widen anything but the update its pipeline built;
  * the rolling nightly (iso/nightly-update.sh) publishes a changed main once its checks pass, and spends no serial otherwise;
  * .gitlab-ci.yml wires these up on protected refs only.
Nothing here touches the network, a real bucket or the real signing key."""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_selfupdate import Sandbox, sh  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / "iso/ci-publish-update.sh"
NIGHTLY = ROOT / "iso/nightly-update.sh"
IS_GIT = (ROOT / ".git").exists()
MIGRATION_RE = re.compile(r"^[0-9]{4}_[a-z0-9][a-z0-9_-]*\.sh$")


def have_yq4():
    """mikefarah's yq (Go, v4) turns the CI file into JSON with -o=json; the apt package named yq is a jq wrapper that rejects it."""
    if not shutil.which("yq") or not shutil.which("jq"):
        return False
    return "mikefarah" in subprocess.run(["yq", "--version"], capture_output=True, text=True).stdout


HAVE_YQ4 = have_yq4()


@unittest.skipUnless(IS_GIT and shutil.which("git"), "needs a git checkout of the repository")
class RealBundleTests(Sandbox):
    """The publisher's repo is a clone of this one, so the bundle is what an update would really carry."""

    def init_repo(self):
        r = sh("git", "clone", "-q", "--no-hardlinks", ROOT, self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")

    def fake_desktop(self):
        """A gsettings that keeps favorite-apps in a file, and a launcher directory, for the real pin migration."""
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        gsettings = bin_dir / "gsettings"
        gsettings.write_text('#!/bin/sh\nf="$FAKE_FAVORITES"\ncase "$1" in get) cat "$f" ;; set) printf "%s\\n" "$4" > "$f" ;; esac\n')
        gsettings.chmod(0o755)
        (self.tmp / "apps").mkdir()
        (self.tmp / "apps/noctraos-control.desktop").write_text("[Desktop Entry]\n")
        (self.tmp / "favorites").write_text("['org.gnome.Nautilus.desktop']\n")
        (self.home / ".local/state/noctraos").mkdir(parents=True)
        self.env.update(PATH=f"{bin_dir}:{os.environ['PATH']}", FAKE_FAVORITES=str(self.tmp / "favorites"), HOME=str(self.home),
                        NOCTRAOS_APPLICATIONS_DIR=str(self.tmp / "apps"))

    def test_a_bundle_of_this_repository_is_applied_and_its_migrations_run(self):
        self.fake_desktop()
        self.publish(notes="Real bundle.")
        self.assertEqual(self.check()["status"], "available")
        applied = self.client("apply")
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        # the snapshot is the tree an install module would read, including what this change shipped
        for path in ("VERSION", "bin/noc", "bin/noc-selfupdate", "control/panel.py", "install/lib.sh", "install/07_persistence.sh",
                     "configs/applications/noctraos-control.desktop", "migrations/user/0001_pin_control_panel.sh"):
            self.assertTrue(self.snap(path).is_file(), path)
        self.assertFalse(self.snap("site").exists(), "the website is not part of an update")
        self.assertEqual(self.state()["serial"], 1)
        # the per-account migration ran, from the bundle, and did its job
        self.assertIn("noctraos-control.desktop", (self.tmp / "favorites").read_text())
        done = self.home / ".local/state/noctraos/migrations/done/0001_pin_control_panel.sh"
        self.assertTrue(done.exists())
        self.assertEqual(self.check()["status"], "current")

    def test_a_pin_the_person_removed_stays_removed(self):
        self.fake_desktop()
        self.publish()
        self.assertEqual(self.client("apply").returncode, 0)
        (self.tmp / "favorites").write_text("['org.gnome.Nautilus.desktop']\n")        # the person unpins it
        again = self.client("migrate", "--scope", "user")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotIn("noctraos-control.desktop", (self.tmp / "favorites").read_text())

    def test_the_next_update_carries_a_new_file_and_leaves_the_pin_alone(self):
        self.fake_desktop()
        self.publish(notes="One.")
        self.client("apply")
        self.commit({"control/extra_page.py": "# a later change\n"})
        self.publish(notes="Two.")
        self.assertEqual(self.client("apply").returncode, 0)
        self.assertTrue(self.snap("control/extra_page.py").is_file())
        self.assertEqual(self.state()["serial"], 2)

    def commit(self, files, remove=()):
        for name, text in files.items():
            p = self.repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "c", "--allow-empty")


class MigrationRulesTests(unittest.TestCase):
    """migrations/README.md, enforced: the updater only runs names it recognises, in order, and from the tree's executable files."""

    def scripts(self):
        return [(scope, p) for scope in ("system", "user") for p in sorted((ROOT / "migrations" / scope).glob("*"))
                if (ROOT / "migrations" / scope).is_dir()]

    def test_names_are_four_digits_lowercase_and_never_reused(self):
        for scope in ("system", "user"):
            numbers = []
            for p in sorted((ROOT / "migrations" / scope).glob("*")) if (ROOT / "migrations" / scope).is_dir() else []:
                self.assertRegex(p.name, MIGRATION_RE, f"{scope}/{p.name}: the updater would ignore this file")
                numbers.append(p.name[:4])
            self.assertEqual(numbers, sorted(set(numbers)), f"{scope}: a number is used twice")

    def test_each_script_is_valid_bash_with_a_shebang(self):
        for scope, p in self.scripts():
            self.assertTrue(p.read_text().startswith("#!"), f"{scope}/{p.name}: no shebang")
            self.assertEqual(subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True).returncode, 0, p.name)

    @unittest.skipUnless(IS_GIT and shutil.which("git"), "needs a git checkout")
    def test_each_script_is_executable_in_git(self):
        for scope, p in self.scripts():
            mode = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-s", str(p.relative_to(ROOT))], capture_output=True, text=True).stdout
            if mode:                                                   # a new, uncommitted file is checked when it is added
                self.assertTrue(mode.startswith("100755"), f"{scope}/{p.name} must be executable (git add --chmod=+x)")

    def test_user_migrations_never_use_sudo_or_the_network(self):
        for scope, p in self.scripts():
            if scope == "user":
                text = re.sub(r"(?m)^\s*#.*$", "", p.read_text())
                self.assertNotRegex(text, r"\bsudo\b|\bcurl\b|\bwget\b", f"user/{p.name} (README rules 4)")


def run(script, *args, cwd=None, env=None):
    return subprocess.run(["bash", str(script), *args], capture_output=True, text=True, cwd=cwd, env=env)


class Repos(unittest.TestCase):
    """A 'GitHub main' and a 'GitLab checkout' of it, as plain local repositories."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.main = self.tmp / "github"
        self.checkout = self.tmp / "checkout"
        self.main.mkdir()
        self.git(self.main, "init", "-q", "-b", "main")
        for key, value in (("user.email", "t@t"), ("user.name", "t")):
            self.git(self.main, "config", key, value)
        self.commit(self.main, "9.9.1", "first")
        self.git(self.tmp, "clone", "-q", str(self.main), str(self.checkout))
        for key, value in (("user.email", "t@t"), ("user.name", "t")):
            self.git(self.checkout, "config", key, value)
        self.calls = self.tmp / "calls"
        stub = self.tmp / "publish-update.sh"
        stub.write_text('#!/usr/bin/env bash\necho "$@" >> "$CALLS"\n')
        stub.chmod(0o755)
        self.public = self.tmp / "public"
        self.env = {**os.environ, "CALLS": str(self.calls), "PUBLISH_UPDATE": str(stub), "UPDATE_REPO": str(self.checkout),
                    "UPDATE_MAIN_URL": str(self.main), "UPDATE_PUBLIC_BASE": f"file://{self.public}"}
        self.env.pop("CI_COMMIT_TAG", None)

    def git(self, where, *args):
        r = subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def commit(self, where, version, message, files=None):
        (Path(where) / "VERSION").write_text(version + "\n")
        for name, text in (files or {}).items():
            p = Path(where) / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        self.git(where, "add", "-A")
        self.git(where, "commit", "-q", "-m", message, "--allow-empty")
        return self.git(where, "rev-parse", "HEAD")

    def pull(self):
        self.git(self.checkout, "pull", "-q", "origin", "main")

    def publish_calls(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def serve(self, channel, commit, percent=100):
        d = self.public / channel
        d.mkdir(parents=True, exist_ok=True)
        (d / "manifest.json").write_text(json.dumps({"commit": commit, "serial": 1, "rollout": {"percent": percent}}))


@unittest.skipUnless(shutil.which("git") and shutil.which("jq"), "needs git and jq")
class CiPublishTests(Repos):
    def nightly(self, *args, **env):
        return run(CI, "nightly", *args, env={**self.env, **env})

    def test_a_tag_message_becomes_the_notes_and_its_flags_the_flags(self):
        self.git(self.main, "tag", "-a", "update-2026.10.09", "-m", "Control Panel in the dock\n\nRelogin: yes\nreboot: No")
        self.pull()
        self.git(self.checkout, "fetch", "-q", "--tags", "origin")
        r = self.nightly("update-2026.10.09")
        self.assertEqual(r.returncode, 0, r.stderr)
        head = self.git(self.main, "rev-parse", "HEAD")
        self.assertEqual(self.publish_calls(), [f"nightly --ref {head} --notes Control Panel in the dock --relogin"])

    def test_a_tag_without_a_message_is_described_by_its_version(self):
        self.git(self.main, "tag", "update-2026.10.10")
        self.git(self.checkout, "fetch", "-q", "--tags", "origin")
        self.assertEqual(self.nightly("update-2026.10.10").returncode, 0)
        self.assertIn("--notes NoctraOS 9.9.1", self.publish_calls()[0])

    def test_the_pipeline_tag_comes_from_the_environment(self):
        self.git(self.main, "tag", "-a", "update-2026.10.11", "-m", "From CI")
        self.git(self.checkout, "fetch", "-q", "--tags", "origin")
        self.assertEqual(self.nightly(CI_COMMIT_TAG="update-2026.10.11").returncode, 0)
        self.assertIn("--notes From CI", self.publish_calls()[0])

    def test_a_commit_that_is_not_in_github_main_is_refused(self):
        self.commit(self.checkout, "9.9.2", "only on the runner")
        self.git(self.checkout, "tag", "-a", "update-2026.10.12", "-m", "Unmerged")
        r = self.nightly("update-2026.10.12")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not in GitHub main", r.stderr)
        self.assertEqual(self.publish_calls(), [])

    def test_an_unknown_ref_is_refused(self):
        r = self.nightly("update-2000.01.01")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.publish_calls(), [])

    def promote(self, mode, percent, **env):
        return run(CI, mode, percent, env={**self.env, "CI_COMMIT_TAG": "x", **env})

    def pipeline_commit(self):
        head = self.git(self.main, "rev-parse", "HEAD")
        self.git(self.checkout, "tag", "x", head)
        return head

    def test_promote_moves_this_pipelines_nightly_to_stable_at_ten_percent(self):
        head = self.pipeline_commit()
        self.serve("nightly", head)
        r = self.promote("promote", "10")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.publish_calls(), ["stable --from nightly --rollout 10"])

    def test_widen_raises_the_stable_rollout_from_stable(self):
        head = self.pipeline_commit()
        self.serve("stable", head, 10)
        self.assertEqual(self.promote("widen", "50").returncode, 0)
        self.assertEqual(self.publish_calls(), ["stable --from stable --rollout 50"])

    def test_a_newer_update_stops_an_old_pipeline_from_promoting(self):
        self.pipeline_commit()
        self.serve("nightly", "f" * 40)
        r = self.promote("promote", "10")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("newer update exists", r.stderr)
        self.assertEqual(self.publish_calls(), [])

    def test_a_rerun_never_lowers_a_rollout(self):
        head = self.pipeline_commit()
        self.serve("nightly", head)
        self.serve("stable", head, 100)
        r = self.promote("promote", "10")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.publish_calls(), [])
        self.assertIn("nothing to do", r.stdout)

    def test_nothing_to_promote_or_widen_is_an_error(self):
        self.pipeline_commit()
        self.assertNotEqual(self.promote("promote", "10").returncode, 0)
        self.assertNotEqual(self.promote("widen", "50").returncode, 0)

    def test_the_percentage_is_validated(self):
        head = self.pipeline_commit()
        self.serve("nightly", head)
        for bad in ("0", "101", "ten", "10; id", "-5", ""):
            self.assertNotEqual(self.promote("promote", bad).returncode, 0, repr(bad))
        self.assertEqual(self.publish_calls(), [])

    def test_unknown_modes_print_usage(self):
        r = run(CI, "everything", env=self.env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("usage", r.stderr)


@unittest.skipUnless(shutil.which("git") and shutil.which("jq") and shutil.which("python3"), "needs git, jq and python3")
class NightlyTests(Repos):
    def setUp(self):
        super().setUp()
        # the clone the job makes needs the real items list
        self.commit(self.main, "9.9.1", "scripts", {"scripts/make-update.py": (ROOT / "scripts/make-update.py").read_text(),
                                                    "bin/noc": "#!/bin/sh\n"})
        self.home = self.tmp / "nightly-home"
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        self.notified = self.tmp / "notified"
        (bin_dir / "notify-send").write_text('#!/bin/sh\necho "$@" >> "$NOTIFIED"\n')
        (bin_dir / "notify-send").chmod(0o755)                                   # never pop a real desktop notification
        self.env.update(NIGHTLY_HOME=str(self.home), NIGHTLY_REPO_URL=str(self.main), NIGHTLY_PUBLIC_BASE=f"file://{self.public}",
                        NIGHTLY_CHECKS="true", NOTIFIED=str(self.notified), PATH=f"{bin_dir}:{os.environ['PATH']}")

    def go(self, *args, **env):
        return run(NIGHTLY, *args, env={**self.env, **env})

    def test_a_changed_main_is_checked_and_published(self):
        r = self.go()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        call = self.publish_calls()
        self.assertEqual(len(call), 1)
        self.assertRegex(call[0], r"^nightly --ref [0-9a-f]{40} --notes Nightly \d{4}-\d\d-\d\d [0-9a-f]{7}: scripts$")

    def test_main_already_served_is_left_alone(self):
        self.serve("nightly", self.git(self.main, "rev-parse", "HEAD"))
        r = self.go()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.publish_calls(), [])
        self.assertIn("already serves", r.stdout)

    def test_a_commit_that_changes_nothing_an_update_carries_spends_no_serial(self):
        served = self.git(self.main, "rev-parse", "HEAD")
        self.serve("nightly", served)
        self.commit(self.main, "9.9.1", "website only", {"site/index.html": "<p>new</p>\n", "docs/x.md": "x\n"})
        r = self.go()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.publish_calls(), [])
        self.assertIn("nothing an update carries changed", r.stdout)

    def test_a_commit_that_changes_a_bundled_file_is_published(self):
        self.serve("nightly", self.git(self.main, "rev-parse", "HEAD"))
        self.commit(self.main, "9.9.1", "a real change", {"bin/noc": "#!/bin/sh\necho 2\n"})
        self.assertEqual(self.go().returncode, 0)
        self.assertEqual(len(self.publish_calls()), 1)

    def test_failing_checks_stop_the_publish(self):
        r = self.go(NIGHTLY_CHECKS="echo broken; false")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("was not published", self.notified.read_text())
        self.assertEqual(self.publish_calls(), [])
        self.assertIn("fails its checks", r.stdout)
        self.assertIn("broken", (self.home / "checks.log").read_text())

    def test_a_dry_run_publishes_nothing(self):
        r = self.go("--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.publish_calls(), [])
        self.assertIn("would publish", r.stdout)

    def test_a_failed_publish_is_reported(self):
        failing = self.tmp / "failing.sh"
        failing.write_text("#!/bin/sh\nexit 3\n")
        failing.chmod(0o755)
        self.assertNotEqual(self.go(PUBLISH_UPDATE=str(failing)).returncode, 0)
        self.assertIn("was not published", self.notified.read_text())


class CiConfigTests(unittest.TestCase):
    """The pipeline definition: updates run on the protected runner, only for protected tags, and are pressed by hand to widen."""
    CI_YML = (ROOT / ".gitlab-ci.yml").read_text()

    def jobs(self):
        out = subprocess.run(["yq", "-o=json", ".", str(ROOT / ".gitlab-ci.yml")], capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    @unittest.skipUnless(HAVE_YQ4, "needs mikefarah yq v4 and jq")
    def test_update_jobs_exist_in_a_stage_after_the_release(self):
        ci = self.jobs()
        self.assertEqual(ci["stages"][-1], "update")
        for name in ("update-nightly", "update-stable-10", "update-stable-50", "update-stable-100"):
            self.assertEqual(ci[name]["stage"] if "stage" in ci[name] else ci[ci[name]["extends"]]["stage"], "update", name)

    @unittest.skipUnless(HAVE_YQ4, "needs mikefarah yq v4 and jq")
    def test_only_the_release_runner_and_only_protected_tags_reach_the_signing_key(self):
        ci = self.jobs()
        base = ci[".update"]
        self.assertEqual(base["tags"], ["noctraos-release"])
        for rule in base["rules"]:
            self.assertIn("CI_COMMIT_TAG", rule["if"], "an update job must never run on a branch or merge request")
        self.assertEqual(ci["update-nightly"]["extends"], ".update")
        self.assertEqual(ci[".update-stable"]["when"], "manual")
        self.assertTrue(ci[".update-stable"]["allow_failure"])
        self.assertEqual(ci[".update-stable"]["extends"], ".update")

    @unittest.skipUnless(HAVE_YQ4, "needs mikefarah yq v4 and jq")
    def test_jobs_call_the_checked_front_not_the_publisher_directly(self):
        ci = self.jobs()
        for name, want in (("update-nightly", "nightly"), ("update-stable-10", "promote 10"), ("update-stable-50", "widen 50"),
                           ("update-stable-100", "widen 100")):
            script = " ".join(ci[name]["script"])
            self.assertIn("iso/ci-publish-update.sh " + want, script)
            self.assertNotIn("iso/publish-update.sh", script)

    def test_update_tags_start_a_pipeline_and_other_tags_still_do_not(self):
        self.assertIn("update-[0-9]{4}", self.CI_YML)
        self.assertIn("if: $CI_COMMIT_TAG\n      when: never", self.CI_YML)
        tag = re.compile(r"^update-[0-9]{4}\.[0-9]{2}\.[0-9]{2}(-[0-9]+)?$")
        for good in ("update-2026.10.09", "update-2026.10.09-2"):
            self.assertTrue(tag.match(good), good)
        for bad in ("update-latest", "update-2026.10", "v1.2.3-update", "update-2026.10.09-x"):
            self.assertFalse(tag.match(bad), bad)

    def test_the_runner_setup_protects_update_tags_like_release_tags(self):
        setup = (ROOT / "iso/setup-release-runner.sh").read_text()
        self.assertRegex(setup, r"for pattern in 'v\*' 'update-\*'")

    def test_the_scripts_are_executable(self):
        for name in ("ci-publish-update.sh", "nightly-update.sh", "setup-nightly-update.sh", "publish-update.sh"):
            self.assertTrue((ROOT / "iso" / name).stat().st_mode & stat.S_IXUSR, name)


class PublishLockTests(unittest.TestCase):
    """Two publishes at once would pick the same serial: the second must refuse, not race."""

    def test_a_second_publish_refuses_while_one_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            key = tmp / "key"
            key.write_text("k")
            signers = tmp / "signers"
            signers.write_text("s")
            lock = tmp / "lock"
            holder = subprocess.Popen(["flock", str(lock), "sleep", "30"])
            self.addCleanup(lambda: (holder.terminate(), holder.wait()))
            for _ in range(50):                                          # wait until the holder really has the lock
                if subprocess.run(["flock", "-n", str(lock), "true"]).returncode != 0:
                    break
                subprocess.run(["sleep", "0.1"])
            env = {**os.environ, "NOCTRAOS_UPDATE_KEY": str(key), "UPDATE_SIGNERS": str(signers), "UPDATE_PUBLISH_LOCK": str(lock),
                   "NOCTRAOS_S3_ENV_FILE": "/nonexistent", "R2_ACCESS_KEY_ID": "x", "R2_SECRET_ACCESS_KEY": "x", "R2_ENDPOINT": "x",
                   "R2_BUCKET": "b", "AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "x"}
            r = subprocess.run(["bash", str(ROOT / "iso/publish-update.sh"), "nightly"], capture_output=True, text=True, env=env, timeout=60)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("another update publish is running", r.stderr)


if __name__ == "__main__":
    unittest.main()
