from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class LLMRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LLMMessage(BaseModel):
    role: LLMRole
    content: str


class LLMTier(str, Enum):
    FAST = "fast"
    TEACHING = "teaching"
    REASONING = "reasoning"


class LLMRequest(BaseModel):
    messages: list[LLMMessage]
    tier: LLMTier | None = None
    max_tokens: int = Field(default=1024, ge=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class LLMResponse(BaseModel):
    content: str
    tier: LLMTier
    model: str
    finish_reason: Literal["stop", "length"] = "stop"
    usage_tokens: int = 0
