"""
Security-Sensitive Capability Analysis for the GitSkills Dataset

This script connects to the approved GitSkills sample database and analyzes
unique skill contents for indicators of potentially security-sensitive
capabilities. It examines GitSkills-designated primary artifacts to:

1. Retrieve the artifact content and source fields needed for analysis,
   including repository name, artifact path, file SHA, skill name,
   description, and available commit timestamps.
2. Select artifacts where dedup_primary = 1 so that each distinct file
   content is scanned once rather than repeatedly scanning identical copies.
3. Scan artifact content for predefined text patterns associated with command
   execution, file-system access, and network access.
4. Record each detected pattern with its capability category, matched text,
   line number, evidence, and surrounding context.
5. Preserve the source metadata needed to trace every detection back to its
   corresponding GitSkills artifact.
6. Count the number of unique artifacts associated with each capability
   category and calculate their percentages among all scanned artifacts.
7. Produce detailed and summary output files that can support subsequent
   manual validation.(results are written to the results/ directory in the project root)

The results provide an initial screening of security-sensitive capability
indicators in unique GitSkills content. A detected pattern is treated as a
potential capability indicator, not as proof that an artifact is vulnerable,
malicious, over-privileged, or unnecessary. Matches may occur in actionable
instructions, code examples, warnings, or descriptive text and therefore
require manual review.

This stage identifies capabilities already present in artifact contents. It
does not by itself determine whether a capability was newly introduced by a
modified version. That determination requires a separate comparison of
related, non-identical artifacts.

The script analyzes all artifact content strictly as untrusted text and does
not execute, evaluate, import, or invoke any commands, scripts, or code
contained within the GitSkills dataset.
"""

from pathlib import Path

import duckdb
import pandas as pd

from capability_detector import detect_capabilities


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "agent_skills_sample.db"
RESULTS_DIR = PROJECT_ROOT / "results"

DETECTIONS_PATH = RESULTS_DIR / "capability_detections.csv"
SUMMARY_PATH = RESULTS_DIR / "capability_summary.csv"


def load_unique_artifacts() -> pd.DataFrame:
    """Load one GitSkills-designated representative per unique content hash."""

    if not DB_PATH.is_file():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    connection = duckdb.connect(str(DB_PATH), read_only=True)

    try:
        return connection.execute(
            """
            SELECT
                repo_full_name,
                path,
                file_sha,
                name,
                description,
                first_commit_at,
                last_commit_at,
                content
            FROM artifacts
            WHERE dedup_primary = 1
              AND file_sha IS NOT NULL
              AND content IS NOT NULL
            ORDER BY file_sha, repo_full_name, path
            """
        ).fetchdf()
    finally:
        connection.close()


def scan_artifacts(artifacts: pd.DataFrame) -> pd.DataFrame:
    """Run text-pattern detection and return one row per pattern match."""

    rows: list[dict] = []

    for artifact in artifacts.to_dict("records"):
        findings = detect_capabilities(artifact["content"])

        for finding in findings:
            rows.append(
                {
                    "repo_full_name": artifact["repo_full_name"],
                    "path": artifact["path"],
                    "file_sha": artifact["file_sha"],
                    "name": artifact["name"],
                    "description": artifact["description"],
                    "first_commit_at": artifact["first_commit_at"],
                    "last_commit_at": artifact["last_commit_at"],
                    "capability_category": finding.category,
                    "matched_pattern": finding.matched_pattern,
                    "matched_text": finding.matched_text,
                    "line_number": finding.line_number,
                    "evidence": finding.evidence,
                }
            )

    columns = [
        "repo_full_name",
        "path",
        "file_sha",
        "name",
        "description",
        "first_commit_at",
        "last_commit_at",
        "capability_category",
        "matched_pattern",
        "matched_text",
        "line_number",
        "evidence",
    ]

    return pd.DataFrame(rows, columns=columns)


def build_summary(
    artifacts: pd.DataFrame,
    detections: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize unique artifacts detected in each capability category."""

    total_artifacts = len(artifacts)

    if detections.empty:
        return pd.DataFrame(
            columns=[
                "capability_category",
                "unique_artifacts",
                "percentage_of_scanned_artifacts",
            ]
        )

    unique_categories = detections.drop_duplicates(
        subset=["file_sha", "capability_category"]
    )

    summary = (
        unique_categories.groupby("capability_category")["file_sha"]
        .nunique()
        .rename("unique_artifacts")
        .reset_index()
    )

    summary["percentage_of_scanned_artifacts"] = (
        summary["unique_artifacts"] / total_artifacts * 100
    ).round(2)

    return summary.sort_values("capability_category")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    artifacts = load_unique_artifacts()
    detections = scan_artifacts(artifacts)
    summary = build_summary(artifacts, detections)

    detections.to_csv(DETECTIONS_PATH, index=False)
    summary.to_csv(SUMMARY_PATH, index=False)

    unique_detected = (
        detections["file_sha"].nunique()
        if not detections.empty
        else 0
    )

    print("=" * 70)
    print("CAPABILITY ANALYSIS")
    print("=" * 70)
    print(f"Unique artifacts scanned: {len(artifacts)}")
    print(f"Unique artifacts flagged: {unique_detected}")
    print(f"Total pattern matches: {len(detections)}")

    print("\nSummary:")
    if summary.empty:
        print("No detections found.")
    else:
        print(summary.to_string(index=False))

    print(f"\nDetailed results: {DETECTIONS_PATH}")
    print(f"Summary results:  {SUMMARY_PATH}")


if __name__ == "__main__":
    main()