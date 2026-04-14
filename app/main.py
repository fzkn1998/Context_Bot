import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from dotenv import load_dotenv
from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent
STATIC_DIR = PROJECT_DIR / "static"
TEMPLATES_DIR = PROJECT_DIR / "templates"

# Load .env BEFORE importing rag so env vars are available at module level
load_dotenv(PROJECT_DIR / ".env")

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
        get_api_status,
    )
    from app.database import init_db
    from app.auth import (
        create_session_token,
        create_verify_token,
        decode_token,
        hash_password,
        send_verification_email,
        verify_password,
    )
    from app.database import get_db
except ModuleNotFoundError:
    from rag import (
        DATA_DIR,
        SUPPORTED_EXTENSIONS,
        ask_question,
        build_vectorstore,
        get_api_status,
    )
    from database import init_db
    from auth import (
        create_session_token,
        create_verify_token,
        decode_token,
        hash_password,
        send_verification_email,
        verify_password,
    )
    from database import get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="ContextDesk", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_current_user(cd_session: Optional[str] = Cookie(default=None)) -> Optional[dict]:
    if not cd_session:
        return None
    payload = decode_token(cd_session)
    if not payload or payload.get("type") != "session":
        return None
    return {"id": int(payload["sub"]), "email": payload["email"]}


def require_auth(user: Optional[dict] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/")
def home(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/auth", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"app_name": "ContextDesk", "user": user},
    )


@app.get("/auth")
def auth_page(request: Request, user: Optional[dict] = Depends(get_current_user)):
    if user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request=request, name="auth.html", context={})


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.post("/auth/signup")
def signup(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    email = email.strip().lower()
    name = name.strip()

    if len(password) < 8:
        return RedirectResponse(
            url="/auth?" + urlencode({"tab": "signup", "error": "weak_password"}),
            status_code=303,
        )

    if password != confirm_password:
        return RedirectResponse(
            url="/auth?" + urlencode({"tab": "signup", "error": "password_mismatch"}),
            status_code=303,
        )

    db = get_db()
    try:
        existing = db.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if existing:
            return RedirectResponse(
                url="/auth?" + urlencode({"tab": "signup", "error": "email_exists"}),
                status_code=303,
            )

        pw_hash = hash_password(password)
        db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, pw_hash),
        )
        db.commit()
    finally:
        db.close()

    # Send verification email
    token = create_verify_token(email)
    verify_url = f"{_base_url(request)}/verify-email?token={token}"
    try:
        send_verification_email(email, name, verify_url)
    except Exception as exc:
        print(f"[ContextDesk] Email send failed: {exc}")
        print(f"[ContextDesk] Verify URL (manual): {verify_url}")
        return RedirectResponse(
            url="/auth?" + urlencode({"tab": "signup", "error": "email_failed"}),
            status_code=303,
        )

    return RedirectResponse(
        url="/auth?" + urlencode({"msg": "email_sent"}),
        status_code=303,
    )


@app.post("/auth/login")
def login(
    email: str = Form(...),
    password: str = Form(...),
):
    email = email.strip().lower()

    db = get_db()
    try:
        user = db.execute(
            "SELECT id, name, password_hash, is_verified FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    finally:
        db.close()

    if not user or not verify_password(password, user["password_hash"]):
        return RedirectResponse(
            url="/auth?" + urlencode({"error": "invalid_credentials"}),
            status_code=303,
        )

    if not user["is_verified"]:
        return RedirectResponse(
            url="/auth?" + urlencode({"error": "not_verified"}),
            status_code=303,
        )

    token = create_session_token(user["id"], email)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="cd_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,  # 7 days
    )
    return response


@app.get("/verify-email")
def verify_email(token: str):
    payload = decode_token(token)
    if not payload or payload.get("type") != "verify":
        return RedirectResponse(
            url="/auth?" + urlencode({"error": "token_invalid"}),
            status_code=302,
        )

    email = payload.get("email", "")
    db = get_db()
    try:
        user = db.execute(
            "SELECT id, is_verified FROM users WHERE email = ?", (email,)
        ).fetchone()
        if not user:
            return RedirectResponse(
                url="/auth?" + urlencode({"error": "token_invalid"}),
                status_code=302,
            )
        if not user["is_verified"]:
            db.execute(
                "UPDATE users SET is_verified = 1 WHERE email = ?", (email,)
            )
            db.commit()
    finally:
        db.close()

    return RedirectResponse(
        url="/auth?" + urlencode({"msg": "verified"}),
        status_code=302,
    )


@app.get("/logout")
def logout():
    response = RedirectResponse(
        url="/auth?" + urlencode({"msg": "logged_out"}),
        status_code=302,
    )
    response.delete_cookie("cd_session")
    return response


# ---------------------------------------------------------------------------
# API routes (require auth)
# ---------------------------------------------------------------------------

@app.get("/status")
def status(_: dict = Depends(require_auth)):
    return get_api_status()


@app.get("/documents")
def list_documents(_: dict = Depends(require_auth)):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    files = [
        p.name for p in DATA_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return {"files": sorted(files)}


@app.post("/upload")
def upload_file(file: UploadFile = File(...), _: dict = Depends(require_auth)):
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
def delete_document(filename: str, _: dict = Depends(require_auth)):
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
def reindex(_: dict = Depends(require_auth)):
    try:
        chunks, location = build_vectorstore()
        return {"message": "Index rebuilt", "chunks": chunks, "location": location}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/chat")
def chat(payload: dict, _: dict = Depends(require_auth)):
    question = payload.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    try:
        return ask_question(question)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
