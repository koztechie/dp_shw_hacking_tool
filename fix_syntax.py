import os
import glob
import re

for file_path in glob.glob("src/api/*.py"):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove all inline/wrongly indented imports we added
    content = content.replace("from src.db import get_connection\n", "")
    content = content.replace("from src.db import get_connection", "")
    
    # Add it at the top level
    content = "from src.db import get_connection\n" + content
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    
print("Syntax fixed")
