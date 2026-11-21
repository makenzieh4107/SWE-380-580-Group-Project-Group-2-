# Security-Sensitive Capability Analysis

## Purpose

This analysis screens unique GitSkills artifact contents for textual
indicators of potentially security-sensitive capabilities. The categories
are:

- Command execution
- File-system access
- Network access

A detection is a pattern match requiring review. It is not, by itself,
evidence that a skill is vulnerable, malicious, or over-privileged.

## Dataset selection

The analysis uses the approved GitSkills sample database:

`data/agent_skills_sample.db`

The query selects rows where:

- `dedup_primary = 1`
- `file_sha IS NOT NULL`
- `content IS NOT NULL`

`dedup_primary = 1` selects one GitSkills-designated representative for each
byte-distinct content hash. This prevents repeated scanning of byte-identical
content. A modified content has a different `file_sha` and therefore retains
its own representative.

Exact-copy occurrences can later be restored by joining detection results to
all artifact rows on `file_sha`.

The `dedup_primary` field does not identify the original author, earliest
version, or direction of copying.

## Detection process

For every selected artifact, the pipeline:

1. Treats artifact content strictly as untrusted text.
2. Applies documented regular-expression rules.
3. Assigns matches to one of the three capability categories.
4. Records matched text, source line, evidence, and surrounding context.
5. Retains repository, path, file SHA, skill name, description, and commit
   metadata for traceability.
6. Deduplicates overlapping matches from the same category on the same line.
7. Summarizes unique artifact hashes by capability category.

## Output interpretation

The analysis distinguishes among:

- **Pattern match:** One regular-expression match.
- **Artifact-category association:** A distinct combination of `file_sha` and
  capability category.
- **Flagged artifact:** A distinct content hash with at least one detected
  category.
- **Artifact occurrence:** A repository/path row containing that hash.

These counts must not be treated as interchangeable.

## Limitations

The detector may produce false positives and false negatives. Matches may
appear in:

- Actionable instructions
- Code examples
- Warnings or prohibitions
- Descriptive references
- Ambiguous text

Manual review is required before interpreting a result as an actual
capability instruction. The detector does not determine malicious intent or
whether a capability exceeds the skill's stated purpose.

This stage also does not determine whether a capability was newly introduced.
That requires identifying candidate related artifacts with different hashes,
ordering them using documented evidence, and comparing their capability sets.

## Safety

The pipeline never executes, evaluates, imports, or invokes commands, scripts,
or code from the GitSkills dataset.

## Running the analysis

From the repository root:

```powershell
python .\src\capability_analysis.py