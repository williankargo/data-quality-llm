"""Error envelope schema (D#10).

All 4xx/5xx responses are wrapped in this structure so the frontend
can display human-readable messages alongside technical details.
"""

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    user_message: str
    technical_detail: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
