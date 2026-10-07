# Sprint 1

## Analysis Pipeline
The first analysis pipeline loads the approved GitSkills sample database and uses DuckDB SQL queries to identify identical artifacts.

The pipeline:

Connects to the GitSkills database.
Loads the artifacts table.
Identifies artifacts with matching file_sha values.
Groups artifacts with identical content.
Examines dedup_primary and available timestamp information.
Outputs results for further reuse and security analysis.
The SQL queries were developed and tested in DuckDB before being incorporated into the Python pipeline.

## Chart Interpretations

1. Unique vs. Duplicate Artifacts

The dataset contains 29,786 artifacts. Of these, 9,622 (32.3%) have unique content, while 20,164 (67.7%) are part of duplicated-content groups. Within the duplicated content, 3,378 artifacts (11.3% of the full dataset) are the first instance of their duplicated content, while 16,786 (56.4%) are redundant copies. This shows that identical reuse is a substantial part of the dataset.

2. Duplicate Group Size Distribution

There are 3,378 duplicate groups. The largest number of groups are simple pairs: 1,376 groups (41%) contain exactly two artifacts. However, larger groups account for a substantial amount of duplicated content. In particular, the 336 groups containing 11 or more artifacts account for 47% of all duplicated artifacts. This indicates that while many reuse cases involve only one copy, a smaller number of artifacts are reused many times.

3. Largest Duplicate Groups

The most frequently duplicated artifact is vercel-react-best-practices, which appears as 188 identical copies. Other highly duplicated artifacts include Writing Hookify Rules (171 copies), an unnamed artifact (170 copies), and shadcn (153 copies). This demonstrates that some specific skills are reused extensively across the dataset.

4. Source Repositories

The repository with the most non-primary copies is MikeCheng1208/BattleTree, with 2,840 copies. Other high-copy repositories include Jeeva0104/connector-service-mini (1,024) and Yash0009/9tattvas (808). The chart also distinguishes copies made within the same repository from copies made into other repositories. The presence of copies across repositories is particularly relevant to the project's supply-chain focus because it demonstrates that artifacts can spread beyond their original repository.

5. Copies Over Time

The number of earliest instances of duplicated artifacts increases substantially over the dataset's timeline. There are very few early instances, followed by a noticeable increase beginning around late 2025 and early 2026, with the highest point occurring around June 2026 at approximately 200 artifacts. This shows that duplicated artifacts become increasingly common in the later portion of the dataset.

6. dedup_primary Check

All 3,378 duplicate groups (100%) have exactly one primary artifact, with zero groups having either zero or multiple primaries. This provides a strong sanity check for the dataset and supports using dedup_primary to distinguish the primary instance from redundant copies.

7. Same Name, Different Content

There are 1,089 artifacts with the same name but different content. Of these, 106 are classified as minor edits, meaning their similarity to the earliest version is 90% or higher. The distribution also shows many versions with substantially lower similarity scores, indicating that artifacts sharing the same name can represent significantly different content.

This is particularly important for the research question because it provides a population of potentially modified/reused skills that can be examined in the next stage to determine what changed between versions.

## Overall Interpretation

Together, these results establish a clear baseline for the study: artifact reuse is common in the GitSkills dataset, and reuse occurs both through exact copies and through versions with different content. A substantial portion of the dataset consists of redundant copies, while some artifacts are reused across many repositories.

However, these charts do not yet demonstrate that reuse or modification creates security risks. They identify the artifacts and reuse patterns that can be examined in the next stage. The next analysis should compare original and modified versions to determine whether modifications introduce security-relevant capabilities, such as command execution, file-system access, or network access, and whether those capabilities are necessary for the skill's stated purpose.