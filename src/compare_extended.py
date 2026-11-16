"""
Compare Cisco scanner results for baseline and variant skills.

Run from the repository root:
    python src/compare_extended.py

Default inputs:
    charts/name_variant_pairs.csv
    results/expanded_scan/cisco_scan_results.csv

Default outputs:
    results/expanded_scan/baseline_variant_pair_comparison.csv
    results/expanded_scan/baseline_variant_summary.csv

This script only reads existing CSV files. It does not rerun the scanner.
"""

from pathlib import Path
import argparse
import pandas as pd
import matplotlib.pyplot as plt
import json



ROOT = Path(__file__).resolve().parent.parent

DEFAULT_PAIR_FILE = ROOT / "charts" / "name_variant_pairs.csv"
DEFAULT_SCAN_FILE = ROOT / "results" / "expanded_scan" / "cisco_scan_results.csv"
DEFAULT_OUTPUT_DIR = ROOT / "results" / "expanded_scan"


def load_inputs(pair_file: Path, scan_file: Path):
    """Load and validate the input CSVs before any comparison logic runs.

    This helper verifies the required schema, trims SHA values, drops incomplete
    pair records, and fails fast if the scanner data contains duplicate file
    hashes. Those checks keep the rest of the pipeline working against a clean,
    consistent dataset rather than silently mixing partial or ambiguous results.
    """
    pairs = pd.read_csv(pair_file, dtype=str)
    scans = pd.read_csv(scan_file, dtype={"file_sha": str})

    required_pair_columns = {
        "name", "similarity", "baseline_repo", "baseline_path",
        "baseline_sha", "variant_repo", "variant_path", "variant_sha"
    }
    required_scan_columns = {
        "file_sha", "scan_status", "findings_count",
        "categories", "severities"
    }

    missing_pairs = required_pair_columns - set(pairs.columns)
    missing_scans = required_scan_columns - set(scans.columns)

    if missing_pairs:
        raise ValueError(f"Pair CSV is missing columns: {sorted(missing_pairs)}")
    if missing_scans:
        raise ValueError(f"Scanner CSV is missing columns: {sorted(missing_scans)}")

    pairs["baseline_sha"] = pairs["baseline_sha"].str.strip()
    pairs["variant_sha"] = pairs["variant_sha"].str.strip()

    # Remove pairs that are missing either SHA hash.
    before_count = len(pairs)

    pairs = pairs.dropna(subset=["baseline_sha", "variant_sha"])

    # Also remove empty SHA values.
    pairs = pairs[
        (pairs["baseline_sha"] != "") &
        (pairs["variant_sha"] != "")
    ].copy()

    removed_count = before_count - len(pairs)

    print(f"Skipped {removed_count} pairs with missing SHA hashes.")

    scans["file_sha"] = scans["file_sha"].astype(str).str.strip()

    scans["findings_count"] = pd.to_numeric(
        scans["findings_count"], errors="coerce"
    )

    # A SHA should identify one scanned content version. Stop rather than
    # silently choosing between conflicting scanner rows.
    duplicate_hashes = scans.loc[
        scans["file_sha"].duplicated(keep=False), "file_sha"
    ].unique()
    if len(duplicate_hashes):
        raise ValueError(
            "Scanner CSV contains duplicate file_sha values. "
            f"Examples: {list(duplicate_hashes[:5])}"
        )

    return pairs, scans


def build_pair_comparison(pairs: pd.DataFrame, scans: pd.DataFrame):
    """Join each baseline/variant pair to the exact scanner records it represents.

    The comparison is anchored on SHA values so every pair is evaluated against
    the same content version on both sides. The function also computes a
    per-pair outcome describing whether the variant had more findings, fewer
    findings, no change, or an unknown result when counts were missing.
    """
    scan_lookup = scans.set_index("file_sha")

    baseline_hashes = set(scan_lookup.index)
    missing_baseline = sorted(set(pairs["baseline_sha"].dropna()) - baseline_hashes)
    missing_variant = sorted(set(pairs["variant_sha"].dropna()) - baseline_hashes)

    if missing_baseline or missing_variant:
        raise ValueError(
            "Some pair hashes do not have scanner results. "
            f"Missing baseline hashes: {len(missing_baseline)}; "
            f"missing variant hashes: {len(missing_variant)}. "
            "Check that the pair and scanner CSVs came from the same dataset/run."
        )

    rows = []
    for _, pair in pairs.iterrows():
        baseline = scan_lookup.loc[pair["baseline_sha"]]
        variant = scan_lookup.loc[pair["variant_sha"]]

        baseline_count = baseline["findings_count"]
        variant_count = variant["findings_count"]

        if pd.isna(baseline_count) or pd.isna(variant_count):
            difference = pd.NA
            outcome = "unknown"
        else:
            difference = int(variant_count - baseline_count)
            if difference > 0:
                outcome = "more findings in variant"
            elif difference < 0:
                outcome = "more findings in baseline"
            else:
                outcome = "same finding count"

        rows.append({
            "name": pair["name"],
            "similarity": pair["similarity"],
            "baseline_repo": pair["baseline_repo"],
            "baseline_path": pair["baseline_path"],
            "baseline_sha": pair["baseline_sha"],
            "baseline_scan_status": baseline["scan_status"],
            "baseline_findings_count": baseline_count,
            "baseline_categories": baseline["categories"],
            "baseline_severities": baseline["severities"],
            "variant_repo": pair["variant_repo"],
            "variant_path": pair["variant_path"],
            "variant_sha": pair["variant_sha"],
            "variant_scan_status": variant["scan_status"],
            "variant_findings_count": variant_count,
            "variant_categories": variant["categories"],
            "variant_severities": variant["severities"],
            "variant_minus_baseline": difference,
            "pair_outcome": outcome,
        })

    return pd.DataFrame(rows)


def make_summary(pair_results: pd.DataFrame, scans: pd.DataFrame):
    """Summarize the pair-level comparison into a compact reporting table.

    This helper groups metrics into three categories: per-record summaries,
    paired outcome totals, and unique content-version summaries. By tracking
    unique SHA-based content separately, it avoids inflating counts when the
    same file version appears in multiple pair comparisons.
    """
    summary_rows = []

    # Pair-record summary: each row in the pair CSV contributes once.
    for group in ("baseline", "variant"):
        counts = pair_results[f"{group}_findings_count"]
        summary_rows.append({
            "measure": "pair_records",
            "group": group,
            "records": len(pair_results),
            "unique_sha_hashes": pair_results[f"{group}_sha"].nunique(),
            "records_with_findings": int((counts > 0).sum()),
            "records_with_zero_findings": int((counts == 0).sum()),
            "average_findings_per_record": counts.mean(),
            "median_findings_per_record": counts.median(),
            "total_findings_across_pair_records": counts.sum(),
        })

    # Paired outcomes: each baseline-variant pair contributes one result.
    outcome_counts = pair_results["pair_outcome"].value_counts()
    for outcome in (
        "more findings in variant",
        "more findings in baseline",
        "same finding count",
        "unknown",
    ):
        summary_rows.append({
            "measure": "paired_outcome",
            "group": outcome,
            "records": int(outcome_counts.get(outcome, 0)),
            "unique_sha_hashes": pd.NA,
            "records_with_findings": pd.NA,
            "records_with_zero_findings": pd.NA,
            "average_findings_per_record": pd.NA,
            "median_findings_per_record": pd.NA,
            "total_findings_across_pair_records": pd.NA,
        })

    # Unique scanned-content summary. This avoids counting a repeated SHA
    # multiple times when the same skill version occurs in multiple pairs.
    used_hashes = set(pair_results["baseline_sha"]) | set(pair_results["variant_sha"])
    unique_scans = scans[scans["file_sha"].isin(used_hashes)].copy()
    role_map = {}
    for role, column in (
        ("baseline", "baseline_sha"),
        ("variant", "variant_sha"),
    ):
        for sha in pair_results[column].dropna().unique():
            role_map.setdefault(sha, set()).add(role)

    for role in ("baseline", "variant"):
        hashes = [sha for sha, roles in role_map.items() if role in roles]
        group_scans = unique_scans[unique_scans["file_sha"].isin(hashes)]
        counts = group_scans["findings_count"]
        summary_rows.append({
            "measure": "unique_content_versions",
            "group": role,
            "records": len(group_scans),
            "unique_sha_hashes": group_scans["file_sha"].nunique(),
            "records_with_findings": int((counts > 0).sum()),
            "records_with_zero_findings": int((counts == 0).sum()),
            "average_findings_per_record": counts.mean(),
            "median_findings_per_record": counts.median(),
            "total_findings_across_pair_records": counts.sum(),
        })

    return pd.DataFrame(summary_rows)

def count_severity_records(pair_results, column, severity):
    """Count pair records that include a specific severity label.

    The severity column stores a semicolon-delimited list of severities, so this
    helper parses each value and checks whether the requested label appears
    anywhere in that list. Reusing this logic keeps the report and summary
    sections consistent without repeating the same string-matching pattern.
    """
    return pair_results[column].fillna("").astype(str).str.upper().str.contains(
        rf"\b{severity}\b", regex=True
    ).sum()

def write_text_report(pair_results, output_file):
    """Create a plain-language report that explains the comparison results.

    This function converts the numeric comparison into a readable narrative for
    reviewers who may not want to open the CSV or charts. It combines overall
    counts, paired outcome summaries, and category breakdowns so the report can
    stand alone as a concise interpretation of the scanner results.
    """

    lines = [
        "BASELINE VS. VARIANT CISCO SCANNER COMPARISON",
        "=" * 48,
        "",
        "OVERVIEW",
        "--------",
        f"Total baseline-variant pairs analyzed: {len(pair_results)}",
        "",
        "BASELINE RESULTS",
        "----------------",
        f"Average findings: {pair_results['baseline_findings_count'].mean():.2f}",
        f"Records with findings: {(pair_results['baseline_findings_count'] > 0).sum()}",
        f"Records with zero findings: {(pair_results['baseline_findings_count'] == 0).sum()}",
        "",
        "VARIANT RESULTS",
        "---------------",
        f"Average findings: {pair_results['variant_findings_count'].mean():.2f}",
        f"Records with findings: {(pair_results['variant_findings_count'] > 0).sum()}",
        f"Records with zero findings: {(pair_results['variant_findings_count'] == 0).sum()}",
        "",
        "PAIRED COMPARISON",
        "-----------------",
        f"More findings in variant: {(pair_results['pair_outcome'] == 'more findings in variant').sum()}",
        f"More findings in baseline: {(pair_results['pair_outcome'] == 'more findings in baseline').sum()}",
        f"Same finding count: {(pair_results['pair_outcome'] == 'same finding count').sum()}",
        "",
        "SEVERITY COMPARISON",
        "-------------------",
        "Number of pair records containing each severity:",
        "",
    ]

    severities = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]

    for severity in severities:
        baseline_count = count_severity_records(
            pair_results, "baseline_severities", severity
        )
        variant_count = count_severity_records(
            pair_results, "variant_severities", severity
        )

        lines.append(
            f"{severity}: Baseline = {baseline_count}, "
            f"Variant = {variant_count}"
        )

    lines.extend([
        "",
        "INTERPRETATION",
        "--------------",
        "These results compare the total number of scanner findings.",
        "The same finding count does not necessarily mean the skills have",
        "the same types of security findings.",
        "",
        "Scanner findings are alerts and do not prove that a skill is malicious",
        "or that the reported behavior was executed.",
        "",
        "FINDING TYPES",
        "-------------",
        "The following counts show how many unique content versions had each finding category.",
        "A content version is counted once per category, even if it appears in multiple pairs.",
        "",
    ])

    for group, label in (
        ("baseline", "Baseline"),
        ("variant", "Variant"),
    ):
        sha_column = f"{group}_sha"
        category_column = f"{group}_categories"

        # Count each unique content version only once.
        unique_versions = pair_results[
            [sha_column, category_column]
        ].drop_duplicates(subset=[sha_column])

        category_counts = {}

        for categories in unique_versions[category_column].dropna():
            for category in str(categories).split(";"):
                category = category.strip()

                if category:
                    category_counts[category] = (
                        category_counts.get(category, 0) + 1
                    )

        lines.append(f"{label} finding types:")

        if category_counts:
            for category, count in sorted(
                category_counts.items(),
                key=lambda item: item[1],
                reverse=True,
            ):
                lines.append(f"  {category}: {count} unique content versions")
        else:
            lines.append("  No finding categories recorded.")

        lines.append("")

    output_file.write_text("\n".join(lines), encoding="utf-8")

def create_severity_chart(pair_results, output_dir):
    """Visualize how often each severity appears across unique content versions.

    The chart compares the baseline and variant sets by counting unique SHA-based
    content versions that contain each severity level. This keeps the plot aligned
    with the dataset's actual artifacts rather than counting the same content
    multiple times just because it appears in several pair comparisons.
    """

    severities = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    results = {"Baseline": [], "Variant": []}

    for group in ("baseline", "variant"):
        sha_column = f"{group}_sha"
        severity_column = f"{group}_severities"

        unique_versions = pair_results[
            [sha_column, severity_column]
        ].drop_duplicates(subset=[sha_column])

        for severity in severities:
            count = unique_versions[severity_column].fillna("").astype(str).apply(
                lambda value: severity in [
                    item.strip().upper()
                    for item in value.split(";")
                ]
            ).sum()

            results[group.capitalize()].append(count)

    x = range(len(severities))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.bar(
        [i - width / 2 for i in x],
        results["Baseline"],
        width,
        label="Baseline"
    )

    ax.bar(
        [i + width / 2 for i in x],
        results["Variant"],
        width,
        label="Variant"
    )

    ax.set_title("Baseline vs. Variant: Scanner Severity Comparison")
    ax.set_xlabel("Severity Level")
    ax.set_ylabel("Unique Content Versions")
    ax.set_xticks(list(x))
    ax.set_xticklabels(severities)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()

    output_file = output_dir / "baseline_variant_severities.png"
    plt.savefig(output_file, dpi=300)
    plt.close()

    print(f"Saved severity chart: {output_file}")

def create_rule_id_chart(pair_results, output_dir, reports_file):
    """Compare the Cisco rule IDs triggered in the baseline and variant versions.

    This chart is useful for spotting whether one version tends to trigger a
    different set of findings rather than simply a different count. It reads the
    full scanner reports, groups findings by artifact SHA, and excludes the
    generic license-metadata result so the plot stays focused on security-relevant
    alerts.
    """

    with open(reports_file, "r", encoding="utf-8") as file:
        report_data = json.load(file)

    # Match each scanner report to its artifact SHA.
    findings_by_sha = {}

    for report in report_data["scans"].values():
        sha = report.get("file_sha")

        if not sha:
            continue

        findings_by_sha[sha] = (
            report.get("report", {}).get("findings", []) or []
        )

    results = {
        "Baseline": {},
        "Variant": {}
    }

    # Count findings for each unique content version.
    for group in ("baseline", "variant"):
        sha_column = f"{group}_sha"
        unique_hashes = pair_results[sha_column].dropna().unique()

        for sha in unique_hashes:
            findings = findings_by_sha.get(sha, [])

            for finding in findings:
                rule_id = finding.get("rule_id", "UNKNOWN")

                results[group.capitalize()][rule_id] = (
                    results[group.capitalize()].get(rule_id, 0) + 1
                )

    # Include every rule found in either group.
        # Exclude the common license metadata finding from the security chart.
    excluded_rules = {"MANIFEST_MISSING_LICENSE"}

    rule_ids = sorted(
        rule for rule in (set(results["Baseline"]) | set(results["Variant"]))
        if rule not in excluded_rules
    )


    baseline_counts = [
        results["Baseline"].get(rule, 0) for rule in rule_ids
    ]

    variant_counts = [
        results["Variant"].get(rule, 0) for rule in rule_ids
    ]

    # Create a horizontal comparison chart.
    positions = range(len(rule_ids))
    height = 0.35

    fig, ax = plt.subplots(figsize=(12, 8))

    ax.barh(
        [p - height / 2 for p in positions],
        baseline_counts,
        height,
        label="Baseline"
    )

    ax.barh(
        [p + height / 2 for p in positions],
        variant_counts,
        height,
        label="Variant"
    )

    ax.set_title("Baseline vs. Variant: Cisco Findings by Rule ID")
    ax.set_xlabel("Number of Findings")
    ax.set_ylabel("Cisco Rule ID")
    ax.set_yticks(list(positions))
    ax.set_yticklabels(rule_ids)
    ax.legend()
    ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()

    output_file = output_dir / "baseline_variant_rule_ids.png"
    plt.savefig(output_file, dpi=300)
    plt.close()


    # Separate chart for license metadata findings.
    license_counts = [
        results["Baseline"].get("MANIFEST_MISSING_LICENSE", 0),
        results["Variant"].get("MANIFEST_MISSING_LICENSE", 0)
    ]

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(
    ["Baseline", "Variant"],
    license_counts,
    color=["steelblue", "orange"]
)
    ax.set_title("Missing License Findings")
    ax.set_ylabel("Number of Findings")
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / "baseline_variant_license.png", dpi=300)
    plt.close()



    print(f"Saved rule-ID chart: {output_file}")


def create_severity_charts(pair_results, output_dir):
    """Generate one comparison chart for each severity bucket.

    This breaks the overall severity comparison into more targeted views so a
    reviewer can inspect the baseline-versus-variant delta for critical, high,
    medium, low, and informational findings independently. Each chart counts
    unique content versions containing that severity so the visual remains stable
    even when the same artifact appears in multiple pair records.
    """

    severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]

    for severity in severities:
        baseline_count = 0
        variant_count = 0

        for group in ["baseline", "variant"]:
            column = f"{group}_severities"

            # Count unique content versions containing this severity.
            unique_versions = pair_results[
                ["baseline_sha", "variant_sha", column]
            ].drop_duplicates(subset=[f"{group}_sha"])

            count = unique_versions[column].fillna("").astype(str).apply(
                lambda value: severity in [
                    item.strip().upper()
                    for item in value.replace(";", ",").split(",")
                ]
            ).sum()

            if group == "baseline":
                baseline_count = count
            else:
                variant_count = count

        fig, ax = plt.subplots(figsize=(7, 5))

        ax.bar(
            ["Baseline", "Variant"],
            [baseline_count, variant_count],
            color=["steelblue", "orange"]
        )

        ax.set_title(f"Baseline vs. Variant: {severity} Findings")
        ax.set_ylabel("Unique Content Versions")
        ax.grid(axis="y", alpha=0.3)

        plt.tight_layout()

        output_file = output_dir / f"baseline_variant_{severity.lower()}.png"
        plt.savefig(output_file, dpi=300)
        plt.close()

        print(f"Saved severity chart: {output_file}")


def main():
    """Run the full comparison workflow from CLI inputs to saved reports and charts.

    This entry point wires together the data loading, pair comparison,
    summary generation, report writing, and chart creation steps. It also
    exposes the file locations through command-line arguments so the analysis can
    be reproduced against different input datasets without editing the script.
    """
    parser = argparse.ArgumentParser(
        description="Compare Cisco scanner findings for baseline and variant skills."
    )
    parser.add_argument("--pairs", type=Path, default=DEFAULT_PAIR_FILE)
    parser.add_argument("--scans", type=Path, default=DEFAULT_SCAN_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
    "--reports",
    type=Path,
    default=ROOT / "results" / "expanded_scan" / "cisco_all_scan_reports.json"
)

    args = parser.parse_args()

    charts_dir = args.output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)


    pairs, scans = load_inputs(args.pairs, args.scans)
    pair_results = build_pair_comparison(pairs, scans)
    summary = make_summary(pair_results, scans)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pair_output = args.output_dir / "baseline_variant_pair_comparison.csv"
    summary_output = args.output_dir / "baseline_variant_summary.csv"
    text_output = args.output_dir / "baseline_variant_report.txt"

    pair_results.to_csv(pair_output, index=False)
    summary.to_csv(summary_output, index=False)
    write_text_report(pair_results, text_output)

    create_severity_chart(pair_results, charts_dir)
    create_rule_id_chart(pair_results, charts_dir, args.reports)
    create_severity_charts(pair_results, charts_dir)
    
    print(f"Compared {len(pair_results)} baseline-variant pairs.")
    print(f"Unique baseline SHA hashes: {pair_results['baseline_sha'].nunique()}")
    print(f"Unique variant SHA hashes: {pair_results['variant_sha'].nunique()}")
    print("\nPaired finding-count outcomes:")
    print(pair_results["pair_outcome"].value_counts().to_string())
    print(f"\nSaved pair-level results: {pair_output}")
    print(f"Saved summary: {summary_output}")
    print(f"Saved text report: {text_output}")


if __name__ == "__main__":
    main()