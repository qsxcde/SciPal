from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.schemas import AuthRequest, AuthResponse, UserResponse
from backend.api.security import create_access_token, get_current_user
from backend.application import auth as auth_service
from backend.config import settings

router = APIRouter(prefix="/auth")


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: AuthRequest) -> AuthResponse:
    """注册账号并直接签发 token。"""
    if not settings.jwt_secret_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Auth not configured")
    username = body.username.strip()
    if not username or len(username) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username must be at least 2 characters")
    if len(body.password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 6 characters")
    user = auth_service.register_user(username, body.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    token = create_access_token(user["id"], user["username"])
    return AuthResponse(
        token=token,
        user={"id": user["id"], "username": user["username"]},
    )


@router.post("/login", response_model=AuthResponse)
def login(body: AuthRequest) -> AuthResponse:
    """用用户名密码换取 JWT。"""
    if not settings.jwt_secret_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Auth not configured")
    user = auth_service.authenticate(body.username.strip(), body.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    token = create_access_token(user["id"], user["username"])
    return AuthResponse(
        token=token,
        user={"id": user["id"], "username": user["username"]},
    )


@router.get("/me", response_model=UserResponse)
def me(user: dict = Depends(get_current_user)) -> UserResponse:
    """返回当前 token 对应的用户。"""
    return UserResponse(id=user["id"], username=user["username"])
