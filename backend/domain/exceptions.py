class PaperParseError(Exception):
    def __init__(self, message: str = "", session_id: str | None = None, document_id: str | None = None):
        self.session_id = session_id
        self.document_id = document_id
        super().__init__(message)


class EmbeddingModelUnavailableError(RuntimeError):
    pass


class SessionNotFoundError(KeyError):
    def __init__(self, message: str = "", session_id: str | None = None):
        self.session_id = session_id
        super().__init__(message)


class ActiveIndexNotReadyError(RuntimeError):
    def __init__(self, message: str = "", session_id: str | None = None):
        self.session_id = session_id
        super().__init__(message)
