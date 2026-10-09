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


if __name__ == "__main__":
    unittest.main()
