from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.domain.config import settings
from backend.storage.sqlite import users as user_repo
from pydantic import BaseModel

router = APIRouter(prefix="/auth")


class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


class UserResponse(BaseModel):
    id: str
    username: str


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: AuthRequest) -> AuthResponse:
    if not settings.jwt_secret_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Auth not configured")
    username = body.username.strip()
    if not username or len(username) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username must be at least 2 characters")
    if len(body.password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 6 characters")
    existing = user_repo.get_user_by_username(username)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    hashed = hash_password(body.password)
    user = user_repo.create_user(username, hashed)
    token = create_access_token(user["id"], user["username"])
    return AuthResponse(
        token=token,
        user={"id": user["id"], "username": user["username"]},
    )


@router.post("/login", response_model=AuthResponse)
def login(body: AuthRequest) -> AuthResponse:
    if not settings.jwt_secret_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Auth not configured")
    user = user_repo.get_user_by_username(body.username.strip())
    if user is None or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    token = create_access_token(user["id"], user["username"])
    return AuthResponse(
        token=token,
        user={"id": user["id"], "username": user["username"]},
    )


@router.get("/me", response_model=UserResponse)
def me(user: dict = Depends(get_current_user)) -> UserResponse:
    return UserResponse(id=user["id"], username=user["username"])
