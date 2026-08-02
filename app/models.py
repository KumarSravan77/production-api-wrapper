from typing import Any, Dict, List, Optional, Union

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
