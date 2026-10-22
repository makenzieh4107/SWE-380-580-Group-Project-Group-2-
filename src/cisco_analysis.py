
import duckdb
import subprocess
import json
from pathlib import Path
import tempfile

DB_PATH = "data/agent_skills_sample.db"

# Connect to GitSkills database
con = duckdb.connect(":memory:")
con.execute(
    f"ATTACH '{Path(DB_PATH).resolve().as_posix()}' AS GitSkills (READ_ONLY)"
)

# Get one real Markdown skill
row = con.execute("""
    SELECT repo_full_name, path, content, file_sha
    FROM GitSkills.artifacts
    WHERE content IS NOT NULL
      AND lower(path) LIKE '%.md'
      AND trim(content) <> ''
    LIMIT 1
""").fetchone()

con.close()

if not row:
    raise SystemExit("No Markdown artifacts found in the database.")

repo, artifact_path, content, file_sha = row

print("Repository:", repo)
print("Artifact path:", artifact_path)
print("SHA:", file_sha)

# Create a temporary skill folder for scanning
with tempfile.TemporaryDirectory(prefix="gitskills_test_") as temp:
    skill_dir = Path(temp) / "test_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        content, encoding="utf-8", errors="replace"
    )

    report_path = Path("results/cisco_skill_test_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = report_path.resolve()

    command = [
        "skill-scanner",
        "scan",
        str(skill_dir),
        "--lenient",
        "--format", "json",
        "--output-json", str(report_path),
    ]

    print("\nRunning Cisco Skill Scanner...")
    result = subprocess.run(command, text=True, check=False)

    if report_path.exists():
        print("\nReport saved to:", report_path)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        print(json.dumps(report, indent=2)[:5000])
    else:
        print("No JSON report was created.")
        print("Scanner exit code:", result.returncode)




# Read the JSON report created by Cisco Skill Scanner
report_path = Path("results/cisco_skill_test_report.json")

# Write a readable text report
output_path = Path("results/cisco_skill_test_report.txt")

report = json.loads(report_path.read_text(encoding="utf-8"))

lines = [
    "CISCO AI DEFENSE SKILL SCANNER RESULTS",
    "=" * 45,
    f"Skill: {report.get('skill_name', 'Unknown')}",
    f"Safe according to scanner: {report.get('is_safe', 'Unknown')}",
    f"Maximum severity: {report.get('max_severity', 'Unknown')}",
    f"Total findings: {report.get('findings_count', len(report.get('findings', [])))}",
]

findings = report.get("findings", [])

for number, finding in enumerate(findings, start=1):
    lines.extend([
        "",
        f"--- Finding {number} ---",
        f"Rule: {finding.get('rule_id', '')}",
        f"Category: {finding.get('category', '')}",
        f"Severity: {finding.get('severity', '')}",
        f"Title: {finding.get('title', '')}",
        f"Description: {finding.get('description', '')}",
        f"Location: {finding.get('file_path', '')}",
        f"Line: {finding.get('line_number', '')}",
        f"Evidence: {finding.get('snippet', '')}",
        f"Remediation: {finding.get('remediation', '')}",
    ])

if not findings:
    lines.extend(["", "No findings were listed in the report."])

output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text("\n".join(lines), encoding="utf-8")

print(f"Text report saved to: {output_path.resolve()}")
