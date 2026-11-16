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

* **`Baseline Skill`** — The original version of a skill used as a starting point for comparison. It represents the earlier version before the modifications being studied.

* **`Variant Skill`** — A modified or reused version of a baseline skill. It may containt changes to its instructions, content, or functionality.

- **`new_security_capability`** — Indicates that a security-sensitive
  capability appears in a later related artifact but was not detected in the
  earlier artifact.

## Finding Definitions

| Finding ID | Plain-English Definition | Potential Concern |
|---|---|---|
| `ACTIVE_DYNAMIC_EXECUTION` | Detects code that dynamically executes commands or instructions. | Potential command execution |
| `SECRET_CONNECTION_STRING` | Detects a connection string that may contain sensitive credentials or access information. | Exposed secrets |
| `SUPPLY_CHAIN_UNPINNED_DEPENDENCY` | Detects dependencies that are not pinned to a specific version. | Dependency supply-chain risk |
| `YARA_command_injection_generic` | Detects patterns associated with command injection, where unexpected input may influence executed commands. | Potential command injection |
| `PIPELINE_TAINT_FLOW` | Detects potentially unsafe movement of untrusted data through a code execution pipeline. | Unsafe data handling |
| `CORRELATED_NETWORK_EXECUTION_FLOW` | Detects a combination of network activity and code execution that may create a security risk. | Network and execution risk |
| `OBFUSCATION_BASE64_LARGE` | Detects large amounts of Base64-encoded content that may make code or data harder to inspect. | Potentially hidden content |
| `PROMPT_INJECTION_IGNORE_INSTRUCTIONS` | Detects instructions that attempt to make an AI system ignore previous instructions. | Prompt injection |
| `PROMPT_INJECTION_UNRESTRICTED_MODE` | Detects language that may attempt to place an AI system into an unrestricted mode. | Prompt injection |
| `SOCIAL_ENG_VAGUE_DESCRIPTION` | Flags vague or potentially misleading descriptions that may make a skill's behavior difficult to understand. | Unclear or potentially deceptive description |
| `MANIFEST_INVALID_NAME` | Detects an invalid or improperly formatted skill manifest name. | Manifest configuration issue |
| `MANIFEST_MISSING_LICENSE` | Detects that a skill manifest does not include a license declaration. | Missing license information |

## Severity Definitions

| Severity | Meaning |
|---|---|
| INFO | Informational observation or scanner coverage note. Does not necessarily indicate a security problem. |
| LOW | A potential security concern with relatively limited impact. |
| MEDIUM | A more significant potential security concern that deserves investigation. |
| HIGH | A serious potential security concern. |
| CRITICAL | An especially serious potential security concern requiring attention. |

Severity should be interpreted alongside the finding and its description. An INFO finding may indicate incomplete analysis rather than a harmless skill.

