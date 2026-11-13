"""Domain exceptions. Each carries an HTTP status and a stable machine-readable code."""

from __future__ import annotations


class StudyMateError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint


class NotFoundError(StudyMateError):
    status_code = 404
    code = "not_found"


class BadRequestError(StudyMateError):
    status_code = 400
    code = "bad_request"


class UnprocessableError(StudyMateError):
    status_code = 422
    code = "unprocessable"


class PayloadTooLargeError(StudyMateError):
    status_code = 413
    code = "payload_too_large"


class LLMUnavailableError(StudyMateError):
    """The configured model could not be reached (and no usable fallback exists)."""

    status_code = 503
    code = "llm_unavailable"


class LLMResponseError(StudyMateError):
    """The model answered, but the answer could not be used (e.g. invalid JSON)."""

    status_code = 502
    code = "llm_bad_response"
