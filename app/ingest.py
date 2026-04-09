import sys
from pathlib import Path

from dotenv import load_dotenv

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent
for path in (CURRENT_DIR, PROJECT_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

try:
    from app.rag import build_vectorstore
except ModuleNotFoundError:
    from rag import build_vectorstore


if __name__ == "__main__":
    load_dotenv()
    chunks, location = build_vectorstore()
    print(f"Indexed {chunks} chunks into {location}")
