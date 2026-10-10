import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel

from src.engine.rag_chain import RAGChain
from src.ingestion.pipeline import IngestionPipeline

# Configuration Constants
SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY", "super-secret-zero-trust-key-change-in-prod"
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

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
    description="Enterprise Zero-Trust Retrieval Augmented Generation platform with metadata-enforced access control.",
    version="1.0.0",
    lifespan=lifespan,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Mock In-Memory User Store (Role & Clearance Mapping)
MOCK_USERS_DB = {
    "alice_eng": {
        "username": "alice_eng",
        "password": "password123",
        "roles": ["engineering"],
        "clearance": 2,
    },
    "bob_hr": {
        "username": "bob_hr",
        "password": "password123",
        "roles": ["hr"],
        "clearance": 4,
    },
    "admin_user": {
        "username": "admin_user",
        "password": "password123",
        "roles": ["admin", "engineering", "hr"],
        "clearance": 5,
    },
}


# Pydantic Schemas
class Token(BaseModel):
    access_token: str
    token_type: str


class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    query: str
    answer: str
    accessed_documents: List[str]
    user_roles: List[str]
    user_clearance: int


# Auth Utilities
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=15)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate JWT credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None or username not in MOCK_USERS_DB:
            raise credentials_exception
        return MOCK_USERS_DB[username]
    except JWTError:
        raise credentials_exception


def require_admin(current_user: dict = Depends(get_current_user)):
    """FastAPI dependency to restrict endpoints strictly to admin role."""
    if "admin" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Admin privileges required to perform document uploads.",
        )
    return current_user


# --- API Endpoints ---


@app.post("/token", response_model=Token, tags=["Auth"])
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    user = MOCK_USERS_DB.get(form_data.username)
    if not user or user["password"] != form_data.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user["username"],
            "roles": user["roles"],
            "clearance": user["clearance"],
        },
        expires_delta=access_token_expires,
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/query", response_model=QueryResponse, tags=["RAG Engine"])
async def query_rag_engine(
    request: QueryRequest, current_user: dict = Depends(get_current_user)
):
    """Executes an RBAC-filtered RAG query using credentials extracted directly from the user's JWT."""
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


MANIFEST_PATH = "data/manifest.json"


@app.post("/upload", tags=["Ingestion"])
async def upload_document(
    file: UploadFile = File(...),
    target_roles: str = Form(...),  # Comma-separated: e.g. "engineering,hr"
    clearance_level: int = Form(...),
    admin_user: dict = Depends(require_admin),  # Route guard
):
    if not (file.filename.endswith(".txt") or file.filename.endswith(".md")):
        raise HTTPException(
            status_code=400, detail="Only .txt and .md files are supported."
        )

    # 1. Parse target roles
    roles_list = [
        r.strip().lower() for r in target_roles.split(",") if r.strip()
    ]
    if not roles_list:
        raise HTTPException(
            status_code=400, detail="At least one target role must be provided."
        )

    content = (await file.read()).decode("utf-8")

    # 2. Save raw file locally inside data/
    os.makedirs("data", exist_ok=True)
    file_path = os.path.join("data", file.filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    # 3. Update manifest.json
    manifest_data = []
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
        except json.JSONDecodeError:
            manifest_data = []

    # Remove existing record if re-uploading the same file name
    manifest_data = [
        doc for doc in manifest_data if doc.get("filename") != file.filename
    ]

    new_entry = {
        "filename": file.filename,
        "allowed_roles": roles_list,
        "clearance_level": clearance_level,
        "uploaded_by": admin_user["username"],
    }
    manifest_data.append(new_entry)

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=4)

    # 4. Chunk & Index into Qdrant using IngestionPipeline
    from pathlib import Path

    ingestion_pipeline.ingest_file(
        file_path=Path(file_path),
        allowed_roles=roles_list,
        clearance_level=clearance_level,
    )

    return {
        "status": "success",
        "filename": file.filename,
        "assigned_roles": roles_list,
        "assigned_clearance": clearance_level,
        "manifest_updated": True,
    }