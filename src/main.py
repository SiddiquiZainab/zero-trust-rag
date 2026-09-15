import os
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from src.engine.rag_chain import RAGChain

# Configuration Constants
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "zero-trust-rag-super-secret-key-change-in-prod")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

app = FastAPI(
    title="Zero-Trust RBAC RAG API",
    description="Enterprise Zero-Trust Retrieval Augmented Generation platform with metadata-enforced access control.",
    version="1.0.0"
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
rag_chain = RAGChain()

# Mock In-Memory User Store (Role & Clearance Mapping)
MOCK_USERS_DB = {
    "alice_eng": {
        "username": "alice_eng",
        "password": "password123",  # In production, hash using Passlib/Bcrypt
        "roles": ["engineering"],
        "clearance": 1
    },
    "bob_hr": {
        "username": "bob_hr",
        "password": "password123",
        "roles": ["hr"],
        "clearance": 4
    }
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
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
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


# --- API Endpoints ---

@app.post("/token", response_model=Token, tags=["Auth"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
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
            "clearance": user["clearance"]
        },
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/query", response_model=QueryResponse, tags=["RAG Engine"])
async def query_rag_engine(
        request: QueryRequest,
        current_user: dict = Depends(get_current_user)
):
    """
    Executes an RBAC-filtered RAG query using credentials extracted directly from the user's JWT.
    """
    response = rag_chain.run(
        query=request.query,
        user_roles=current_user["roles"],
        user_clearance=current_user["clearance"]
    )

    return QueryResponse(
        query=request.query,
        answer=response.get("answer", ""),
        accessed_documents=response.get("accessed_documents", []),
        user_roles=current_user["roles"],
        user_clearance=current_user["clearance"]
    )


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "service": "Zero-Trust RAG API"}