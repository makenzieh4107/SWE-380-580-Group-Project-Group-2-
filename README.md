# GitSkills Security and Risk Analysis
## Project Overview

This project investigates security risks in AI agent skills from the GitSkills dataset. We compare baseline skills with their modified or variant versions to understand how their security findings differ.

The analysis uses the Cisco security scanner to identify potential security issues in skill files. Scanner findings are treated as potential risks, not proof that a skill is malicious or that a vulnerability has been exploited.

## Research Question

How do security risks differ between baseline and variant AI agent skills in the GitSkills dataset, and what types of security risks are present?

We focus on identifying and comparing security findings related to areas such as:

Command execution: Running shell commands or external programs.

File-system access: Reading, writing, modifying, or deleting files.

Network access: Sending requests, connecting to external servers, or downloading data.

Other security concerns: Potential exposed secrets, unsafe dependencies, and other issues identified by the scanner.

## Analysis Approach

The project compares baseline and variant skills using their content hashes to connect each skill version to its scanner results.

The analysis examines:

The number of security findings in baseline and variant skills.

Differences in findings between paired baseline and variant versions.

The types and severity of security findings detected.

How frequently findings appear across unique skill content versions.

The project also includes manual review of selected scanner findings to help evaluate the results.

## Dataset

The project uses the approved GitSkills sample dataset.

The database is approximately 277 MB and is not stored in this GitHub repository because it exceeds GitHub's 100 MB file-size limit.

See data/README.md for instructions on obtaining and setting up the dataset.

## Limitations

- Scanner findings indicate potential security issues and require interpretation.

- The analysis may not identify every security issue in a skill or its supporting files.

- Results depend on the scanner's detection rules and capabilities.

- Multiple repository artifacts may contain identical content, so artifact counts and unique content-version counts are not always the same.

- Findings do not establish that a skill is malicious or that detected behavior has actually been executed.


