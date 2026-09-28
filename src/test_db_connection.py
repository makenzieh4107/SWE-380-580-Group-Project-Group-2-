import duckdb
import os

db_path = "data/agent_skills_sample.db"

print("Current folder:", os.getcwd())
print("Database path:", os.path.abspath(db_path))
print("Database exists:", os.path.exists(db_path))
print("Database size:", os.path.getsize(db_path), "bytes")

con = duckdb.connect()

con.execute(f"ATTACH '{db_path}' AS GitSkills")

print("\nTables:")
print(con.execute("SHOW TABLES FROM GitSkills").fetchdf())

con.close()