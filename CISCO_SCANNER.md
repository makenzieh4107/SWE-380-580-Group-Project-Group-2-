# Cisco AI Defense Skill Scanner

## Purpose
This project uses the Cisco AI Defense Skill Scanner to examine selected
GitSkills artifacts for potential security issues. The scanner provides
findings that help us decide which skills or changes need closer review.

A scanner finding is an alert to investigate, not proof that an artifact
is malicious or that a capability was executed.

## How We Use It
1. Select baseline and variant artifacts from the approved GitSkills
   sample.
2. Retrieve the artifact content from data/agent_skills_sample.db
   using the identifiers recorded in the selected-pairs CSV.
3. Provide the selected skill content to the Cisco scanner.
4. Save the scanner reports as JSON so the results can be reviewed and
   processed again.
5. Use Python to extract and count findings by rule ID.
6. Generate tables or charts from the saved reports.
7. Manually review a sample of findings to assess whether the alert is
   supported by the content and whether a security-sensitive capability
   appears to have been introduced by a change.

## Findings and Filtering
The scanner can report different types of issues, including findings
related to dynamic execution, command injection, network execution
flows, secrets, dependencies, and skill metadata. The exact rule IDs and
available findings depend on the scanner version, configuration, and
input.

Counts must be described precisely. A count of finding occurrences is
not the same as the number of affected artifacts, baseline--variant
pairs, or manually confirmed security risks.

## Reproducibility
Record the analysis scripts and input/output paths in the repository
README. Retain the JSON reports as the source for post-processing, and
regenerate visualizations from those reports rather than from
screenshots.

Use the command documented by the current scanner script to run scans.
Then run the project's report-processing or chart script from the
repository root. Confirm that configured input paths match the files
present in the checkout before running.
Safety and Limitations
- Dataset content is treated as data. The project does not execute
  scripts or commands found inside the skills.
- Scanner findings may include false positives and false negatives.
- A finding does not prove malicious intent, successful execution, or
  real-world impact.
- Scanning only a skill's main SKILL.md file may miss behavior
  implemented in supporting files, if those files are not included in
  the scan.
- The scanner's categories do not directly answer whether a capability
  is necessary for the skill's stated purpose.
- Manual review is needed to assess whether a reported issue is
  supported and whether a baseline--variant change introduces a
  relevant new risk.
- Results from a limited set of pairs should be reported as
  preliminary results for that sample, not as estimates for the entire
  GitSkills dataset.

## How This Supports the Research Question

The scanner provides candidate security findings for the project's
comparison of modified skills. We compare findings
for baseline and variant artifacts to identify potential changes in
security-sensitive behavior. Manual review and the skill's stated
purpose help assess whether those changes may represent unnecessary or
excessive capabilities.

The scanner supports this investigation, but it does not by itself
establish that a modification exceeds what is necessary.