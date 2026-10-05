"""Keep the existing-project preflight metadata-only and read-only."""

from pathlib import Path
import re
import unittest


SQL = (Path(__file__).resolve().parents[1] / "db" / "preflight_existing.sql").read_text()


class ExistingProjectPreflightTests(unittest.TestCase):
    def test_executable_part_cannot_mutate_or_read_contact_rows(self) -> None:
        # The aggregate lead-history query is deliberately commented out until
        # the first metadata query shows that the legacy tables are compatible.
        executable = "\n".join(line.split("--", 1)[0] for line in SQL.splitlines())
        without_strings = re.sub(r"'(?:''|[^'])*'", "''", executable)
        self.assertEqual(len([part for part in without_strings.split(";") if part.strip()]), 1)
        self.assertRegex(without_strings, r"(?i)^\s*with\b")
        self.assertNotRegex(
            without_strings,
            r"(?i)\b(create|alter|drop|insert|update|delete|truncate|grant|"
            r"revoke|call|do|execute|copy|merge)\b",
        )
        self.assertNotRegex(
            without_strings,
            r"(?i)\b(from|join)\s+public\.(cold_leads|cold_campaigns)\b",
        )


if __name__ == "__main__":
    unittest.main()
