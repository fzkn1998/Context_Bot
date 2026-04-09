import os
import pickle
import re
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse

import docx2txt
import numpy as np
import requests
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = Path(__file__).resolve().parent.parent
VECTORSTORE_DIR = BASE_DIR / os.getenv("VECTORSTORE_DIR", "vectorstore")
INDEX_FILE = VECTORSTORE_DIR / "tfidf_index.pkl"
DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:7b")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "4"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def normalize_lookup_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def build_search_text(document: Document) -> str:
    source = document.metadata.get("source", "")
    source_stem = Path(source).stem if source else ""
    return "\n".join(
        part for part in (source, source_stem, normalize_lookup_text(source_stem), document.page_content) if part
    )


def list_uploaded_sources() -> List[str]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    files = [
        path.name for path in DATA_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(files)


def get_retrieval_backend() -> str:
    if not INDEX_FILE.exists():
        return "not-built"

    try:
        store = load_vectorstore()
    except Exception:
        return "unknown"

    if store.get("retrieval_backend"):
        return str(store["retrieval_backend"])
    if "embeddings" in store:
        return "sentence-transformers"
    if {"vectorizer", "matrix"}.issubset(store):
        return "tfidf"
    return "unknown"


def load_documents_from_data_dir() -> List[Document]:
    docs: List[Document] = []
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for path in DATA_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        ext = path.suffix.lower()
        if ext == ".pdf":
            pages = PyPDFLoader(str(path)).load()
            for p in pages:
                p.metadata["source"] = path.name
            docs.extend(pages)
        elif ext in {".txt", ".md"}:
            loaded = TextLoader(str(path), encoding="utf-8").load()
            for d in loaded:
                d.metadata["source"] = path.name
            docs.extend(loaded)
        elif ext == ".docx":
            text = docx2txt.process(str(path))
            docs.append(Document(page_content=text, metadata={"source": path.name}))

    return docs


def split_documents(documents: List[Document]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_documents(documents)


def _build_tfidf_vectorstore(chunks: List[Document], texts: List[str]) -> Tuple[int, str]:
    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform(texts)

    VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
    with INDEX_FILE.open("wb") as handle:
        pickle.dump(
            {
                "documents": chunks,
                "vectorizer": vectorizer,
                "matrix": matrix,
                "retrieval_backend": "tfidf",
            },
            handle,
        )

    return len(chunks), str(INDEX_FILE)


def build_vectorstore() -> Tuple[int, str]:
    docs = load_documents_from_data_dir()
    if not docs:
        raise ValueError("No supported files found in data/ directory.")

    chunks = split_documents(docs)
    texts = [build_search_text(chunk) for chunk in chunks]

    try:
        embedder = SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)
        embeddings = embedder.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    except Exception:
        return _build_tfidf_vectorstore(chunks, texts)

    VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
    with INDEX_FILE.open("wb") as handle:
        pickle.dump(
            {
                "documents": chunks,
                "embeddings": embeddings,
                "model_name": EMBEDDING_MODEL,
                "retrieval_backend": "sentence-transformers",
            },
            handle,
        )

    return len(chunks), str(INDEX_FILE)


def load_vectorstore() -> dict:
    if not INDEX_FILE.exists():
        raise FileNotFoundError("Vector store not found. Run ingestion first.")

    with INDEX_FILE.open("rb") as handle:
        return pickle.load(handle)


def _legacy_retrieve_documents(store: dict, question: str, top_k: int) -> List[Document]:
    vectorizer = store["vectorizer"]
    matrix = store["matrix"]
    documents: List[Document] = store["documents"]

    normalized_question = normalize_lookup_text(question)
    query_vector = vectorizer.transform([f"{question}\n{normalized_question}"])
    scores = cosine_similarity(query_vector, matrix).flatten()
    ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)

    results: List[Document] = []
    for index, score in ranked[:top_k]:
        if score <= 0:
            continue
        results.append(documents[index])
    return results


def retrieve_documents_by_source_match(documents: List[Document], question: str, top_k: int) -> List[Document]:
    normalized_question = normalize_lookup_text(question)
    if not normalized_question:
        return []

    matched: List[Document] = []
    seen_sources = set()
    for document in documents:
        source = document.metadata.get("source", "")
        source_stem = Path(source).stem if source else ""
        candidates = {normalize_lookup_text(source), normalize_lookup_text(source_stem)}
        if any(candidate and candidate in normalized_question for candidate in candidates):
            source_key = source or source_stem or id(document)
            if source_key in seen_sources:
                continue
            seen_sources.add(source_key)
            matched.append(document)
            if len(matched) >= top_k:
                break
    return matched


def answer_source_inventory_question(question: str) -> dict | None:
    normalized_question = normalize_lookup_text(question)
    sources = list_uploaded_sources()
    if not sources:
        return None

    if "how many document" in normalized_question or "how many file" in normalized_question:
        count = len(sources)
        noun = "document" if count == 1 else "documents"
        return {
            "answer": f"I currently have {count} uploaded {noun}: {', '.join(sources)}.",
            "sources": sources,
        }

    if (
        "what documents" in normalized_question
        or "which documents" in normalized_question
        or "list documents" in normalized_question
        or "list files" in normalized_question
        or "what files" in normalized_question
    ):
        return {
            "answer": "Uploaded sources: " + ", ".join(sources) + ".",
            "sources": sources,
        }

    return None


def get_ollama_tags_url() -> str:
    parsed = urlparse(OLLAMA_BASE_URL)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return f"{base}/api/tags"


def get_ollama_status() -> dict:
    retrieval_backend = get_retrieval_backend()
    try:
        response = requests.get(get_ollama_tags_url(), timeout=5)
        response.raise_for_status()
    except requests.RequestException as exc:
        return {
            "connected": False,
            "model_available": False,
            "base_url": OLLAMA_BASE_URL,
            "model": OLLAMA_MODEL,
            "retrieval_backend": retrieval_backend,
            "detail": (
                "Could not connect to Ollama. Start the Ollama app or server and make sure it"
                f"is reachable at {OLLAMA_BASE_URL}."
            ),
            "error": str(exc),
        }

    payload = response.json()
    models = payload.get("models", [])
    available_names = {model.get("name") for model in models if model.get("name")}
    return {
        "connected": True,
        "model_available": OLLAMA_MODEL in available_names,
        "base_url": OLLAMA_BASE_URL,
        "model": OLLAMA_MODEL,
        "retrieval_backend": retrieval_backend,
        "available_models": sorted(available_names),
        "detail": (
            "Ollama is reachable."
            if OLLAMA_MODEL in available_names
            else f"Ollama is reachable, but model '{OLLAMA_MODEL}' is not pulled yet."
        ),
    }


def get_llm() -> ChatOpenAI:
    status = get_ollama_status()
    if not status["connected"]:
        raise RuntimeError(status["detail"])
    if not status["model_available"]:
        raise RuntimeError(
            f"Model '{OLLAMA_MODEL}' is not available in Ollama. Pull it first with "
            f"'ollama pull {OLLAMA_MODEL}'."
        )

    return ChatOpenAI(
        model=OLLAMA_MODEL,
        api_key=OLLAMA_API_KEY,
        base_url=OLLAMA_BASE_URL,
        temperature=0.2,
    )


def retrieve_documents(question: str, top_k: int = RETRIEVAL_TOP_K) -> List[Document]:
    store = load_vectorstore()
    documents: List[Document] = store["documents"]
    matched_by_source = retrieve_documents_by_source_match(documents, question, top_k)
    if matched_by_source:
        return matched_by_source

    if "embeddings" in store:
        embeddings = store["embeddings"]
        model_name = store.get("model_name", EMBEDDING_MODEL)

        try:
            embedder = SentenceTransformer(model_name, local_files_only=True)
            query_vector = embedder.encode([question], convert_to_numpy=True)
            scores = cosine_similarity(query_vector, embeddings).flatten()
            ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)

            results: List[Document] = []
            for index, score in ranked[:top_k]:
                if score <= 0:
                    continue
                results.append(documents[index])
            return results
        except Exception:
            if {"documents", "vectorizer", "matrix"}.issubset(store):
                return _legacy_retrieve_documents(store, question, top_k)
            raise

    if {"documents", "vectorizer", "matrix"}.issubset(store):
        return _legacy_retrieve_documents(store, question, top_k)

    raise ValueError(
        "Vector store format is not supported. Rebuild the index from the UI or run "
        "'python -m app.ingest'."
    )

def format_context(documents: List[Document]) -> str:
    parts = []
    for doc in documents:
        source = doc.metadata.get("source", "unknown")
        parts.append(f"Source: {source}\n{doc.page_content}")
    return "\n\n".join(parts)


def extract_answer_content(result) -> str:
    content = getattr(result, "content", result)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item) for item in content
        )
    return str(content)


def ask_general_question(question: str) -> dict:
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are a helpful multilingual assistant inside a document chatbot. "
                    "If the user asks a general conversational question that does not require "
                    "uploaded documents, answer naturally and concisely. If the user asks in Urdu "
                    "or asks whether you can speak Urdu, respond in Urdu."
                ),
            ),
            ("human", "Question: {input}"),
        ]
    )

    llm = get_llm()
    response = llm.invoke(prompt.format_messages(input=question))
    return {
        "answer": extract_answer_content(response) or "No answer generated.",
        "sources": [],
    }


def ask_question(question: str) -> dict:
    inventory_answer = answer_source_inventory_question(question)
    if inventory_answer is not None:
        return inventory_answer

    context_docs = retrieve_documents(question)
    if not context_docs:
        try:
            return ask_general_question(question)
        except Exception:
            return {
                "answer": "I could not find relevant information in the uploaded data.",
                "sources": [],
            }

    system_prompt = """You are a helpful assistant.
Use the retrieved context to answer the user.
If the answer is not in the context, say clearly that it was not found in the uploaded data.
Keep the answer concise and reliable.

Context:
{context}
"""

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "Question: {input}"),
        ]
    )

    llm = get_llm()
    response = llm.invoke(
        prompt.format_messages(
            context=format_context(context_docs),
            input=question,
        )
    )

    sources = []
    seen = set()
    for doc in context_docs:
        source = doc.metadata.get("source", "unknown")
        if source not in seen:
            seen.add(source)
            sources.append(source)

    return {
        "answer": extract_answer_content(response) or "No answer generated.",
        "sources": sources,
    }
