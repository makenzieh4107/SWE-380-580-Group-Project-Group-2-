import sys
import unittest
from pathlib import Path

import pandas as pd

# Allow the project source directory to be imported when the test is executed
# from the Automated Test folder rather than the repository root.
ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from compare_extended import count_severity_records, make_summary


class TestCompareExtendedSummary(unittest.TestCase):
    # Verify that semicolon-delimited severities are counted correctly even when
    # multiple labels appear in a single cell.
    def test_count_severity_records_matches_semicolon_delimited_severity_values(self):
        # Build a small frame that mirrors how severity lists are stored in the
        # comparison output: a single string containing multiple severity names.
        pair_results = pd.DataFrame({
            "baseline_severities": [
                "HIGH; MEDIUM",
                "INFO; LOW",
                "CRITICAL",
                "",
            ],
            "variant_severities": [
                "LOW",
                "MEDIUM",
                "HIGH",
                "INFO",
            ],
        })

        self.assertEqual(count_severity_records(pair_results, "baseline_severities", "HIGH"), 1)
        self.assertEqual(count_severity_records(pair_results, "baseline_severities", "LOW"), 1)
        self.assertEqual(count_severity_records(pair_results, "variant_severities", "MEDIUM"), 1)
        self.assertEqual(count_severity_records(pair_results, "baseline_severities", "CRITICAL"), 1)
        self.assertEqual(count_severity_records(pair_results, "baseline_severities", "INFO"), 1)

    def test_make_summary_counts_paired_outcomes_and_unique_content_versions(self):
        # Check that the summary aggregates pair-level outcomes and unique
        # content-version totals without double-counting repeated SHA values.
        pair_results = pd.DataFrame(
            [
                {
                    "name": "alpha",
                    "similarity": "90",
                    "baseline_repo": "repo-a",
                    "baseline_path": "alpha.md",
                    "baseline_sha": "sha_a",
                    "baseline_findings_count": 3,
                    "baseline_categories": "X",
                    "baseline_severities": "HIGH; LOW",
                    "variant_repo": "repo-b",
                    "variant_path": "beta.md",
                    "variant_sha": "sha_b",
                    "variant_findings_count": 5,
                    "variant_categories": "Y",
                    "variant_severities": "HIGH",
                    "pair_outcome": "more findings in variant",
                },
                {
                    "name": "beta",
                    "similarity": "95",
                    "baseline_repo": "repo-a",
                    "baseline_path": "gamma.md",
                    "baseline_sha": "sha_c",
                    "baseline_findings_count": 1,
                    "baseline_categories": "Z",
                    "baseline_severities": "INFO",
                    "variant_repo": "repo-b",
                    "variant_path": "delta.md",
                    "variant_sha": "sha_d",
                    "variant_findings_count": 1,
                    "variant_categories": "Z",
                    "variant_severities": "INFO",
                    "pair_outcome": "same finding count",
                },
            ]
        )

        scans = pd.DataFrame(
            [
                {"file_sha": "sha_a", "scan_status": "completed", "findings_count": 3, "categories": "X", "severities": "HIGH; LOW"},
                {"file_sha": "sha_b", "scan_status": "completed", "findings_count": 5, "categories": "Y", "severities": "HIGH"},
                {"file_sha": "sha_c", "scan_status": "completed", "findings_count": 1, "categories": "Z", "severities": "INFO"},
                {"file_sha": "sha_d", "scan_status": "completed", "findings_count": 1, "categories": "Z", "severities": "INFO"},
            ]
        )

        summary = make_summary(pair_results, scans)

        # Paired outcomes should count each baseline/variant comparison once, even
        # when the same content is reused elsewhere in the dataset.
        outcome_rows = summary[summary["measure"] == "paired_outcome"]
        self.assertEqual(
            outcome_rows[outcome_rows["group"] == "more findings in variant"]["records"].iat[0],
            1,
        )
        self.assertEqual(
            outcome_rows[outcome_rows["group"] == "same finding count"]["records"].iat[0],
            1,
        )

        # The unique-content summary should show the number of distinct SHA-based
        # versions, not the raw number of pair records that reference them.
        unique_rows = summary[summary["measure"] == "unique_content_versions"]
        self.assertEqual(unique_rows[unique_rows["group"] == "baseline"]["records"].iat[0], 2)
        self.assertEqual(unique_rows[unique_rows["group"] == "variant"]["records"].iat[0], 2)


if __name__ == "__main__":
    unittest.main()
