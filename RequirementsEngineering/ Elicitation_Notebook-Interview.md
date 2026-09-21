#  Elicitation/Notebook-Interview

## Prompt:

How many Gitskills are repetitive?

## Output:

In the full **GitSkills** dataset, **50.5% of all file occurrences are verbatim copies** of another file[1][2].

Specifically:

* **Total** **SKILL.md** **file occurrences:** **3,797,117**[3]
* **Distinct skill contents:** **1,877,981**[3]
* **Repetitive / duplicate copies:** **1,919,136** files (representing the copies beyond the distinct contents)[1].

For comparison, in the curated **sample dataset**:

* **Total file occurrences:** **29,786**[3]
* **Distinct skill contents:** **13,000**[3]
* **Repetitive / duplicate copies in sample:** **16,786** files[3]

The authors note that because agent skills lack a central registry or package manager, reuse across GitHub repositories primarily occurs through direct folder copying[2][6].

## Prompt:

How does skill reuse vary by programming language?

## Output:

While the sources record repository language metadata and overall reuse statistics, **they do not contain a breakdown of skill reuse rates by specific programming language**[1][2].

Here is what the sources do provide regarding languages and duplication:

* **Top Languages in GitSkills:** The dataset captures skills across public GitHub repositories, where the most frequent primary languages are **Python** (71,801 repositories), **TypeScript** (67,104), **JavaScript** (23,938), **Shell** (19,780), **HTML** (12,187), **Rust** (8,371), and **Go** (8,094)[2].
* **Overall Duplication Rate:** Across the entire dataset, **50.5% of all skill file occurrences are verbatim copies** of another file[2][3].

Because the dataset links each skill occurrence to its host repository's primary language via the `repos` table, determining how skill adoption and duplication differ across programming languages is highlighted as an **open research question** for the MSR 2027 Mining Challenge[1].

## Prompt:

How difficult would it be to search for commands that exhibit risky behavior?

## Output:

Searching for commands that exhibit risky behavior in **GitSkills** is **very accessible and straightforward**, primarily because the dataset stores text content directly in a queryable SQLite database and Parquet format[1][2].

Here is how the dataset structure facilitates this type of security analysis, along with a few practical considerations:

#### What makes it straightforward

* **Direct Access to Instructions:** The `artifacts` table contains a `content` column with the full text of every distinct `SKILL.md` file[1][2]. You can search directly for dangerous commands or patterns (such as `rm -rf`, `curl | bash`, `eval`, or environment variable exfiltration) using standard SQL `LIKE` queries or regular expressions[1][3].
* **Queryable Bundled Scripts:** The `artifact_siblings` table stores the raw text of scripts bundled alongside skills (up to 100 KB), allowing you to scan executed bash or Python code for risky behavior[4][5].
* **Built-in Filtering Flags:** The `artifacts` table includes boolean flags like `has_scripts` and `has_references`, allowing you to narrow your search immediately to skills that invoke external code[1].
* **Diffing Copies for Injected Commands:** Because duplicate files are tracked by content hash (`file_sha`), you can compare modified copies of widely reused skills against their originals to check if unreviewed forks introduced new command executions or network calls (a key supply-chain threat highlighted by the dataset authors)[1][6].

### Practical Considerations

* **Natural Language Parsing:** Because `SKILL.md` files instruct LLMs using natural language rather than strict code, pattern matching (regex or NLP models) is needed to distinguish benign command documentation from instructions telling an agent to perform dangerous actions[7][8].
* **File Size Cap on Siblings:** Text files larger than 100 KB and binary executables in `artifact_siblings` omit raw content in the dataset (`skipped_reason`), though their Git blob hashes (`entry_sha`) are preserved if you need to fetch them directly from GitHub[4][5].
