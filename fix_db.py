import os

def fix_duckdb_connect(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    if "duckdb.connect" not in content:
        return

    # Add import safely
    if "from src.db import get_connection" not in content:
        content = content.replace("import duckdb", "import duckdb\nfrom src.db import get_connection", 1)

    content = content.replace("duckdb.connect(DB_PATH, read_only=True)", "get_connection(read_only=True)")
    content = content.replace("duckdb.connect(DB_PATH)", "get_connection(read_only=False)")
    content = content.replace("duckdb.connect(str(DB_PATH))", "get_connection(read_only=False)")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

for root, _, files in os.walk("src/api"):
    for file in files:
        if file.endswith(".py"):
            fix_duckdb_connect(os.path.join(root, file))
print("Fixed DB connections")
