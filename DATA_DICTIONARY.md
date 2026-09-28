# Data Dictionary

## `artifacts` Table

* **`repo_full_name`** — GitHub repository containing the artifact.
* **`path`** — Location of the artifact within the repository.
* **`content`** — Text/code contained in the artifact. Used for security analysis.
* **`file_sha`** — Hash representing the artifact's content. Used to find identical artifacts.
* **`name`** — Name of the skill or artifact.
* **`description`** — Description of the skill or artifact.
* **`first_commit_at`** — Time of the first recorded commit.
* **`last_commit_at`** — Time of the last recorded commit.
* **`dedup_primary`** — Identifies the GitSkills-designated primary artifact in a duplicate group.

## Security Categories

* **Command execution** — Running commands or processes.
* **File-system access** — Reading, writing, or modifying files.
* **Network access** — Making network connections or requests.

