from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_REAL_ARCHIVE_GUIDES = (
    ROOT / "README.md",
    ROOT / "docs" / "A0_REAL_ARCHIVE_GATE.md",
)


class PublicDocumentationPrivacyTests(unittest.TestCase):
    def test_real_archive_cli_examples_use_neutral_identifiers(self) -> None:
        target_examples = 0
        conversation_id_examples = 0

        for path in PUBLIC_REAL_ARCHIVE_GUIDES:
            text = path.read_text(encoding="utf-8")

            targets = re.findall(r"--target\s+([^\s\\]+)", text)
            target_examples += len(targets)
            for value in targets:
                self.assertEqual(
                    value,
                    "EXACT_TARGET",
                    f"{path.relative_to(ROOT)} must not publish a concrete real-data target",
                )

            conversation_ids = re.findall(r"--conversation-id\s+([^\s\\]+)", text)
            conversation_id_examples += len(conversation_ids)
            for value in conversation_ids:
                self.assertEqual(
                    value,
                    "CANONICAL_CONVERSATION_ID",
                    f"{path.relative_to(ROOT)} must not publish a concrete canonical conversation ID",
                )

        self.assertGreater(target_examples, 0, "expected at least one documented --target example")
        self.assertGreater(
            conversation_id_examples,
            0,
            "expected at least one documented --conversation-id example",
        )


if __name__ == "__main__":
    unittest.main()
