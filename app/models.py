from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class WebhookConfig(BaseModel):
    url: HttpUrl
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: Union[str, List[Dict[str, Any]]]
    model: Optional[str] = None
    instructions: Optional[str] = None
    max_output_tokens: Optional[int] = Field(default=None, gt=0)
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    metadata: Dict[str, str] = Field(default_factory=dict)
    webhook: Optional[WebhookConfig] = None


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: Literal["developer", "system", "user", "assistant", "tool"]
    content: Any


class ChatCompletionRequest(BaseModel):
    """Validated subset of the OpenAI-compatible Chat Completions contract."""

    model_config = ConfigDict(extra="allow")
    model: Optional[str] = None
    messages: List[ChatMessage] = Field(min_length=1)
    max_tokens: Optional[int] = Field(default=None, gt=0)
    max_completion_tokens: Optional[int] = Field(default=None, gt=0)
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    stream: bool = False
    user: Optional[str] = Field(default=None, max_length=128)


class ResponsesRequest(BaseModel):
    """Validated pass-through contract for an OpenAI-compatible Responses endpoint."""

    model_config = ConfigDict(extra="allow")
    model: Optional[str] = None
    input: Union[str, List[Dict[str, Any]]]
    instructions: Optional[str] = None
    max_output_tokens: Optional[int] = Field(default=None, gt=0)
    stream: bool = False
    metadata: Dict[str, str] = Field(default_factory=dict)
