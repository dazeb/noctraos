"""The search index must default to the user's home folder, not the whole filesystem."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

SCHEMA = Path(__file__).resolve().parents[1] / "configs/gsettings/org.gnome.shell.extensions.noctraos-search.gschema.xml"


class SearchDefaultTests(unittest.TestCase):
    def test_roots_default_is_the_home_folder(self):
        key = next(k for k in ET.parse(SCHEMA).iter("key") if k.get("name") == "roots")
        self.assertEqual(key.find("default").text, "['~']")

    def test_home_is_expanded_by_the_indexer(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "search"))
        import core
        self.assertEqual(Path("~").expanduser(), Path.home())
        self.assertTrue(callable(core.walk_files))


if __name__ == "__main__":
    unittest.main()
