# SWE 380.CSC 580 Group Assignment 2: Requirements Engineering

## Question: What’s the difference between SpecMines and GitSkills?

Notebook Answer: 

* **GitSkills**: A dataset of **agent skills** (SKILL.md files) that provide natural-language instructions and bundled tools guiding AI agents on **how** to perform specific tasks\[1\]\[2\].  
* **SpecMine**: A dataset of **Spec-Driven Development (SDD)** artifacts (such as spec.md and .kiro/specs/ files) that define **what** code or feature an AI agent should build\[3\]\[4\].  
* **Main Focus**: **GitSkills** tracks procedural agent instructions and verbatim skill reuse across repositories\[2\]\[5\]. **SpecMine** tracks software specifications and links them directly to code changes via pull requests and reference indices\[3\]\[6\].  
* **Data Scale**: **GitSkills** captures **3.8 million skill files** across 282,200 repositories\[1\]\[7\]. **SpecMine** captures **\~569,000 specification artifacts** across 18 SDD tool families

Source cited: GitHub \- giuseppedestefanis/gitskills-sample: Sample dataset for the MSR'27 mining challenge · GitHub 

Team Interpretation: GitSkills provide instructions and tools for AI agents on how to do their tasks. SpecMine has the specifications for what the AI agent should be working on/doing.

Follow up / Uncertainty: What’s the difference in scale?

## Question: How many Gitskills are repetitive?

Notebook Answers: In the full \*\*GitSkills\*\* dataset, \*\*50.5% of all file occurrences are verbatim copies\*\* of another file. 

Specifically:  
\* \*\*Total \`SKILL.md\` file occurrences:\*\* \*\*3,797,117\*\*  
\* \*\*Distinct skill contents:\*\* \*\*1,877,981\*\*  
\* \*\*Repetitive / duplicate copies:\*\* \*\*1,919,136\*\* files (representing the copies beyond the distinct contents).

For comparison, in the curated \*\*sample dataset\*\*:  
\* \*\*Total file occurrences:\*\* \*\*29,786\*\*  
\* \*\*Distinct skill contents:\*\* \*\*13,000\*\*  
\* \*\*Repetitive / duplicate copies in sample:\*\* \*\*16,786\*\* files

The authors note that because agent skills lack a central registry or package manager, reuse across GitHub repositories primarily occurs through direct folder copying.

Source cited: GitHub \- giuseppedestefanis/gitskills-sample: Sample dataset for the MSR'27 mining challenge · GitHub

MSR 2027 \- Mining Challenge \- MSR 2027

Team Interpretation: This can drastically reduce the amount of files needed to check

Follow up / Uncertainty: “Distinct skills” may still have many similarities

## Question: What kind of security risks could come up with reused and copied skills?

Notebook Answer: 

* **Supply-Chain Attacks**: Modified copies of widely reused skills can secretly add command execution or network access that was absent from the original version\[1\]\[2\].  
* **Unvetted Executable Scripts**: Skills can instruct AI agents to run bundled executable files or system commands without formal safety checks\[1\]\[2\].  
* **Lack of Central Registry**: Skills spread by direct copying between repositories without a package manager, compiler verification, or formal code review\[1\].  
* **Staleness & Maintenance Risks**: Reused skills can become outdated relative to the tools and projects they describe, leading to unmaintained or incorrect execution\[1\]\[2\].

Source cited: MSR 2027 \- Mining Challenge \- MSR 2027 

Team Interpretation: There could be added information into copied or reused skills that could unintentionally add extra privileges that may cause risk.

Follow up / Uncertainty: How many of these copies/reuses have overprivileges?

## Question: Where are these kinds of risks most found?

Notebook Answer: **Non-canonical file paths**: Over 90% of mined skill files sit outside the canonical .claude/skills/ path—55.4% are stored under generic skills/ directories and 34.8% sit in other non-standard locations 

Source cited: GitHub \- giuseppedestefanis/gitskills-sample: Sample dataset for the MSR'27 mining challenge · GitHub 

Team Interpretation: Most are outside of the canonical skills path.

Follow up / Uncertainty: What kinds of fields are they really in?

## Question: How to determine reuse/copy/modified?

Notebook Answer: **Verbatim Copies (Content Hash)**: Group files by file\_sha (the Git blob hash) in the artifacts table\[1\]. Files sharing the same hash contain byte-for-byte identical content\[1\].

* **Copy Counts**: Run a SQL query (GROUP BY file\_sha) to calculate the total number of repositories holding an exact copy of a skill\[2\].  
* **Modifications & History (Commit Metadata)**: Trace edits, churn, and author shifts over time using commit fields (first\_commit\_at, last\_commit\_at, commit\_count, first\_commit\_author, last\_commit\_author)\[1\].  
* **Text & Structural Changes**: Compare parsed YAML front matter (name, description), body length (body\_chars), or body text against group representatives (dedup\_primary \= 1)\[1\].  
* **Bundled Sibling Variations**: Check the artifact\_siblings table to see if supporting files (such as shell scripts or JSON schemas) were added, altered, or omitted across different repository copies

Source cited: GitHub \- giuseppedestefanis/gitskills-sample: Sample dataset for the MSR'27 mining challenge · GitHub 

Team Interpretation: There are many ways we can group files to see if they are direct copies, use history to trace commits, and compare artifact siblings.

Follow up / Uncertainty: What about copies that are just slightly different?

## Question: what is file\_sha and how does it work? 

Notebook Answer:  **file\_sha** is a database column in the dataset that stores the **Git blob hash** of a file's contents\[1\].

* **Identical Bytes \= Identical Hash**: If two files have the exact same content, they produce the same file\_sha value\[1\].  
* **Detecting Verbatim Copies**: In GitSkills, files across different repositories are grouped by file\_sha to identify exact duplicate copies\[1\]\[2\].  
* **Verification & Integrity**: When dataset contents are downloaded, the bytes are checked against file\_sha to ensure the text matches the Git blob hash exactly\[1\].  
* **Counting Reuse**: Researchers can run SQL queries grouping by file\_sha (GROUP BY file\_sha) to count how many times a specific skill file has been copied across repositories

Source cited: GitHub \- giuseppedestefanis/gitskills-sample: Sample dataset for the MSR'27 mining challenge · GitHub 

Team Interpretation: file\_sha may be a really helpful column when trying to find copies because they will have identical hash.

Follow up / Uncertainty: Still hard to determine if it's really close and just one word off or something.

## Question: what is dedup\_primary and how does that work?

Notebook Answer: **dedup\_primary** is a database column in the GitSkills artifacts table that marks the **single representative file** chosen for each distinct skill content\[1\]\[2\].

* **Grouping by Hash**: When the dataset was created, all SKILL.md files were grouped by their Git blob hash (file\_sha), identifying identical copies across repositories\[1\]\[2\].  
* **Designating One Primary File**: For every unique content group, the collection pipeline selected **one representative file** (preferring files located in standard paths like .claude/skills/) and assigned it dedup\_primary \= 1\[2\]. All verbatim copies of that content have dedup\_primary \= 0\[1\]\[2\].  
* **Selective Storage**: To save storage space, resource-intensive fields—such as the full raw text (content), parsed YAML metadata, and folder contents (sibling\_count, has\_scripts)—are populated **only on the representative row** where dedup\_primary \= 1\[1\].  
* **Filtering Duplicate Data**: Researchers can filter SQL queries with WHERE dedup\_primary \= 1 to analyze the 1.88 million unique skill contents without scanning duplicate occurrences

Source cited: GitHub \- giuseppedestefanis/gitskills-sample: Sample dataset for the MSR'27 mining challenge · GitHub 

Team Interpretation: Really helpful when doing copy/modification paths because we can find the 1st one.

Follow up / Uncertainty: Have to learn how to use it to help us in our project.

## Question: How difficult would it be to search for commands that exhibit risky behavior?

Notebook Answer: Searching for commands that exhibit risky behavior in **GitSkills** is **very accessible and straightforward**, primarily because the dataset stores text content directly in a queryable SQLite database and Parquet format\[1\]\[2\].  
Here is how the dataset structure facilitates this type of security analysis, along with a few practical considerations:

#### **What makes it straightforward**

* **Direct Access to Instructions:** The artifacts table contains a content column with the full text of every distinct SKILL.md file\[1\]\[2\]. You can search directly for dangerous commands or patterns (such as rm \-rf, curl | bash, eval, or environment variable exfiltration) using standard SQL LIKE queries or regular expressions\[1\]\[3\].  
* **Queryable Bundled Scripts:** The artifact\_siblings table stores the raw text of scripts bundled alongside skills (up to 100 KB), allowing you to scan executed bash or Python code for risky behavior\[4\]\[5\].  
* **Built-in Filtering Flags:** The artifacts table includes boolean flags like has\_scripts and has\_references, allowing you to narrow your search immediately to skills that invoke external code\[1\].  
* **Diffing Copies for Injected Commands:** Because duplicate files are tracked by content hash (file\_sha), you can compare modified copies of widely reused skills against their originals to check if unreviewed forks introduced new command executions or network calls (a key supply-chain threat highlighted by the dataset authors)\[1\]\[6\].

#### **Practical Considerations**

* **Natural Language Parsing:** Because SKILL.md files instruct LLMs using natural language rather than strict code, pattern matching (regex or NLP models) is needed to distinguish benign command documentation from instructions telling an agent to perform dangerous actions\[7\]\[8\].  
* **File Size Cap on Siblings:** Text files larger than 100 KB and binary executables in artifact\_siblings omit raw content in the dataset (skipped\_reason), though their Git blob hashes (entry\_sha) are preserved if you need to fetch them directly from GitHub\[4\]\[5\].

Source cited: GitSkills: A Dataset of Agent Skills on GitHub | Zenodo

GitHub \- giuseppedestefanis/gitskills-sample: Sample dataset for the MSR'27 mining challenge · GitHub

Team Interpretation: Searchability may not be as difficult as it may seem.

Follow up / Uncertainty: Having the different search terms can lead to different results.

## Question: How does skill reuse vary by programming language?

Notebook Answer: While the sources record repository language metadata and overall reuse statistics, **they do not contain a breakdown of skill reuse rates by specific programming language**\[1\]\[2\].  
Here is what the sources do provide regarding languages and duplication:

* **Top Languages in GitSkills:** The dataset captures skills across public GitHub repositories, where the most frequent primary languages are **Python** (71,801 repositories), **TypeScript** (67,104), **JavaScript** (23,938), **Shell** (19,780), **HTML** (12,187), **Rust** (8,371), and **Go** (8,094)\[2\].  
* **Overall Duplication Rate:** Across the entire dataset, **50.5% of all skill file occurrences are verbatim copies** of another file\[2\]\[3\].

Because the dataset links each skill occurrence to its host repository's primary language via the repos table, determining how skill adoption and duplication differ across programming languages is highlighted as an **open research question** for the MSR 2027 Mining Challenge\[1\]

Source cited: GitHub \- giuseppedestefanis/gitskills-sample: Sample dataset for the MSR'27 mining challenge · GitHub

Team Interpretation: Text based programming seems to be the most popular. Could be easiest for human validation.

Follow up / Uncertainty: More security flaws could be in languages that are not as popular

## Question: How many GitSkills are related to security?

Notebook Answer: **Your sources do not contain a specific count or percentage of security-related GitSkills.**

While an exact figure is missing, the dataset documentation explicitly highlights **security, maintenance, and trust** as one of the primary research tracks for analyzing GitSkills\[1\]:

* **Supply-Chain & Execution Risks:** Because agent skills propagate by direct folder copying without a central package manager or review registry, the dataset is designed to study whether modified copies introduce unreviewed command execution, script execution, or network access into developer workflows\[2\]\[3\].  
* **Executable Capabilities:** The dataset captures folder composition via metadata flags (has\_scripts, has\_references) in the artifacts table\[4\] and includes **7,264,865 bundled sibling files** (such as bash and Python scripts) to help identify executable instructions\[5\]\[6\].

Source cited: MSR 2027 \- Mining Challenge \- MSR 2027

Team Interpretation: It can not tell us exactly but it is probably significant enough to be included as part of the challenge

Follow up / Uncertainty: We would have to do the work ourselves to figure out a better answer for this.

