

"""
Plot Cisco AI Defense Skill Scanner findings from existing JSON reports.

Run from the repository root:
    python src/plot_cisco_findings.py

Input:
    results/cisco_all_scan_reports.json

Output:
    results/cisco_rule_frequency.png

This script does not run the scanner or modify the original JSON.
"""

import json
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt

# File paths
INPUT_FILE = Path("results/cisco_all_scan_reports.json")
OUTPUT_FILE = Path("results/cisco_rule_frequency.png")

# Exclude findings not relevant to the security analysis
EXCLUDED_RULES = {
#    "MANIFEST_MISSING_LICENSE",
}

TOP_N = 15


def collect_findings(data):
    """Collect finding dictionaries from nested JSON reports."""
    findings = []

    def walk(obj):
        if isinstance(obj, dict):
            # Check for lists containing findings
            for key, value in obj.items():
                normalized_key = key.lower().replace("-", "_")

                if normalized_key in {
                    "findings",
                    "issues",
                    "vulnerabilities",
                    "detections",
                    "alerts",
                } and isinstance(value, list):
                    findings.extend(
                        item for item in value if isinstance(item, dict)
                    )
                else:
                    walk(value)

        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return findings


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Could not find {INPUT_FILE.resolve()}\n"
            "Make sure the JSON report file is in the results folder."
        )

    with INPUT_FILE.open("r", encoding="utf-8") as file:
        reports = json.load(file)

    findings = collect_findings(reports)

    rule_counts = Counter()
    for finding in findings:
        rule_id = finding.get("rule_id") or finding.get("rule")

        if not rule_id:
            continue

        rule_id = str(rule_id)

        if rule_id not in EXCLUDED_RULES:
            rule_counts[rule_id] += 1

    if not rule_counts:
        print("No findings found after filtering.")
        print("Check the JSON structure and finding field names.")
        return

    top_rules = rule_counts.most_common(TOP_N)

    labels = [rule for rule, _ in top_rules][::-1]
    counts = [count for _, count in top_rules][::-1]

    # Create the chart
    height = max(5, len(labels) * 0.42)
    fig, ax = plt.subplots(figsize=(12, height))

    bars = ax.barh(labels, counts)

    ax.set_title(
        "Most Frequent Cisco Security Findings",
        fontsize=15,
        pad=14,
    )
    ax.set_xlabel("Finding occurrences")
    ax.set_ylabel("Cisco rule ID")
    ax.bar_label(bars, padding=4)
    ax.grid(axis="x", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)

    plt.tight_layout()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_FILE, dpi=300, bbox_inches="tight")
    plt.show()

    print(f"Total finding occurrences after filtering: {sum(rule_counts.values())}")
    print(f"Distinct rule IDs: {len(rule_counts)}")
    print(f"Chart saved to: {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    main()
