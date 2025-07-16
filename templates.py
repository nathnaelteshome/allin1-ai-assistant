import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s]: %(message)s:')

# List of files to be created
list_of_files = [
    ".gitignore",
    "README.md",
    "requirements.txt",
    "src/app.py",
    "src/controllers/query_controller.py",
    "src/domain/models/llm_selection.py",
    "src/infrastructure/apis/__init__.py",  # Keep folder visible in version control
    "src/infrastructure/llm/llm_interface.py",
    "src/infrastructure/llm/chatgpt_llm.py",
    "src/infrastructure/llm/claude_llm.py",
    "src/infrastructure/llm/gemini_llm.py",
    "src/infrastructure/llm/llm_list.py",
    "src/use_cases/route_query.py",
]

# Create directories and files
for filepath in list_of_files:
    filepath = Path(filepath)
    filedir, filename = os.path.split(filepath)

    if filedir != "":
        os.makedirs(filedir, exist_ok=True)
        logging.info(f"Creating directory: {filedir} for the file: {filename}")
    
    if (not os.path.exists(filepath)) or (os.path.getsize(filepath) == 0):
        with open(filepath, 'w') as f:
            pass  # Create an empty file
        logging.info(f"Creating empty file: {filepath}")
    else:
        logging.info(f"{filename} already exists")
