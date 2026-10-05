# Sprint 1 Retrospective

## What We Learned

- Learned how to work with the approved GitSkills dataset using DuckDB.
- Learned that identical `file_sha` values can identify identical artifacts
  but do not prove copying direction.
- Learned that the large dataset cannot be stored directly in GitHub because
  of the file-size limit.
- Learned that security detection requires predefined rules and manual
  validation to reduce false positives.

## What Went Well

- Defined a specific research question.
- Successfully loaded and analyzed the approved dataset.
- Created the initial duplicate-artifact analysis pipeline.
- Generated initial exploratory results.
- Established a branch and pull-request workflow.

## What Changed in the Backlog

We added tasks for:

- Security-sensitive capability detection.
- Manual validation of detection results.
- Comparing related artifacts.
- Assessing whether newly introduced capabilities appear related to the
  stated skill purpose.

## Next Sprint

The next sprint will focus on completing security-capability detection and
comparing related artifacts to identify newly introduced capabilities.