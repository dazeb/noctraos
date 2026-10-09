"""The first-run installer downloads only what the person chose: no language model, no embedding model, nothing a
hardware check picks for them. Local AI is the optional step install/optional/local_llm.sh (run later: `noc llm setup`)."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
CORE_MODULES = sorted(p for p in (ROOT / "install").glob("*.sh"))
OPTIONAL_MODULE = ROOT / "install/optional/local_llm.sh"
MODEL_WORDS = re.compile(r"ollama\s+pull|/api/pull|nomic-embed|qwen2|llama3|gemma\d|phi4|deepseek-coder|NOCTRAOS_MODEL|NOCTRAOS_EMBED_MODEL|\b[Ee]mbedding|noc-gpu\"?\s+install")


class CoreInstallTests(unittest.TestCase):
    def test_the_core_run_has_no_local_ai_or_gpu_step(self):
        run = re.findall(r"^run_module (\S+)", INSTALL.read_text(), re.MULTILINE)
        self.assertTrue(run)
        self.assertFalse([m for m in run if m.startswith(("02b", "03", "optional"))], run)

    def test_the_flags_for_local_ai_are_gone(self):
        text = INSTALL.read_text()
        self.assertNotIn("--skip-ai", text)
        self.assertNotIn("--skip-gpu", text)

    def test_no_core_module_downloads_a_model_or_picks_one(self):
        for path in [INSTALL, *CORE_MODULES]:
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                self.assertFalse(MODEL_WORDS.search(line), f"{path.relative_to(ROOT)}:{number}: {line.strip()}")

    def test_the_optional_step_downloads_the_engine_and_the_finder_but_no_model(self):
        text = OPTIONAL_MODULE.read_text()
        self.assertNotRegex(text, r"ollama\s+pull")
        self.assertNotRegex(text, r"/api/pull")
        self.assertIn('bash "$REPO_ROOT/bin/noc-gpu" install', text)
        self.assertIn("as_user pipx install llmfit", text)
        self.assertLess(text.index('noc-gpu" install'), text.index("ollama.com/install.sh"), "GPU must come before Ollama")


class LanguageTests(unittest.TestCase):
    """NoctraOS installs only what it needs itself: Node (the coding-agent launchers and the Hermes build) and the terminal tools.
    A language nothing uses, and what only it needed, stays out; people add theirs with mise."""

    def test_the_mise_baseline_is_node_and_the_terminal_tools(self):
        import tomllib
        tools = tomllib.loads((ROOT / "configs/mise/config.toml").read_text())["tools"]
        self.assertEqual(set(tools), {"node", "herdr", "starship", "lazygit", "lazydocker"})

    def test_node_is_still_needed_by_what_installs_it(self):
        self.assertIn("npm install -g", (ROOT / "bin/noctraos-agent").read_text())
        self.assertIn("noctraos-mise.sh", (ROOT / "bin/noctraos-hermes").read_text())     # the desktop build

    def test_no_apt_language_or_compiler_for_one_and_no_python_build_libraries(self):
        text = (ROOT / "install/04_workstation_apps.sh").read_text()
        apt = set(re.search(r"APT_APPS=\((.*?)\n\)", text, re.S).group(1).split())
        self.assertFalse({"ruby", "clang", "golang", "golang-go", "python3-pip"} & apt, apt)
        self.assertNotIn("PYTHON_BUILD_PKGS", (ROOT / "install/01_system.sh").read_text())

    def test_the_editor_gets_no_extension_for_a_language_that_is_not_installed(self):
        ids = [line.split("#")[0].strip() for line in (ROOT / "configs/vscode/extensions.list").read_text().splitlines()]
        self.assertNotIn("golang.go", ids)
        self.assertIn("continue.continue", ids)


if __name__ == "__main__":
    unittest.main()
