"""
Compare Cisco scanner results for baseline and variant skills.

Run from the repository root:
    python src/compare_baseline_variants.py

Default inputs:
    charts/name_variant_pairs_60-97.csv
    results/cisco_scan_results.csv

Default outputs:
    results/baseline_variant_pair_comparison.csv
    results/baseline_variant_summary.csv

This script only reads existing CSV files. It does not rerun the scanner.
"""

from pathlib import Path
import argparse
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent

DEFAULT_PAIR_FILE = ROOT / "charts" / "name_variant_pairs_60-97.csv"
DEFAULT_SCAN_FILE = ROOT / "results" / "cisco_scan_results.csv"
DEFAULT_OUTPUT_DIR = ROOT / "results"


def load_inputs(pair_file: Path, scan_file: Path):
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

def write_text_report(pair_results, output_file):
    """Create a human-readable text report of the comparison."""

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
        "INTERPRETATION",
        "--------------",
        "These results compare the total number of scanner findings.",
        "The same finding count does not necessarily mean the skills have",
        "the same types of security findings.",
        "",
        "Scanner findings are alerts and do not prove that a skill is malicious",
        "or that the reported behavior was executed.",
    ]

        # Finding types by baseline and variant
    lines.extend([
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


def main():
    parser = argparse.ArgumentParser(
        description="Compare Cisco scanner findings for baseline and variant skills."
    )
    parser.add_argument("--pairs", type=Path, default=DEFAULT_PAIR_FILE)
    parser.add_argument("--scans", type=Path, default=DEFAULT_SCAN_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

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
