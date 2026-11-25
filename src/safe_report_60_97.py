"""
Safe reviewer report for the 60-97% similarity band scanned by test_cisco_gitskills.py.

Inputs (all produced by test_cisco_gitskills.py and the pair CSVs in charts/):
  results/cisco_all_scan_reports.json                      scans of the 238 band artifacts
  results/baseline_variant_pair_comparison.csv             pair comparison (filtered to the band)
  charts/name_variant_pairs_60-97.csv                      the band itself, with commit dates
  results/cisco_scan_errors.csv                            scan errors

Output: results/safe_report_60-97/
  safe_report.md, safe_report.json, review_queue.csv, pairs_review.csv

Usage (from the repository root):
    python src/safe_report_60_97.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import safe_report as sr  # noqa: E402

BAND_CSV = Path("charts/name_variant_pairs_60-97.csv")
PAIR_COMPARISON = Path("results/baseline_variant_pair_comparison.csv")
REPORTS = Path("results/cisco_all_scan_reports.json")
ERRORS = Path("results/cisco_scan_errors.csv")
OUT = Path("results/safe_report_60-97")


def pair_key(r: dict) -> tuple:
    return (r.get("baseline_repo"), r.get("baseline_path"),
            r.get("variant_repo"), r.get("variant_path"))


def main() -> None:
    for required in (BAND_CSV, PAIR_COMPARISON, REPORTS):
        if not required.exists():
            sys.exit(f"Missing {required}. Run from the repository root.")

    band_rows = list(csv.DictReader(open(BAND_CSV, encoding="utf-8-sig")))
    band_keys = {pair_key(r) for r in band_rows}

    # Keep only comparison rows whose pair is in the 60-97 band.
    comparison = list(csv.DictReader(open(PAIR_COMPARISON, encoding="utf-8-sig")))
    in_band = [r for r in comparison if pair_key(r) in band_keys]
    filtered = OUT / "_band_pair_comparison.csv"
    OUT.mkdir(parents=True, exist_ok=True)
    with filtered.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(comparison[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(in_band)

    reports = sr.load_reports(REPORTS)
    rows = sr.flatten(reports, include_info=False)
    pairs = sr.load_pairs(filtered, sr.load_pair_dates(BAND_CSV))
    errors = sr.load_errors(ERRORS)

    md, data = sr.build(reports, rows, pairs, errors, False, REPORTS.name)
    (OUT / "safe_report.md").write_text(md, encoding="utf-8")
    (OUT / "safe_report.json").write_text(
        __import__("json").dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    review = sr.dedupe(sorted([r for r in rows if r["severity"] != "INFO"],
                              key=lambda r: -sr.SEVERITY_ORDER.index(r["severity"])))
    sr.write_csv(OUT / "review_queue.csv", review,
                 ["severity", "category", "rule_id", "repo", "path", "file_sha", "file", "line",
                  "analyzer", "snippet", "snippet_sha256", "note"])
    sr.write_csv(OUT / "pairs_review.csv", pairs,
                 ["name", "similarity", "baseline", "variant", "baseline_findings", "variant_findings",
                  "variant_minus_baseline", "pair_outcome", "baseline_categories", "variant_categories",
                  "baseline_severities", "variant_severities"])
    filtered.unlink()
    print(f"Band rows: {len(band_rows)} (unique baseline/variant pairs: {len(band_keys)}); comparison rows kept: {len(in_band)}")
    print(f"wrote {OUT / 'safe_report.md'}, safe_report.json, review_queue.csv, pairs_review.csv")


if __name__ == "__main__":
    main()
