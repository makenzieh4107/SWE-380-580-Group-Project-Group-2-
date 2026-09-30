## Dataset Setup

This project uses the approved GitSkills sample database.

The database file is named:

agent_skills_sample.db

## Setup Steps

Obtain the approved GitSkills sample database.
Place the database file directly inside the project's data folder.
The final file path should be:
data/agent_skills_sample.db
Do not rename the database file.
Do not place it inside the samples folder.
The database is not stored in this GitHub repository because it is approximately 277 MB, which exceeds GitHub's 100 MB file-size limit.

After setup, the project should look like:

project/
├── data/
│   ├── agent_skills_sample.db
│   └── README.md
├── src/
│   └── duplicate_analysis.py
└── README.md

The analysis scripts expect the database at exactly:

data/agent_skills_sample.db

## Verify the Setup

From the project root, run:

python src/test_db_connection.py

If the database is in the correct location, the script will connect to it and run the duplicate-artifact analysis.

Important: The dataset is analyzed as data only. Do not execute scripts or code contained within the dataset.
