"""
Scan GitSkills artifacts with Cisco AI Defense Skill Scanner.

Research purpose:
Compare security scanner findings across exact duplicates and
related/sibling artifacts to investigate whether changes between
related skills are associated with different security findings.

Outputs:
    results/cisco_all_scan_reports.json (all raw scan reports and metadata)
    results/cisco_scan_results.csv
    results/cisco_duplicate_group_comparison.csv
    results/cisco_sibling_group_comparison.csv
    results/cisco_scan_errors.csv

Safety:
    - The database is attached read-only.
    - Skill instructions are written to temporary Markdown files.
    - Skill instructions are never executed by this script.
    - Only the scanner process is executed.
"""

import csv
import hashlib
import json
import shutil
import subprocess
import tempfile

from collections import defaultdict
from pathlib import Path

import duckdb


# ============================================================
# 1. Configuration
# ============================================================

DB_PATH = Path("data/agent_skills_sample.db")

RESULTS_DIR = Path("results")
ALL_REPORTS_JSON = RESULTS_DIR / "cisco_all_scan_reports.json"

ARTIFACT_RESULTS_CSV = RESULTS_DIR / "cisco_scan_results.csv"
DUPLICATE_GROUPS_CSV = (
    RESULTS_DIR / "cisco_duplicate_group_comparison.csv"
)
SIBLING_GROUPS_CSV = (
    RESULTS_DIR / "cisco_sibling_group_comparison.csv"
)
ERRORS_CSV = RESULTS_DIR / "cisco_scan_errors.csv"

# None means scan every eligible artifact.
# For a quick test, temporarily change this to 10 or 25.
MAX_ARTIFACTS = 1000

# Reuse valid JSON reports from earlier runs.
USE_REPORT_CACHE = True

# Scanner CLI arguments from the current project setup.
SCANNER_ARGUMENTS = [
    "--lenient",
    "--format",
    "json",
]


# ============================================================
# 2. General helper functions
# ============================================================

# Output helper: write result dictionaries to CSV with a fixed column order.
def write_csv(file_path, rows, columns):
    """Write dictionaries to a CSV file."""

    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


# Normalize optional database values so missing values and strings are handled consistently.
def normalize_value(value):
    """Convert a database value into a comparable string."""

    if value is None:
        return None

    return str(value).strip()


# Hash the actual Markdown text; useful when the dataset SHA is missing or differs.
def calculate_content_hash(content):
    """Calculate a stable SHA-256 hash for skill content."""

    return hashlib.sha256(
        content.encode("utf-8", errors="replace")
    ).hexdigest()


# Give each loaded row a run-local key so sibling links can refer to loaded artifacts.
def make_artifact_key(index, row):
    """Create a stable identifier for an artifact in this run."""

    return f"artifact_{index}"


# ============================================================
# 3. Load artifacts from GitSkills using DuckDB
# ============================================================

# Database-loading stage: inspect the schema, load eligible Markdown rows, and read sibling links.
def load_artifacts():
    """
    Load artifact metadata and content from the read-only database.

    The database schema is inspected rather than assuming every
    possible optional field exists.
    """

    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH.resolve()}\n"
            "Run this script from the repository root."
        )

    connection = duckdb.connect(":memory:")

    try:
        db_path = (
            DB_PATH.resolve()
            .as_posix()
            .replace("'", "''")
        )

        connection.execute(
            f"ATTACH '{db_path}' AS GitSkills (READ_ONLY)"
        )

        table_names = [
            row[0]
            for row in connection.execute(
                "SHOW TABLES FROM GitSkills"
            ).fetchall()
        ]

        if "artifacts" not in table_names:
            raise RuntimeError(
                "The GitSkills database has no artifacts table."
            )

        # Inspect available columns first because dataset versions may not expose identical fields.
        # Use the real schema so optional fields can be handled safely.
        schema_rows = connection.execute(
            "DESCRIBE SELECT * FROM GitSkills.artifacts"
        ).fetchall()

        available_columns = {
            row[0] for row in schema_rows
        }

        required_columns = {"content", "path"}
        missing = required_columns - available_columns

        if missing:
            raise RuntimeError(
                f"Missing required artifacts columns: {sorted(missing)}"
            )

        desired_columns = [
            "repo_full_name",
            "path",
            "filename",
            "content",
            "file_sha",
            "name",
            "description",
            "first_commit_at",
            "last_commit_at",
            "commit_count",
            "dedup_primary",
        ]

        selected_columns = [
            column
            for column in desired_columns
            if column in available_columns
        ]

        # Quote column names to avoid SQL identifier issues.
        column_sql = ", ".join(
            '"' + column.replace('"', '""') + '"'
            for column in selected_columns
        )

        # Keep only artifacts with usable Markdown content for scanning.
        query = f"""
            SELECT {column_sql}
            FROM GitSkills.artifacts
            WHERE content IS NOT NULL
              AND trim(content) <> ''
              AND lower(path) LIKE '%.md'
        """

        if "dedup_primary" in available_columns:
            query += """
                ORDER BY
                    CASE WHEN dedup_primary = 1 THEN 0 ELSE 1 END,
                    path
            """

        if MAX_ARTIFACTS is not None:
            query += f" LIMIT {int(MAX_ARTIFACTS)}"

        result = connection.execute(query)

        rows = result.fetchall()
        columns = [description[0] for description in result.description]

        artifacts = []

        for index, values in enumerate(rows):
            row = dict(zip(columns, values))

            content = str(row["content"])
            original_sha = normalize_value(row.get("file_sha"))

            # If file_sha is missing, use a calculated content hash.
            # This fallback is marked separately in the output.
            # Store both the dataset-provided SHA and a hash of the content for traceability.
            content_hash = calculate_content_hash(content)

            artifact = {
                "artifact_key": make_artifact_key(index, row),
                "repo_full_name": row.get("repo_full_name"),
                "path": row.get("path"),
                "filename": row.get("filename"),
                "name": row.get("name"),
                "description": row.get("description"),
                "first_commit_at": row.get("first_commit_at"),
                "last_commit_at": row.get("last_commit_at"),
                "commit_count": row.get("commit_count"),
                "dedup_primary": row.get("dedup_primary"),
                "file_sha": original_sha,
                "content_hash": content_hash,
                "effective_hash": original_sha or content_hash,
                "hash_source": (
                    "file_sha"
                    if original_sha
                    else "calculated_content_hash"
                ),
                "content": content,
            }

            artifacts.append(artifact)

        # Load relationship records separately for later comparisons of related artifacts.
        # Read the sibling relation table, if available.
        sibling_rows = []
        sibling_columns = []

        if "artifact_siblings" in table_names:
            sibling_result = connection.execute(
                "SELECT * FROM GitSkills.artifact_siblings"
            )
            sibling_rows = sibling_result.fetchall()
            sibling_columns = [
                description[0]
                for description in sibling_result.description
            ]

        return artifacts, sibling_rows, sibling_columns

    finally:
        connection.close()


# ============================================================
# 4. Discover sibling relationships
# ============================================================

# Relationship stage: combine artifacts connected by recognizable sibling links.
def build_sibling_groups(artifacts, sibling_rows, sibling_columns):
    """
    Build connected groups from recognizable artifact_siblings links.

    The function looks for relationship endpoint columns and matches
    their values against artifact identifiers, paths, and hashes.

    If the table uses an unrecognized schema, exact file_sha grouping
    still works, but sibling grouping may be incomplete.
    """

    parent = {
        artifact["artifact_key"]: artifact["artifact_key"]
        for artifact in artifacts
    }

    # Find a component representative and compress paths for faster future lookups.
    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    # Join two components when a relationship row identifies both artifacts.
    def union(first, second):
        root_first = find(first)
        root_second = find(second)

        if root_first != root_second:
            parent[root_second] = root_first

    # Map recognizable IDs, paths, and hashes to the loaded artifact keys.
    # Build a lookup for known artifact identifiers.
    identity_lookup = defaultdict(set)

    identity_columns = {
        "id",
        "artifact_id",
        "artifactid",
        "artifact_uuid",
        "path",
        "artifact_path",
        "file_sha",
        "sha",
        "sha256",
        "content_hash",
        "file_hash",
    }

    for artifact in artifacts:
        for field, value in artifact.items():
            if value is None or field == "content":
                continue

            normalized_field = field.lower()

            is_identity = (
                normalized_field in identity_columns
                or (
                    "artifact" in normalized_field
                    and any(
                        token in normalized_field
                        for token in ("id", "path", "sha", "hash")
                    )
                )
            )

            if is_identity:
                identity_lookup[str(value).strip()].add(
                    artifact["artifact_key"]
                )

    # Relationship schemas can vary, so identify likely endpoint columns from their names.
    # Identify columns that appear to represent relationship endpoints.
    endpoint_columns = []

    endpoint_words = (
        "artifact",
        "sibling",
        "source",
        "target",
        "parent",
        "child",
        "left",
        "right",
        "from",
        "to",
    )

    for column in sibling_columns:
        lowered = column.lower()

        looks_like_endpoint = (
            any(word in lowered for word in endpoint_words)
            and any(
                token in lowered
                for token in ("id", "path", "sha", "hash")
            )
        )

        if looks_like_endpoint:
            endpoint_columns.append(column)

    # Each relationship row can connect two or more loaded artifacts into one group.
    # Join endpoints within each sibling relationship row.
    for values in sibling_rows:
        relation = dict(zip(sibling_columns, values))
        matched_artifacts = set()

        for column in endpoint_columns:
            value = relation.get(column)

            if value is None:
                continue

            matches = identity_lookup.get(str(value).strip(), set())
            matched_artifacts.update(matches)

        matched_artifacts = list(matched_artifacts)

        if len(matched_artifacts) >= 2:
            first = matched_artifacts[0]

            for other in matched_artifacts[1:]:
                union(first, other)

    groups = defaultdict(list)

    for artifact in artifacts:
        root = find(artifact["artifact_key"])
        groups[root].append(artifact["artifact_key"])

    # Keep only components containing more than one artifact.
    return [
        members
        for members in groups.values()
        if len(members) > 1
    ]


# ============================================================
# 5. Extract finding information from scanner JSON
# ============================================================

FINDING_LIST_KEYS = {
    "findings",
    "issues",
    "vulnerabilities",
    "detections",
    "alerts",
}


# Report parsing stage: tolerate common JSON layouts while retaining raw reports for review.
def extract_findings(report):
    """
    Extract finding objects from common JSON report layouts.

    The raw JSON report is retained separately so this extraction
    can be reviewed against the scanner's actual output format.
    """

    if not isinstance(report, (dict, list)):
        return []

    found_lists = []

    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = key.lower().replace("-", "_")

                if (
                    normalized in FINDING_LIST_KEYS
                    and isinstance(child, list)
                ):
                    found_lists.append(child)
                else:
                    visit(child)

        elif isinstance(value, list):
            for child in value:
                if isinstance(child, (dict, list)):
                    visit(child)

    visit(report)

    # Use the first non-empty recognized list to avoid double counting
    # the same findings if the report contains duplicated summaries.
    for items in found_lists:
        if items:
            return items

    return []


# Extract a useful field from one finding without assuming a single scanner schema.
def value_from_finding(finding, candidate_keys):
    """Find the first matching field in a finding object."""

    if not isinstance(finding, dict):
        return ""

    normalized = {
        str(key).lower().replace("-", "_"): value
        for key, value in finding.items()
    }

    for key in candidate_keys:
        value = normalized.get(key)

        if value is not None:
            if isinstance(value, (str, int, float, bool)):
                return str(value)

            return json.dumps(value, ensure_ascii=False)

    return ""


# Convert detailed scanner JSON into a compact summary for CSVs and group comparisons.
def summarize_report(report):
    """Create a compact summary without assuming one report schema."""

    findings = extract_findings(report)

    categories = set()
    severities = set()
    signatures = set()

    for finding in findings:
        category = value_from_finding(
            finding,
            ["category", "rule_category", "type", "rule_id"],
        )
        severity = value_from_finding(
            finding,
            ["severity", "level", "risk"],
        )
        rule = value_from_finding(
            finding,
            ["rule_id", "rule", "title", "name", "id"],
        )

        if category:
            categories.add(category)

        if severity:
            severities.add(severity)

        # Used to compare scanner results between related artifacts.
        signatures.add(
            "|".join([category, severity, rule])
        )

    return {
        "findings_count": len(findings),
        "categories": "; ".join(sorted(categories)),
        "severities": "; ".join(sorted(severities)),
        "finding_signatures": signatures,
        "findings": findings,
    }


# ============================================================
# 6. Scan one unique skill content
# ============================================================

# Scanner stage: reuse a cached report when possible; otherwise scan a temporary SKILL.md.
def scan_unique_skill(artifact, scanner_path, cached_scans):
    """
    Scan one unique content hash.

    Raw reports are kept in memory and later written together to one
    consolidated JSON file. The scanner's temporary report is deleted
    automatically with its temporary directory.
    """

    content_hash = artifact["content_hash"]

    if USE_REPORT_CACHE and content_hash in cached_scans:
        cached_entry = cached_scans[content_hash]
        cached_report = cached_entry.get("report", {})

        if isinstance(cached_report, (dict, list)):
            summary = summarize_report(cached_report)
            return {
                "status": "cached",
                "exit_code": cached_entry.get("scanner_exit_code", ""),
                "report_path": str(ALL_REPORTS_JSON),
                "report": cached_report,
                **summary,
            }

    with tempfile.TemporaryDirectory(
        prefix="gitskills_cisco_"
    ) as temporary_directory:

        temporary_directory = Path(temporary_directory)
        skill_directory = temporary_directory / "test_skill"
        skill_directory.mkdir(parents=True, exist_ok=True)
        temporary_report_path = temporary_directory / "scanner_report.json"

        skill_file = skill_directory / "SKILL.md"
        skill_file.write_text(
            artifact["content"],
            encoding="utf-8",
            errors="replace",
        )

        command = [
            scanner_path,
            "scan",
            str(skill_directory),
            *SCANNER_ARGUMENTS,
            "--output-json",
            str(temporary_report_path),
        ]

        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )

        except OSError as error:
            return {
                "status": "scanner_start_error",
                "exit_code": "",
                "report_path": str(ALL_REPORTS_JSON),
                "report": {},
                "findings_count": 0,
                "categories": "",
                "severities": "",
                "finding_signatures": set(),
                "findings": [],
                "error": str(error),
            }

        if temporary_report_path.exists():
            try:
                report = json.loads(
                    temporary_report_path.read_text(encoding="utf-8")
                )
                summary = summarize_report(report)
                status = (
                    "completed"
                    if process.returncode == 0
                    else "report_created_nonzero_exit"
                )

                return {
                    "status": status,
                    "exit_code": process.returncode,
                    "report_path": str(ALL_REPORTS_JSON),
                    "report": report,
                    "stdout": process.stdout,
                    "stderr": process.stderr,
                    **summary,
                }

            except (json.JSONDecodeError, OSError) as error:
                return {
                    "status": "invalid_json_report",
                    "exit_code": process.returncode,
                    "report_path": str(ALL_REPORTS_JSON),
                    "report": {},
                    "findings_count": 0,
                    "categories": "",
                    "severities": "",
                    "finding_signatures": set(),
                    "findings": [],
                    "error": str(error),
                    "stdout": process.stdout,
                    "stderr": process.stderr,
                }

        return {
            "status": "no_report_created",
            "exit_code": process.returncode,
            "report_path": str(ALL_REPORTS_JSON),
            "report": {},
            "findings_count": 0,
            "categories": "",
            "severities": "",
            "finding_signatures": set(),
            "findings": [],
            "error": (
                process.stderr
                or process.stdout
                or "Scanner did not create a JSON report."
            ),
        }


# ============================================================
# 7. Compare duplicate and sibling groups
# ============================================================

# Comparison stage: summarize scanner findings across exact-duplicate and sibling-related groups.
def compare_groups(artifacts, scan_by_hash, groups, group_type):
    """Summarize finding differences within groups of related artifacts."""

    artifact_by_key = {
        artifact["artifact_key"]: artifact
        for artifact in artifacts
    }

    comparison_rows = []

    for group_number, members in enumerate(groups, start=1):
        group_artifacts = [
            artifact_by_key[key]
            for key in members
        ]

        hashes = {
            artifact["content_hash"]
            for artifact in group_artifacts
        }

        signatures_by_hash = {}
        artifacts_with_findings = 0
        total_findings_across_artifacts = 0

        for artifact in group_artifacts:
            scan = scan_by_hash.get(artifact["content_hash"])

            if not scan:
                continue

            count = scan.get("findings_count", 0)
            total_findings_across_artifacts += count

            if count > 0:
                artifacts_with_findings += 1

            signatures_by_hash[artifact["content_hash"]] = (
                scan.get("finding_signatures", set())
            )

        all_signatures = set()

        for signatures in signatures_by_hash.values():
            all_signatures.update(signatures)

        # Exact duplicates should share content; modified related artifacts can have different hashes.
        # A change in findings is only meaningful when there are
        # distinct content versions to compare.
        if len(hashes) > 1:
            signatures_differ = (
                len({
                    tuple(sorted(signatures))
                    for signatures in signatures_by_hash.values()
                }) > 1
            )
        else:
            signatures_differ = False

        repos = sorted({
            str(artifact.get("repo_full_name") or "")
            for artifact in group_artifacts
        })

        paths = sorted({
            str(artifact.get("path") or "")
            for artifact in group_artifacts
        })

        comparison_rows.append({
            "group_type": group_type,
            "group_id": f"{group_type}_{group_number}",
            "artifact_count": len(group_artifacts),
            "distinct_content_versions": len(hashes),
            "artifacts_with_findings": artifacts_with_findings,
            "total_findings_across_artifacts": (
                total_findings_across_artifacts
            ),
            "distinct_finding_signatures": len(all_signatures),
            "findings_differ_across_versions": signatures_differ,
            "repositories": "; ".join(repos),
            "artifact_paths": "; ".join(paths),
        })

    return comparison_rows


# Human-readable output complements structured CSV summaries and per-artifact JSON reports.
def write_readable_results(artifact_rows, duplicate_rows, sibling_rows, error_rows):
    """Write a readable text summary of all Cisco scanner results."""

    output_path = RESULTS_DIR / "cisco_scan_results.txt"
    lines = [
        "GITSKILLS CISCO AI DEFENSE SCANNER RESULTS",
        "=" * 55,
        "",
        f"Total artifacts: {len(artifact_rows)}",
        f"Exact duplicate groups: {len(duplicate_rows)}",
        f"Sibling groups: {len(sibling_rows)}",
        f"Scan errors: {len(error_rows)}",
        "",
        "ARTIFACT SCAN RESULTS",
        "=" * 55,
    ]

    for number, artifact in enumerate(artifact_rows, start=1):
        lines.extend([
            "",
            f"Artifact {number}",
            "-" * 40,
            f"Repository: {artifact.get('repo_full_name', '')}",
            f"Path: {artifact.get('path', '')}",
            f"Name: {artifact.get('name', '')}",
            f"File SHA: {artifact.get('file_sha', '')}",
            f"Content hash: {artifact.get('content_hash', '')}",
            f"Primary artifact: {artifact.get('dedup_primary', '')}",
            f"Scan status: {artifact.get('scan_status', '')}",
            f"Findings: {artifact.get('findings_count', 0)}",
            f"Categories: {artifact.get('categories', '') or 'None listed'}",
            f"Severities: {artifact.get('severities', '') or 'None listed'}",
            f"Report: {artifact.get('report_path', '')}",
        ])

    lines.extend([
        "",
        "EXACT DUPLICATE GROUP COMPARISONS",
        "=" * 55,
    ])

    for group in duplicate_rows:
        lines.extend([
            "",
            f"Group: {group.get('group_id', '')}",
            f"Artifacts: {group.get('artifact_count', 0)}",
            f"Distinct content versions: {group.get('distinct_content_versions', 0)}",
            f"Artifacts with findings: {group.get('artifacts_with_findings', 0)}",
            f"Total findings across artifacts: {group.get('total_findings_across_artifacts', 0)}",
            f"Findings differ across versions: {group.get('findings_differ_across_versions', False)}",
            f"Repositories: {group.get('repositories', '')}",
            f"Paths: {group.get('artifact_paths', '')}",
        ])

    lines.extend([
        "",
        "SIBLING GROUP COMPARISONS",
        "=" * 55,
    ])

    for group in sibling_rows:
        lines.extend([
            "",
            f"Group: {group.get('group_id', '')}",
            f"Artifacts: {group.get('artifact_count', 0)}",
            f"Distinct content versions: {group.get('distinct_content_versions', 0)}",
            f"Artifacts with findings: {group.get('artifacts_with_findings', 0)}",
            f"Total findings across artifacts: {group.get('total_findings_across_artifacts', 0)}",
            f"Findings differ across versions: {group.get('findings_differ_across_versions', False)}",
            f"Repositories: {group.get('repositories', '')}",
            f"Paths: {group.get('artifact_paths', '')}",
        ])

    lines.extend([
        "",
        "SCAN ERRORS",
        "=" * 55,
    ])

    if not error_rows:
        lines.append("No scan errors were recorded.")
    else:
        for error in error_rows:
            lines.extend([
                "",
                f"Repository: {error.get('repo_full_name', '')}",
                f"Path: {error.get('path', '')}",
                f"Status: {error.get('status', '')}",
                f"Error: {error.get('error', '')}",
            ])

    lines.extend([
        "",
        "RESEARCH NOTES",
        "=" * 55,
        "- Findings are scanner detections, not proof of malicious behavior.",
        "- Different findings across modified versions are candidates for manual review.",
        "- Exact duplicate files share content; this does not prove copy direction.",
        "- Full raw scanner reports are stored together in cisco_all_scan_reports.json.",
        "",
    ])

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Readable text results saved to: {output_path.resolve()}")


# ============================================================
# 8. Main workflow
# ============================================================

# Main orchestration: load records, scan unique content, compare relationships, and write outputs.
def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load the previous consolidated file as a cache, if enabled.
    cached_scans = {}
    if USE_REPORT_CACHE and ALL_REPORTS_JSON.exists():
        try:
            cached_data = json.loads(
                ALL_REPORTS_JSON.read_text(encoding="utf-8")
            )
            cached_scans = cached_data.get("scans", {})
            if not isinstance(cached_scans, dict):
                cached_scans = {}
        except (json.JSONDecodeError, OSError):
            print("Existing consolidated report is unreadable; rescanning.")

    scanner_path = shutil.which("skill-scanner")

    if not scanner_path:
        raise SystemExit(
            "Could not find 'skill-scanner' on PATH.\n"
            "Activate the environment where Cisco Skill Scanner "
            "is installed, then run this script again."
        )

    print("Loading GitSkills artifacts through DuckDB...")

    artifacts, sibling_rows, sibling_columns = load_artifacts()

    if not artifacts:
        raise SystemExit("No non-empty Markdown artifacts were found.")

    print(f"Eligible Markdown artifacts: {len(artifacts)}")
    print(f"Sibling relationship rows: {len(sibling_rows)}")
    print(f"Sibling table columns: {sibling_columns}")

    # Group by GitSkills file_sha to identify records with identical dataset-provided hashes.
    # Build exact duplicate groups using the dataset's file_sha.
    by_file_sha = defaultdict(list)

    for artifact in artifacts:
        if artifact["file_sha"]:
            by_file_sha[artifact["file_sha"]].append(
                artifact["artifact_key"]
            )

    duplicate_groups = [
        members
        for members in by_file_sha.values()
        if len(members) > 1
    ]

    sibling_groups = build_sibling_groups(
        artifacts,
        sibling_rows,
        sibling_columns,
    )

    print(f"Exact duplicate groups: {len(duplicate_groups)}")
    print(f"Recognized sibling groups: {len(sibling_groups)}")

    # Scan one representative for each distinct content hash to reduce redundant scanner work.
    # Scan one instance of each unique content version.
    unique_artifacts = {}
    for artifact in artifacts:
        unique_artifacts.setdefault(
            artifact["content_hash"],
            artifact,
        )

    unique_items = list(unique_artifacts.items())
    scan_by_hash = {}
    error_rows = []

    print(f"\nUnique content versions to scan: {len(unique_items)}")

    for position, (content_hash, artifact) in enumerate(
        unique_items,
        start=1,
    ):
        print(
            f"[{position}/{len(unique_items)}] "
            f"{artifact.get('repo_full_name')} :: "
            f"{artifact.get('path')}"
        )

        scan = scan_unique_skill(artifact, scanner_path, cached_scans)
        scan_by_hash[content_hash] = scan

        if scan["status"] not in ("completed", "cached"):
            if scan["status"] != "report_created_nonzero_exit":
                error_rows.append({
                    "content_hash": content_hash,
                    "repo_full_name": artifact.get("repo_full_name"),
                    "path": artifact.get("path"),
                    "status": scan["status"],
                    "exit_code": scan.get("exit_code", ""),
                    "error": scan.get("error", ""),
                })

        print(
            f"    Status: {scan['status']} | "
            f"Findings: {scan.get('findings_count', 0)}"
        )

    # --------------------------------------------------------
    # 9. Save every raw scan report into one consolidated JSON file
    # --------------------------------------------------------

    consolidated_scans = {}
    for content_hash, artifact in unique_items:
        scan = scan_by_hash.get(content_hash, {})
        consolidated_scans[content_hash] = {
            "content_hash": content_hash,
            "repo_full_name": artifact.get("repo_full_name"),
            "path": artifact.get("path"),
            "name": artifact.get("name"),
            "description": artifact.get("description"),
            "file_sha": artifact.get("file_sha"),
            "scan_status": scan.get("status", "not_scanned"),
            "scanner_exit_code": scan.get("exit_code", ""),
            "findings_count": scan.get("findings_count", 0),
            "categories": scan.get("categories", ""),
            "severities": scan.get("severities", ""),
            "error": scan.get("error", ""),
            "report": scan.get("report", {}),
        }

    ALL_REPORTS_JSON.write_text(
        json.dumps(
            {
                "description": (
                    "Consolidated Cisco Skill Scanner output. "
                    "Each key in scans is a unique skill content SHA-256."
                ),
                "unique_content_versions": len(unique_items),
                "scans": consolidated_scans,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"All raw scan reports saved together to: {ALL_REPORTS_JSON.resolve()}")

    # --------------------------------------------------------
    # 10. One output row per dataset artifact
    # --------------------------------------------------------

    artifact_result_rows = []

    for artifact in artifacts:
        scan = scan_by_hash.get(artifact["content_hash"], {})

        artifact_result_rows.append({
            "artifact_key": artifact["artifact_key"],
            "repo_full_name": artifact.get("repo_full_name"),
            "path": artifact.get("path"),
            "name": artifact.get("name"),
            "description": artifact.get("description"),
            "file_sha": artifact.get("file_sha"),
            "content_hash": artifact["content_hash"],
            "hash_source": artifact["hash_source"],
            "dedup_primary": artifact.get("dedup_primary"),
            "first_commit_at": artifact.get("first_commit_at"),
            "last_commit_at": artifact.get("last_commit_at"),
            "commit_count": artifact.get("commit_count"),
            "scan_status": scan.get("status", "not_scanned"),
            "scanner_exit_code": scan.get("exit_code", ""),
            "findings_count": scan.get("findings_count", 0),
            "categories": scan.get("categories", ""),
            "severities": scan.get("severities", ""),
            "report_path": scan.get("report_path", ""),
        })

    write_csv(
        ARTIFACT_RESULTS_CSV,
        artifact_result_rows,
        [
            "artifact_key",
            "repo_full_name",
            "path",
            "name",
            "description",
            "file_sha",
            "content_hash",
            "hash_source",
            "dedup_primary",
            "first_commit_at",
            "last_commit_at",
            "commit_count",
            "scan_status",
            "scanner_exit_code",
            "findings_count",
            "categories",
            "severities",
            "report_path",
        ],
    )

    # --------------------------------------------------------
    # 11. Compare duplicate groups and sibling groups
    # --------------------------------------------------------

    duplicate_comparisons = compare_groups(
        artifacts,
        scan_by_hash,
        duplicate_groups,
        "file_sha_duplicate",
    )

    sibling_comparisons = compare_groups(
        artifacts,
        scan_by_hash,
        sibling_groups,
        "artifact_siblings",
    )

    comparison_columns = [
        "group_type",
        "group_id",
        "artifact_count",
        "distinct_content_versions",
        "artifacts_with_findings",
        "total_findings_across_artifacts",
        "distinct_finding_signatures",
        "findings_differ_across_versions",
        "repositories",
        "artifact_paths",
    ]

    write_csv(
        DUPLICATE_GROUPS_CSV,
        duplicate_comparisons,
        comparison_columns,
    )

    write_csv(
        SIBLING_GROUPS_CSV,
        sibling_comparisons,
        comparison_columns,
    )

    write_csv(
        ERRORS_CSV,
        error_rows,
        [
            "content_hash",
            "repo_full_name",
            "path",
            "status",
            "exit_code",
            "error",
        ],
    )

    write_readable_results(
        artifact_result_rows,
        duplicate_comparisons,
        sibling_comparisons,
        error_rows,
    )

    # --------------------------------------------------------
    # 12. Final summary
    # --------------------------------------------------------

    successful = sum(
        1
        for scan in scan_by_hash.values()
        if scan["status"] in (
            "completed",
            "cached",
            "report_created_nonzero_exit",
        )
    )

    total_findings = sum(
        scan.get("findings_count", 0)
        for scan in scan_by_hash.values()
    )



    print("\n" + "=" * 55)
    print("GITSKILLS CISCO SCANNER SUMMARY")
    print("=" * 55)
    print(f"Artifacts represented: {len(artifacts)}")
    print(f"Unique content versions: {len(unique_items)}")
    print(f"Reports available: {successful}")
    print(f"Unique-version findings counted: {total_findings}")
    print(f"Exact duplicate groups: {len(duplicate_groups)}")
    print(f"Recognized sibling groups: {len(sibling_groups)}")
    print(f"Errors: {len(error_rows)}")
    print("\nOutput files:")
    print(f"  {ARTIFACT_RESULTS_CSV}")
    print(f"  {DUPLICATE_GROUPS_CSV}")
    print(f"  {SIBLING_GROUPS_CSV}")
    print(f"  {ERRORS_CSV}")
    print(f"  {ALL_REPORTS_JSON}")


if __name__ == "__main__":
    main()
