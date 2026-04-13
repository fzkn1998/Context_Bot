# RAG Chatbot for Local Document Q&A

A local document question-answering chatbot built with FastAPI, LangChain, local retrieval, and Ollama.

This project lets you:
- upload local documents
- build a searchable knowledge index
- ask questions grounded in your uploaded files
- prepare JSONL data for later fine-tuning workflows

## Features

- FastAPI backend with a single-page web UI
- Supports `.txt`, `.md`, `.pdf`, and `.docx`
- Local document indexing
- Retrieval using:
  - `sentence-transformers` if the embedding model is available locally
  - `TF-IDF` fallback if embeddings are not available
- Ollama-based local LLM inference
- Simple dataset preparation script for SFT-style JSONL generation

## Project Structure

```text
Context_chatbot/
|-- app/
|   |-- main.py          # FastAPI app and UI
|   |-- rag.py           # document loading, indexing, retrieval, chat logic
|   |-- ingest.py        # manual index build entrypoint
|   `-- dataset_prep.py  # JSONL dataset preparation
|-- data/                # uploaded documents, ignored by git
|-- vectorstore/         # generated index files, ignored by git
|-- .env.example         # example environment variables
|-- requirements.txt
`-- README.md
```

## Requirements

- Python 3.10+
- Ollama installed and running locally
- A pulled Ollama model, for example:

```bash
ollama pull deepseek-r1:7b
```

## Setup

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Configuration

Update `.env` if needed:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
OLLAMA_MODEL=deepseek-r1:7b
OLLAMA_API_KEY=ollama
VECTORSTORE_DIR=vectorstore
DATA_DIR=data
RETRIEVAL_TOP_K=4
```

## Run The App

Start the FastAPI server:

```bash
uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## Typical Workflow

1. Start Ollama locally.
2. Run the FastAPI app.
3. Upload documents from the web UI.
4. Rebuild the index with the `Reindex` action.
5. Ask questions grounded in your uploaded files.

## Optional Scripts

Build the vector index manually:

```bash
python app/ingest.py
```

Prepare JSONL training-style data from local documents:

```bash
python app/dataset_prep.py
```

## Notes

- Keep `.env` out of Git because it may contain local configuration or secrets.
- The `data/` and `vectorstore/` directories are generated locally and should usually stay untracked.
- If `sentence-transformers` is not available locally, the app falls back to TF-IDF retrieval.
