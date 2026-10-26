"""Authentication use cases: credential checks and user persistence."""

import bcrypt

from backend.storage.sqlite import users as user_repo


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def register_user(username: str, password: str) -> dict | None:
    """Create the account, or return None when the username is taken."""
    if user_repo.get_user_by_username(username) is not None:
        return None
    return user_repo.create_user(username, hash_password(password))


def authenticate(username: str, password: str) -> dict | None:
    """Return the user row when the credentials match, otherwise None."""
    user = user_repo.get_user_by_username(username)
    if user is None:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


def get_user(user_id: str) -> dict | None:
    return user_repo.get_user_by_id(user_id)
