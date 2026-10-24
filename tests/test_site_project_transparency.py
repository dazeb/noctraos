"""Public project and funding claims on the static website."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


class SiteProjectTransparencyTests(unittest.TestCase):
    def test_site_has_no_patreon_links(self):
        for page in SITE.glob("*.html"):
            self.assertNotIn("patreon.com", page.read_text().lower(), page)

    def test_first_run_does_not_claim_to_download_a_model(self):
        pages = "\n".join(
            (SITE / name).read_text()
            for name in ("index.html", "features.html", "download.html")
        )
        self.assertNotIn("downloading the AI model", pages)
        self.assertNotIn("sets up local AI", pages)
        self.assertIn("No model is downloaded until you choose one.", pages)

    def test_project_evidence_is_publicly_linked(self):
        community = (SITE / "community.html").read_text()
        for path in ("docs/roadmap.md", "docs/objectives.md", "SECURITY.md"):
            self.assertIn(path, community)

    def test_optional_setup_explains_git_identity(self):
        features = (SITE / "features.html").read_text()
        self.assertIn("You decide what gets set up", features)
        self.assertIn("Git needs them to label commits", features)
        self.assertIn("Noctra remembers the choice", features)

    def test_alpha_bar_describes_risk_without_promising_breakage(self):
        for page in SITE.glob("*.html"):
            text = page.read_text()
            self.assertNotIn("expect things to break", text, page)
            self.assertIn("Under active development.", text, page)


if __name__ == "__main__":
    unittest.main()
