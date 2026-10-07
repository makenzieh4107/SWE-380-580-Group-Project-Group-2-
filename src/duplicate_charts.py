"""
Duplicate Artifact Charts for the GitSkills Dataset

1. How much of the dataset is unique vs. identical copies.
2. Distribution of duplicate group sizes.
3. The largest identical-content groups (labelled by earliest artifact name).
4. Repos whose dedup_primary artifacts are copied the most (same repo vs. other repos).
5. How long after the first appearance each copy showed up (copy lag).
6. Earliest instances vs. later copies over time, by month.
7. dedup_primary sanity check: primaries per duplicate group.
8. Near-duplicates (rapidfuzz): artifacts that share a name but differ in
   content, scored by similarity to the earliest version of that name.

Charts are written to ./charts/, along with name_variant_pairs.csv, which lists
the near-duplicate pairs from chart 8 for later security comparison.

Like duplicate_analysis.py, this treats artifacts as data only and never
executes any scripts or code contained within them.
"""

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")  # render to files, no display needed
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter
import pandas as pd
from rapidfuzz import fuzz

DB_PATH = "data/agent_skills_sample.db"
OUTPUT_DIR = Path("charts")

TOP_N = 15                    # bars shown in "top" charts
MAX_VARIANTS_PER_NAME = 50    # cap on fuzzy comparisons per skill name
MAX_CONTENT_CHARS = 20_000    # truncate very long content before fuzzy matching

# Same duplicate-group definition used throughout duplicate_analysis.py
DUP_SHAS = """
    SELECT file_sha
    FROM GitSkills.artifacts
    GROUP BY file_sha
    HAVING COUNT(*) > 1
"""

plt.rcParams.update({
    "figure.figsize": (10, 6),
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


# ---------------------------------------------------------
# Data loading
# ---------------------------------------------------------

def to_utc_naive(series):
    """Parse timestamps (string or datetime) to naive UTC; bad values become NaT."""
    return pd.to_datetime(series, utc=True, errors="coerce").dt.tz_convert(None)


def load_total_count(con):
    return con.execute("SELECT COUNT(*) FROM GitSkills.artifacts").fetchone()[0]


def load_duplicate_artifacts(con):
    """Queries 3 + 5 combined: every artifact in a duplicate group."""
    df = con.execute(f"""
        SELECT
            repo_full_name,
            path,
            file_sha,
            name,
            dedup_primary,
            first_commit_at,
            last_commit_at,
            COUNT(*) OVER (PARTITION BY file_sha) AS artifacts_in_group
        FROM GitSkills.artifacts
        WHERE file_sha IN ({DUP_SHAS})
        ORDER BY artifacts_in_group DESC, file_sha, first_commit_at
    """).fetchdf()

    df["first_commit_at"] = to_utc_naive(df["first_commit_at"])
    df["last_commit_at"] = to_utc_naive(df["last_commit_at"])
    df["dedup_primary"] = (
        pd.to_numeric(df["dedup_primary"], errors="coerce").fillna(0).astype(int)
    )
    return df


def load_group_summary(con):
    """Query 4: one row per duplicate group with the earliest artifact's name."""
    return con.execute(f"""
        WITH ranked_artifacts AS (
            SELECT
                file_sha,
                name,
                description,
                first_commit_at,
                ROW_NUMBER() OVER (
                    PARTITION BY file_sha
                    ORDER BY first_commit_at ASC
                ) AS rn
            FROM GitSkills.artifacts
            WHERE file_sha IN ({DUP_SHAS})
        )
        SELECT
            file_sha,
            COUNT(*) AS artifact_count,
            MAX(CASE WHEN rn = 1 THEN name END) AS earliest_artifact_name,
            MAX(CASE WHEN rn = 1 THEN description END) AS earliest_artifact_description,
            MIN(first_commit_at) AS earliest_first_commit
        FROM ranked_artifacts
        GROUP BY file_sha
        ORDER BY artifact_count DESC
    """).fetchdf()


def load_name_variants(con):
    """Artifacts whose (normalized) name appears with more than one file_sha."""
    df = con.execute("""
        WITH named AS (
            SELECT
                lower(trim(name)) AS norm_name,
                name,
                repo_full_name,
                path,
                file_sha,
                content,
                first_commit_at
            FROM GitSkills.artifacts
            WHERE name IS NOT NULL
              AND trim(name) <> ''
              AND content IS NOT NULL
              AND file_sha IS NOT NULL
        )
        SELECT *
        FROM named
        WHERE norm_name IN (
            SELECT norm_name
            FROM named
            GROUP BY norm_name
            HAVING COUNT(DISTINCT file_sha) > 1
        )
    """).fetchdf()
    df["first_commit_at"] = to_utc_naive(df["first_commit_at"])
    return df


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def save(fig, filename):
    path = OUTPUT_DIR / filename
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  saved {path}")


def skip(filename, reason):
    print(f"  skipped {filename}: {reason}")


def add_group_rank(dups):
    """Order each group by first_commit_at; rank 0 is the earliest instance."""
    dups = dups.sort_values(["file_sha", "first_commit_at"], na_position="last")
    return dups.assign(rank_in_group=dups.groupby("file_sha").cumcount())


# ---------------------------------------------------------
# Charts
# ---------------------------------------------------------

def chart_unique_vs_duplicate(total, dups):
    filename = "01_unique_vs_duplicate.png"
    if total == 0:
        return skip(filename, "artifacts table is empty")

    n_groups = dups["file_sha"].nunique()
    n_in_groups = len(dups)
    counts = pd.Series({
        "Unique content": total - n_in_groups,
        "First instance of\nduplicated content": n_groups,
        "Redundant copies": n_in_groups - n_groups,
    })

    fig, ax = plt.subplots()
    bars = ax.bar(counts.index, counts.values, color=["#4C72B0", "#55A868", "#C44E52"])
    ax.bar_label(bars, labels=[f"{v:,}\n({v / total:.1%})" for v in counts.values])
    ax.set_ylabel("Artifacts")
    ax.set_title(f"How much of the dataset is identical copies? ({total:,} artifacts)")
    ax.margins(y=0.15)
    save(fig, filename)


def chart_group_size_distribution(dups):
    """
    Group sizes have a long tail (2 up to 100+), so plotting every size as its
    own bar is unreadable. Sizes are binned into ranges instead, and shown two
    ways: how many groups fall in each range (left) and how many artifacts
    those groups contain (right). The right panel shows that the few large
    groups account for a big share of the duplicated artifacts.
    """
    filename = "02_group_size_distribution.png"
    if dups.empty:
        return skip(filename, "no duplicate groups")

    group_sizes = dups.groupby("file_sha").size()
    n_groups = len(group_sizes)
    n_artifacts = int(group_sizes.sum())

    # Left edges of each bin; right=False means [2, 3), [3, 4), ... [101, inf)
    edges = [2, 3, 4, 5, 6, 11, 21, 51, 101, float("inf")]
    labels = ["2", "3", "4", "5", "6–10", "11–20", "21–50", "51–100", "101+"]
    size_bin = pd.cut(group_sizes, bins=edges, labels=labels, right=False)

    groups_per_bin = size_bin.value_counts(sort=False)
    artifacts_per_bin = group_sizes.groupby(size_bin, observed=False).sum()

    # Drop empty bins at the top end (e.g. no groups of 101+ in a small sample)
    last = max(i for i, v in enumerate(groups_per_bin.values) if v > 0)
    groups_per_bin = groups_per_bin.iloc[: last + 1]
    artifacts_per_bin = artifacts_per_bin.iloc[: last + 1]
    x = groups_per_bin.index.astype(str)

    def pct_label(share):
        return "<1%" if 0 < share < 0.005 else f"{share:.0%}"

    fig, (ax_groups, ax_artifacts) = plt.subplots(1, 2, figsize=(13, 5.5))

    panels = [
        (ax_groups, groups_per_bin, n_groups, "#4C72B0",
         "How many groups are this size?", "Duplicate groups"),
        (ax_artifacts, artifacts_per_bin, n_artifacts, "#C44E52",
         "How many artifacts sit in groups this size?", "Artifacts in those groups"),
    ]
    for ax, values, total, color, title, ylabel in panels:
        bars = ax.bar(x, values.values, color=color)
        ax.bar_label(
            bars,
            labels=[f"{v:,}\n({pct_label(v / total)})" for v in values.values],
            fontsize=9,
        )
        # Bars after "5" cover ranges of sizes, so mark where that switch happens
        if "6–10" in list(x):
            split = list(x).index("6–10") - 0.5
            ax.axvline(split, color="grey", linestyle="--", linewidth=0.8)
            ax.text(split + 0.1, 0.97, "size ranges →", transform=ax.get_xaxis_transform(),
                    fontsize=8, color="grey", va="top")
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Group size (artifacts sharing the same file_sha)")
        ax.set_ylabel(ylabel)
        ax.grid(axis="x", visible=False)
        ax.margins(y=0.18)
        ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))

    pairs_share = groups_per_bin.get("2", 0) / n_groups
    big = group_sizes >= 11
    fig.suptitle(
        f"{n_groups:,} duplicate groups: {pairs_share:.0%} are simple pairs, "
        f"but the {big.sum():,} groups of 11+ hold "
        f"{group_sizes[big].sum() / n_artifacts:.0%} of duplicated artifacts",
        fontsize=12.5,
    )
    save(fig, filename)


def chart_largest_groups(summary):
    filename = "03_largest_groups.png"
    if summary.empty:
        return skip(filename, "no duplicate groups")

    top = summary.head(TOP_N).iloc[::-1]
    labels = [
        f"{name if isinstance(name, str) and name.strip() else '(no name)'}  [{sha[:8]}]"
        for name, sha in zip(top["earliest_artifact_name"], top["file_sha"].astype(str))
    ]

    fig, ax = plt.subplots(figsize=(10, max(4, 0.45 * len(top) + 1.5)))
    bars = ax.barh(labels, top["artifact_count"], color="#C44E52")
    ax.bar_label(bars, padding=3)
    ax.set_xlabel("Identical copies")
    ax.set_title(f"Top {len(top)} most-duplicated artifacts (earliest name, file_sha)")
    ax.margins(x=0.1)
    save(fig, filename)


def chart_top_source_repos(dups):
    filename = "04_top_source_repos.png"
    primaries = (
        dups[dups["dedup_primary"] == 1]
        .drop_duplicates("file_sha")[["file_sha", "repo_full_name"]]
        .rename(columns={"repo_full_name": "primary_repo"})
    )
    copies = dups[dups["dedup_primary"] == 0].merge(primaries, on="file_sha", how="inner")
    if copies.empty:
        return skip(filename, "no non-primary copies linked to a primary")

    copies = copies.assign(
        location=(copies["repo_full_name"] == copies["primary_repo"]).map(
            {True: "Same repo", False: "Other repos"}
        )
    )
    table = copies.pivot_table(
        index="primary_repo", columns="location", values="file_sha",
        aggfunc="count", fill_value=0,
    )
    for col in ("Other repos", "Same repo"):
        if col not in table.columns:
            table[col] = 0
    table["total"] = table["Other repos"] + table["Same repo"]
    top = table.nlargest(TOP_N, "total").iloc[::-1]

    fig, ax = plt.subplots(figsize=(10, max(4, 0.45 * len(top) + 1.5)))
    ax.barh(top.index, top["Other repos"], color="#C44E52", label="Copied into other repos")
    ax.barh(top.index, top["Same repo"], left=top["Other repos"], color="#DD8452",
            label="Copied within the same repo")
    for y, total in enumerate(top["total"]):
        ax.text(total, y, f" {total}", va="center")
    ax.set_xlabel("Non-primary copies")
    ax.set_title("Repos whose primary artifacts are copied the most")
    ax.legend(loc="lower right")
    ax.margins(x=0.1)
    save(fig, filename)


def chart_copy_lag(dups):
    filename = "05_copy_lag.png"
    ranked = add_group_rank(dups)
    earliest = ranked.groupby("file_sha")["first_commit_at"].transform("min")
    lag_days = (ranked["first_commit_at"] - earliest).dt.total_seconds() / 86400
    lag_days = lag_days[ranked["rank_in_group"] > 0].dropna()
    if lag_days.empty:
        return skip(filename, "no copies with usable first_commit_at")

    buckets = pd.cut(
        lag_days,
        bins=[0, 1, 7, 30, 90, 365, float("inf")],
        labels=["< 1 day", "1-7 days", "1-4 weeks", "1-3 months", "3-12 months", "> 1 year"],
        right=False,
    ).value_counts(sort=False)

    fig, ax = plt.subplots()
    bars = ax.bar(buckets.index.astype(str), buckets.values, color="#8172B2")
    ax.bar_label(bars)
    ax.set_xlabel("Time between the group's first appearance and this copy")
    ax.set_ylabel("Copies")
    ax.set_title(f"How quickly does content get copied? (median lag: {lag_days.median():.0f} days)")
    ax.margins(y=0.1)
    save(fig, filename)


def chart_copies_over_time(dups):
    filename = "06_copies_over_time.png"
    ranked = add_group_rank(dups).dropna(subset=["first_commit_at"])
    if ranked.empty:
        return skip(filename, "no usable first_commit_at values")

    ranked = ranked.assign(
        month=ranked["first_commit_at"].dt.to_period("M").dt.to_timestamp(),
        kind=ranked["rank_in_group"].map(lambda r: "Earliest instance" if r == 0 else "Later copy"),
    )
    monthly = ranked.pivot_table(index="month", columns="kind", values="file_sha",
                                 aggfunc="count", fill_value=0)
    full_range = pd.date_range(monthly.index.min(), monthly.index.max(), freq="MS")
    monthly = monthly.reindex(full_range, fill_value=0)

    fig, ax = plt.subplots()
    colors = {"Earliest instance": "#55A868", "Later copy": "#C44E52"}
    for kind in monthly.columns:
        ax.plot(monthly.index, monthly[kind], marker="o", markersize=3,
                label=kind, color=colors.get(kind))
    ax.set_xlabel("Month of first commit")
    ax.set_ylabel("Artifacts")
    ax.set_title("Duplicated content over time: originals vs. later copies")
    ax.legend()
    fig.autofmt_xdate()
    save(fig, filename)


def chart_primary_check(dups):
    filename = "07_dedup_primary_check.png"
    if dups.empty:
        return skip(filename, "no duplicate groups")

    per_group = dups.groupby("file_sha")["dedup_primary"].sum()
    labels = ["0 primaries", "Exactly 1 primary", "2+ primaries"]
    counts = pd.cut(per_group, bins=[-1, 0, 1, float("inf")], labels=labels).value_counts(sort=False)

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(counts.index.astype(str), counts.values,
                  color=["#C44E52", "#55A868", "#DD8452"])
    ax.bar_label(bars, labels=[f"{v:,} ({v / len(per_group):.1%})" for v in counts.values])
    ax.set_ylabel("Duplicate groups")
    ax.set_title(f"dedup_primary check across {len(per_group):,} duplicate groups")
    ax.margins(y=0.15)
    save(fig, filename)


def compare_name_variants(variants):
    """Score each distinct variant of a name against that name's earliest version."""
    variants = (
        variants.sort_values(["norm_name", "first_commit_at"], na_position="last")
        .drop_duplicates(["norm_name", "file_sha"], keep="first")
    )
    rows = []
    for norm_name, group in variants.groupby("norm_name", sort=False):
        baseline = group.iloc[0]
        base_text = str(baseline["content"])[:MAX_CONTENT_CHARS]
        for _, other in group.iloc[1:MAX_VARIANTS_PER_NAME].iterrows():
            rows.append({
                "name": baseline["name"],
                "similarity": fuzz.ratio(base_text, str(other["content"])[:MAX_CONTENT_CHARS]),
                "baseline_repo": baseline["repo_full_name"],
                "baseline_path": baseline["path"],
                "baseline_sha": baseline["file_sha"],
                "baseline_first_commit": baseline["first_commit_at"],
                "variant_repo": other["repo_full_name"],
                "variant_path": other["path"],
                "variant_sha": other["file_sha"],
                "variant_first_commit": other["first_commit_at"],
            })
    return pd.DataFrame(rows)


def chart_name_variant_similarity(pairs):
    filename = "08_name_variant_similarity.png"
    if pairs.empty:
        return skip(filename, "no names with more than one distinct content version")

    fig, ax = plt.subplots()
    ax.hist(pairs["similarity"], bins=range(0, 105, 5), color="#4C72B0", edgecolor="white")
    ax.axvspan(90, 100, color="#C44E52", alpha=0.12, zorder=0, label="≥ 90: minor edits")
    ax.axvspan(50, 90, color="#DD8452", alpha=0.10, zorder=0, label="50-90: substantial edits")
    ax.set_xlim(0, 100)
    ax.set_xlabel("Content similarity to earliest version of the same name (rapidfuzz ratio)")
    ax.set_ylabel("Variant artifacts")
    minor = (pairs["similarity"] >= 90).sum()
    ax.set_title(f"Same name, different content: {len(pairs):,} variants, "
                 f"{minor:,} are minor edits")
    ax.legend()
    save(fig, filename)

    csv_path = OUTPUT_DIR / "name_variant_pairs.csv"
    pairs.sort_values("similarity", ascending=False).to_csv(csv_path, index=False)
    print(f"  saved {csv_path}")


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    if not Path(DB_PATH).exists():
        raise SystemExit(f"Database not found: {Path(DB_PATH).resolve()}")
    OUTPUT_DIR.mkdir(exist_ok=True)

    con = duckdb.connect()
    try:
        con.execute(f"ATTACH '{DB_PATH}' AS GitSkills (READ_ONLY)")

        print("Loading data...")
        total = load_total_count(con)
        dups = load_duplicate_artifacts(con)
        summary = load_group_summary(con)
        variants = load_name_variants(con)
    finally:
        con.close()

    print(f"  {total:,} artifacts, {len(dups):,} in "
          f"{dups['file_sha'].nunique():,} duplicate groups")

    print("\nBuilding charts...")
    chart_unique_vs_duplicate(total, dups)
    chart_group_size_distribution(dups)
    chart_largest_groups(summary)
    chart_top_source_repos(dups)
    chart_copy_lag(dups)
    chart_copies_over_time(dups)
    chart_primary_check(dups)

    print("\nComparing same-name variants with rapidfuzz...")
    pairs = compare_name_variants(variants)
    chart_name_variant_similarity(pairs)

    print(f"\nDone. Charts are in {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
