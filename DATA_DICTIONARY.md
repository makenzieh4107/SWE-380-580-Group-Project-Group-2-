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

- **`command_execution`** — Indicates that the artifact contains patterns
  associated with running commands, starting processes, or executing external
  programs.

- **`file_system_access`** — Indicates patterns associated with reading,
  writing, modifying, deleting, or accessing files and directories.

- **`network_access`** — Indicates patterns associated with making network
  requests, connecting to external servers, or downloading data.

- **`new_security_capability`** — Indicates that a security-sensitive
  capability appears in a later related artifact but was not detected in the
  earlier artifact.

