"""Authorization rules that can be evaluated without touching the storage layer."""


def session_is_accessible(session: dict | None, user_id: str | None) -> bool:
    """Return True when ``user_id`` may read/write the given session row.

    Rules:

    * missing or archived sessions are never accessible (callers turn this into 404);
    * sessions created while authentication was disabled have ``user_id = NULL`` and
      stay accessible to everyone (legacy single-user data);
    * otherwise the owner must match exactly.
    """
    if session is None or session.get("is_archived"):
        return False
    owner = session.get("user_id")
    if not owner:
        return True
    return owner == (user_id or None)
