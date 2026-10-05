# GitSkills Security and Risk Analysis
## Project Overview

This project investigates security risks in reused, copied, and modified skills from the GitSkills dataset.

## Research Question

How frequently do reused/copied/modified skills introduce new security risks, and do these modifications exceed what is necessary?

We focus on security-sensitive capabilities such as:

Command execution
File-system access
Network access

## Dataset

The project uses the approved GitSkills sample dataset.

The database is approximately 277 MB and is not stored in this GitHub repository because it exceeds GitHub's 100 MB file-size limit.

See data/README.md for instructions on obtaining and setting up the dataset.


# Sprint 1

## Analysis Pipeline

The first analysis pipeline loads the approved GitSkills sample database and
uses DuckDB SQL queries to identify identical artifacts.

The pipeline:

1. Connects to the GitSkills database.
2. Loads the `artifacts` table.
3. Identifies artifacts with matching `file_sha` values.
4. Groups artifacts with identical content.
5. Examines `dedup_primary` and available timestamp information.
6. Outputs results for further reuse and security analysis.

The SQL queries were developed and tested in DuckDB before being incorporated
into the Python pipeline.
