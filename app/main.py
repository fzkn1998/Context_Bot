import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent
STATIC_DIR = PROJECT_DIR / "static"
TEMPLATES_DIR = PROJECT_DIR / "templates"

for path in (CURRENT_DIR, PROJECT_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

try:
    from app.rag import (
        DATA_DIR,
        SUPPORTED_EXTENSIONS,
        ask_question,
        build_vectorstore,
        get_ollama_status,
    )
except ModuleNotFoundError:
    from rag import (
        DATA_DIR,
        SUPPORTED_EXTENSIONS,
        ask_question,
        build_vectorstore,
        get_ollama_status,
    )

load_dotenv()

app = FastAPI(title="ContextDesk")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"app_name": "ContextDesk"},
    )


@app.get("/status")
def status():
    return get_ollama_status()


@app.get("/documents")
def list_documents():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    files = [
        p.name for p in DATA_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return {"files": sorted(files)}


@app.post("/upload")
def upload_file(file: UploadFile = File(...)):
    safe_name = Path(file.filename or "").name
    if not safe_name:
        raise HTTPException(status_code=400, detail="Filename is required")

    suffix = Path(safe_name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    destination = (DATA_DIR / safe_name).resolve()
    data_dir_resolved = DATA_DIR.resolve()
    if destination.parent != data_dir_resolved:
        raise HTTPException(status_code=400, detail="Invalid filename")

    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"message": "File uploaded", "filename": safe_name}


@app.delete("/documents/{filename}")
def delete_document(filename: str):
    safe_name = Path(filename).name
    path = (DATA_DIR / safe_name).resolve()
    data_dir_resolved = DATA_DIR.resolve()
    if path.parent != data_dir_resolved:
        raise HTTPException(status_code=400, detail="Invalid file")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file")
    path.unlink()
    return {"message": "Deleted", "filename": safe_name}


@app.post("/reindex")
def reindex():
    try:
        chunks, location = build_vectorstore()
        return {"message": "Index rebuilt", "chunks": chunks, "location": location}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/chat")
def chat(payload: dict):
    question = payload.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    try:
        return ask_question(question)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
