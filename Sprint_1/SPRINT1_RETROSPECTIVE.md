# Sprint 1 Retrospective

## What We Learned

We learned how to work with the approved GitSkills dataset using DuckDB and Python.

We learned how to use file_sha to identify artifacts with identical content across repositories.

We learned that identical content does not prove which artifact was copied from another artifact.

We found that duplicate content makes up a substantial portion of the dataset, which supports further investigation of reuse and supply-chain risks.

We learned that duplicate groups vary greatly in size. Some are simple pairs, while other groups contain content reused across many artifacts.

We learned how to examine where copies occur, including whether copies appear in the same repository or in different repositories.

We learned that dedup_primary provides a way to identify the GitSkills-designated primary artifact in each duplicate group.

We expanded our analysis beyond exact duplicates by comparing artifacts with the same name but different content using RapidFuzz similarity scores. The analysis produces name_variant_pairs.csv for later security comparison.

## What Went Well

We established a specific research question focused on security and supply-chain risks in modified skills.
We successfully loaded and analyzed the approved GitSkills sample.
We created a working data-loading and extraction pipeline.
We identified 3,378 duplicate groups and 20,164 artifacts belonging to those groups.
We generated multiple exploratory visualizations to understand the duplicate artifacts, including:
- Unique content vs. redundant copies
- Duplicate group sizes
- Largest duplicate groups
- Repositories with the most copied artifacts
- Copies over time
- dedup_primary validation
- Same-name content variants

We created reusable chart-generation code that saves the visualizations to the charts/ directory.

We established documentation for the research question, dataset, variables, and threats to validity.
We established a GitHub workflow using issues, branches, and pull requests.

## What Changed in Our Backlog

Based on what we learned during Sprint 1, we added and refined tasks for:

Detecting command execution, file-system access, and network access.

Comparing exact duplicate groups and near-duplicate artifacts.

Comparing earlier and later versions to identify newly introduced security-sensitive capabilities.

Assessing whether newly introduced capabilities appear related to the stated purpose of the skill.

Documenting limitations around identifying copying direction and determining whether a capability is actually necessary.

## Next Sprint

In the next sprint, we will focus on security-capability detection and artifact comparison. We will use the duplicate relationships identified during Sprint 1 to determine whether modified skills introduce new security-sensitive capabilities, such as command execution, file-system access, or network access.