"""
Safe reviewer report for the existing Cisco scan outputs.

Reads the outputs your pipeline already writes and produces a report that a
reviewer can work from without the report re-publishing anything dangerous:

  results/expanded_scan/cisco_all_scan_reports.json   (required)
  results/expanded_scan/baseline_variant_pair_comparison.csv   (optional)
  charts/name_variant_pairs.csv                        (optional; commit dates for the order check)
  results/expanded_scan/cisco_scan_errors.csv          (optional)

Writes, to --out (default results/expanded_scan/safe_report/):

  safe_report.md             reader-facing report, prioritized for review
  safe_report.json           same content, machine-readable
  review_queue.csv           one row per non-INFO finding, sanitized, for labeling

What is removed or changed before anything is written:
  * live secrets            -> [REDACTED:<kind>:<length>]; secret_exposure snippets withheld
  * webhook / bot tokens    -> token part of the URL removed
  * URLs                    -> defanged (hxxps://host[.]tld/...)
  * IPv4 addresses          -> defanged (178[.]128[.]214[.]12)
  * local paths             -> skill_path and any C:\\Users\\... or /home/... become <LOCAL_PATH>
  * HTML / Markdown         -> escaped in table cells
  * hidden Unicode          -> stripped before redaction, count noted
  * snippets                -> one line, max 120 characters

What is kept so a reviewer can go back to the source:
  repo, path, file_sha, rule_id, category, severity, file_path, line_number,
  and snippet_sha256 (SHA-256 of the un-redacted snippet line).

Nothing is executed. Input is read as JSON/CSV only.

Usage (from the repository root):
    python src/safe_report.py
    python src/safe_report.py --include-info     # also list the INFO-level findings
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SEVERITY_ORDER = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
SNIPPET_LIMIT = 120
EXAMPLES_PER_RULE = 3
LOCATION_ONLY_CATEGORIES = {"hardcoded_secrets"}
NOISE_RULES = {"MANIFEST_MISSING_LICENSE"}  # 1,427 INFO findings in the expanded scan

HIDDEN_RE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff\u00ad]")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

SECRET_PATTERNS = [
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("api_key", re.compile(r"\bsk-(proj-|ant-)?[A-Za-z0-9_\-]{16,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{8,}\b")),
    ("google_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(-----END [A-Z ]*PRIVATE KEY-----|$)", re.S)),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")),
]
TOKEN_URL_PATTERNS = [
    (re.compile(r"(discord(?:app)?\.com/api/webhooks/)[^\s'\"`)>]+", re.I), r"\1[REDACTED:webhook_token]"),
    (re.compile(r"(hooks\.slack\.com/services/)[^\s'\"`)>]+", re.I), r"\1[REDACTED:webhook_token]"),
    (re.compile(r"(api\.telegram\.org/bot)[^\s/'\"`)>]+", re.I), r"\1[REDACTED:bot_token]"),
]
CONN_STRING_RE = re.compile(r"\b([a-z][a-z0-9+]{1,15}://)([^\s:/@'\"]+):([^\s@/'\"]+)@", re.I)
ASSIGN_RE = re.compile(
    r"(?i)\b((?:api[_-]?key|secret|token|passw(?:or)?d|pwd|access[_-]?key|auth)[\w-]*\s*[:=]\s*['\"]?)"
    r"([^\s'\",;]{6,})")
PLACEHOLDER_RE = re.compile(r"(?i)(your[_-]|<|\$\{|\$[A-Z_]|xxx|\*\*\*|example|changeme|placeholder|dummy|test)")
URL_RE = re.compile(r"\b(https?|ftp|wss?)://([^\s/'\"`<>)]+)([^\s'\"`<>)]*)", re.I)
IP_RE = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")
LOCAL_PATH_RE = re.compile(r"([A-Za-z]:\\+Users\\+[^\\\s]+|/home/[^/\s]+|/Users/[^/\s]+|/root)(?=[\\/\s]|$)")


def redact(text: str) -> str:
    for pat, repl in TOKEN_URL_PATTERNS:
        text = pat.sub(repl, text)
    for kind, pat in SECRET_PATTERNS:
        text = pat.sub(lambda m, k=kind: f"[REDACTED:{k}:{len(m.group(0))}]", text)
    text = CONN_STRING_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}:[REDACTED:password]@", text)

    def assign(m):
        v = m.group(2)
        if PLACEHOLDER_RE.search(v) or v.startswith("[REDACTED"):
            return m.group(0)
        return f"{m.group(1)}[REDACTED:value:{len(v)}]"
    return ASSIGN_RE.sub(assign, text)


def defang(text: str) -> str:
    scheme_map = {"http": "hxxp", "https": "hxxps", "ftp": "fxp", "ws": "wxs", "wss": "wxss"}

    def url(m):
        s = scheme_map.get(m.group(1).lower(), m.group(1))
        return f"{s}://{m.group(2).replace('.', '[.]')}{m.group(3)}"
    text = URL_RE.sub(url, text)
    return IP_RE.sub(r"\1[.]\2[.]\3[.]\4", text)


def scrub_paths(text: str) -> str:
    return LOCAL_PATH_RE.sub("<LOCAL_PATH>", text or "")


def sanitize(text: str, limit: int = SNIPPET_LIMIT) -> tuple[str, int]:
    text = text or ""
    hidden = len(HIDDEN_RE.findall(text))
    text = HIDDEN_RE.sub("", text)
    text = CONTROL_RE.sub("", text).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = scrub_paths(redact(text))
    text = defang(text)
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text, hidden


def md_cell(text: str) -> str:
    text = html.escape(str(text), quote=True)
    for ch in "\\`*_[]|#!":
        text = text.replace(ch, "\\" + ch)
    return text.replace("\n", " ")


def norm_snippet(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\r", "")).strip()


def load_reports(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for key, entry in data.get("scans", {}).items():
        rep = entry.get("report") or {}
        meta = rep.get("scan_metadata") or {}
        out.append({
            "key": key,
            "repo": entry.get("repo_full_name", ""),
            "path": entry.get("path", ""),
            "sha": entry.get("file_sha", ""),
            "name": entry.get("name", ""),
            "description": entry.get("description", ""),
            "scan_status": entry.get("scan_status", ""),
            "error": entry.get("error") or "",
            "policy_fingerprint": meta.get("policy_fingerprint_sha256", ""),
            "policy_name": meta.get("policy_name", ""),
            "findings": rep.get("findings", []) or [],
        })
    return out


def flatten(reports: list[dict], include_info: bool) -> list[dict]:
    rows = []
    for r in reports:
        for f in r["findings"]:
            sev = (f.get("severity") or "INFO").upper()
            if sev == "INFO" and not include_info:
                continue
            if f.get("rule_id") in NOISE_RULES and not include_info:
                continue
            raw_line = f.get("snippet") or ""
            snippet, hidden = sanitize(raw_line)
            category = f.get("category", "")
            note = []
            if category in LOCATION_ONLY_CATEGORIES:
                snippet = "[withheld: credential-shaped value; see location]"
            if hidden:
                note.append(f"{hidden} hidden Unicode characters removed")
            rows.append({
                "repo": r["repo"],
                "path": scrub_paths(r["path"]),
                "file_sha": r["sha"],
                "rule_id": f.get("rule_id", ""),
                "category": category,
                "severity": sev,
                "file": scrub_paths(f.get("file_path") or ""),
                "line": f.get("line_number"),
                "analyzer": f.get("analyzer", ""),
                "snippet": snippet,
                "snippet_sha256": hashlib.sha256(raw_line.encode("utf-8")).hexdigest(),
                "note": "; ".join(note),
                "_norm": norm_snippet(raw_line),
            })
    return rows


def dedupe(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        key = (r["rule_id"], r["repo"], r["path"], r["file"], r["_norm"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def load_pair_dates(path: Path | None) -> dict:
    """Commit dates live in charts/name_variant_pairs.csv, not in the comparison file."""
    if not path or not path.exists():
        return {}
    out = {}
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        k = (r.get("baseline_repo"), r.get("baseline_path"), r.get("variant_repo"), r.get("variant_path"))
        out[k] = (r.get("baseline_first_commit", ""), r.get("variant_first_commit", ""))
    return out


def load_pairs(path: Path | None, dates: dict | None = None) -> list[dict]:
    if not path or not path.exists():
        return []
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    dates = dates or {}
    out = []
    for r in rows:
        bd, vd = dates.get((r.get("baseline_repo"), r.get("baseline_path"),
                            r.get("variant_repo"), r.get("variant_path")), ("", ""))
        try:
            sim = float(r.get("similarity") or 0)
        except ValueError:
            sim = 0.0
        out.append({
            "name": r.get("name", ""),
            "similarity": round(sim, 2),
            "baseline": f"{r.get('baseline_repo','')} / {scrub_paths(r.get('baseline_path',''))}",
            "variant": f"{r.get('variant_repo','')} / {scrub_paths(r.get('variant_path',''))}",
            "baseline_findings": r.get("baseline_findings_count", ""),
            "variant_findings": r.get("variant_findings_count", ""),
            "variant_minus_baseline": r.get("variant_minus_baseline", ""),
            "pair_outcome": r.get("pair_outcome", ""),
            "baseline_categories": r.get("baseline_categories", ""),
            "variant_categories": r.get("variant_categories", ""),
            "baseline_severities": r.get("baseline_severities", ""),
            "variant_severities": r.get("variant_severities", ""),
            "baseline_repo": r.get("baseline_repo", ""),
            "variant_repo": r.get("variant_repo", ""),
            "baseline_first_commit": bd,
            "variant_first_commit": vd,
        })
    return out


def load_errors(path: Path | None) -> list[dict]:
    if not path or not path.exists():
        return []
    return [{"repo": r.get("repo_full_name", ""), "path": scrub_paths(r.get("path", "")),
             "status": r.get("status", ""), "error": sanitize(r.get("error", ""), 160)[0]}
            for r in csv.DictReader(open(path, encoding="utf-8-sig"))]


def build(reports, rows, pairs, errors, include_info, source_name):
    counted = [r for r in rows if r["severity"] != "INFO"]
    by_sev = Counter(r["severity"] for r in counted)
    by_cat = Counter(r["category"] for r in counted)
    by_rule = Counter(r["rule_id"] for r in counted)
    artifacts_flagged = {(r["repo"], r["path"]) for r in counted}
    fingerprints = Counter(r["policy_fingerprint"] for r in reports)
    statuses = Counter(r["scan_status"] for r in reports)

    total_artifacts = len(reports)
    review = dedupe(sorted(counted, key=lambda r: (-SEVERITY_ORDER.index(r["severity"]), r["repo"], r["path"])))

    md = []
    w = md.append
    w("# Scan review report (safe to share)")
    w("")
    w("This report summarizes Cisco skill-scanner output for reviewers. Every row is a *finding* "
      "to check, not a verdict that a skill is malicious or that it changed in a copy. URLs are "
      "defanged, secrets redacted, local paths removed and snippets shortened on purpose. Use the "
      "`snippet_sha256` and `file_sha` values to find the exact line in the source data.")
    w("")
    w("## Provenance")
    w("")
    w(f"- Source file: `{source_name}`")
    w(f"- Artifacts scanned: {total_artifacts}; scan status: "
      + ", ".join(f"{k} {v}" for k, v in statuses.most_common()))
    w("- Policy fingerprint(s): " + ", ".join(f"`{k[:12]}…` ({v})" for k, v in fingerprints.most_common())
      + ("  (the default policy hash is `3f48e661…`; a corrected policy should show a different value)"
         if fingerprints and "3f48e661bfbc" in " ".join(fingerprints) else ""))
    w(f"- Findings excluded from this report as noise: "
      + ("none (`--include-info`)" if include_info else
         f"INFO-level `MANIFEST_MISSING_LICENSE` and similar; rerun with `--include-info` to list them"))
    w("")
    w("## Headline counts (non-INFO)")
    w("")
    w(f"- Artifacts with at least one non-INFO finding: **{len(artifacts_flagged)}** of {total_artifacts}")
    w(f"- Findings: {len(counted)} total, {len(review)} after removing repeats of the same rule and line text")
    w("")
    w("| Severity | Findings |")
    w("|---|---:|")
    for s in reversed(SEVERITY_ORDER):
        if by_sev.get(s):
            w(f"| {s} | {by_sev[s]} |")
    w("")
    w("| Category | Findings |")
    w("|---|---:|")
    for c, n in by_cat.most_common():
        w(f"| {md_cell(c)} | {n} |")
    w("")

    w("## Review queue, highest severity first")
    w("")
    w("Each row needs a reviewer decision: *real risk*, *expected for this skill*, or *not a risk*. "
      "Findings in security corpora or test fixtures are listed too; their paths make that visible.")
    w("")
    w("| # | Severity | Category | Rule | Repo | Path | file:line | Snippet (sanitized) |")
    w("|---:|---|---|---|---|---|---|---|")
    for i, r in enumerate(review[:150], 1):
        snippet = md_cell(r["snippet"]) + (f" *({md_cell(r['note'])})*" if r["note"] else "")
        loc = f"{md_cell(r['file'])}:{r['line']}" if r["file"] else str(r["line"] or "")
        w(f"| {i} | {r['severity']} | {md_cell(r['category'])} | `{md_cell(r['rule_id'])}` | "
          f"`{md_cell(r['repo'])}` | `{md_cell(r['path'])[:70]}` | {loc} | {snippet} |")
    if len(review) > 150:
        w("")
        w(f"Showing 150 of {len(review)}. The full list is in `review_queue.csv`.")
    w("")

    w("## Examples by rule")
    w("")
    w(f"Up to {EXAMPLES_PER_RULE} examples per rule, to show what each rule catches.")
    w("")
    grouped = defaultdict(list)
    for r in review:
        grouped[r["rule_id"]].append(r)
    for rule, _ in by_rule.most_common():
        items = grouped[rule][:EXAMPLES_PER_RULE]
        w(f"**{rule}** ({len(grouped[rule])} findings)")
        w("")
        for r in items:
            w(f"- {r['severity']} `{md_cell(r['repo'])}` `{md_cell(r['path'])[:70]}` "
              f"line {r['line']}: {md_cell(r['snippet'])}")
        w("")

    if pairs:
        w("## Baseline vs. variant pairs")
        w("")
        outcomes = Counter(p["pair_outcome"] for p in pairs)
        w(f"Pairs: {len(pairs)}. Outcome by finding count: "
          + ", ".join(f"{k or 'unknown'} {v}" for k, v in outcomes.most_common()) + ".")
        w("")
        w("Finding counts are a weak signal: a swapped finding and an unchanged one can look the same. "
          "Use the category and severity columns below, and check the order of the pair before "
          "calling anything 'introduced'. Only pairs at or above 60% similarity are listed first.")
        w("")
        w("| Name | Sim. | Outcome | Baseline → variant findings | Variant categories | Baseline repo | Variant repo | Order basis |")
        w("|---|---:|---|---|---|---|---|---|")
        interesting = [p for p in pairs if p["pair_outcome"].startswith("more findings in variant")]
        interesting.sort(key=lambda p: -p["similarity"])
        for p in interesting[:60]:
            order = ("commit dates on both sides" if p["baseline_first_commit"] and p["variant_first_commit"]
                     else "no commit dates (order not established)")
            w(f"| {md_cell(p['name'])} | {p['similarity']} | {md_cell(p['pair_outcome'])} | "
              f"{p['baseline_findings']} → {p['variant_findings']} | {md_cell(p['variant_categories'])} | "
              f"`{md_cell(p['baseline_repo'])}` | `{md_cell(p['variant_repo'])}` | {order} |")
        if len(interesting) > 60:
            w("")
            w(f"Showing 60 of {len(interesting)} pairs where the variant has more findings. Full list in `pairs_review.csv`.")
        w("")

    if errors:
        w("## Scan errors")
        w("")
        w(f"{len(errors)} artifact(s) did not scan cleanly. These are not clean results; "
          "treat them as unknown until rescanned.")
        w("")
        w("| Repo | Path | Status | Error |")
        w("|---|---|---|---|")
        for e in errors[:50]:
            w(f"| `{md_cell(e['repo'])}` | `{md_cell(e['path'])[:70]}` | {md_cell(e['status'])} | {md_cell(e['error'])} |")
        w("")

    w("## Handling")
    w("")
    w("- Do not paste snippets from the raw JSON into issues, slides or chat. Regenerate this report instead.")
    w("- A finding that looks like a live credential: do not test it. Report it privately to the repository "
      "owner through the SECURITY.md contact or GitHub private vulnerability reporting.")
    w("- Refer to repositories, not people. Commit-author fields are not included.")
    w("")

    data = {
        "source": source_name,
        "artifacts_scanned": total_artifacts,
        "artifacts_flagged": len(artifacts_flagged),
        "counts": {"severity": dict(by_sev), "category": dict(by_cat), "rule": dict(by_rule)},
        "policy_fingerprints": dict(fingerprints),
        "review_queue": [{k: v for k, v in r.items() if not k.startswith("_")} for r in review],
        "pairs": pairs,
        "scan_errors": errors,
    }
    return "\n".join(md), data


def write_csv(path: Path, rows: list[dict], cols: list[str]):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    base = Path("results/expanded_scan")
    ap.add_argument("--reports", default=str(base / "cisco_all_scan_reports.json"))
    ap.add_argument("--pairs", default=str(base / "baseline_variant_pair_comparison.csv"))
    ap.add_argument("--pair-dates", default="charts/name_variant_pairs.csv")
    ap.add_argument("--errors", default=str(base / "cisco_scan_errors.csv"))
    ap.add_argument("--out", default=str(base / "safe_report"))
    ap.add_argument("--include-info", action="store_true")
    args = ap.parse_args(argv)

    reports_path = Path(args.reports)
    if not reports_path.exists():
        sys.exit(f"Missing {reports_path}. Run from the repository root or pass --reports.")
    reports = load_reports(reports_path)
    rows = flatten(reports, args.include_info)
    pairs = load_pairs(Path(args.pairs), load_pair_dates(Path(args.pair_dates)))
    errors = load_errors(Path(args.errors))
    md, data = build(reports, rows, pairs, errors, args.include_info, reports_path.name)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "safe_report.md").write_text(md, encoding="utf-8")
    (out / "safe_report.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    review = dedupe(sorted([r for r in rows if r["severity"] != "INFO"],
                           key=lambda r: -SEVERITY_ORDER.index(r["severity"])))
    write_csv(out / "review_queue.csv", review,
              ["severity", "category", "rule_id", "repo", "path", "file_sha", "file", "line",
               "analyzer", "snippet", "snippet_sha256", "note"])
    if pairs:
        write_csv(out / "pairs_review.csv", pairs,
                  ["name", "similarity", "baseline", "variant", "baseline_findings", "variant_findings",
                   "variant_minus_baseline", "pair_outcome", "baseline_categories", "variant_categories",
                   "baseline_severities", "variant_severities"])
    print(f"wrote {out/'safe_report.md'}, safe_report.json, review_queue.csv"
          + (", pairs_review.csv" if pairs else ""))


if __name__ == "__main__":
    main()
