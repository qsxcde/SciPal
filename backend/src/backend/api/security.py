from datetime import UTC, datetime, timedelta

import asyncio

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from backend.application import auth as auth_service
from backend.config import settings

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

# 未配置 JWT_SECRET_KEY 时允许匿名访问的环境；生产环境必须显式配置鉴权。
_ANONYMOUS_ALLOWED_ENVS = frozenset({"development", "dev", "local", "test", "testing"})


def anonymous_access_allowed() -> bool:
    """Whether an unset JWT secret may degrade to anonymous access."""
    return settings.app_env.strip().lower() in _ANONYMOUS_ALLOWED_ENVS


def create_access_token(user_id: str, username: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "username": username, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        return None


async def get_current_user(token: str | None = Depends(_oauth2_scheme)) -> dict:
    if not settings.jwt_secret_key:
        if settings.app_env.strip().lower() not in _ANONYMOUS_ALLOWED_ENVS:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication is not configured",
            )
        return {"id": "", "username": "dev"}
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    # SQLite 是同步驱动：放到线程里查，避免阻塞事件循环（会影响同进程的 SSE）
    user = await asyncio.to_thread(auth_service.get_user, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
