import hmac
import json
import os
import re
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from src.engine.rag_chain import RAGChain
from src.ingestion.pipeline import IngestionPipeline

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
MAX_UPLOAD_BYTES = 1_048_576
MIN_PASSWORD_LENGTH = 12


def _required_config_value(name: str, minimum_length: int) -> str:
    value = os.getenv(name, "").strip()
    lowered = value.lower()
    if len(value) < minimum_length or any(
        marker in lowered for marker in ("replace_with", "change_me", "your_secret")
    ):
        raise RuntimeError(
            f"{name} must be configured with a non-placeholder value "
            f"of at least {minimum_length} characters."
        )
    return value


SECRET_KEY = _required_config_value("JWT_SECRET_KEY", 32)


def _build_configured_users() -> dict:
    """Load local account credentials from environment; never ship shared passwords."""
    return {
        "alice_eng": {
            "username": "alice_eng",
            "password": _required_config_value("DEMO_ALICE_PASSWORD", MIN_PASSWORD_LENGTH),
            "roles": ["engineering"],
            "clearance": 2,
        },
        "bob_hr": {
            "username": "bob_hr",
            "password": _required_config_value("DEMO_HR_PASSWORD", MIN_PASSWORD_LENGTH),
            "roles": ["hr"],
            "clearance": 4,
        },
        "admin_user": {
            "username": "admin_user",
            "password": _required_config_value("DEMO_ADMIN_PASSWORD", MIN_PASSWORD_LENGTH),
            "roles": ["admin", "engineering", "hr"],
            "clearance": 5,
        },
    }


USERS_BY_USERNAME = _build_configured_users()
rag_chain: Optional[RAGChain] = None
ingestion_pipeline: Optional[IngestionPipeline] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag_chain, ingestion_pipeline
    rag_chain = RAGChain()
    ingestion_pipeline = IngestionPipeline(data_dir="data")
    yield


app = FastAPI(
    title="Zero-Trust RBAC RAG API",
    description="Document-level access-controlled retrieval-augmented generation API.",
    version="1.1.0",
    lifespan=lifespan,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class Token(BaseModel):
    access_token: str
    token_type: str


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)


class QueryResponse(BaseModel):
    query: str
    answer: str
    accessed_documents: List[str]
    user_roles: List[str]
    user_clearance: int


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate JWT credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None or username not in USERS_BY_USERNAME:
            raise credentials_exception
        # Authorization attributes come from the server-side user map.
        return USERS_BY_USERNAME[username]
    except JWTError as exc:
        raise credentials_exception from exc


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Restrict document uploads to the configured administrator identity."""
    if "admin" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: admin privileges are required for document uploads.",
        )
    return current_user


@app.post("/token", response_model=Token, tags=["Auth"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = USERS_BY_USERNAME.get(form_data.username)
    provided = form_data.password.encode("utf-8")
    expected = user["password"].encode("utf-8") if user else b"invalid-user-password"
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(
        data={
            "sub": user["username"],
            "roles": user["roles"],
            "clearance": user["clearance"],
        }
    )
    return {"access_token": token, "token_type": "bearer"}


@app.post("/query", response_model=QueryResponse, tags=["RAG Engine"])
async def query_rag_engine(
    request: QueryRequest, current_user: dict = Depends(get_current_user)
):
    response = rag_chain.run(
        query=request.query,
        user_roles=current_user["roles"],
        user_clearance=current_user["clearance"],
    )
    return QueryResponse(
        query=request.query,
        answer=response.get("answer", ""),
        accessed_documents=response.get("accessed_documents", []),
        user_roles=current_user["roles"],
        user_clearance=current_user["clearance"],
    )


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "service": "Zero-Trust RAG API"}


MANIFEST_PATH = Path("data/manifest.json")


@app.post("/upload", tags=["Ingestion"])
async def upload_document(
    file: UploadFile = File(...),
    target_roles: str = Form(...),
    clearance_level: int = Form(...),
    admin_user: dict = Depends(require_admin),
):
    """Validate and index a UTF-8 text or Markdown document."""
    raw_filename = file.filename or ""
    if not raw_filename or "/" in raw_filename or "\\" in raw_filename:
        raise HTTPException(status_code=400, detail="Filename must not contain a path.")

    filename = Path(raw_filename).name
    if filename in {"", ".", ".."} or Path(filename).suffix.lower() not in {".txt", ".md"}:
        raise HTTPException(status_code=400, detail="Only .txt and .md files are supported.")
    if not 1 <= clearance_level <= 5:
        raise HTTPException(status_code=400, detail="clearance_level must be between 1 and 5.")

    roles_list = [role.strip().lower() for role in target_roles.split(",") if role.strip()]
    if not roles_list or any(
        not re.fullmatch(r"[a-z0-9_-]{1,64}", role) for role in roles_list
    ):
        raise HTTPException(
            status_code=400,
            detail="Provide roles using letters, numbers, underscores, or hyphens.",
        )

    content_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds the 1 MiB limit.")
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Upload must be UTF-8 encoded text.") from exc
    if not content.strip():
        raise HTTPException(status_code=400, detail="Empty documents cannot be indexed.")

    data_dir = Path("data").resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    file_path = data_dir / filename
    if file_path.is_symlink() or file_path.resolve().parent != data_dir:
        raise HTTPException(status_code=400, detail="Unsafe upload path.")

    manifest_path = MANIFEST_PATH
    manifest_data = []
    if manifest_path.exists():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest_data, list) or any(
                not isinstance(item, dict) for item in manifest_data
            ):
                raise ValueError("Manifest root must be a list of objects.")
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=500,
                detail="The document manifest is invalid; repair it before uploading.",
            ) from exc

    existing_entry = next(
        (item for item in manifest_data if item.get("filename") == filename), {}
    )
    # Reuse custom manifest IDs so old indexed chunks are replaced, not orphaned.
    stable_doc_id = existing_entry.get("doc_id") or f"doc-{Path(filename).stem}"
    updated_manifest = [
        item for item in manifest_data if item.get("filename") != filename
    ]
    updated_manifest.append({
        "filename": filename,
        "doc_id": stable_doc_id,
        "allowed_roles": roles_list,
        "clearance_level": clearance_level,
        "uploaded_by": admin_user["username"],
    })

    temp_path = None
    temp_manifest_path = None
    try:
        # Stage content outside the manifest path and keep the public source name
        # stable. The indexer replaces prior chunks for this doc_id before upsert.
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".upload-",
            suffix=".tmp",
            dir=data_dir,
            delete=False,
        ) as staged_file:
            staged_file.write(content)
            temp_path = Path(staged_file.name)

        temp_manifest_path = manifest_path.with_name(
            f".{manifest_path.name}.{uuid.uuid4().hex}.tmp"
        )
        temp_manifest_path.write_text(
            json.dumps(updated_manifest, indent=2), encoding="utf-8"
        )

        ingestion_pipeline.ingest_file(
            file_path=temp_path,
            allowed_roles=roles_list,
            clearance_level=clearance_level,
            doc_id=stable_doc_id,
            source_name=filename,
        )
        os.replace(temp_path, file_path)
        os.replace(temp_manifest_path, manifest_path)
    finally:
        for leftover in (temp_path, temp_manifest_path):
            if leftover is not None and leftover.exists():
                leftover.unlink()

    return {
        "status": "success",
        "filename": filename,
        "assigned_roles": roles_list,
        "assigned_clearance": clearance_level,
        "manifest_updated": True,
    }
