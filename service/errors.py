"""
Unified application error definitions.
"""

from dataclasses import dataclass


@dataclass
class AppError(Exception):
    message: str
    code: str = "APP_ERROR"
    status_code: int = 400

    def to_dict(self):
        return {"error": self.code, "message": self.message}


class ValidationError(AppError):
    def __init__(self, message: str):
        super().__init__(message=message, code="VALIDATION_ERROR", status_code=400)


class NotFoundError(AppError):
    def __init__(self, message: str):
        super().__init__(message=message, code="NOT_FOUND", status_code=404)


class ConflictError(AppError):
    def __init__(self, message: str):
        super().__init__(message=message, code="CONFLICT", status_code=409)


class ExternalServiceError(AppError):
    def __init__(self, message: str):
        super().__init__(message=message, code="EXTERNAL_SERVICE_ERROR", status_code=502)
