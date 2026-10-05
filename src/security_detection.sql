ATTACH 'data/agent_skills_sample.db' AS GitSkills;

-- Analysis developed and tested in DuckDB first.
-- These queries were then incorporated into the Python pipeline
-- to make the analysis reproducible and automated.

-- Risky code patterns to look for in the codebase


-- Command Execution
-- Look for examples to find running shell commands
SELECT
    repo_full_name,
    path,
    name,
    description,
    LEFT(content, 1000) AS content_preview
FROM GitSkills.artifacts
WHERE LOWER(content) LIKE '%subprocess%'
   OR LOWER(content) LIKE '%os.system%'
   OR LOWER(content) LIKE '%os.popen%'
   OR LOWER(content) LIKE '%shell=true%'
   OR LOWER(content) LIKE '%bash%'
   OR LOWER(content) LIKE '%sh -c%'
   OR LOWER(content) LIKE '%powershell%'
   OR LOWER(content) LIKE '%cmd.exe%'
LIMIT 50;

-- Look for examples to find starting processes
SELECT
    repo_full_name,
    path,
    name,
    description,
    LEFT(content, 1000) AS content_preview
FROM GitSkills.artifacts
WHERE LOWER(content) LIKE '%subprocess.popen%'
   OR LOWER(content) LIKE '%subprocess.run%'
   OR LOWER(content) LIKE '%subprocess.call%'
   OR LOWER(content) LIKE '%subprocess.check_output%'
   OR LOWER(content) LIKE '%subprocess.check_call%'
   OR LOWER(content) LIKE '%os.spawn%'
LIMIT 50;

-- Look for examples to find executing external programs
SELECT
    repo_full_name,
    path,
    name,
    description,
    LEFT(content, 1000) AS content_preview
FROM GitSkills.artifacts
WHERE LOWER(content) LIKE '%execve%'
   OR LOWER(content) LIKE '%execv%'
   OR LOWER(content) LIKE '%execvp%'
   OR LOWER(content) LIKE '%spawn%'
   OR LOWER(content) LIKE '%.exe%'
   OR LOWER(content) LIKE '%.bat%'
   OR LOWER(content) LIKE '%.cmd%'
   OR LOWER(content) LIKE '%.sh%'
LIMIT 50;