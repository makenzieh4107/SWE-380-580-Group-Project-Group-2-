"""
Content similarity analysis for GitSkills artifacts.

Pipeline
--------
1. Load every artifact from the GitSkills database.
2. Filter out the exact copies (dedup_primary = 0), keeping one row per
   unique file. Only primary rows have their content stored anyway.
3. Measure how similar the remaining artifacts' content is to each other,
   as a percentage (100% = identical text).
4. Save CSV results and charts to output/content_similarity/.

Why two stages?
---------------
There are ~13,000 unique artifacts, which is ~84 million possible pairs.
Fuzzy-comparing every pair of multi-kilobyte files would take many hours.
So we:
  a) use MinHash + LSH (a standard near-duplicate detection technique) to
     quickly find candidate pairs that share a lot of wording, then
  b) score each candidate pair precisely with RapidFuzz.
Pairs that LSH never pairs up share very little wording (roughly < 40%
overlap), so they are reported as "no close match".

A separate analysis compares ALL pairs among artifacts that share the same
skill name (e.g. every "code-review" skill), which does not depend on LSH.

Run from PyCharm or a terminal:  python src/content_similarity.py
"""

from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
import re
import time
import zlib

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from rapidfuzz import fuzz

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # works from any working dir
DB_PATH = PROJECT_ROOT / "data" / "agent_skills_sample.db"
OUTPUT_DIR = PROJECT_ROOT / "output" / "content_similarity"

RANDOM_SEED = 42            # fixed seed so every run gives the same results
SHINGLE_WORDS = 5           # MinHash compares overlapping 5-word phrases
NUM_PERM = 128              # MinHash signature length
LSH_BANDS = 32              # 32 bands x 4 rows -> pairs with ~40%+ overlap become candidates
MAX_BUCKET_SIZE = 500       # skip huge LSH buckets (shared boilerplate) to bound runtime
MAX_COMPARE_CHARS = 30_000  # cap text length for RapidFuzz (affects ~2% of files)
NEAR_DUPLICATE = 90         # similarity % at or above which we call files near-duplicates
SAME_NAME_MIN_GROUP = 5     # name groups need at least this many artifacts
SHOW_CHARTS = True          # open chart windows at the end (PNG files are saved either way)

BANDS = [  # best-match categories used in the summary and chart
    (90, 101, "Near-duplicate (90-100%)"),
    (70, 90, "Heavily reused (70-89%)"),
    (50, 70, "Partly similar (50-69%)"),
    (0, 50, "Weak match (<50%)"),
]
NO_MATCH = "No close match"


# ---------------------------------------------------------------------------
# Step 1 and 2: load and filter
# ---------------------------------------------------------------------------
def load_artifacts() -> pd.DataFrame:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}. See data/README.md.")
    con = duckdb.connect()
    con.execute(f"ATTACH '{DB_PATH.as_posix()}' AS GitSkills (TYPE sqlite)")
    df = con.execute("""
        SELECT repo_full_name, path, file_sha, name, location_class,
               dedup_primary, content
        FROM GitSkills.artifacts
    """).fetchdf()
    con.close()
    return df


def filter_primary(df: pd.DataFrame) -> pd.DataFrame:
    kept = df[df["dedup_primary"] == 1].copy()
    kept = kept[kept["content"].notna() & (kept["content"].str.strip() != "")]
    kept = kept.reset_index(drop=True)

    print("Step 1-2: Filter out exact copies (dedup_primary = 0)")
    print(f"  Total artifacts:            {len(df):>7,}")
    print(f"  Removed (dedup_primary=0):  {(df['dedup_primary'] == 0).sum():>7,}")
    print(f"  Kept unique artifacts:      {len(kept):>7,}\n")
    return kept


# ---------------------------------------------------------------------------
# Step 3a: MinHash + LSH candidate pairs
# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    """Lowercase and collapse whitespace so formatting changes don't count."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def minhash_signatures(texts: list[str]) -> np.ndarray:
    prime = np.uint64((1 << 31) - 1)
    rng = np.random.default_rng(RANDOM_SEED)
    a = rng.integers(1, prime, NUM_PERM, dtype=np.uint64)[:, None]
    b = rng.integers(0, prime, NUM_PERM, dtype=np.uint64)[:, None]

    sigs = np.empty((len(texts), NUM_PERM), dtype=np.uint64)
    for i, text in enumerate(texts):
        words = text.split()
        if len(words) < SHINGLE_WORDS:
            shingles = {" ".join(words)}
        else:
            shingles = {" ".join(words[j:j + SHINGLE_WORDS])
                        for j in range(len(words) - SHINGLE_WORDS + 1)}
        # crc32 instead of hash(): deterministic across runs and machines
        hashes = np.fromiter((zlib.crc32(s.encode()) for s in shingles),
                             dtype=np.uint64, count=len(shingles)) % prime
        sigs[i] = ((a * hashes + b) % prime).min(axis=1)
    return sigs


def lsh_candidate_pairs(sigs: np.ndarray) -> set[tuple[int, int]]:
    rows = NUM_PERM // LSH_BANDS
    pairs = set()
    skipped = 0
    for band in range(LSH_BANDS):
        buckets = defaultdict(list)
        chunk = sigs[:, band * rows:(band + 1) * rows]
        for i, row in enumerate(chunk):
            buckets[row.tobytes()].append(i)
        for members in buckets.values():
            if len(members) < 2:
                continue
            if len(members) > MAX_BUCKET_SIZE:
                skipped += 1
                continue
            pairs.update(combinations(members, 2))
    if skipped:
        print(f"  Note: skipped {skipped} oversized LSH buckets (shared boilerplate)")
    return pairs


# ---------------------------------------------------------------------------
# Step 3b: precise similarity with RapidFuzz
# ---------------------------------------------------------------------------
def similarity(t1: str, t2: str) -> float:
    """Character-level similarity in percent (RapidFuzz Indel ratio)."""
    return fuzz.ratio(t1[:MAX_COMPARE_CHARS], t2[:MAX_COMPARE_CHARS])


def score_pairs(df: pd.DataFrame, texts: list[str],
                pairs: set[tuple[int, int]]) -> pd.DataFrame:
    rows = []
    for n, (i, j) in enumerate(sorted(pairs), 1):
        rows.append((i, j, similarity(texts[i], texts[j])))
        if n % 20_000 == 0:
            print(f"    scored {n:,} / {len(pairs):,} pairs")
    scored = pd.DataFrame(rows, columns=["i", "j", "similarity_pct"])
    for side in ("i", "j"):
        info = df.loc[scored[side], ["repo_full_name", "path", "name"]].reset_index(drop=True)
        info.columns = [f"{c}_{side}" for c in info.columns]
        scored = pd.concat([scored, info], axis=1)
    return scored.sort_values("similarity_pct", ascending=False).reset_index(drop=True)


def best_match_per_artifact(df: pd.DataFrame, scored: pd.DataFrame) -> pd.DataFrame:
    both = pd.concat([
        scored[["i", "j", "similarity_pct"]].rename(columns={"i": "idx", "j": "match"}),
        scored[["j", "i", "similarity_pct"]].rename(columns={"j": "idx", "i": "match"}),
    ])
    best = both.sort_values("similarity_pct", ascending=False).drop_duplicates("idx")
    best = best.set_index("idx")

    out = df[["repo_full_name", "path", "name", "location_class"]].copy()
    out["best_match_pct"] = best["similarity_pct"].reindex(out.index)
    match_idx = best["match"].reindex(out.index)
    out["best_match_repo"] = df["repo_full_name"].reindex(match_idx).values
    out["best_match_path"] = df["path"].reindex(match_idx).values

    def band(pct):
        if pd.isna(pct):
            return NO_MATCH
        return next(label for lo, hi, label in BANDS if lo <= pct < hi)

    out["band"] = out["best_match_pct"].apply(band)
    return out


# ---------------------------------------------------------------------------
# Extra analysis: do skills with the same name have the same content?
# ---------------------------------------------------------------------------
def same_name_similarity(df: pd.DataFrame, texts: list[str]) -> pd.DataFrame:
    names = df["name"].fillna("").str.strip().str.lower()
    rows = []
    for name, idx in names.groupby(names).groups.items():
        if not name or len(idx) < SAME_NAME_MIN_GROUP:
            continue
        for i, j in combinations(idx, 2):
            rows.append((name, len(idx), similarity(texts[i], texts[j])))
    return pd.DataFrame(rows, columns=["name", "group_size", "similarity_pct"])


# ---------------------------------------------------------------------------
# Near-duplicate clusters (union-find over pairs >= NEAR_DUPLICATE)
# ---------------------------------------------------------------------------
def near_duplicate_clusters(df: pd.DataFrame, scored: pd.DataFrame) -> pd.DataFrame:
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in scored.loc[scored["similarity_pct"] >= NEAR_DUPLICATE, ["i", "j"]].itertuples(index=False):
        parent[find(i)] = find(j)

    members = defaultdict(list)
    for x in list(parent):
        members[find(x)].append(x)

    rows = []
    for idx in members.values():
        names = Counter(df.loc[idx, "name"].fillna("(no name)"))
        rows.append({
            "cluster_size": len(idx),
            "most_common_name": names.most_common(1)[0][0],
            "distinct_repos": df.loc[idx, "repo_full_name"].nunique(),
        })
    return pd.DataFrame(rows).sort_values("cluster_size", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def save(fig, filename):
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / filename, dpi=150)
    print(f"  saved {filename}")


def chart_filter(total, removed, kept):
    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(["All artifacts", "Exact copies removed\n(dedup_primary = 0)", "Unique artifacts kept"],
                  [total, removed, kept], color=["#7f8c8d", "#c0392b", "#2980b9"])
    ax.bar_label(bars, labels=[f"{v:,}" for v in (total, removed, kept)], padding=3)
    ax.set_ylabel("Artifacts")
    ax.set_title(f"{removed / total:.0%} of artifacts are exact copies of another file")
    ax.margins(y=0.12)
    save(fig, "01_dedup_filter.png")


def chart_pair_histogram(scored):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(scored["similarity_pct"], bins=range(0, 102, 2), color="#2980b9", edgecolor="white")
    ax.axvline(NEAR_DUPLICATE, color="#c0392b", linestyle="--", label=f"Near-duplicate ({NEAR_DUPLICATE}%)")
    ax.set_xlabel("Content similarity (%)")
    ax.set_ylabel("Number of artifact pairs")
    ax.set_title("Similarity of candidate pairs that share wording")
    ax.legend()
    save(fig, "02_pair_similarity_histogram.png")


def chart_bands(best):
    order = [label for _, _, label in BANDS] + [NO_MATCH]
    pct = best["band"].value_counts(normalize=True).reindex(order, fill_value=0) * 100
    counts = best["band"].value_counts().reindex(order, fill_value=0)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.barh(order[::-1], pct[order[::-1]],
                   color=["#95a5a6", "#f1c40f", "#e67e22", "#d35400", "#c0392b"])
    ax.bar_label(bars, labels=[f"{p:.1f}%  ({c:,})" for p, c in zip(pct[order[::-1]], counts[order[::-1]])],
                 padding=3)
    ax.set_xlabel("% of unique artifacts")
    ax.set_title("How similar is each artifact to its closest other artifact?")
    ax.margins(x=0.35)
    save(fig, "03_best_match_bands.png")


def chart_same_name(same_name, top_n=12):
    if same_name.empty:
        return
    top = (same_name.groupby("name")["group_size"].first()
           .sort_values(ascending=False).head(top_n).index)
    data = [same_name.loc[same_name["name"] == n, "similarity_pct"] for n in top]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.boxplot(data, orientation="horizontal", tick_labels=[f"{n} (n={same_name.loc[same_name['name'] == n, 'group_size'].iat[0]})"
                                              for n in top])
    ax.invert_yaxis()
    ax.axvline(NEAR_DUPLICATE, color="#c0392b", linestyle="--", linewidth=1)
    ax.set_xlabel("Pairwise content similarity (%)")
    ax.set_title("Do skills with the same name contain the same content?")
    save(fig, "04_same_name_similarity.png")


def chart_clusters(clusters, top_n=15):
    if clusters.empty:
        return
    top = clusters.head(top_n).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    bars = ax.barh([f"{r.most_common_name} ({r.distinct_repos} repos)" for r in top.itertuples()],
                   top["cluster_size"], color="#8e44ad")
    ax.bar_label(bars, padding=3)
    ax.set_xlabel("Artifacts in cluster (unique files, after removing exact copies)")
    ax.set_title(f"Largest near-duplicate clusters (>= {NEAR_DUPLICATE}% similar)")
    ax.margins(x=0.1)
    save(fig, "05_near_duplicate_clusters.png")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    start = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_artifacts = load_artifacts()
    df = filter_primary(all_artifacts)
    texts = [normalize(t) for t in df["content"]]

    print("Step 3: Compare content")
    print("  Building MinHash signatures...")
    sigs = minhash_signatures(texts)
    pairs = lsh_candidate_pairs(sigs)
    print(f"  Candidate pairs from LSH: {len(pairs):,} (out of {len(df) * (len(df) - 1) // 2:,} possible)")
    print("  Scoring candidate pairs with RapidFuzz...")
    scored = score_pairs(df, texts, pairs)
    best = best_match_per_artifact(df, scored)
    clusters = near_duplicate_clusters(df, scored)
    print("  Comparing artifacts that share a skill name...")
    same_name = same_name_similarity(df, texts)

    # ---- console summary ----
    print("\nResults")
    print("  Closest match for each unique artifact:")
    for label, count in best["band"].value_counts().items():
        print(f"    {label:<26} {count:>6,}  ({count / len(best):.1%})")
    if not scored.empty:
        print(f"  Median similarity of candidate pairs: {scored['similarity_pct'].median():.1f}%")
    print(f"  Near-duplicate clusters (>= {NEAR_DUPLICATE}%): {len(clusters):,} "
          f"covering {clusters['cluster_size'].sum() if not clusters.empty else 0:,} artifacts")
    if not same_name.empty:
        summary = (same_name.groupby("name")
                   .agg(group_size=("group_size", "first"), median_pct=("similarity_pct", "median"))
                   .sort_values("group_size", ascending=False))
        print(f"\n  Same-name groups (>= {SAME_NAME_MIN_GROUP} artifacts), top 10:")
        print(summary.head(10).round(1).to_string())

    # ---- files ----
    print(f"\nSaving results to {OUTPUT_DIR}")
    scored.drop(columns=["i", "j"]).to_csv(OUTPUT_DIR / "similar_pairs.csv", index=False)
    best.to_csv(OUTPUT_DIR / "best_match_per_artifact.csv", index=False)
    clusters.to_csv(OUTPUT_DIR / "near_duplicate_clusters.csv", index=False)
    same_name.to_csv(OUTPUT_DIR / "same_name_pairs.csv", index=False)
    print("  saved 4 CSV files")

    removed = int((all_artifacts["dedup_primary"] == 0).sum())
    chart_filter(len(all_artifacts), removed, len(df))
    chart_pair_histogram(scored)
    chart_bands(best)
    chart_same_name(same_name)
    chart_clusters(clusters)

    print(f"\nDone in {time.time() - start:.0f} seconds.")
    if SHOW_CHARTS:
        plt.show()


if __name__ == "__main__":
    main()
