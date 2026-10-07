# Data Table Analysis

| Measure                       | Result |
| ----------------------------- | -----: |
| Total artifacts examined      | 29,786 |
| Identical-content groups      |  3,378 |
| Artifacts in duplicate groups | 20,164 |
| Groups with a primary         |  3,378 |
| Groups with a non-primary     |  3,378 |



### Interpretation

The analysis identified 3,378 groups of artifacts with identical content.
These groups contain 20,164 artifacts in total. Every identified group
contained a GitSkills-designated primary artifact and at least one
non-primary artifact.

These groups provide the starting point for investigating potential reuse
and copying and will be used in later analysis of security-sensitive
capabilities.

Matching `file_sha` values indicate identical content but do not prove who
copied whom.

# Visualization Analysis

Visualization graph for this spring is saved to results/duplicate_group_size_distribution.png

Most duplicate groups contain a small number of artifacts, but some groups contain the same content across many artifacts. This shows that some skills are reused across multiple repositories. These repeated artifacts provide a useful starting point for investigating whether modified or reused skills introduce new security-sensitive capabilities.