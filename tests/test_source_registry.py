"""Checks for the supplied source directory and its conservative import rules."""

from __future__ import annotations

import importlib.util
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_source_registry", ROOT / "scripts" / "build_source_registry.py"
)
assert SPEC and SPEC.loader
registry_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(registry_module)


class SourceRegistryTests(unittest.TestCase):
    def test_safe_url_normalization_preserves_distinct_destinations(self) -> None:
        normalize = registry_module.normalize_url
        self.assertEqual(normalize("HTTPS://Example.COM:443/"), "https://example.com")
        self.assertEqual(normalize("http://Example.COM:80/"), "http://example.com")
        self.assertEqual(
            normalize("https://EXAMPLE.com/Apply/?Ref=Job"),
            "https://example.com/Apply/?Ref=Job",
        )
        self.assertNotEqual(
            normalize("https://example.com/Apply"), normalize("https://example.com/apply")
        )
        self.assertNotEqual(
            normalize("https://example.com/apply"), normalize("https://example.com/apply/")
        )
        self.assertNotEqual(
            normalize("https://example.com/?ref=A"), normalize("https://example.com/?ref=a")
        )
        self.assertNotEqual(
            normalize("https://www.example.com"), normalize("https://example.com")
        )
        with self.assertRaises(ValueError):
            normalize("file:///etc/passwd")
        with self.assertRaises(ValueError):
            normalize("https://user:secret@example.com/")

    def test_workbook_rows_are_preserved_under_unique_urls(self) -> None:
        registry = registry_module.build_registry(registry_module.WORKBOOK)
        self.assertEqual(registry["row_count"], 393)
        self.assertEqual(registry["source_count"], 169)
        sources = registry["sources"]
        self.assertEqual(len(sources), len({source["url"] for source in sources}))

        references = [row for source in sources for row in source["source_rows"]]
        self.assertEqual(len(references), 393)
        self.assertEqual([row["row"] for row in references[:3]], [2, 3, 4])
        self.assertEqual({row["row"] for row in references}, set(range(2, 395)))
        self.assertEqual(
            Counter(row["original_category"] for row in references),
            Counter({"fb group": 250, "platforms": 92, "agency": 29, "subreddit": 21, "": 1}),
        )

        contra = next(source for source in sources if source["url"] == "https://contra.com")
        self.assertEqual(
            [(row["row"], row["original_url"]) for row in contra["source_rows"]],
            [(4, "https://contra.com"), (347, "https://contra.com/")],
        )
        bravo = next(source for source in sources if source["url"] == "https://bravovirtualassistants.com")
        self.assertEqual(bravo["category"], "unclassified")
        self.assertEqual(bravo["source_rows"][0]["original_category"], "")

    def test_registry_grants_no_collection_or_contact_authority(self) -> None:
        registry = registry_module.build_registry(registry_module.WORKBOOK)
        for source in registry["sources"]:
            self.assertIs(source["enabled"], False)
            self.assertEqual(source["access_method"], "manual_review")
            self.assertEqual(
                set(source),
                {"url", "name", "category", "access_method", "enabled", "source_rows"},
            )
            for row in source["source_rows"]:
                self.assertEqual(
                    set(row),
                    {"sheet", "row", "name", "original_url", "original_category"},
                )


if __name__ == "__main__":
    unittest.main()
