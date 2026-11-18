# GitSkills Security and Risk Analysis
## Project Overview

This project investigates security risks in AI agent skills from the GitSkills dataset. We compare baseline skills with their modified or variant versions to understand how their security findings differ.

The analysis uses the Cisco security scanner to identify potential security issues in skill files. Scanner findings are treated as potential risks, not proof that a skill is malicious or that a vulnerability has been exploited.

## Research Question

How do security risks differ between baseline and variant AI agent skills in the GitSkills dataset, and what types of security risks are present?

We focus on identifying and comparing security findings related to areas such as:

Command execution: Running shell commands or external programs.

File-system access: Reading, writing, modifying, or deleting files.

Network access: Sending requests, connecting to external servers, or downloading data.

Other security concerns: Potential exposed secrets, unsafe dependencies, and other issues identified by the scanner.

## Analysis Approach

The project compares baseline and variant skills using their content hashes to connect each skill version to its scanner results.

The analysis examines:

The number of security findings in baseline and variant skills.

Differences in findings between paired baseline and variant versions.

The types and severity of security findings detected.

How frequently findings appear across unique skill content versions.

The project also includes manual review of selected scanner findings to help evaluate the results.

### Severity Meaning
- **INFO:** Informational observation. Something is worth noting, but it may not represent a direct security threat.
- **LOW:** A potential security concern with relatively limited impact.
- **MEDIUM:** A more significant potential security issue that deserves investigation.
- **HIGH:** A serious potential security issue that could have substantial impact.
- **CRITICAL:** An especially serious issue that may require immediate attention.

## Dataset

The project uses the approved GitSkills sample dataset.

The database is approximately 277 MB and is not stored in this GitHub repository because it exceeds GitHub's 100 MB file-size limit.

See data/README.md for instructions on obtaining and setting up the dataset.

## How to Use This Project

This project is organized as a reproducible analysis workflow for comparing GitSkills artifact content and scanner findings.

### 1. Set up the environment

From the repository root, create and activate a Python environment, then install the project dependencies:

```bash
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# or .venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

If the Cisco Skill Scanner CLI is required for a run, make sure it is installed and available on your PATH:

```bash
skill-scanner --help
```

### 2. Prepare the dataset

The project expects the GitSkills sample database at:

```text
data/agent_skills_sample.db
```

Follow the instructions in [data/README.md](data/README.md) to obtain or restore the database before running the analysis steps.

### 3. Run the automated checks

The repository includes a small smoke-test runner that executes all active project tests:

```bash
python "Automated Test/run_current_tests.py"
```

This will discover and run every test file matching `test_*.py` in the `src/` and `Automated Test/` directories.

### 4. Run the expanded GitSkills comparison workflow

The main scanner workflow is implemented in [src/test_cisco_gitskills_expanded.py](src/test_cisco_gitskills_expanded.py). From the repository root, run:

```bash
python src/test_cisco_gitskills_expanded.py
```

This script:

- reads the similarity pair CSV from `charts/name_variant_pairs.csv`
- matches selected artifacts against the GitSkills database
- deduplicates content by hash
- scans only unique content versions
- writes consolidated scanner reports and CSV summaries under `results/expanded_scan/`
- saves a readable text report for human review

### 5. Inspect the outputs

The main outputs are stored in the `results/` and `results/expanded_scan/` folders, including:

- `results/expanded_scan/cisco_scan_results.csv`
- `results/expanded_scan/baseline_variant_pair_comparison.csv`
- `results/expanded_scan/baseline_variant_summary.csv`
- `results/expanded_scan/cisco_all_scan_reports.json`
- `results/expanded_scan/cisco_scan_results.txt`

Charts and comparison visualizations are also written to the `results/expanded_scan/charts/` directory.

### 6. Reproduce the comparison summary

To generate the final comparison tables and summary outputs from the pair CSV and scanner results files, run:

```bash
python src/compare_extended.py
```

This produces the baseline-versus-variant comparison outputs used for analysis and reporting.

## Limitations

- Scanner findings indicate potential security issues and require interpretation.

- The analysis may not identify every security issue in a skill or its supporting files.

- Results depend on the scanner's detection rules and capabilities.

- Multiple repository artifacts may contain identical content, so artifact counts and unique content-version counts are not always the same.

- Findings do not establish that a skill is malicious or that detected behavior has actually been executed.


