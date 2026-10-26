"""Authentication transfer models."""

from pydantic import BaseModel


class AuthRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str


class AuthResponse(BaseModel):
    token: str
    user: UserResponse
