# Research Question

## MSR Topic

**Skill Security and Supply-Chain Risk**

This project investigates security risks that may be introduced when skills
are reused, copied, or modified across repositories.

## Research Question

**How frequently do modified skills introduce new security
risks, and do these modifications exceed what is necessary?**

## Motivation

Skills can be reused or modified across different repositories. When a skill
is modified, new security-sensitive capabilities may be introduced. These
capabilities could include command execution, file-system access, or network
access.

Understanding how often these capabilities are introduced can help identify
potential security and supply-chain risks in reused skills.

## Expected Contribution

This project will provide a data-driven analysis of reused and modified
skills in the GitSkills dataset. The analysis will:

- Identify groups of reused or identical artifacts.
- Detect security-sensitive capabilities in skill content.
- Compare related artifacts to identify newly introduced capabilities.
- Measure how frequently new security-sensitive capabilities appear.
- Assess whether newly introduced capabilities appear related to the stated
  purpose of the skill.

## Competing or Simpler Explanation

A newly introduced security-sensitive capability does not necessarily mean
that a modification created an unnecessary security risk. The capability may
have been added because the skill's purpose changed or because the capability
was necessary for a new feature.

Therefore, the analysis will treat newly detected capabilities as potential
security risks rather than automatically classifying them as harmful or
unnecessary.



## Study Design

### Unit of Analysis

The primary unit of analysis is an individual skill artifact in the GitSkills
dataset.

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
| Security capabilities | Detected command, file-system, or network capabilities |

### Outcome Measures

The primary outcomes will be:

1. The number and percentage of related artifacts that introduce at least
   one new security-sensitive capability.
2. The type of security-sensitive capability introduced.
3. Whether the newly introduced capability appears related to the stated
   purpose of the skill.
