# Research Question

## MSR Topic

**Skill Security and Supply-Chain Risk**

This project investigates security risks in AI agent skills by comparing original skills with modified or reused versions across repositories.

## Research Question

**How do security risks differ between baseline and variant AI agent skills in the GitSkills dataset, and what types of security risks are present?**

## Motivation

Skills can be reused or modified across different repositories. When a skill is modified, its content and functionality may change, potentially introducing new security concerns.

These concerns may include command execution, file-system access, network access, exposed secrets, or unsafe dependencies.

Understanding how security findings differ between original and modified skills can help identify potential security and supply-chain risks associated with skill reuse.

## Expected Contribution

- This project will provide a data-driven analysis of security findings in baseline and variant skills from the GitSkills dataset. The analysis will:

- Identify groups of reused or identical artifacts.

- Identify baseline skills and their corresponding variants.

- Use the Cisco security scanner to detect potential security issues.

- Compare security findings between baseline and variant versions.

- Measure how frequently findings are introduced, removed, or remain unchanged.

- Identify the types and severity of security findings present in the dataset.

## Competing or Simpler Explanation

A higher number of security findings in a variant does not automatically mean that the modification introduced harmful behavior. The differences may result from legitimate functionality changes, differences in skill content, or limitations in the scanner.

Additionally, a scanner finding is not proof that a skill is malicious or that a vulnerability has been exploited.

Therefore, this project will treat scanner findings as potential security concerns and avoid automatically classifying modified skills as harmful.

## Study Design

### Unit of Analysis

The primary unit of analysis is an individual skill artifact. Baseline and variant artifacts will also be compared as related pairs to identify differences in their security findings.

### Population

The population consists of skill artifacts collected by the GitSkills mining
dataset.

### Sample

The analysis uses the approved GitSkills sample provided for the project.

The sample database is `agent_skills_sample.db`.

### Variables

| Variable | Description |
|---|---|
| `repo_full_name` | Repository containing the artifact |
| `path` | Location of the artifact in the repository |
| `content` | Content of the skill artifact |
| `file_sha` | Hash used to identify identical artifact content |
| `name` | Skill/artifact name |
| `description` | Description of the skill/artifact |
| `first_commit_at` | First recorded commit time |
| `last_commit_at` | Last recorded commit time |
| `dedup_primary` | GitSkills-designated primary artifact |
| `scan_status` | Status of the security scan |
| `findings_count` | Number of security findings detected |
| `categories` | Categories or rule identifiers associated with findings |
| `severities` | Severity levels associated with findings |
| `baseline/variant_role` | Identifies whether an artifact is the baseline or variant |


### Outcome Measures

The primary outcomes will be:

1. The number and percentage of baseline and variant skills with at least one security finding.

2. The average number of security findings in baseline and variant skills.

3. The number of paired comparisons where the variant has more, fewer, or the same number of findings as the baseline.

4. The types and severity levels of security findings detected.

5. The number of findings that appear in variants but not in their corresponding baselines.

Results will distinguish between individual artifact records, unique content versions, and baseline-variant pairs to avoid counting repeated content as separate unique versions.

## Limitations

- Scanner findings represent potential security issues, not confirmed vulnerabilities or malicious behavior.

- The scanner may not detect every security issue.

- Results depend on the scanner's detection rules and the content available for scanning.

- The analysis may not cover supporting scripts or files outside the scanned skill content.

- Identical content may appear in multiple repositories, so artifact counts and unique content-version counts may differ.

- The results may not represent all AI agent skills outside the GitSkills sample.