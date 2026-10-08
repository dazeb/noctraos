"""bin/noc-accounts: Git identity (real git, temp HOME) and the GitHub device-flow sign-in (stub gh). No network, no real
account, and the real ~/.gitconfig and ~/.config/gh are never touched."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "bin/noc-accounts"

GH_STUB = r'''#!/usr/bin/env bash
# stub of the gh CLI: the device flow, status, setup-git, logout, api user
echo "$*" >> "$GH_LOG"
hosts="$GH_CONFIG_DIR/hosts.yml"
case "$1 $2" in
  "auth login")
    env | grep -E '^(GH_TOKEN|GITHUB_TOKEN)=' >> "$GH_LOG.env" || true
    echo "! First copy your one-time code: ABCD-1234"
    echo "Open this URL to continue in your web browser: https://github.com/login/device"
    case "${GH_STUB_MODE:-approve}" in
      approve) sleep 0.3; mkdir -p "$GH_CONFIG_DIR"; printf 'github.com:\n    user: octocat\n    git_protocol: https\n' > "$hosts"
               echo "✓ Authentication complete."; exit 0 ;;
      deny)    sleep 0.2; echo "failed to authenticate via web browser: access_denied" >&2; exit 1 ;;
      hang)    sleep 60 ;;
    esac ;;
  "auth status") grep -q 'user:' "$hosts" 2>/dev/null && [ -z "${GH_STUB_REVOKED:-}" ] ;;
  "auth setup-git") exit 0 ;;
  "auth logout") rm -f "$hosts"; exit 0 ;;
  "api user") printf '{"login":"octocat","id":583231,"name":%s,"email":%s}\n' "${GH_STUB_NAME:-\"The Octocat\"}" "${GH_STUB_EMAIL:-null}" ;;
esac
'''


class Box(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.gh = self.tmp / "gh"
        self.gh.write_text(GH_STUB)
        self.gh.chmod(0o755)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "GH_", "GITHUB_"))}
        self.env.update(HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / ".config"), GH_CONFIG_DIR=str(self.home / "ghcfg"),
                        NOC_ACCOUNTS_GH=str(self.gh), GH_LOG=str(self.tmp / "gh.log"), GIT_CONFIG_NOSYSTEM="1")

    def run_tool(self, *args, **env):
        return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env={**self.env, **env})

    def git_get(self, key):
        r = subprocess.run(["git", "config", "--global", "--get", key], capture_output=True, text=True, env=self.env)
        return r.stdout.strip()

    def events(self, result):
        return [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]

    def gh_calls(self):
        log = self.tmp / "gh.log"
        return log.read_text().splitlines() if log.exists() else []


class StatusTests(Box):
    def test_a_fresh_account_has_nothing_set(self):
        data = json.loads(self.run_tool("status", "--json").stdout)
        self.assertEqual(data["git"], {"installed": True, "name": "", "email": "", "ready": False})
        self.assertEqual(data["github"], {"installed": True, "signed_in": False, "login": ""})

    def test_status_is_local_and_never_asks_github(self):
        (self.home / "ghcfg").mkdir()
        (self.home / "ghcfg/hosts.yml").write_text("github.com:\n    user: octocat\n")
        data = json.loads(self.run_tool("status", "--json").stdout)
        self.assertEqual((data["github"]["signed_in"], data["github"]["login"]), (True, "octocat"))
        self.assertEqual(self.gh_calls(), [])                  # no gh process was started

    def test_verify_notices_a_revoked_login(self):
        (self.home / "ghcfg").mkdir()
        (self.home / "ghcfg/hosts.yml").write_text("github.com:\n    user: octocat\n")
        data = json.loads(self.run_tool("status", "--json", "--verify", GH_STUB_REVOKED="1").stdout)
        self.assertFalse(data["github"]["signed_in"])

    def test_the_login_is_read_for_github_dot_com_only(self):
        (self.home / "ghcfg").mkdir()
        (self.home / "ghcfg/hosts.yml").write_text("ghe.example.com:\n    user: corp\ngithub.com:\n    user: octocat\n")
        self.assertEqual(json.loads(self.run_tool("status", "--json").stdout)["github"]["login"], "octocat")

    def test_without_gh_installed(self):
        data = json.loads(self.run_tool("status", "--json", NOC_ACCOUNTS_GH="", PATH="/nonexistent").stdout)
        self.assertFalse(data["github"]["installed"])


class IdentityTests(Box):
    def test_saves_name_email_and_a_default_branch(self):
        r = self.run_tool("git", "set", "--name", "Ada Lovelace", "--email", "ada@example.com")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.git_get("user.name"), self.git_get("user.email")), ("Ada Lovelace", "ada@example.com"))
        self.assertEqual(self.git_get("init.defaultBranch"), "main")
        self.assertIn("Ada Lovelace", r.stdout)
        self.assertTrue(json.loads(self.run_tool("status", "--json").stdout)["git"]["ready"])

    def test_an_existing_default_branch_is_not_overridden(self):
        subprocess.run(["git", "config", "--global", "init.defaultBranch", "trunk"], env=self.env, check=True)
        self.run_tool("git", "set", "--name", "Ada", "--email", "ada@example.com")
        self.assertEqual(self.git_get("init.defaultBranch"), "trunk")

    def test_bad_input_changes_nothing(self):
        for name, email in (("", "ada@example.com"), ("   ", "ada@example.com"), ("Ada", ""), ("Ada", "not-an-email"),
                            ("Ada", "a@b"), ("Ada <x>", "ada@example.com"), ("Ada\nEvil", "ada@example.com"),
                            ("x" * 101, "ada@example.com"), ("Ada", "a b@example.com")):
            with self.subTest(name=name, email=email):
                r = self.run_tool("git", "set", "--name", name, "--email", email)
                self.assertEqual(r.returncode, 1)
                self.assertEqual((self.git_get("user.name"), self.git_get("user.email")), ("", ""))

    def test_values_are_data_never_options_or_shell(self):
        r = self.run_tool("git", "set", "--name", "-c core.editor=evil; rm -rf ~", "--email", "ada@example.com")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.git_get("user.name"), "-c core.editor=evil; rm -rf ~")
        self.assertEqual(self.git_get("core.editor"), "")


class LoginTests(Box):
    def test_the_device_flow_reports_the_code_then_the_result_and_wires_git(self):
        r = self.run_tool("github", "login", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        events = self.events(r)
        self.assertEqual(events[0], {"event": "code", "code": "ABCD-1234", "url": "https://github.com/login/device"})
        self.assertEqual((events[-1]["event"], events[-1]["ok"], events[-1]["login"]), ("done", True, "octocat"))
        calls = self.gh_calls()
        self.assertIn("auth login --hostname github.com --git-protocol https --web", calls)
        self.assertIn("auth setup-git --hostname github.com", calls)         # git push over https now just works
        self.assertTrue(json.loads(self.run_tool("status", "--json").stdout)["github"]["signed_in"])

    def test_the_code_is_announced_once(self):
        events = self.events(self.run_tool("github", "login", "--json"))
        self.assertEqual([e["event"] for e in events].count("code"), 1)

    def test_a_denied_sign_in_says_so_and_does_not_set_up_git(self):
        r = self.run_tool("github", "login", "--json", GH_STUB_MODE="deny")
        self.assertEqual(r.returncode, 1)
        done = self.events(r)[-1]
        self.assertEqual((done["event"], done["ok"]), ("done", False))
        self.assertIn("access_denied", done["message"])
        self.assertFalse(any("setup-git" in c for c in self.gh_calls()))

    def test_token_variables_never_reach_gh(self):
        self.run_tool("github", "login", "--json", GH_TOKEN="secret-a", GITHUB_TOKEN="secret-b")
        self.assertFalse((self.tmp / "gh.log.env").exists() and (self.tmp / "gh.log.env").read_text().strip(),
                         "gh refuses to log in while a token variable is set, and the person's login is what we want")

    def test_cancel_stops_the_program_and_gh(self):
        proc = subprocess.Popen([sys.executable, "-u", str(TOOL), "github", "login", "--json"], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, env={**self.env, "GH_STUB_MODE": "hang"})
        self.addCleanup(proc.stdout.close)
        self.addCleanup(proc.kill)
        first = proc.stdout.readline()
        self.assertEqual(json.loads(first)["event"], "code")
        proc.send_signal(signal.SIGTERM)
        started = time.time()
        proc.wait(timeout=10)
        self.assertLess(time.time() - started, 5)
        self.assertEqual(proc.returncode, 130)
        time.sleep(0.3)
        left = subprocess.run(["pgrep", "-f", f"{self.gh} auth login"], capture_output=True, text=True)
        self.assertEqual(left.stdout.strip(), "", "the gh child must not be left running")

    def test_without_gh_it_says_so(self):
        r = self.run_tool("github", "login", "--json", NOC_ACCOUNTS_GH="", PATH="/nonexistent")
        done = self.events(r)[-1]
        self.assertEqual((done["event"], done["ok"]), ("done", False))
        self.assertIn("not installed", done["message"])

    def test_plain_text_mode_tells_a_person_what_to_do(self):
        r = self.run_tool("github", "login")
        self.assertIn("ABCD-1234", r.stdout)
        self.assertIn("https://github.com/login/device", r.stdout)
        self.assertIn("Signed in to GitHub as octocat", r.stdout)

    def test_logout(self):
        self.run_tool("github", "login", "--json")
        self.assertEqual(self.run_tool("github", "logout").returncode, 0)
        self.assertFalse(json.loads(self.run_tool("status", "--json").stdout)["github"]["signed_in"])


class SuggestTests(Box):
    def test_private_address_uses_the_account_id(self):
        data = json.loads(self.run_tool("github", "suggest", "--json").stdout)
        self.assertEqual(data["private_email"], "583231+octocat@users.noreply.github.com")
        self.assertEqual((data["login"], data["name"], data["public_email"]), ("octocat", "The Octocat", ""))

    def test_a_nameless_account_falls_back_to_the_login(self):
        data = json.loads(self.run_tool("github", "suggest", "--json", GH_STUB_NAME="null").stdout)
        self.assertEqual(data["name"], "octocat")

    def test_a_public_address_is_offered_too(self):
        data = json.loads(self.run_tool("github", "suggest", "--json", GH_STUB_EMAIL='"octo@example.com"').stdout)
        self.assertEqual(data["public_email"], "octo@example.com")

    def test_not_signed_in_or_offline_is_a_clear_failure(self):
        r = self.run_tool("github", "suggest", "--json", NOC_ACCOUNTS_GH="/bin/false")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Sign in first", r.stderr)


if __name__ == "__main__":
    unittest.main()
