"""Safe domain errors shared by transports and business operations."""


class DomainError(ValueError):
    def __init__(self, code, message, status=400, current_revision=None):
        super().__init__(message)
        self.code, self.status = code, status
        self.current_revision = current_revision
