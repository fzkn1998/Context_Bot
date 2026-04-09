"""Prepare supervised fine-tuning style JSONL from local documents.

This does NOT fine-tune DeepSeek API directly.
It helps you structure your data so you can later fine-tune an open model
(e.g. with LoRA/SFT) or create synthetic Q&A pairs.
"""

import json
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
    from app.rag import load_documents_from_data_dir, split_documents
except ModuleNotFoundError:
    from rag import load_documents_from_data_dir, split_documents

OUT_FILE = Path("training_data.jsonl")


def build_jsonl() -> int:
    docs = load_documents_from_data_dir()
    chunks = split_documents(docs)

    count = 0
    with OUT_FILE.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            text = chunk.page_content.strip()
            if len(text) < 120:
                continue
            sample = {
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an assistant that answers only from the provided company knowledge.",
                    },
                    {
                        "role": "user",
                        "content": f"Use this knowledge to answer future questions accurately:\n\n{text[:2500]}",
                    },
                    {
                        "role": "assistant",
                        "content": "Understood. I will use this information as domain knowledge.",
                    },
                ],
                "metadata": chunk.metadata,
            }
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
            count += 1
    return count


if __name__ == "__main__":
    load_dotenv()
    total = build_jsonl()
    print(f"Wrote {total} training samples to {OUT_FILE}")
