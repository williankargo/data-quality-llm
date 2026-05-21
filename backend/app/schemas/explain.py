"""Schemas for multi-turn NL chat and LLM failure explanation (D#25, D#30)."""

from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str  # assistant messages store the previous tool_use JSON as a string


class ExplainResponse(BaseModel):
    explanation: str         # 1-2 sentences in plain English
    possible_causes: list[str]  # 2-4 bullet points
    suggested_action: str    # 1 sentence action recommendation
