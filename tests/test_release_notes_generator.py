import pathlib
import sys
import unittest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.generate_release_notes_document import (  # noqa: E402
    build_release_notes_soql,
    render_release_notes_markdown,
)


class BuildReleaseNotesSoqlTests(unittest.TestCase):
    def test_build_query_with_account_filter(self) -> None:
        soql = build_release_notes_soql(
            "Spring 2026",
            "001ABC123",
            release_note_object="Release_Note__c",
            release_lookup_field="Release__r.Name",
            account_field="Account__c",
            name_field="Name",
            details_field="Details__c",
        )

        expected = (
            "SELECT Name, Details__c FROM Release_Note__c "
            "WHERE Release__r.Name = 'Spring 2026' "
            "AND (Account__c = null OR Account__c = '001ABC123') "
            "ORDER BY Name"
        )
        self.assertEqual(soql, expected)

    def test_build_query_without_account_filter(self) -> None:
        soql = build_release_notes_soql(
            "Spring 2026",
            None,
            release_note_object="Release_Note__c",
            release_lookup_field="Release__r.Name",
            account_field="Account__c",
            name_field="Name",
            details_field="Details__c",
        )

        expected = (
            "SELECT Name, Details__c FROM Release_Note__c "
            "WHERE Release__r.Name = 'Spring 2026' "
            "AND Account__c = null "
            "ORDER BY Name"
        )
        self.assertEqual(soql, expected)


class RenderReleaseNotesMarkdownTests(unittest.TestCase):
    def test_renders_records_with_name_and_details(self) -> None:
        output = render_release_notes_markdown(
            "Spring 2026",
            "001ABC123",
            [
                {"Name": "Feature A", "Details__c": "Details A"},
                {"Name": "Feature B", "Details__c": "Details B"},
            ],
            name_field="Name",
            details_field="Details__c",
        )

        self.assertIn("# Release Notes - Spring 2026", output)
        self.assertIn("## 1. Feature A", output)
        self.assertIn("Details A", output)
        self.assertIn("## 2. Feature B", output)
        self.assertIn("Details B", output)

    def test_renders_empty_message_when_no_records(self) -> None:
        output = render_release_notes_markdown(
            "Spring 2026",
            None,
            [],
            name_field="Name",
            details_field="Details__c",
        )
        self.assertIn("No release notes matched the selected filters.", output)


if __name__ == "__main__":
    unittest.main()
