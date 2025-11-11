"""Custom exceptions for the API."""

from typing import Any, Dict, Optional


class APIException(Exception):
    """Base exception for API errors."""
    
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ImageProcessingError(APIException):
    """Raised when image processing fails."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=422, details=details)


class StorageError(APIException):
    """Raised when S3 storage operations fail."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=500, details=details)


class ValidationError(APIException):
    """Raised when request validation fails."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=400, details=details)


class NotFoundError(APIException):
    """Raised when a resource is not found."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=404, details=details)

