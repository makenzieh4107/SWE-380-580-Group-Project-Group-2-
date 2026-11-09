"""
Scan GitSkills artifacts listed in the 60–97% similarity CSV
with Cisco AI Defense Skill Scanner.

Only baseline and variant artifacts listed in the CSV are eligible
for scanning. One scan is performed per unique content hash.
Completed reports are cached immediately and reused after cancellation.

Outputs:
    results/cisco_all_scan_reports.json
    results/cisco_scan_results.csv
    results/cisco_duplicate_group_comparison.csv
    results/cisco_sibling_group_comparison.csv
    results/cisco_scan_errors.csv
    results/cisco_scan_results.txt

Safety:
    - The database is attached read-only.
    - Skill instructions are written to temporary Markdown files.
    - Skill instructions are never executed by this script.
    - Only the scanner process is executed.
"""

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
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
PAIR_CSV = Path("charts/name_variant_pairs.csv")

RESULTS_DIR = Path("results/expanded_scan")
ALL_REPORTS_JSON = RESULTS_DIR / "cisco_all_scan_reports.json"

ARTIFACT_RESULTS_CSV = RESULTS_DIR / "cisco_scan_results.csv"
DUPLICATE_GROUPS_CSV = RESULTS_DIR / "cisco_duplicate_group_comparison.csv"
SIBLING_GROUPS_CSV = RESULTS_DIR / "cisco_sibling_group_comparison.csv"
ERRORS_CSV = RESULTS_DIR / "cisco_scan_errors.csv"

# Do not limit database loading. The CSV filter is applied afterward.
MAX_ARTIFACTS = None

# Reuse valid reports for matching content hashes.
USE_REPORT_CACHE = True
# Bound concurrent scanner subprocesses; cache writes stay in the main thread.
MAX_CONCURRENT_SCANS = 2

SCANNER_ARGUMENTS = [
    "--lenient",
    "--format",
    "json",
]

def save_report_cache(cached_scans, metadata=None):
    """Save completed scanner reports immediately."""

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    temporary_path = ALL_REPORTS_JSON.with_suffix(".json.tmp")
    cache_data = {
        "description": (
            "Consolidated Cisco Skill Scanner output "
            "for selected unique content versions."
        ),
        "selected_csv": str(PAIR_CSV),
    }
    if metadata:
        cache_data.update(metadata)
    cache_data["scans"] = cached_scans

    try:
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(
                cache_data,
                file,
                indent=2,
                ensure_ascii=False,
            )

        temporary_path.replace(ALL_REPORTS_JSON)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


# ============================================================
# 2. General helper functions
# ============================================================

def write_csv(file_path, rows, columns):
    """Write result dictionaries to CSV."""

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


def normalize_value(value):
    """Convert optional values into comparable strings."""

    if value is None:
        return None
    return str(value).strip()


def calculate_content_hash(content):
    """Calculate SHA-256 from actual content."""

    return hashlib.sha256(
        content.encode("utf-8", errors="replace")
    ).hexdigest()


def make_artifact_key(index, row):
    """Create a unique identifier for this run."""

    return f"artifact_{index}"


def artifact_identity(artifact):
    """Return the database identity used to match CSV entries."""

    return (
        normalize_value(artifact.get("repo_full_name")),
        normalize_value(artifact.get("path")),
        normalize_value(artifact.get("file_sha")),
    )


# ============================================================
# 3. Load selected pairs from the 60–97% similarity CSV
# ============================================================

def load_selected_pairs():
    """
    Load baseline and variant artifacts explicitly listed in the CSV.

    The CSV must contain:
        baseline_repo, baseline_path, baseline_sha,
        variant_repo, variant_path, variant_sha
    """

    if not PAIR_CSV.exists():
        raise FileNotFoundError(
            f"Pair CSV not found: {PAIR_CSV.resolve()}"
        )

    required_columns = {
        "baseline_repo",
        "baseline_path",
        "baseline_sha",
        "variant_repo",
        "variant_path",
        "variant_sha",
    }

    pairs = []
    selected_keys = set()
    skipped_rows = 0

    with PAIR_CSV.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError("The pair CSV has no header row.")

        reader.fieldnames = [
            column.strip() for column in reader.fieldnames
        ]

        missing_columns = required_columns - set(reader.fieldnames)

        if missing_columns:
            raise ValueError(
                "The pair CSV is missing required columns: "
                f"{sorted(missing_columns)}\n"
                f"Found columns: {reader.fieldnames}"
            )

        for row in reader:
            if not row:
                skipped_rows += 1
                continue

            row = {
                key.strip(): value.strip() if value else ""
                for key, value in row.items()
                if key is not None
            }

            values = [
                row.get(column, "")
                for column in required_columns
            ]

            # Skip incomplete rows and unresolved merge conflicts.
            if (
                not all(values)
                or any(
                    marker in " ".join(values)
                    for marker in (
                        "<<<<<<<",
                        "=======",
                        ">>>>>>>",
                    )
                )
            ):
                skipped_rows += 1
                continue

            pairs.append(row)

            selected_keys.add((
                row["baseline_repo"],
                row["baseline_path"],
                row["baseline_sha"],
            ))

            selected_keys.add((
                row["variant_repo"],
                row["variant_path"],
                row["variant_sha"],
            ))

    if not pairs:
        raise ValueError(
            "No valid pairs were found in the CSV. "
            "Check its headers and remove merge-conflict content."
        )

    print(f"Valid CSV pairs: {len(pairs)}")
    print(f"Unique artifact identities requested: {len(selected_keys)}")

    if skipped_rows:
        print(f"Invalid CSV rows skipped: {skipped_rows}")

    return pairs, selected_keys


# ============================================================
# 4. Load artifacts from GitSkills using DuckDB
# ============================================================

def load_artifacts():
    """Load Markdown artifacts and sibling relationship rows."""

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
            column for column in desired_columns
            if column in available_columns
        ]

        column_sql = ", ".join(
            '"' + column.replace('"', '""') + '"'
            for column in selected_columns
        )

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
        columns = [
            description[0]
            for description in result.description
        ]

        artifacts = []

        for index, values in enumerate(rows):
            row = dict(zip(columns, values))
            content = str(row["content"])
            original_sha = normalize_value(row.get("file_sha"))
            content_hash = calculate_content_hash(content)

            artifacts.append({
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
            })

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
# 5. Discover sibling relationships
# ============================================================

def build_sibling_groups(artifacts, sibling_rows, sibling_columns):
    """Build connected groups from recognizable sibling links."""

    parent = {
        artifact["artifact_key"]: artifact["artifact_key"]
        for artifact in artifacts
    }

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(first, second):
        root_first = find(first)
        root_second = find(second)

        if root_first != root_second:
            parent[root_second] = root_first

    identity_lookup = defaultdict(set)

    identity_columns = {
        "id", "artifact_id", "artifactid", "artifact_uuid",
        "path", "artifact_path", "file_sha", "sha", "sha256",
        "content_hash", "file_hash",
    }

    for artifact in artifacts:
        for field, value in artifact.items():
            if value is None or field == "content":
                continue

            lowered = field.lower()

            is_identity = (
                lowered in identity_columns
                or (
                    "artifact" in lowered
                    and any(
                        token in lowered
                        for token in ("id", "path", "sha", "hash")
                    )
                )
            )

            if is_identity:
                identity_lookup[str(value).strip()].add(
                    artifact["artifact_key"]
                )

    endpoint_columns = []

    endpoint_words = (
        "artifact", "sibling", "source", "target", "parent",
        "child", "left", "right", "from", "to",
    )

    for column in sibling_columns:
        lowered = column.lower()

        if (
            any(word in lowered for word in endpoint_words)
            and any(
                token in lowered
                for token in ("id", "path", "sha", "hash")
            )
        ):
            endpoint_columns.append(column)

    for values in sibling_rows:
        relation = dict(zip(sibling_columns, values))
        matched = set()

        for column in endpoint_columns:
            value = relation.get(column)

            if value is not None:
                matched.update(
                    identity_lookup.get(str(value).strip(), set())
                )

        matched = list(matched)

        if len(matched) >= 2:
            for other in matched[1:]:
                union(matched[0], other)

    groups = defaultdict(list)

    for artifact in artifacts:
        groups[find(artifact["artifact_key"])].append(
            artifact["artifact_key"]
        )

    return [
        members for members in groups.values()
        if len(members) > 1
    ]


# ============================================================
# 6. Parse scanner findings
# ============================================================

FINDING_LIST_KEYS = {
    "findings",
    "issues",
    "vulnerabilities",
    "detections",
    "alerts",
}


def extract_findings(report):
    """Extract finding objects from common JSON report layouts."""

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

    for items in found_lists:
        if items:
            return items

    return []


def value_from_finding(finding, candidate_keys):
    """Find the first matching field in a finding."""

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


def summarize_report(report):
    """Create a compact finding summary."""

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

        signatures.add("|".join([category, severity, rule]))

    return {
        "findings_count": len(findings),
        "categories": "; ".join(sorted(categories)),
        "severities": "; ".join(sorted(severities)),
        "finding_signatures": signatures,
        "findings": findings,
    }


def cached_scan_result(content_hash, cached_scans):
    """Return a normalized result for a reusable cached report."""

    if not USE_REPORT_CACHE or content_hash not in cached_scans:
        return None

    cached_entry = cached_scans[content_hash]
    if not isinstance(cached_entry, dict):
        return None

    cached_report = cached_entry.get("report", {})

    if (
        cached_entry.get("scan_status")
        not in ("completed", "cached", "report_created_nonzero_exit")
        or not isinstance(cached_report, (dict, list))
    ):
        return None

    summary = summarize_report(cached_report)
    return {
        "status": "cached",
        "exit_code": cached_entry.get("scanner_exit_code", ""),
        "report_path": str(ALL_REPORTS_JSON),
        "report": cached_report,
        **summary,
    }


# ============================================================
# 7. Scan one unique skill content
# ============================================================

def scan_unique_skill(artifact, scanner_path, cached_scans):
    """Scan one content hash or reuse its cached report."""

    content_hash = artifact["content_hash"]
    cached_result = cached_scan_result(content_hash, cached_scans)
    if cached_result is not None:
        return cached_result

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
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    if os.name == "nt"
                    else 0
                ),
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
# 8. Compare duplicate and sibling groups
# ============================================================

def compare_groups(artifacts, scan_by_hash, groups, group_type):
    """Summarize finding differences within groups."""

    artifact_by_key = {
        artifact["artifact_key"]: artifact
        for artifact in artifacts
    }

    comparison_rows = []

    for group_number, members in enumerate(groups, start=1):
        group_artifacts = [
            artifact_by_key[key] for key in members
        ]

        hashes = {
            artifact["content_hash"]
            for artifact in group_artifacts
        }

        signatures_by_hash = {}
        artifacts_with_findings = 0
        total_findings = 0

        for artifact in group_artifacts:
            scan = scan_by_hash.get(artifact["content_hash"])

            if not scan:
                continue

            count = scan.get("findings_count", 0)
            total_findings += count

            if count > 0:
                artifacts_with_findings += 1

            signatures_by_hash[artifact["content_hash"]] = (
                scan.get("finding_signatures", set())
            )

        all_signatures = set()

        for signatures in signatures_by_hash.values():
            all_signatures.update(signatures)

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
            "total_findings_across_artifacts": total_findings,
            "distinct_finding_signatures": len(all_signatures),
            "findings_differ_across_versions": signatures_differ,
            "repositories": "; ".join(repos),
            "artifact_paths": "; ".join(paths),
        })

    return comparison_rows


# ============================================================
# 9. Write readable text results
# ============================================================

def write_readable_results(
    artifact_rows,
    duplicate_rows,
    sibling_rows,
    error_rows,
):
    """Write a readable summary of the scan results."""

    output_path = RESULTS_DIR / "cisco_scan_results.txt"

    lines = [
        "GITSKILLS CISCO AI DEFENSE SCANNER RESULTS",
        "=" * 55,
        "",
        f"Total artifact records: {len(artifact_rows)}",
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

    for heading, groups in (
        ("EXACT DUPLICATE GROUP COMPARISONS", duplicate_rows),
        ("SIBLING GROUP COMPARISONS", sibling_rows),
    ):
        lines.extend(["", heading, "=" * 55])

        for group in groups:
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

    lines.extend(["", "SCAN ERRORS", "=" * 55])

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
        "- Raw scanner reports are stored together in cisco_all_scan_reports.json.",
        "",
    ])

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Readable text results saved to: {output_path.resolve()}")


# ============================================================
# 10. Main workflow
# ============================================================

def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load prior consolidated reports as a cache, if enabled.
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

    # Load CSV pair identities first.
    print("Loading only artifacts from the 60–97% similarity CSV...")

    selected_pairs, selected_keys = load_selected_pairs()

    print(f"Pairs loaded from CSV: {len(selected_pairs)}")
    print(f"Unique artifact identities selected: {len(selected_keys)}")

    # Load the database, then restrict artifacts to those listed in the CSV.
    all_artifacts, sibling_rows, sibling_columns = load_artifacts()

    artifacts = [
        artifact
        for artifact in all_artifacts
        if artifact_identity(artifact) in selected_keys
    ]

    if not artifacts:
        raise SystemExit(
            "No CSV-selected artifacts matched the database. "
            "Check the CSV repository names, paths, and SHA values."
        )

    matched_keys = {
        artifact_identity(artifact)
        for artifact in artifacts
    }

    missing_keys = selected_keys - matched_keys

    print(f"\nValid similarity pairs: {len(selected_pairs)}")
    print(f"Unique artifact identities requested: {len(selected_keys)}")
    print(f"Artifact records matched: {len(artifacts)}")
    print(f"Artifact identities missing: {len(missing_keys)}")

    if missing_keys:
        print(
            "WARNING: Some CSV entries did not match the database. "
            "Check the repository names, paths, and SHA values."
        )

    print(f"Sibling relationship rows: {len(sibling_rows)}")

    # Group selected artifacts by dataset file_sha.
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

    # Only unique content hashes from CSV-selected artifacts are scanned.
    unique_artifacts = {}

    for artifact in artifacts:
        unique_artifacts.setdefault(
            artifact["content_hash"],
            artifact,
        )

    unique_items = list(unique_artifacts.items())
    scan_by_hash = {}
    for content_hash, _ in unique_items:
        cached_result = cached_scan_result(content_hash, cached_scans)
        if cached_result is not None:
            scan_by_hash[content_hash] = cached_result

    error_rows = []

    print(f"\nCSV-selected artifact records: {len(artifacts)}")
    print(f"Unique content versions to scan: {len(unique_items)}")

    scan_cancelled = False

    def record_scan_result(content_hash, artifact, scan):
        scan_by_hash[content_hash] = scan

        if scan["status"] in (
            "completed",
            "cached",
            "report_created_nonzero_exit",
        ):
            cached_scans[content_hash] = {
                "content_hash": content_hash,
                "repo_full_name": artifact.get("repo_full_name"),
                "path": artifact.get("path"),
                "name": artifact.get("name"),
                "description": artifact.get("description"),
                "file_sha": artifact.get("file_sha"),
                "scan_status": scan["status"],
                "scanner_exit_code": scan.get("exit_code", ""),
                "findings_count": scan.get("findings_count", 0),
                "categories": scan.get("categories", ""),
                "severities": scan.get("severities", ""),
                "report": scan.get("report", {}),
            }
            save_report_cache(cached_scans)
        else:
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

    futures = {}
    processed_futures = set()
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SCANS) as executor:
        try:
            for position, (content_hash, artifact) in enumerate(
                unique_items,
                start=1,
            ):
                print(
                    f"[{position}/{len(unique_items)}] "
                    f"{artifact.get('repo_full_name')} :: "
                    f"{artifact.get('path')}"
                )
                if content_hash in scan_by_hash:
                    print(
                        f"    Status: cached | "
                        f"Findings: "
                        f"{scan_by_hash[content_hash].get('findings_count', 0)}"
                    )
                    continue

                future = executor.submit(
                    scan_unique_skill,
                    artifact,
                    scanner_path,
                    cached_scans,
                )
                futures[future] = (content_hash, artifact)

            for future in as_completed(futures):
                content_hash, artifact = futures[future]
                record_scan_result(content_hash, artifact, future.result())
                processed_futures.add(future)
        except KeyboardInterrupt:
            scan_cancelled = True
            print(
                "\nScan cancelled. Waiting for active scans to finish; "
                "their reports will be saved."
            )
            for future in futures:
                future.cancel()

            for future in as_completed(futures):
                if future in processed_futures or future.cancelled():
                    continue

                content_hash, artifact = futures[future]
                record_scan_result(content_hash, artifact, future.result())
                processed_futures.add(future)

    # Save raw reports for the selected unique content versions only.
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

    save_report_cache(
        consolidated_scans,
        {
            "description": (
                "Consolidated Cisco Skill Scanner output for "
                "unique content versions selected from the "
                "60–97% similarity CSV."
            ),
            "valid_similarity_pairs": len(selected_pairs),
            "selected_artifact_records": len(artifacts),
            "unique_content_versions": len(unique_items),
        },
    )

    report_message = (
        "Partial scan reports saved to: "
        if scan_cancelled
        else "All selected raw scan reports saved together to: "
    )
    print(f"{report_message}{ALL_REPORTS_JSON.resolve()}")

    # Write one output row per selected database artifact record.
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
    print(f"Valid CSV pairs: {len(selected_pairs)}")
    print(f"Artifact records represented: {len(artifacts)}")
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
    print(f"  {RESULTS_DIR / 'cisco_scan_results.txt'}")


if __name__ == "__main__":
    main()
