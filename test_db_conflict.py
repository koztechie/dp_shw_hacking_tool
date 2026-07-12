import duckdb
from src.db import get_connection, DB_PATH
from src.analyzer.prompt_manager import prompt_manager

print("1. Opening read-write connection...")
con = get_connection()

print("2. Fetching prompt using prompt_manager...")
try:
    prompt = prompt_manager.get_prompt("techspec_generator")
    print("Success! Prompt fetched.")
except Exception as e:
    print(f"Error fetching prompt: {e}")

print("3. Closing main connection...")
con.close()
