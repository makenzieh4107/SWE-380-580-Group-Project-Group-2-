"""
Security Detection for the GitSkills Dataset

This script connects to the approved GitSkills sample database and runs the
security-detection SQL queries developed and tested in DuckDB. It analyzes
skill content to identify potential security-sensitive capabilities. It
examines the artifacts table to:

1. Detect capabilities related to command execution, including running shell
   commands, starting processes, and executing external programs.
2. Detect file-system access, including reading, writing, modifying, deleting,
   and accessing files or directories.
3. Detect network access, including making HTTP/HTTPS requests, connecting to
   external servers, and downloading data from the internet.
4. Run the SQL detection queries and retrieve the matching artifacts and
   detected security-sensitive capabilities.
5. Record the detection results for later comparison between related artifacts.
6. Provide the results needed to determine whether modified or reused artifacts
   introduce new security-sensitive capabilities.

The SQL queries were developed and tested in DuckDB first to explore the
dataset and verify the detection rules. The Python script then runs these
queries as part of the analysis pipeline to make the security detection
reproducible and automated.

The detection results identify potential capabilities based on patterns found
in the artifact content. A detected capability does not prove that the code
was executed or that the capability is harmful, unnecessary, or malicious.

The script analyzes the dataset as data only and does not execute any
scripts or code contained within the artifacts.
"""
