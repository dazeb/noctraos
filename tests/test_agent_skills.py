"""configs/agent-skills/noctraos (the NoctraOS skill) and bin/noc-agent-skills, which puts it in ~/.agents/skills.

Two things are pinned: the skill itself is valid for Hermes, Codex and Claude Code alike (frontmatter, every reference linked,
no dead links), and the installer keeps what the person made (an edited copy, a folder it did not install, an opt-out).
Everything runs against a temp HOME; the real ~/.agents, ~/.hermes and ~/.claude are never touched."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "bin/noc-agent-skills"
SKILLS = ROOT / "configs/agent-skills"
SKILL = SKILLS / "noctraos"


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md must start with a --- frontmatter block"
    out = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


class SkillContentTests(unittest.TestCase):
    def test_frontmatter_is_valid_for_every_agent(self):
        for skill in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
            fm = frontmatter((skill / "SKILL.md").read_text())
            self.assertEqual(set(fm), {"name", "description"}, f"{skill.name}: only name and description are portable")
            self.assertEqual(fm["name"], skill.name)
            self.assertRegex(fm["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
            self.assertLessEqual(len(fm["description"]), 1024)
            self.assertGreater(len(fm["description"]), 40)

    def test_every_reference_is_linked_and_every_link_resolves(self):
        text = (SKILL / "SKILL.md").read_text()
        linked = set(re.findall(r"\]\((references/[^)#]+\.md)\)", text))
        on_disk = {f"references/{p.name}" for p in (SKILL / "references").glob("*.md")}
        self.assertEqual(linked, on_disk, "SKILL.md must link every reference file, and only real ones")
        for ref in sorted(on_disk):
            for target in re.findall(r"\]\(([a-z0-9-]+\.md)\)", (SKILL / ref).read_text()):
                self.assertTrue((SKILL / "references" / target).is_file(), f"{ref} links to missing {target}")

    def test_skill_page_stays_small(self):
        self.assertLess(len((SKILL / "SKILL.md").read_text().splitlines()), 120, "put detail in references/")

    def test_documented_noc_commands_exist(self):
        noc = (ROOT / "bin/noc").read_text()
        text = (SKILL / "references/noc-cli.md").read_text()
        for cmd in sorted(set(re.findall(r"`noc ([a-z-]+)", text))):
            self.assertRegex(noc, rf"(?m)^\s+{re.escape(cmd)}\)", f"noc {cmd} is documented but not dispatched")

    def test_no_secrets_or_symlinks_ship(self):
        for path in SKILL.rglob("*"):
            self.assertFalse(path.is_symlink(), f"{path}: bundles hold plain files only")
        self.assertNotRegex("\n".join(p.read_text() for p in SKILL.rglob("*.md")), r"(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,})")

    def test_installed_and_updated_by_the_pipeline(self):
        self.assertIn("bin/noc-agent-skills", (ROOT / "install/07_persistence.sh").read_text())
        self.assertIn("noc-agent-skills install", (ROOT / "install/07_persistence.sh").read_text())
        self.assertIn("noc-agent-skills install", (ROOT / "install/11_hermes.sh").read_text())
        self.assertIn("'configs'", (ROOT / "scripts/make-update.py").read_text(), "the skill rides in the configs bundle item")
        self.assertTrue(os.access(ROOT / "migrations/user/0002_install_agent_skill.sh", os.X_OK))


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.tmp = Path(self._t.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.src = self.tmp / "src"
        (self.src / "noctraos" / "references").mkdir(parents=True)
        (self.src / "noctraos/SKILL.md").write_text("---\nname: noctraos\ndescription: A test skill for the installer checks.\n---\n# one\n")
        (self.src / "noctraos/references/a.md").write_text("a\n")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_",))}
        self.env.update(HOME=str(self.home), NOC_TEST_HOOKS="1", NOC_SKILLS_SRC=str(self.src))

    def run_tool(self, *args):
        return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, env=self.env)

    @property
    def dest(self):
        return self.home / ".agents/skills/noctraos"

    def test_fresh_install_copies_and_second_run_is_a_noop(self):
        r = self.run_tool("install")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.dest / "SKILL.md").is_file())
        self.assertTrue((self.dest / "references/a.md").is_file())
        self.assertEqual(self.dest.stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.dest / "SKILL.md").stat().st_mode & 0o777, 0o644)
        self.assertEqual([p.name for p in self.dest.parent.iterdir()], ["noctraos"], "no staging folder left behind")
        again = self.run_tool("install")
        self.assertIn("up to date", again.stdout)

    def test_dry_run_changes_nothing(self):
        r = self.run_tool("install", "--dry-run")
        self.assertEqual(r.returncode, 0)
        self.assertIn("install into", r.stdout)
        self.assertFalse((self.home / ".agents").exists())
        self.assertFalse((self.home / ".local/state/noctraos").exists())

    def test_links_only_for_agents_that_are_there(self):
        self.run_tool("install")
        self.assertFalse((self.home / ".hermes").exists(), "an agent that is not installed gets no folder")
        self.assertFalse((self.home / ".claude").exists())
        (self.home / ".hermes").mkdir()
        (self.home / ".claude").mkdir()
        self.run_tool("install")
        for rel in (".hermes/skills/noctraos", ".claude/skills/noctraos"):
            link = self.home / rel
            self.assertTrue(link.is_symlink(), rel)
            self.assertEqual(os.readlink(link), "../../.agents/skills/noctraos")
            self.assertTrue((link / "SKILL.md").is_file(), "the relative link must resolve")

    def test_an_existing_agent_folder_is_left_alone(self):
        (self.home / ".claude/skills/noctraos").mkdir(parents=True)
        (self.home / ".claude/skills/noctraos/SKILL.md").write_text("mine\n")
        r = self.run_tool("install")
        self.assertIn("left alone", r.stdout)
        self.assertFalse((self.home / ".claude/skills/noctraos").is_symlink())
        self.assertEqual((self.home / ".claude/skills/noctraos/SKILL.md").read_text(), "mine\n")

    def test_update_replaces_an_untouched_copy(self):
        self.run_tool("install")
        (self.src / "noctraos/references/a.md").write_text("a, newer\n")
        (self.src / "noctraos/references/b.md").write_text("b\n")
        r = self.run_tool("install")
        self.assertIn("updated", r.stdout)
        self.assertEqual((self.dest / "references/a.md").read_text(), "a, newer\n")
        self.assertTrue((self.dest / "references/b.md").is_file())
        self.assertEqual(json.loads(self.run_tool("status", "--json").stdout)["skills"][0]["state"], "current")

    def test_an_edited_copy_is_kept(self):
        self.run_tool("install")
        (self.dest / "SKILL.md").write_text("my own version\n")
        (self.src / "noctraos/references/a.md").write_text("a, newer\n")
        r = self.run_tool("install")
        self.assertIn("kept as it is", r.stdout)
        self.assertEqual((self.dest / "SKILL.md").read_text(), "my own version\n")
        self.assertEqual((self.dest / "references/a.md").read_text(), "a\n")
        self.assertEqual(json.loads(self.run_tool("status", "--json").stdout)["skills"][0]["state"], "modified")

    def test_a_folder_we_did_not_install_is_kept(self):
        self.dest.mkdir(parents=True)
        (self.dest / "SKILL.md").write_text("someone else's noctraos skill\n")
        r = self.run_tool("install")
        self.assertIn("kept as it is", r.stdout)
        self.assertEqual((self.dest / "SKILL.md").read_text(), "someone else's noctraos skill\n")

    def test_status_reports_an_outdated_copy(self):
        self.run_tool("install")
        (self.src / "noctraos/SKILL.md").write_text("---\nname: noctraos\ndescription: A newer test skill for the installer.\n---\n")
        row = json.loads(self.run_tool("status", "--json").stdout)["skills"][0]
        self.assertEqual(row["state"], "outdated")

    def test_remove_switches_it_off_and_keeps_edits(self):
        (self.home / ".hermes").mkdir()
        self.run_tool("install")
        r = self.run_tool("remove")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.dest.exists())
        self.assertFalse((self.home / ".hermes/skills/noctraos").is_symlink())
        self.assertTrue((self.home / ".config/noctraos/no-agent-skills").is_file())
        self.assertIn("switched off", self.run_tool("install").stdout)
        self.assertFalse(self.dest.exists(), "the choice sticks")
        self.run_tool("on")
        self.run_tool("install")
        self.assertTrue(self.dest.is_dir())
        (self.dest / "SKILL.md").write_text("edited\n")
        self.run_tool("remove")
        self.assertEqual((self.dest / "SKILL.md").read_text(), "edited\n", "an edited copy is never deleted")

    def test_a_same_named_hermes_skill_is_reported_not_touched(self):
        clash = self.home / ".hermes/skills/software-development/noctraos"
        clash.mkdir(parents=True)
        (clash / "SKILL.md").write_text("---\nname: noctraos\ndescription: Hermes wrote this one.\n---\nbody\n")
        r = self.run_tool("install")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("NOTE Hermes also has a skill called noctraos", r.stdout)
        self.assertIn(str(clash), r.stdout)
        self.assertEqual((clash / "SKILL.md").read_text().splitlines()[-1], "body", "their skill is never edited")
        row = json.loads(self.run_tool("status", "--json").stdout)["skills"][0]
        self.assertEqual(row["clashes"], [str(clash)])
        self.assertIn("hides both", self.run_tool("status").stdout)

    def test_no_clash_note_when_the_names_differ(self):
        other = self.home / ".hermes/skills/other"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("---\nname: other\ndescription: x\n---\n")
        self.assertNotIn("NOTE", self.run_tool("install").stdout)
        self.assertEqual(json.loads(self.run_tool("status", "--json").stdout)["skills"][0]["clashes"], [])

    def test_other_skills_in_the_agents_folder_are_never_touched(self):
        other = self.home / ".agents/skills/other"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("not ours\n")
        self.run_tool("install")
        self.run_tool("remove")
        self.assertEqual((other / "SKILL.md").read_text(), "not ours\n")

    def test_refuses_to_run_as_root_without_the_test_hook(self):
        if os.geteuid() != 0:
            self.skipTest("only meaningful as root")
        env = {k: v for k, v in self.env.items() if k != "NOC_TEST_HOOKS"}
        r = subprocess.run([sys.executable, str(TOOL), "status"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 2)

    def test_the_real_skill_installs_from_a_checkout(self):
        env = {**self.env}
        env.pop("NOC_SKILLS_SRC")
        env["NOC_TEST_HOOKS"] = "1"
        r = subprocess.run([sys.executable, str(TOOL), "install"], capture_output=True, text=True, env=env)
        snapshot = Path("/usr/local/share/noctraos/repo/configs/agent-skills")
        if snapshot.is_dir():
            self.skipTest("this machine has a NoctraOS snapshot, which wins over the checkout")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.dest / "SKILL.md").is_file())
        self.assertTrue((self.dest / "references/noc-cli.md").is_file())


class DispatchTests(unittest.TestCase):
    def test_noc_hands_agent_skills_to_the_tool(self):
        with tempfile.TemporaryDirectory() as t:
            stub = Path(t) / "noc-agent-skills"
            stub.write_text('#!/usr/bin/env bash\necho "args: $*"\n')
            stub.chmod(0o755)
            env = {**os.environ, "NOC_TEST_HOOKS": "1", "NOC_SKILLSTOOL": str(stub)}
            r = subprocess.run(["bash", str(ROOT / "bin/noc"), "agent-skills", "status", "--json"], capture_output=True, text=True, env=env)
            self.assertEqual(r.stdout.strip(), "args: status --json")

    def test_migration_calls_the_tool(self):
        with tempfile.TemporaryDirectory() as t:
            stub = Path(t) / "tool"
            stub.write_text('#!/usr/bin/env bash\necho "ran $*"\n')
            stub.chmod(0o755)
            script = ROOT / "migrations/user/0002_install_agent_skill.sh"
            r = subprocess.run(["bash", str(script)], capture_output=True, text=True, env={**os.environ, "NOCTRAOS_AGENT_SKILLS_TOOL": str(stub)})
            self.assertEqual((r.returncode, r.stdout.strip()), (0, "ran install"))
            r = subprocess.run(["bash", str(script)], capture_output=True, text=True,
                               env={**os.environ, "NOCTRAOS_AGENT_SKILLS_TOOL": str(Path(t) / "missing")})
            self.assertEqual(r.returncode, 1, "a missing tool is retried at the next login")


if __name__ == "__main__":
    unittest.main()
